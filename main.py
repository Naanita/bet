# main.py — v4.2
import config
import pandas as pd

from modules.sheets_db import sheets_db
from modules.risk import RiskEngine
from modules.odds_api import OddsAPI
from modules.pipeline_v5 import run_pipeline_v5 as run_quant_pipeline
from modules.free_channel import (
    send_free_picks, send_result_to_free_channel,
    send_daily_recap_to_free_channel, send_monthly_recap,
    build_conversion_nudge, build_free_pick_keyboard,
    build_weekly_promo_message, build_premium_pick_keyboard,
    build_pick_keyboard, _market_explanation,
)
from modules.image_generator import (
    generate_pick_image, generate_result_image, generate_daily_recap_image
)

from datetime import datetime, timedelta, time
import pytz
import re
import logging
import concurrent.futures

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

ASK_NAME, ASK_PHONE, ASK_PLATFORM, ASK_TRANSACTION, ASK_RECEIPT = range(5)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def determine_winner(market: str, home_score: int, away_score: int):
    market      = market.lower()
    total_goals = home_score + away_score
    if "gana local"  in market: return "W" if home_score > away_score else "L"
    if "gana visita" in market: return "W" if away_score > home_score else "L"
    if "empate"      in market: return "W" if home_score == away_score else "L"
    if "mas de" in market and "goles" in market:
        try: line = float(re.findall(r"mas de (\d+\.?\d*)", market)[0])
        except: return None
        return "W" if total_goals > line else "L"
    if "menos de" in market and "goles" in market:
        try: line = float(re.findall(r"menos de (\d+\.?\d*)", market)[0])
        except: return None
        return "W" if total_goals < line else "L"
    if "ambos anotan" in market and "si" in market:
        return "W" if home_score > 0 and away_score > 0 else "L"
    if "ambos anotan" in market and "no" in market:
        return "W" if home_score == 0 or away_score == 0 else "L"
    return None


def _build_pick_message(p: dict) -> str:
    max_stake = config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT
    stake_lvl = max(1, min(10, int(round((p.get('stake_amount', 0) / max_stake) * 10))))
    stake_str = f"{stake_lvl}/10"
    confidence = p.get("confidence", "")
    source_tag = "Rushbet" if p.get("source") == "rushbet" else "Mercado"
    return (
        f"{p.get('sport','⚽')} <b>NUEVA OPORTUNIDAD</b> {confidence}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>{p['home']}  vs  {p['away']}</b>\n"
        f"⏱️ <b>Hora:</b> {p.get('time','')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Mercado:</b> {p['market']}\n"
        f"💵 <b>Cuota:</b> <code>{p['odds']}</code> ({source_tag})\n"
        f"✅ <b>Probabilidad:</b> {p['prob']:.1f}%\n"
        f"📈 <b>EV:</b> +{p['ev']:.1f}%\n"
        f"📊 <b>Stake:</b> {stake_str}\n"
        f"🧠 <i>{str(p.get('reason',''))[:100]}</i>"
    )


def _generate_pick_img(pick: dict) -> bytes | None:
    def _gen():
        try:
            max_stake = config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT
            stake_lvl = max(1, min(10, int(round((pick.get('stake_amount', 0) / max_stake) * 10))))
            return generate_pick_image(
                home=pick.get("home", ""),
                away=pick.get("away", ""),
                market=pick.get("market", ""),
                odds=pick.get("odds", 0),
                prob=pick.get("prob", 0),
                ev=pick.get("ev", 0),
                stake_level=f"{stake_lvl}/10",
                stake_cop=0,
                confidence=pick.get("confidence", "MEDIA"),
                sport_icon=pick.get("sport", "⚽"),
                match_time=pick.get("time", ""),
                channel_name=f"⚡ {config.BOT_NAME}",
            )
        except Exception as e:
            logger.debug(f"Error generando imagen: {e}")
            return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_gen).result(timeout=8)
    except Exception:
        return None


# ─────────────────────────────────────────────
# Distribucion de picks
# ─────────────────────────────────────────────

async def _distribute_picks(context, picks: list):
    """Envia picks al canal premium y gratuito."""

    # ── Canal Premium — todos los picks ──
    if config.CHANNEL_ID_BANKERS:
        for p in picks:
            msg      = _build_pick_message(p)
            keyboard = build_premium_pick_keyboard(p)
            img      = _generate_pick_img(p)
            try:
                if img:
                    await context.bot.send_photo(
                        chat_id=config.CHANNEL_ID_BANKERS, photo=img,
                        caption=msg, parse_mode='HTML', reply_markup=keyboard)
                else:
                    await context.bot.send_message(
                        chat_id=config.CHANNEL_ID_BANKERS,
                        text=msg, parse_mode='HTML', reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error canal premium: {e}")

    # ── Usuarios premium individuales ──
    active_users = sheets_db.get_active_users()
    if active_users:
        for p in picks:
            msg      = _build_pick_message(p)
            keyboard = build_premium_pick_keyboard(p)
            img      = _generate_pick_img(p)
            for uid in active_users:
                try:
                    if img:
                        await context.bot.send_photo(
                            chat_id=uid, photo=img,
                            caption=msg, parse_mode='HTML', reply_markup=keyboard)
                    else:
                        await context.bot.send_message(
                            chat_id=uid, text=msg,
                            parse_mode='HTML', reply_markup=keyboard)
                except Exception as e:
                    logger.warning(f"Error usuario {uid}: {e}")

    # ── Canal gratuito ──
    await send_free_picks(context, picks)


# ─────────────────────────────────────────────
# CRONJOBS
# ─────────────────────────────────────────────

async def cron_market_scanner(context: ContextTypes.DEFAULT_TYPE):
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str = now_local.strftime('%Y-%m-%d')
    logger.info(f"[CRON] Escaner ({now_local.strftime('%H:%M')})...")

    live_picks     = await run_quant_pipeline(today_str, config.BANKROLL_INICIAL)
    existing_picks = sheets_db.get_existing_picks(today_str)
    new_picks      = [
        p for p in live_picks
        if f"{p['home']} vs {p['away']}_{p['market']}" not in existing_picks
    ]

    if not new_picks:
        logger.info("[CRON] Sin nuevas apuestas.")
        # Notificar solo en el escaneo de las 08:00
        if now_local.hour == 8:
            msg_no_picks = (
                f"📡 <b>Escaneo completado — {today_str}</b>\n\n"
                f"🔍 No se encontraron apuestas con valor esperado positivo hoy.\n\n"
                f"<i>El sistema seguirá monitoreando durante el día.</i>"
            )
            for ch_id in [config.CHANNEL_ID_BANKERS, config.CHANNEL_ID_FREE]:
                if ch_id:
                    try:
                        await context.bot.send_message(
                            chat_id=ch_id, text=msg_no_picks, parse_mode='HTML')
                    except Exception as e:
                        logger.error(f"Error no-picks: {e}")
        return

    sheets_db.save_daily_picks(new_picks, today_str)
    await _distribute_picks(context, new_picks)


async def cron_auto_settle(context: ContextTypes.DEFAULT_TYPE):
    logger.info("[CRON] Auto-settle...")
    pending = sheets_db.get_pending_bets()
    if not pending:
        return

    api        = OddsAPI()
    scores_map = api.get_scores(days_from=3)
    updates    = 0

    for bet in pending:
        match_name = bet['data'].get('Partido')
        market     = bet['data'].get('Mercado')
        if match_name in scores_map:
            score  = scores_map[match_name]
            result = determine_winner(market, score['home'], score['away'])
            if result:
                sheets_db.update_bet_result(bet['index'], result)
                updates += 1

    if updates > 0:
        logger.info(f"[CRON] {updates} apuestas liquidadas.")
        await _notify_results(context)


async def _notify_results(context):
    pendientes   = sheets_db.get_unnotified_results()
    if not pendientes:
        return
    active_users = sheets_db.get_active_users()

    for pick in pendientes:
        is_win  = pick['resultado'] == "W"
        icono   = "GANADA ✅" if is_win else "PERDIDA ❌"
        partido = pick.get('partido', '')
        partes  = partido.split(' vs ') if ' vs ' in partido else [partido, '']

        img_bytes = generate_result_image(
            home=partes[0], away=partes[1],
            market=pick.get('mercado', ''),
            odds=float(str(pick.get('cuota', 0)).replace(',', '.')),
            result=pick['resultado'],
            channel_name=f"⚡ {config.BOT_NAME}",
        )
        caption = (
            f"🔔 <b>RESULTADO FINAL</b>\n\n"
            f"🏆 <b>{partido}</b>\n"
            f"📌 {pick['mercado']}\n\n"
            f"Resultado: <b>{icono}</b>"
        )

        for ch_id in [config.CHANNEL_ID_BANKERS]:
            if ch_id:
                try:
                    if img_bytes:
                        await context.bot.send_photo(chat_id=ch_id, photo=img_bytes,
                                                      caption=caption, parse_mode='HTML')
                    else:
                        await context.bot.send_message(chat_id=ch_id, text=caption, parse_mode='HTML')
                except Exception: pass

        for u in active_users:
            try:
                if img_bytes:
                    await context.bot.send_photo(chat_id=u, photo=img_bytes,
                                                  caption=caption, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id=u, text=caption, parse_mode='HTML')
            except Exception: pass

        pick_data = {
            "home":   partes[0], "away": partes[1],
            "market": pick.get('mercado', ''),
            "odds":   float(str(pick.get('cuota', 0)).replace(',', '.')),
        }
        await send_result_to_free_channel(context, pick_data, pick['resultado'])
        sheets_db.mark_result_notified(pick['index'], pick['resultado'])

    # Si no quedan pendientes enviar recap del dia
    if not sheets_db.get_pending_bets():
        await _check_send_daily_recap(context)


async def _check_send_daily_recap(context):
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str = now_local.strftime('%Y-%m-%d')
    results   = sheets_db.get_daily_results(today_str)
    if not results: return

    wins, losses, voids, pending = 0, 0, 0, 0
    profit_units = 0.0
    for r in results:
        res = str(r.get("Resultado (W/L)", "")).strip().upper()
        if not res: pending += 1; continue
        try:    odds  = float(str(r.get("Cuota_Rushbet", 0)).replace(',', '.'))
        except: odds  = 0.0
        try:    stake = int(str(r.get("Stake_Nivel", "1/10")).split('/')[0])
        except: stake = 1
        if res == "W":             wins   += 1; profit_units += (odds - 1) * stake
        elif res == "L":           losses += 1; profit_units -= stake
        elif res in ["V","VOID"]:  voids  += 1

    if pending > 0 or wins + losses + voids == 0: return
    await _send_daily_recap(context, today_str, wins, losses, voids, profit_units)


async def daily_recap(context: ContextTypes.DEFAULT_TYPE):
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str = now_local.strftime('%Y-%m-%d')
    results   = sheets_db.get_daily_results(today_str)
    if not results: return

    wins, losses, voids = 0, 0, 0
    profit_units = 0.0
    for r in results:
        res = str(r.get("Resultado (W/L)", "")).strip().upper()
        try:    odds  = float(str(r.get("Cuota_Rushbet", 0)).replace(',', '.'))
        except: odds  = 0.0
        try:    stake = int(str(r.get("Stake_Nivel", "1/10")).split('/')[0])
        except: stake = 1
        if res == "W":            wins   += 1; profit_units += (odds - 1) * stake
        elif res == "L":          losses += 1; profit_units -= stake
        elif res in ["V","VOID"]: voids  += 1

    await _send_daily_recap(context, today_str, wins, losses, voids, profit_units)

    tomorrow = now_local + pd.Timedelta(days=1)
    if tomorrow.month != now_local.month:
        await _send_monthly_recap(context, now_local)


async def _send_daily_recap(context, today_str, wins, losses, voids, profit_units):
    total    = wins + losses + voids
    win_rate = round((wins / total * 100), 1) if total > 0 else 0
    img_bytes = generate_daily_recap_image(
        date_str=today_str, wins=wins, losses=losses,
        voids=voids, profit_units=profit_units,
        channel_name=f"⚡ {config.BOT_NAME}",
    )
    msg = (
        f"🌙 <b>CIERRE DE MERCADO: {today_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Ganadas: {wins}  |  ❌ Perdidas: {losses}  |  🔄 Nulas: {voids}\n"
        f"🎯 <b>Win Rate:</b> {win_rate:.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{config.BOT_NAME}</i>"
    )
    for ch_id in [config.CHANNEL_ID_BANKERS, config.CHANNEL_ID_FREE]:
        if ch_id:
            try:
                if img_bytes:
                    await context.bot.send_photo(chat_id=ch_id, photo=img_bytes,
                                                  caption=msg, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id=ch_id, text=msg, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error recap {ch_id}: {e}")
    sheets_db.save_daily_bankroll(today_str, config.BANKROLL_INICIAL, config.BANKROLL_INICIAL,
                                   wins, losses, voids, profit_units)


async def _send_monthly_recap(context, now_local):
    month_str       = now_local.strftime("%B %Y")
    monthly_results = sheets_db.get_monthly_results(now_local.strftime('%Y-%m'))
    mw = sum(1 for r in monthly_results if str(r.get("Resultado (W/L)","")).strip().upper()=="W")
    ml = sum(1 for r in monthly_results if str(r.get("Resultado (W/L)","")).strip().upper()=="L")
    mv = sum(1 for r in monthly_results if str(r.get("Resultado (W/L)","")).strip().upper() in ["V","VOID"])
    mp = 0.0
    for r in monthly_results:
        res = str(r.get("Resultado (W/L)","")).strip().upper()
        try: o = float(str(r.get("Cuota_Rushbet",0)).replace(',','.')); s = int(str(r.get("Stake_Nivel","1/10")).split('/')[0])
        except: o,s = 0.0,1
        if res=="W": mp+=(o-1)*s
        elif res=="L": mp-=s
    await send_monthly_recap(context, month_str, mw, ml, mv, mp)


async def cron_free_channel_nudge(context: ContextTypes.DEFAULT_TYPE):
    if not config.CHANNEL_ID_FREE: return
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    results   = sheets_db.get_daily_results(now_local.strftime('%Y-%m-%d'))
    wins   = sum(1 for r in results if str(r.get("Resultado (W/L)","")).strip().upper()=="W")
    losses = sum(1 for r in results if str(r.get("Resultado (W/L)","")).strip().upper()=="L")
    msg    = build_weekly_promo_message() if now_local.weekday()==0 else build_conversion_nudge(wins, losses)
    try:
        await context.bot.send_message(chat_id=config.CHANNEL_ID_FREE, text=msg,
                                        parse_mode='HTML', reply_markup=build_free_pick_keyboard())
    except Exception as e:
        logger.error(f"Error nudge: {e}")


# ─────────────────────────────────────────────
# COMANDOS
# ─────────────────────────────────────────────

async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if str(user_id) == config.ADMIN_CHAT_ID: return True
    if sheets_db.check_subscription(user_id): return True
    keyboard = [
        [InlineKeyboardButton("💳 Adquirir Licencia Premium", callback_data="buy_vip")],
        [InlineKeyboardButton("🎧 Soporte", url=f"https://t.me/{config.SUPPORT_USERNAME.replace('@','')}")]
    ]
    await update.message.reply_text("🔒 <b>TERMINAL BLOQUEADA</b>\nNo tienes una licencia activa.",
                                     reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return False


async def show_today_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = update.callback_query is not None
    user_id     = update.effective_user.id
    if str(user_id) != config.ADMIN_CHAT_ID and not sheets_db.check_subscription(user_id):
        if is_callback: await update.callback_query.answer("Acceso Denegado.", show_alert=True)
        return
    if is_callback: await update.callback_query.answer()

    now_local        = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str        = now_local.strftime('%Y-%m-%d')
    current_time_str = now_local.strftime('%H:%M')

    db_picks = sheets_db.get_active_picks_for_today(today_str, current_time_str)
    if not db_picks:
        msg = f"📡 No hay posiciones activas para hoy ({today_str})."
        if is_callback: await context.bot.send_message(chat_id=user_id, text=msg)
        else: await update.message.reply_text(msg)
        return

    response  = f"📡 <b>PICKS DE HOY ({current_time_str})</b>\n"
    response += f"Total: <b>{len(db_picks)}</b>\n"
    response += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for p in db_picks:
        response += (
            f"⚽ <b>{p.get('Partido','')}</b> ({p.get('Hora','')})\n"
            f"📌 {p.get('Mercado','')} @ {p.get('Cuota_Rushbet','')}\n"
            f"✅ {p.get('Probabilidad_%','')} | EV: {p.get('EV_%','')} | Stake: {p.get('Stake_Nivel','')}\n\n"
        )
    if is_callback: await context.bot.send_message(chat_id=user_id, text=response, parse_mode='HTML')
    else: await update.message.reply_text(response, parse_mode='HTML')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if sheets_db.check_subscription(user.id) or str(user.id) == config.ADMIN_CHAT_ID:
        await update.message.reply_text(
            f"⚡️ <b>{config.BOT_NAME} EN LINEA</b>\n\n"
            f"📡 /today — Picks activos de hoy\n"
            f"⚙️ /configbudget [monto] — Ajustar banca", parse_mode='HTML')
    else:
        # Obtener win rate para mostrar en bienvenida
        try:
            results  = sheets_db.get_monthly_results(
                pd.Timestamp.now(tz=config.TIMEZONE).strftime('%Y-%m'))
            wins     = sum(1 for r in results if str(r.get("Resultado (W/L)","")).strip().upper()=="W")
            losses   = sum(1 for r in results if str(r.get("Resultado (W/L)","")).strip().upper()=="L")
            total    = wins + losses
            win_rate = round((wins / total * 100), 1) if total > 0 else 0
            wr_line  = f"\n📊 Win Rate este mes: <b>{win_rate:.1f}%</b> ({wins}W/{losses}L)\n"
        except Exception:
            wr_line = "\n"

        keyboard = [
            [InlineKeyboardButton("💎 Ver planes y suscribirse", callback_data="buy_vip")],
            [InlineKeyboardButton("🎧 Soporte", url=f"https://t.me/{config.SUPPORT_USERNAME.replace('@','')}")]
        ]
        await update.message.reply_text(
            f"📈 <b>BIENVENIDO A {config.BOT_NAME.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
            f"{wr_line}"
            f"Sistema de análisis cuantitativo de apuestas deportivas.\n\n"
            f"Accede al canal premium para recibir señales con EV positivo diariamente.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML')


async def handle_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 <b>REGISTRO DE SUSCRIPCION</b>\n\n"
        "Paso 1/4 — Escribe tu <b>nombre completo</b> (como aparece en tu documento de identidad):",
        parse_mode='HTML')
    return ASK_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_name'] = update.message.text.strip()
    await update.message.reply_text(
        "📱 <b>Paso 2/4</b> — Escribe tu <b>numero de celular / WhatsApp</b>:\n\n"
        "<i>Ejemplo: 3001234567</i>",
        parse_mode='HTML')
    return ASK_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_phone'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("🟡 Nequi",       callback_data="platform_Nequi")],
        [InlineKeyboardButton("🏦 Bancolombia",  callback_data="platform_Bancolombia")],
        [InlineKeyboardButton("💜 Daviplata",    callback_data="platform_Daviplata")],
    ]
    await update.message.reply_text(
        f"💳 <b>Paso 3/4</b> — Selecciona el <b>metodo de pago</b>:\n\n"
        f"💵 Valor: <b>{config.PRECIO_SUSCRIPCION}</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_PLATFORM


_PAYMENT_INFO = {
    "Nequi": (
        "🟡 <b>NEQUI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📲 Numero: <code>{'{NEQUI}'}</code>\n\n"
        "1. Abre Nequi\n"
        "2. Toca <b>Enviar dinero</b>\n"
        "3. Ingresa el numero y el valor\n"
        "4. Guarda el <b>numero de referencia</b> del comprobante"
    ),
    "Bancolombia": (
        "🏦 <b>BANCOLOMBIA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 Cuenta de ahorros: <code>{'{BANCOLOMBIA}'}</code>\n\n"
        "1. Abre tu app Bancolombia\n"
        "2. Ve a <b>Transferencias</b>\n"
        "3. Ingresa el numero de cuenta y el valor\n"
        "4. Guarda el <b>numero de referencia</b> del comprobante"
    ),
    "Daviplata": (
        "💜 <b>DAVIPLATA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📲 Numero: <code>{'{DAVIPLATA}'}</code>\n\n"
        "1. Abre Daviplata\n"
        "2. Toca <b>Enviar</b>\n"
        "3. Ingresa el numero y el valor\n"
        "4. Guarda el <b>numero de referencia</b> del comprobante"
    ),
}


async def receive_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    platform = query.data.replace("platform_", "")
    context.user_data['temp_platform'] = platform

    template = _PAYMENT_INFO.get(platform, "Plataforma seleccionada: <b>{platform}</b>")
    info = (template
            .replace("{NEQUI}",       config.NEQUI_NUMERO)
            .replace("{BANCOLOMBIA}", config.BANCOLOMBIA_CUENTA)
            .replace("{DAVIPLATA}",   config.DAVIPLATA_NUMERO))

    await query.edit_message_text(
        f"{info}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Valor a pagar: <b>{config.PRECIO_SUSCRIPCION}</b>\n\n"
        f"🔢 <b>Paso 4/4</b> — Cuando hayas pagado, escribe el\n"
        f"<b>numero de referencia</b> de la transaccion:",
        parse_mode='HTML')
    return ASK_TRANSACTION


async def receive_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_transaction'] = update.message.text.strip()
    platform = context.user_data.get('temp_platform', '')
    await update.message.reply_text(
        f"✅ <b>Referencia registrada</b>\n\n"
        f"Metodo: <b>{platform}</b>\n"
        f"Referencia: <code>{context.user_data['temp_transaction']}</code>\n\n"
        f"📸 Por ultimo, envia la <b>foto del comprobante</b> de pago.",
        parse_mode='HTML')
    return ASK_RECEIPT


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Envia una <b>IMAGEN</b> del comprobante.", parse_mode='HTML')
        return ASK_RECEIPT

    photo_file  = update.message.photo[-1].file_id
    user        = update.effective_user
    name        = context.user_data.get('temp_name', user.first_name)
    phone       = context.user_data.get('temp_phone', 'N/A')
    platform    = context.user_data.get('temp_platform', 'N/A')
    transaction = context.user_data.get('temp_transaction', 'N/A')
    username    = f"@{user.username}" if user.username else "Sin usuario"

    if 'pending_users' not in context.bot_data:
        context.bot_data['pending_users'] = {}
    context.bot_data['pending_users'][str(user.id)] = {
        'name':        name,
        'username':    username,
        'phone':       phone,
        'platform':    platform,
        'transaction': transaction,
    }

    keyboard = [
        [InlineKeyboardButton("✅ Aprobar", callback_data=f"approve_{user.id}")],
        [InlineKeyboardButton("❌ Rechazar", callback_data=f"reject_{user.id}")]
    ]
    caption = (
        f"🔔 <b>NUEVO PAGO RECIBIDO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Nombre:</b> {name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"📱 <b>Usuario:</b> {username}\n"
        f"📞 <b>Celular:</b> <code>{phone}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Metodo:</b> {platform}\n"
        f"🔢 <b>Referencia:</b> <code>{transaction}</code>"
    )
    await context.bot.send_photo(
        chat_id=config.ADMIN_CHAT_ID,
        photo=photo_file,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML')
    await update.message.reply_text(
        "⏳ <b>Comprobante recibido.</b>\n\n"
        "Un administrador verificara tu pago en los proximos minutos.\n"
        "Te notificaremos cuando tu acceso sea activado. ✅",
        parse_mode='HTML')
    return ConversationHandler.END


async def admin_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != config.ADMIN_CHAT_ID:
        return await query.answer("Acceso Denegado.", show_alert=True)
    action, target_user_id = query.data.split('_', 1)
    pending_data = context.bot_data.get('pending_users', {}).get(target_user_id, {})
    if action == "approve":
        # 1. Registrar en Google Sheets
        sheets_db.approve_payment(
            target_user_id,
            pending_data.get('name', 'Usuario'),
            pending_data.get('username', 'N/A'),
            phone=pending_data.get('phone', ''),
            metodo=pending_data.get('platform', 'Manual'),
            transaction=pending_data.get('transaction', ''),
        )

        # 2. Verificar que quedo activo en sheets
        activo = sheets_db.check_subscription(int(target_user_id))
        estado_tag = "✅ Verificado en base de datos" if activo else "⚠️ Verificar manualmente en sheets"

        # 3. Generar enlace de invitacion unico al canal premium
        invite_link = None
        try:
            link_obj = await context.bot.create_chat_invite_link(
                chat_id=config.CHANNEL_ID_BANKERS,
                member_limit=1,
                name=f"Acceso {pending_data.get('name','')[:20]}",
            )
            invite_link = link_obj.invite_link
        except Exception as e:
            logger.warning(f"No se pudo generar invite link: {e}")

        # 4. Actualizar caption del admin
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n✅ APROBADA\n{estado_tag}",
            parse_mode='HTML')

        # 5. Notificar al usuario con el link
        try:
            if invite_link:
                keyboard = [[InlineKeyboardButton("🔒 Entrar al canal premium", url=invite_link)]]
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🎉 <b>PAGO CONFIRMADO</b>\n\n"
                        f"Bienvenido a <b>{config.BOT_NAME}</b>.\n\n"
                        f"Toca el boton para acceder al canal premium 👇"
                    ),
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🎉 <b>PAGO CONFIRMADO</b>\n\n"
                        f"Bienvenido a <b>{config.BOT_NAME}</b>.\n"
                        f"Usa /today para ver los picks del dia."
                    ),
                    parse_mode='HTML')
        except Exception as e:
            logger.warning(f"No se pudo notificar al usuario {target_user_id}: {e}")

    elif action == "reject":
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n❌ RECHAZADO",
            parse_mode='HTML')
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ <b>Comprobante no valido</b>\n\n"
                    "Tu pago no pudo ser verificado.\n\n"
                    "Por favor envia un comprobante valido con:\n"
                    "• Fecha y hora de la transaccion\n"
                    "• Numero de referencia visible\n"
                    "• Valor pagado\n\n"
                    "Inicia nuevamente con /start."
                ),
                parse_mode='HTML')
        except Exception as e:
            logger.warning(f"No se pudo notificar rechazo a {target_user_id}: {e}")

    await query.answer()


async def manual_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in [config.ADMIN_CHAT_ID, getattr(config,'SUPPORT_CHAT_ID','')]: return
    try:
        sheets_db.approve_payment(context.args[0], "Manual", "Soporte")
        await update.message.reply_text(f"✅ Cliente <code>{context.args[0]}</code> habilitado.", parse_mode='HTML')
        await context.bot.send_message(chat_id=context.args[0],
            text=f"🎉 <b>LICENCIA ACTIVADA</b>\nUsa /today", parse_mode='HTML')
    except Exception:
        await update.message.reply_text("❌ Sintaxis: `/activar ID`", parse_mode='Markdown')


async def liquidar_resultados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != config.ADMIN_CHAT_ID: return
    status_msg = await update.message.reply_text("⏳ Liquidando resultados...")
    await _notify_results(context)
    await status_msg.edit_text("✅ Resultados procesados.")


async def config_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context): return
    try:
        monto = float(context.args[0].replace(',',''))
        context.user_data['bankroll'] = monto
        await update.message.reply_text(f"⚙️ <b>Capital actualizado:</b> ${monto:,.0f} COP", parse_mode='HTML')
    except Exception:
        await update.message.reply_text("❌ Usa: `/configbudget 500000`", parse_mode='Markdown')


async def manual_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != config.ADMIN_CHAT_ID: return
    status_msg = await update.message.reply_text("🕵️ <b>Ejecutando Escaner...</b>", parse_mode='HTML')
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str = now_local.strftime('%Y-%m-%d')
    await status_msg.edit_text("🔄 Analizando mercados...", parse_mode='HTML')

    live_picks = await run_quant_pipeline(today_str, config.BANKROLL_INICIAL)
    existing   = sheets_db.get_existing_picks(today_str)
    new_picks  = [p for p in live_picks if f"{p['home']} vs {p['away']}_{p['market']}" not in existing]

    bankers = sum(1 for p in live_picks if p.get('sport')=='💎')
    goals   = sum(1 for p in live_picks if p.get('sport') in ['⚽','🎯','🌍'])

    await status_msg.edit_text(
        f"📊 <b>Resultado del escaneo:</b>\n\n"
        f"🔍 Total: <b>{len(live_picks)}</b>\n"
        f"  💎 Bankers: {bankers}\n"
        f"  ⚽ Goles/1X2: {goals}\n\n"
        f"🆕 Nuevas: <b>{len(new_picks)}</b>\n"
        f"📁 Ya registradas: <b>{len(existing)}</b>\n\n"
        f"{'✅ Enviando...' if new_picks else '💤 Sin nuevas apuestas.'}",
        parse_mode='HTML')

    if new_picks:
        sheets_db.save_daily_picks(new_picks, today_str)
        await _distribute_picks(context, new_picks)
        picks_txt = ""
        for p in new_picks[:5]:
            picks_txt += f"\n• {p.get('sport','')} {p['home']} vs {p['away']} | {p['market']} @ {p['odds']} | EV: +{p['ev']:.1f}%"
        await update.message.reply_text(
            f"✅ <b>{len(new_picks)} picks enviados:</b>{picks_txt}", parse_mode='HTML')
    else:
        unsent = sheets_db.get_unsent_picks_for_today(today_str)
        if unsent:
            await update.message.reply_text(
                f"⚠️ Hay <b>{len(unsent)} picks guardados</b> sin enviar.\n"
                f"Usa /resend para enviarlos.", parse_mode='HTML')
        else:
            await update.message.reply_text(
                f"ℹ️ <b>Sin picks hoy</b>\n\n"
                f"🕐 {now_local.strftime('%H:%M')} COT | {today_str}\n\n"
                f"• Puede ser semana FIFA\n"
                f"• O partidos ya empezaron\n"
                f"• EV mínimo: {config.MIN_EV_THRESHOLD*100:.0f}% | Prob mínima: {config.MIN_PROBABILITY*100:.0f}%",
                parse_mode='HTML')


async def resend_picks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != config.ADMIN_CHAT_ID: return
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)
    today_str = now_local.strftime('%Y-%m-%d')
    status_msg = await update.message.reply_text("📤 <b>Reenviando picks...</b>", parse_mode='HTML')

    all_today = sheets_db.get_active_picks_for_today(today_str, "00:00")
    if not all_today:
        await status_msg.edit_text("❌ No hay picks guardados para hoy.")
        return

    picks_to_send = []
    for r in all_today:
        stake_str = str(r.get("Stake_Nivel", "5/10"))
        try:    stake_lvl = int(stake_str.split('/')[0])
        except: stake_lvl = 5
        stake_cop = int((stake_lvl / 10.0) * config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT)

        mercado = r.get("Mercado", "")
        if "BANKER" in mercado.upper():                         sport_icon = "💎"
        elif "mas de" in mercado.lower() or "menos de" in mercado.lower(): sport_icon = "🎯"
        else:                                                    sport_icon = "⚽"

        partido = r.get("Partido", "")
        partes  = partido.split(" vs ") if " vs " in partido else [partido, ""]

        event_id_raw   = str(r.get("Event_ID", "")).strip()
        outcome_id_raw = str(r.get("Outcome_ID", "")).strip()
        event_id   = int(event_id_raw)   if event_id_raw.isdigit()   else None
        outcome_id = outcome_id_raw      if outcome_id_raw.isdigit() else ""

        picks_to_send.append({
            "sport":        sport_icon,
            "time":         r.get("Hora", ""),
            "home":         partes[0],
            "away":         partes[1] if len(partes) > 1 else "",
            "market":       mercado,
            "odds":         r.get("Cuota_Rushbet", 0),
            "prob":         float(str(r.get("Probabilidad_%","60")).replace("%","")),
            "ev":           float(str(r.get("EV_%","+5")).replace("%","").replace("+","")),
            "stake_amount": stake_cop,
            "reason":       r.get("Analisis", ""),
            "confidence":   "✅ ALTA",
            "source":       r.get("Fuente", "rushbet"),
            "event_id":     event_id,
            "outcome_id":   outcome_id,
        })

    await status_msg.edit_text(f"📤 Enviando <b>{len(picks_to_send)} picks</b>...", parse_mode='HTML')

    # Canal premium
    enviados = 0
    for p in picks_to_send:
        msg      = _build_pick_message(p)
        keyboard = build_premium_pick_keyboard(p)
        img      = _generate_pick_img(p)
        try:
            if img:
                await context.bot.send_photo(
                    chat_id=config.CHANNEL_ID_BANKERS, photo=img,
                    caption=msg, parse_mode='HTML', reply_markup=keyboard)
            else:
                await context.bot.send_message(
                    chat_id=config.CHANNEL_ID_BANKERS,
                    text=msg, parse_mode='HTML', reply_markup=keyboard)
            enviados += 1
        except Exception as e:
            logger.error(f"Error resend premium: {e}")

    # Canal gratuito
    if config.CHANNEL_ID_FREE:
        n = config.FREE_CHANNEL_MAX_PICKS_PER_DAY
        for i, p in enumerate(picks_to_send[:n], 1):
            stake_lvl_f = max(1, min(10, int(round(
                (p.get('stake_amount',0) / (config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT)) * 10))))
            market_exp = _market_explanation(p.get('market',''))
            msg_free = (
                f"{p.get('sport','⚽')} <b>SENAL #{i} DE {n} — GRATIS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 <b>{p['home']}  vs  {p['away']}</b>\n"
                f"⏱️ {p.get('time','')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>Apuesta:</b> {p['market']}\n"
                f"💡 <i>{market_exp}</i>\n\n"
                f"💵 <b>Cuota Rushbet:</b> <code>{p['odds']}</code>\n"
                f"📊 <b>Prob:</b> {p['prob']:.1f}% | <b>Stake:</b> {stake_lvl_f}/10\n"
                f"🎯 <b>Confianza:</b> {p.get('confidence','')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 <i>Analisis completo en canal premium</i>"
            )
            keyboard_free = build_pick_keyboard(p)
            img_free      = _generate_pick_img(p)
            try:
                if img_free:
                    await context.bot.send_photo(
                        chat_id=config.CHANNEL_ID_FREE, photo=img_free,
                        caption=msg_free, parse_mode='HTML', reply_markup=keyboard_free)
                else:
                    await context.bot.send_message(
                        chat_id=config.CHANNEL_ID_FREE,
                        text=msg_free, parse_mode='HTML', reply_markup=keyboard_free)
            except Exception as e:
                logger.error(f"Error resend free: {e}")

    # Usuarios premium
    active_users = sheets_db.get_active_users()
    for p in picks_to_send:
        msg      = _build_pick_message(p)
        keyboard = build_premium_pick_keyboard(p)
        for uid in active_users:
            try:
                await context.bot.send_message(
                    chat_id=uid, text=msg, parse_mode='HTML', reply_markup=keyboard)
            except Exception as e:
                logger.warning(f"Error resend usuario {uid}: {e}")

    await status_msg.edit_text(
        f"✅ <b>{enviados} picks enviados</b>\n"
        f"• Canal premium\n"
        f"• Canal gratuito ({config.FREE_CHANNEL_MAX_PICKS_PER_DAY} picks)\n"
        f"• {len(active_users)} usuarios premium", parse_mode='HTML')


async def ask_receipt_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Por favor envía la <b>foto</b> del comprobante.", parse_mode='HTML')


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=========================================")
    print(f"[BOT] {config.BOT_NAME} v5.0")
    print(f"[*] Admin:          {config.ADMIN_CHAT_ID}")
    print(f"[*] Canal gratuito: {config.CHANNEL_ID_FREE or 'No configurado'}")
    print(f"[*] Canal premium:  {config.CHANNEL_ID_BANKERS or 'No configurado'}")
    print(f"[*] EV minimo:      {config.MIN_EV_THRESHOLD*100:.0f}%")
    print(f"[*] Prob minima:    {config.MIN_PROBABILITY*100:.0f}%")
    print("=========================================")

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    tz  = pytz.timezone(config.TIMEZONE)

    for h in [time(hour=0,minute=5,tzinfo=tz), time(hour=8,minute=0,tzinfo=tz),
               time(hour=12,minute=0,tzinfo=tz), time(hour=18,minute=0,tzinfo=tz)]:
        app.job_queue.run_daily(cron_market_scanner, h)

    app.job_queue.run_daily(daily_recap,             time(hour=23,minute=59,tzinfo=tz))
    app.job_queue.run_repeating(cron_auto_settle,    interval=1800, first=60)
    app.job_queue.run_daily(cron_free_channel_nudge, time(hour=20,minute=0,tzinfo=tz))

    print("[*] Jobs: 00:05 | 08:00 | 12:00 | 18:00 | settle cada 30min | 20:00 nudge | 23:59 recap")

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_buy_callback, pattern='^buy_vip$')],
        states={
            ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            ASK_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone),
            ],
            ASK_PLATFORM: [
                CallbackQueryHandler(receive_platform, pattern='^platform_'),
            ],
            ASK_TRANSACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transaction),
            ],
            ASK_RECEIPT: [
                MessageHandler(filters.PHOTO, receive_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_receipt_text),
            ],
        },
        fallbacks=[CommandHandler('cancel', start_command)],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",        start_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision_callback, pattern='^(approve|reject)_'))
    app.add_handler(CallbackQueryHandler(show_today_cache,        pattern='^show_today$'))
    app.add_handler(CommandHandler("liquidar",     liquidar_resultados))
    app.add_handler(CommandHandler("activar",      manual_activate))
    app.add_handler(CommandHandler("configbudget", config_budget))
    app.add_handler(CommandHandler("today",        show_today_cache))
    app.add_handler(CommandHandler("scan",         manual_scan))
    app.add_handler(CommandHandler("resend",       resend_picks))

    print("[*] Bot en linea.")
    app.run_polling()


if __name__ == "__main__":
    main()