# modules/sheets_db.py — v2
# Adaptado a estructura DB_BET:
# Picks_Hoy, Historial, Usuarios_Premium, Usuarios_Free, Banca, Resumen_Mensual, Config

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import config
import logging

logger = logging.getLogger(__name__)

PICKS_HOY_COLS = [
    "ID", "Fecha", "Hora", "Deporte", "Partido",
    "Mercado", "Cuota_Rushbet", "Cuota_API",
    "Probabilidad_%", "EV_%", "Stake_Nivel",
    "Stake_COP", "Analisis", "Estado",
    "Resultado (W/L)", "Notificado", "Fuente",
    "Event_ID", "Outcome_ID"
]

HISTORIAL_COLS = [
    "ID", "Fecha", "Hora", "Deporte", "Partido",
    "Mercado", "Cuota_Rushbet", "Probabilidad_%",
    "EV_%", "Stake_Nivel", "Stake_COP",
    "Resultado (W/L)", "P&L_Unidades", "Analisis", "Fuente"
]

COL_RESULTADO  = PICKS_HOY_COLS.index("Resultado (W/L)") + 1   # 15
COL_NOTIFICADO = PICKS_HOY_COLS.index("Notificado") + 1        # 16
COL_ESTADO     = PICKS_HOY_COLS.index("Estado") + 1            # 14


class GoogleSheetsManager:

    def __init__(self):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            # Soporte para Render/Cloud: credenciales en variable de entorno Base64
            import os, json as _json
            _creds_b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64", "")
            if _creds_b64:
                import base64, tempfile
                _decoded   = base64.b64decode(_creds_b64).decode("utf-8")
                _info      = _json.loads(_decoded)
                self.credentials = Credentials.from_service_account_info(_info, scopes=scopes)
            else:
                # Fallback: archivo local credentials.json (desarrollo)
                self.credentials = Credentials.from_service_account_file(
                    "credentials.json", scopes=scopes
                )
            self.client = gspread.authorize(self.credentials)
            self.sheet  = self.client.open(config.GOOGLE_SHEET_NAME)
            logger.info(f"Conectado a Google Sheets: {config.GOOGLE_SHEET_NAME}")
        except Exception as e:
            print(f"ERROR de conexion a Google Sheets: {e}")
            exit()

    def _ws(self, name: str):
        return self.sheet.worksheet(name)

    def _generate_id(self, date_str: str, index: int) -> str:
        return f"{date_str.replace('-', '')}_{index:04d}"

    def _sport_label(self, sport_icon: str) -> str:
        return {
            "⚽": "Futbol Elite",
            "🌍": "Futbol Global",
            "🏀": "Baloncesto",
            "🎾": "Tenis",
            "🔗": "Parlay",
            "💎": "Banker",
            "2️⃣": "Doble Oportunidad",
            "🟨": "Tarjetas",
            "🚩": "Corners",
            "🎯": "Over/Under",
            "⏱️": "Descanso",
        }.get(sport_icon, sport_icon)

    # ─────────────────────────────────────────────
    # Suscripciones
    # ─────────────────────────────────────────────

    def check_subscription(self, telegram_id: int) -> bool:
        try:
            ws      = self._ws("Usuarios_Premium")
            records = ws.get_all_records()
            today   = datetime.now().strftime('%Y-%m-%d')
            for row in records:
                if str(row.get("Telegram_ID", "")) == str(telegram_id):
                    estado = str(row.get("Estado", "")).strip().upper()
                    vence  = str(row.get("Fecha_Vencimiento", ""))
                    if estado == "ACTIVO" and vence >= today:
                        return True
            return False
        except Exception as e:
            logger.error(f"Error check_subscription: {e}")
            return False

    def approve_payment(self, telegram_id: str, name: str, username: str,
                         monto: int = 50000, metodo: str = "Manual",
                         phone: str = "", transaction: str = ""):
        try:
            ws      = self._ws("Usuarios_Premium")
            records = ws.get_all_records()
            today   = datetime.now().strftime('%Y-%m-%d')
            vence   = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

            row_index = next(
                (i + 2 for i, r in enumerate(records)
                 if str(r.get("Telegram_ID", "")) == str(telegram_id)),
                None
            )

            if row_index:
                renovaciones = int(records[row_index - 2].get("Renovaciones", 0)) + 1
                ws.update(f"A{row_index}:L{row_index}", [[
                    str(telegram_id), name, username, phone,
                    records[row_index - 2].get("Fecha_Registro", today),
                    vence, "ACTIVO", monto, metodo, transaction, renovaciones, ""
                ]])
            else:
                ws.append_row([
                    str(telegram_id), name, username, phone,
                    today, vence, "ACTIVO", monto, metodo, transaction, 1, ""
                ])

            logger.info(f"Usuario {telegram_id} activado hasta {vence}")
            return True
        except Exception as e:
            logger.error(f"Error approve_payment: {e}")
            return False

    def get_active_users(self) -> list:
        try:
            ws      = self._ws("Usuarios_Premium")
            records = ws.get_all_records()
            today   = datetime.now().strftime('%Y-%m-%d')
            return [
                str(r["Telegram_ID"])
                for r in records
                if str(r.get("Estado", "")).strip().upper() == "ACTIVO"
                and str(r.get("Fecha_Vencimiento", "")) >= today
            ]
        except Exception as e:
            logger.error(f"Error get_active_users: {e}")
            return []

    def register_free_user(self, telegram_id: int, name: str, username: str):
        try:
            ws      = self._ws("Usuarios_Free")
            records = ws.get_all_records()
            today   = datetime.now().strftime('%Y-%m-%d')
            exists  = any(str(r.get("Telegram_ID","")) == str(telegram_id) for r in records)
            if not exists:
                ws.append_row([str(telegram_id), name, username, today, today, 0, "No", ""])
        except Exception as e:
            logger.error(f"Error register_free_user: {e}")

    # ─────────────────────────────────────────────
    # Picks del dia
    # ─────────────────────────────────────────────

    def get_existing_picks(self, target_date: str) -> set:
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            return {
                f"{r['Partido']}_{r['Mercado']}"
                for r in records
                if str(r.get("Fecha", "")) == target_date
            }
        except Exception as e:
            logger.error(f"Error get_existing_picks: {e}")
            return set()

    def get_active_picks_for_today(self, target_date: str, current_time: str) -> list:
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            return [
                r for r in records
                if str(r.get("Fecha", "")) == target_date
                and not str(r.get("Resultado (W/L)", "")).strip()
                and str(r.get("Hora", "23:59")) > current_time
            ]
        except Exception as e:
            logger.error(f"Error get_active_picks_for_today: {e}")
            return []

    def get_unsent_picks_for_today(self, target_date: str) -> list:
        """Picks de hoy que no fueron enviados a los canales aun."""
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            return [
                r for r in records
                if str(r.get("Fecha", "")) == target_date
                and str(r.get("Notificado", "")).strip().upper() != "ENVIADO"
                and not str(r.get("Resultado (W/L)", "")).strip()
            ]
        except Exception as e:
            logger.error(f"Error get_unsent_picks_for_today: {e}")
            return []

    def mark_picks_sent(self, target_date: str):
        """Marca todos los picks de hoy como enviados."""
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            for i, r in enumerate(records):
                if str(r.get("Fecha", "")) == target_date:
                    ws.update_cell(i + 2, COL_NOTIFICADO, "ENVIADO")
        except Exception as e:
            logger.error(f"Error mark_picks_sent: {e}")

    def save_daily_picks(self, picks: list, target_date: str):
        try:
            ws_hoy  = self._ws("Picks_Hoy")
            ws_hist = self._ws("Historial")
            existing = ws_hoy.get_all_records()
            next_idx = len(existing) + 1

            rows_hoy  = []
            rows_hist = []

            for i, p in enumerate(picks):
                pick_id   = self._generate_id(target_date, next_idx + i)
                sport_lbl = self._sport_label(p.get("sport", ""))
                partido   = f"{p['home']} vs {p['away']}"
                max_stake = config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT
                stake_lvl = max(1, min(10, int(round(
                    (p.get('stake_amount', 0) / max_stake) * 10
                ))))
                stake_str  = f"{stake_lvl}/10"
                cuota_rb   = p.get("odds", 0)
                cuota_api  = p.get("odds_api_value", cuota_rb)
                fuente     = p.get("source", "api")

                rows_hoy.append([
                    pick_id, target_date, p.get("time",""),
                    sport_lbl, partido, p.get("market",""),
                    cuota_rb, cuota_api,
                    f"{p.get('prob',0):.1f}%",
                    f"+{p.get('ev',0):.1f}%",
                    stake_str,
                    int(p.get("stake_amount", 0)),
                    p.get("reason",""),
                    "Pendiente", "", "No", fuente,
                    str(p.get("event_id", "")),
                    str(p.get("outcome_id", "")),
                ])

                rows_hist.append([
                    pick_id, target_date, p.get("time",""),
                    sport_lbl, partido, p.get("market",""),
                    cuota_rb,
                    f"{p.get('prob',0):.1f}%",
                    f"+{p.get('ev',0):.1f}%",
                    stake_str,
                    int(p.get("stake_amount", 0)),
                    "", "", p.get("reason",""), fuente,
                ])

            if rows_hoy:
                ws_hoy.append_rows(rows_hoy)
                ws_hist.append_rows(rows_hist)
                logger.info(f"{len(rows_hoy)} picks guardados en Picks_Hoy e Historial")

        except Exception as e:
            logger.error(f"Error save_daily_picks: {e}")

    # ─────────────────────────────────────────────
    # Resultados W/L
    # ─────────────────────────────────────────────

    def get_pending_bets(self) -> list:
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            return [
                {"index": i + 2, "data": r}
                for i, r in enumerate(records)
                if not str(r.get("Resultado (W/L)", "")).strip()
                and r.get("Partido")
            ]
        except Exception as e:
            logger.error(f"Error get_pending_bets: {e}")
            return []

    def update_bet_result(self, row_index: int, result: str):
        try:
            ws_hoy = self._ws("Picks_Hoy")
            ws_hoy.update_cell(row_index, COL_RESULTADO, result)

            row_data = ws_hoy.row_values(row_index)
            pick_id  = row_data[0] if row_data else None

            if pick_id:
                ws_hist   = self._ws("Historial")
                hist_recs = ws_hist.get_all_records()
                for i, r in enumerate(hist_recs):
                    if str(r.get("ID", "")) == str(pick_id):
                        hist_row = i + 2
                        ws_hist.update_cell(hist_row, 12, result)
                        try:
                            cuota = float(str(r.get("Cuota_Rushbet", 0)).replace(",", "."))
                            stake = int(str(r.get("Stake_Nivel", "1/10")).split("/")[0])
                            pnl   = round((cuota - 1) * stake, 2) if result == "W" else -stake
                            ws_hist.update_cell(hist_row, 13, pnl)
                        except Exception:
                            pass
                        break

        except Exception as e:
            logger.error(f"Error update_bet_result fila {row_index}: {e}")

    def get_unnotified_results(self) -> list:
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            pending = []
            for i, r in enumerate(records):
                res        = str(r.get("Resultado (W/L)", "")).strip().upper()
                notificado = str(r.get("Notificado", "")).strip().upper()
                if res in ["W", "L"] and notificado not in ["SI", "SÍ", "ENVIADO"]:
                    pending.append({
                        "index":    i + 2,
                        "partido":  r.get("Partido", ""),
                        "mercado":  r.get("Mercado", ""),
                        "cuota":    r.get("Cuota_Rushbet", ""),
                        "ev":       r.get("EV_%", ""),
                        "resultado": res,
                    })
            return pending
        except Exception as e:
            logger.error(f"Error get_unnotified_results: {e}")
            return []

    def mark_result_notified(self, row_index: int, result: str):
        try:
            ws = self._ws("Picks_Hoy")
            ws.update_cell(row_index, COL_NOTIFICADO, "Si")
            ws.update_cell(row_index, COL_ESTADO, f"{result} - Notificado")
        except Exception as e:
            logger.error(f"Error mark_result_notified: {e}")

    # ─────────────────────────────────────────────
    # Reportes
    # ─────────────────────────────────────────────

    def get_daily_results(self, target_date: str) -> list:
        try:
            ws      = self._ws("Picks_Hoy")
            records = ws.get_all_records()
            return [r for r in records if str(r.get("Fecha", "")) == target_date]
        except Exception as e:
            logger.error(f"Error get_daily_results: {e}")
            return []

    def get_monthly_results(self, year_month: str) -> list:
        try:
            ws      = self._ws("Historial")
            records = ws.get_all_records()
            return [r for r in records if str(r.get("Fecha", "")).startswith(year_month)]
        except Exception as e:
            logger.error(f"Error get_monthly_results: {e}")
            return []

    def save_daily_bankroll(self, date_str: str, inicio: float, fin: float,
                             wins: int, losses: int, voids: int,
                             profit_units: float, notas: str = ""):
        try:
            ws         = self._ws("Banca")
            ganancia   = fin - inicio
            ganancia_p = round((ganancia / inicio) * 100, 2) if inicio else 0
            total      = wins + losses + voids
            win_rate   = round((wins / total) * 100, 1) if total else 0
            ws.append_row([
                date_str, inicio, fin, ganancia, ganancia_p,
                total, wins, losses, voids,
                win_rate, profit_units, notas
            ])
        except Exception as e:
            logger.error(f"Error save_daily_bankroll: {e}")

    def save_monthly_summary(self, month_str: str, wins: int, losses: int,
                              voids: int, profit_units: float,
                              bankroll_inicio: float, bankroll_fin: float,
                              suscriptores: int = 0, ingresos: int = 0):
        try:
            ws    = self._ws("Resumen_Mensual")
            total = wins + losses + voids
            wr    = round((wins / total) * 100, 1) if total else 0
            roi   = round((profit_units / total) * 100, 1) if total else 0
            ws.append_row([
                month_str, total, wins, losses, voids,
                wr, profit_units, roi,
                bankroll_inicio, bankroll_fin,
                suscriptores, ingresos, ""
            ])
        except Exception as e:
            logger.error(f"Error save_monthly_summary: {e}")

    def clear_picks_hoy(self):
        try:
            ws = self._ws("Picks_Hoy")
            ws.clear()
            ws.append_row(PICKS_HOY_COLS)
            logger.info("Picks_Hoy limpiada.")
        except Exception as e:
            logger.error(f"Error clear_picks_hoy: {e}")


sheets_db = GoogleSheetsManager()