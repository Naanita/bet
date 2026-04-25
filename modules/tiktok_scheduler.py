# modules/tiktok_scheduler.py — v1
# Orquestador de publicación automática en TikTok
#
# Horarios (hora Colombia / COT):
#   08:00  → pick_reveal  (picks del día)
#   22:00  → result_reveal (resultados liquidados)
#   22:30  → daily_recap   (resumen estadístico)
#
# Llama desde main.py:
#   scheduler.run_morning_picks(date_str)
#   scheduler.run_evening_results(date_str)
#   scheduler.run_daily_recap(date_str)

import os
import sqlite3
import logging
from datetime import datetime, date

import pytz

logger = logging.getLogger(__name__)

BOGOTA_TZ = pytz.timezone("America/Bogota")

# Límite de videos TikTok por franja (evitar spam)
MAX_PICKS_PER_SLOT   = 3
MAX_RESULTS_PER_SLOT = 3


class TikTokScheduler:
    """
    Genera y publica videos TikTok automáticamente a partir de los picks
    guardados en Google Sheets y los resultados del sistema de tracking.
    """

    def __init__(self, dry_run: bool = False):
        from modules.tiktok_video    import TikTokVideoGenerator
        from modules.tiktok_uploader import TikTokUploader

        self.gen     = TikTokVideoGenerator(dry_run=dry_run)
        self.up      = TikTokUploader(dry_run=dry_run)
        self.dry_run = dry_run

        # DB SQLite existente
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base, "data", "quant_history.db")
        self._init_table()

    # ── Setup ─────────────────────────────────────────────────────────

    def _init_table(self):
        """Crea la tabla tiktok_posts si no existe."""
        try:
            con = sqlite3.connect(self.db_path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS tiktok_posts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    posted_at    TEXT,
                    video_type   TEXT,
                    reference_id TEXT,
                    video_path   TEXT,
                    publish_id   TEXT,
                    status       TEXT,
                    caption      TEXT
                )
            """)
            con.commit()
            con.close()
        except Exception as e:
            logger.error(f"[TIKTOK_SCH] Error init_table: {e}")

    def _already_posted(self, video_type: str, reference_id: str) -> bool:
        """Devuelve True si ya se publicó este video hoy."""
        try:
            today = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")
            con = sqlite3.connect(self.db_path)
            row = con.execute(
                "SELECT id FROM tiktok_posts "
                "WHERE video_type=? AND reference_id=? AND posted_at LIKE ? AND status!='failed'",
                (video_type, reference_id, f"{today}%"),
            ).fetchone()
            con.close()
            return row is not None
        except Exception:
            return False

    def _log_post(self, video_type, reference_id, video_path, publish_id, status, caption):
        try:
            posted_at = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO tiktok_posts (posted_at,video_type,reference_id,video_path,publish_id,status,caption) "
                "VALUES (?,?,?,?,?,?,?)",
                (posted_at, video_type, reference_id, video_path or "", publish_id or "", status, caption[:500]),
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.error(f"[TIKTOK_SCH] Error _log_post: {e}")

    # ── Helpers de datos ──────────────────────────────────────────────

    def _get_sheets_picks(self, date_str: str) -> list[dict]:
        """Obtiene picks del día desde Google Sheets."""
        try:
            from modules.sheets_db import sheets_db
            return sheets_db.get_active_picks_for_today(date_str, "00:00")
        except Exception as e:
            logger.error(f"[TIKTOK_SCH] Error get_sheets_picks: {e}")
            return []

    def _get_settled_picks(self, date_str: str) -> list[dict]:
        """Obtiene picks liquidados (con W/L) del día."""
        try:
            from modules.sheets_db import sheets_db
            all_picks = sheets_db.get_active_picks_for_today(date_str, "00:00")
            # También los que ya tienen resultado
            ws = sheets_db._ws("Picks_Hoy")
            records = ws.get_all_records()
            return [
                r for r in records
                if str(r.get("Fecha", "")) == date_str
                and str(r.get("Resultado (W/L)", "")).strip().upper() in ("W", "L")
            ]
        except Exception as e:
            logger.error(f"[TIKTOK_SCH] Error get_settled_picks: {e}")
            return []

    def _parse_pick_row(self, row: dict) -> dict:
        """Normaliza una fila de Google Sheets a dict para TikTokVideoGenerator."""
        partido = str(row.get("Partido", ""))
        home, away = "", ""
        if " vs " in partido:
            home, away = partido.split(" vs ", 1)
        elif " VS " in partido:
            home, away = partido.split(" VS ", 1)

        mercado = str(row.get("Mercado", ""))
        # Detectar sport_icon por mercado
        m_low = mercado.lower()
        if "banker" in m_low:
            sport_icon = "💎"
        elif "mas de" in m_low or "menos de" in m_low:
            sport_icon = "🎯"
        elif "corner" in m_low:
            sport_icon = "🚩"
        elif "tarjeta" in m_low:
            sport_icon = "🟨"
        else:
            sport_icon = "⚽"

        # Parsear odds y prob (pueden venir como "1.75" o float)
        try:
            odds = float(str(row.get("Cuota_Rushbet", "1.5")).replace(",", "."))
        except Exception:
            odds = 1.50
        try:
            prob_str = str(row.get("Probabilidad_%", "72")).replace("%", "").strip()
            prob = float(prob_str)
        except Exception:
            prob = 72.0
        try:
            ev_str = str(row.get("EV_%", "10")).replace("%", "").replace("+", "").strip()
            ev = float(ev_str)
        except Exception:
            ev = 10.0

        stake_level = str(row.get("Stake_Nivel", "5/10"))
        match_time  = str(row.get("Hora", ""))
        deporte     = str(row.get("Deporte", ""))

        return {
            "home":        home.strip(),
            "away":        away.strip(),
            "market":      mercado,
            "odds":        odds,
            "prob":        prob,
            "ev":          ev,
            "stake_level": stake_level,
            "match_time":  match_time,
            "sport_icon":  sport_icon,
            "confidence":  "ALTA",
            "pick_id":     str(row.get("ID", "")),
        }

    # ── Slots públicos ────────────────────────────────────────────────

    def run_morning_picks(self, date_str: str = None):
        """
        08:00 COT — Publica un video pick_reveal por cada pick del día
        (máx MAX_PICKS_PER_SLOT).
        """
        if date_str is None:
            date_str = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")

        import config
        if not getattr(config, "TIKTOK_ENABLED", False):
            logger.info("[TIKTOK_SCH] TikTok deshabilitado (TIKTOK_ENABLED=false)")
            return

        picks = self._get_sheets_picks(date_str)
        if not picks:
            logger.info(f"[TIKTOK_SCH] Sin picks para {date_str}")
            return

        posted = 0
        for row in picks[:MAX_PICKS_PER_SLOT]:
            p = self._parse_pick_row(row)
            if not p["home"] or not p["away"]:
                continue

            ref_id = p["pick_id"] or f"{p['home']}_{p['market']}"
            if self._already_posted("pick_reveal", ref_id):
                logger.info(f"[TIKTOK_SCH] pick_reveal ya publicado: {ref_id}")
                continue

            # Generar video
            video_path = self.gen.generate_pick_reveal(
                home=p["home"], away=p["away"], market=p["market"],
                odds=p["odds"], prob=p["prob"], ev=p["ev"],
                stake_level=p["stake_level"], match_time=p["match_time"],
                sport_icon=p["sport_icon"], confidence=p["confidence"],
            )
            if not video_path:
                logger.error(f"[TIKTOK_SCH] No se pudo generar video para: {ref_id}")
                self._log_post("pick_reveal", ref_id, None, None, "failed", "")
                continue

            # Caption + hashtags
            caption, hashtags = self.up.generate_caption("pick_reveal", p)

            # Publicar
            result = self.up.post_video(video_path, caption, hashtags)
            status = "published" if result["success"] else "failed"
            self._log_post("pick_reveal", ref_id, video_path,
                           result.get("publish_id"), status, caption)

            if result["success"]:
                posted += 1
                logger.info(f"[TIKTOK_SCH] pick_reveal publicado: {ref_id} → {result['publish_id']}")
            else:
                logger.error(f"[TIKTOK_SCH] Error publicando pick_reveal {ref_id}: {result.get('error')}")

        logger.info(f"[TIKTOK_SCH] run_morning_picks: {posted} videos publicados")

    def run_evening_results(self, date_str: str = None):
        """
        22:00 COT — Publica result_reveal para picks liquidados del día
        (máx MAX_RESULTS_PER_SLOT).
        """
        if date_str is None:
            date_str = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")

        import config
        if not getattr(config, "TIKTOK_ENABLED", False):
            return

        settled = self._get_settled_picks(date_str)
        if not settled:
            logger.info(f"[TIKTOK_SCH] Sin resultados liquidados para {date_str}")
            return

        posted = 0
        for row in settled[:MAX_RESULTS_PER_SLOT]:
            p = self._parse_pick_row(row)
            result = str(row.get("Resultado (W/L)", "")).strip().upper()
            if result not in ("W", "L"):
                continue

            ref_id = f"result_{p['pick_id'] or p['home']}_{p['market']}"
            if self._already_posted("result_reveal", ref_id):
                continue

            video_path = self.gen.generate_result_reveal(
                home=p["home"], away=p["away"], market=p["market"],
                odds=p["odds"], result=result, ev=p["ev"],
            )
            if not video_path:
                self._log_post("result_reveal", ref_id, None, None, "failed", "")
                continue

            caption, hashtags = self.up.generate_caption("result_reveal", {**p, "result": result})
            result_api = self.up.post_video(video_path, caption, hashtags)
            status = "published" if result_api["success"] else "failed"
            self._log_post("result_reveal", ref_id, video_path,
                           result_api.get("publish_id"), status, caption)

            if result_api["success"]:
                posted += 1

        logger.info(f"[TIKTOK_SCH] run_evening_results: {posted} videos publicados")

    def run_daily_recap(self, date_str: str = None):
        """
        22:30 COT — Publica un daily_recap con las estadísticas del día.
        Solo corre si hay al menos 2 resultados (W+L).
        """
        if date_str is None:
            date_str = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")

        import config
        if not getattr(config, "TIKTOK_ENABLED", False):
            return

        if self._already_posted("daily_recap", date_str):
            logger.info(f"[TIKTOK_SCH] daily_recap ya publicado para {date_str}")
            return

        settled = self._get_settled_picks(date_str)
        wins   = sum(1 for r in settled if str(r.get("Resultado (W/L)", "")).upper() == "W")
        losses = sum(1 for r in settled if str(r.get("Resultado (W/L)", "")).upper() == "L")

        if (wins + losses) < 2:
            logger.info(f"[TIKTOK_SCH] daily_recap: solo {wins+losses} resultados, mínimo 2 requeridos")
            return

        # Calcular P&L en unidades
        profit = 0.0
        for row in settled:
            result = str(row.get("Resultado (W/L)", "")).upper()
            try:
                odds = float(str(row.get("Cuota_Rushbet", "1.5")).replace(",", "."))
            except Exception:
                odds = 1.50
            try:
                stake_str = str(row.get("Stake_Nivel", "5/10"))
                stake_unit = float(stake_str.split("/")[0]) / 10
            except Exception:
                stake_unit = 0.5

            if result == "W":
                profit += stake_unit * (odds - 1)
            elif result == "L":
                profit -= stake_unit

        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        video_path = self.gen.generate_daily_recap(
            date_str=date_display,
            wins=wins,
            losses=losses,
            voids=0,
            profit_units=round(profit, 2),
        )
        if not video_path:
            self._log_post("daily_recap", date_str, None, None, "failed", "")
            return

        data = {"wins": wins, "losses": losses, "date_str": date_display}
        caption, hashtags = self.up.generate_caption("daily_recap", data)
        result_api = self.up.post_video(video_path, caption, hashtags)
        status = "published" if result_api["success"] else "failed"
        self._log_post("daily_recap", date_str, video_path,
                       result_api.get("publish_id"), status, caption)

        if result_api["success"]:
            logger.info(f"[TIKTOK_SCH] daily_recap publicado para {date_str}")
        else:
            logger.error(f"[TIKTOK_SCH] daily_recap falló: {result_api.get('error')}")

    # ── Stats para admin ──────────────────────────────────────────────

    def get_today_stats(self) -> dict:
        """Estadísticas del día para el comando /tiktok_stats."""
        today = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")
        try:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT status FROM tiktok_posts WHERE posted_at LIKE ?",
                (f"{today}%",),
            ).fetchall()
            con.close()
            statuses = [r[0] for r in rows]
            return {
                "posted":  statuses.count("published"),
                "failed":  statuses.count("failed"),
                "dry_run": statuses.count("DRY_RUN"),
                "total":   len(statuses),
            }
        except Exception:
            return {"posted": 0, "failed": 0, "total": 0}

    def get_recent_posts(self, limit: int = 10) -> list[dict]:
        """Últimos N posts para diagnóstico."""
        try:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT posted_at, video_type, reference_id, status FROM tiktok_posts "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            con.close()
            return [
                {"posted_at": r[0], "video_type": r[1], "reference_id": r[2], "status": r[3]}
                for r in rows
            ]
        except Exception:
            return []
