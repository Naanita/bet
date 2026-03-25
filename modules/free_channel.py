# modules/free_channel.py v2
# Canal gratuito: 4 picks con stake, imagen por pick, boton de ir a Rushbet

import config
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def _rushbet_url(home: str, away: str, event_id: int = None, outcome_id: str = None) -> str:
    """
    URL de Rushbet:
    - Con outcome_id: abre boleto pre-llenado
    - Con event_id: va directo al partido
    """
    if outcome_id:
        return f"https://www.rushbet.co/?page=sportsbook#add-to-betslip/{outcome_id}"
    if event_id:
        return f"https://www.rushbet.co/?page=sportsbook#event/{event_id}"
    return "https://www.rushbet.co/?page=sportsbook"


def _stake_label(stake_level: str) -> str:
    """Convierte stake nivel a descripcion."""
    try:
        n = int(str(stake_level).split('/')[0])
    except Exception:
        return stake_level
    if n >= 9:   return f"{stake_level} 🔥 MAXIMO"
    elif n >= 7: return f"{stake_level} ✅ ALTO"
    elif n >= 5: return f"{stake_level} 🟡 MEDIO"
    else:        return f"{stake_level} ⚪ BAJO"


def _market_explanation(market: str) -> str:
    """Explica brevemente el mercado para usuarios nuevos."""
    m = market.lower()
    if "banker" in m:           return "Alta confianza: el local gana"
    if "mas de 2.5" in m:       return "El partido termina con 3 o mas goles"
    if "mas de 1.5" in m:       return "El partido termina con 2 o mas goles"
    if "mas de 3.5" in m:       return "El partido termina con 4 o mas goles"
    if "ambos anotan: si" in m: return "Ambos equipos anotan al menos 1 gol"
    if "ambos anotan: no" in m: return "Al menos uno no anota"
    if "1x" == m:               return "Local gana o empate"
    if "x2" == m:               return "Visitante gana o empate"
    if "12" == m:               return "Cualquiera gana (no empate)"
    if "tarjetas mas" in m:     return f"El partido tiene muchas tarjetas"
    if "tarjetas menos" in m:   return f"El partido tiene pocas tarjetas"
    if "corners mas" in m:      return f"Muchos tiros de esquina"
    if "corners menos" in m:    return f"Pocos tiros de esquina"
    if "ht" in m:               return "Resultado al descanso"
    return market


def build_free_pick_message(pick: dict, pick_number: int, total: int) -> str:
    sport   = pick.get("sport", "⚽")
    home    = pick.get("home", "")
    away    = pick.get("away", "")
    market  = pick.get("market", "")
    odds    = pick.get("odds", 0)
    prob    = pick.get("prob", 0)
    ev      = pick.get("ev", 0)
    time_   = pick.get("time", "")
    conf    = pick.get("confidence", "")

    # Stake
    stake_str  = str(pick.get("stake_level", "5/10"))
    stake_desc = _stake_label(stake_str)
    market_exp = _market_explanation(market)

    msg = (
        f"{sport} <b>SENAL #{pick_number} DE {total} — GRATIS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>{home}  vs  {away}</b>\n"
        f"⏱️ <b>Hora:</b> {time_}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Apuesta:</b> {market}\n"
        f"💡 <i>{market_exp}</i>\n\n"
        f"💵 <b>Cuota Rushbet:</b> <code>{odds}</code>\n"
        f"📊 <b>Probabilidad:</b> {prob:.1f}%\n"
        f"📈 <b>Valor esperado:</b> +{ev:.1f}%\n"
        f"🎯 <b>Confianza:</b> {conf}\n"
        f"💰 <b>Stake sugerido:</b> {stake_desc}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <i>Analisis completo + {total} picks premium disponibles abajo</i>"
    )
    return msg


def build_pick_keyboard(pick: dict) -> InlineKeyboardMarkup:
    """Botones: Ir a apostar en Rushbet + Unirse al premium."""
    event_id   = pick.get("event_id")
    outcome_id = pick.get("outcome_id", "")
    home       = pick.get("home", "")
    away       = pick.get("away", "")
    url        = _rushbet_url(home, away, event_id, outcome_id)

    keyboard = [
        [InlineKeyboardButton("🎰 Ir a apostar en Rushbet", url=url)],
        [InlineKeyboardButton("💎 Canal Premium — $50.000/mes", callback_data="buy_vip")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_premium_pick_keyboard(pick: dict) -> InlineKeyboardMarkup:
    """Boton solo de ir a apostar para usuarios premium."""
    event_id   = pick.get("event_id")
    outcome_id = pick.get("outcome_id", "")
    home       = pick.get("home", "")
    away       = pick.get("away", "")
    url        = _rushbet_url(home, away, event_id, outcome_id)
    keyboard = [[InlineKeyboardButton("🎰 Apostar en Rushbet", url=url)]]
    return InlineKeyboardMarkup(keyboard)


def build_result_notification(pick: dict, result: str) -> str:
    is_win  = result.upper() == "W"
    icon    = "🟢" if is_win else "🔴"
    word    = "GANADA ✅" if is_win else "PERDIDA ❌"
    home    = pick.get("home", "")
    away    = pick.get("away", "")
    market  = pick.get("market", "")
    odds    = pick.get("odds", 0)

    msg = (
        f"{icon} <b>RESULTADO: {word}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 {home} vs {away}\n"
        f"📌 {market} @ {odds}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if is_win:
        msg += "\n💰 <b>Mas picks como este en el canal premium:</b>"
    else:
        msg += "\n📊 <i>Las perdidas son parte del proceso. El edge matematico se demuestra a largo plazo.</i>"
    return msg


def build_conversion_nudge(wins_today: int, losses_today: int) -> str:
    total    = wins_today + losses_today
    win_rate = (wins_today / total * 100) if total > 0 else 0
    msg = (
        f"📈 <b>RESUMEN DEL DIA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Ganadas: {wins_today}  |  ❌ Perdidas: {losses_today}\n"
        f"🎯 Win Rate hoy: {win_rate:.0f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔒 <b>En premium hoy tuvimos:</b>\n"
        f"• Picks con analisis cuantitativo completo\n"
        f"• Gestion de banca con Kelly Criterion\n"
        f"• Stake personalizado segun tu capital\n"
        f"• Alertas instantaneas de oportunidades\n\n"
        f"💵 <b>Solo $50.000 COP/mes</b>\n"
    )
    return msg


def build_weekly_promo_message() -> str:
    return (
        f"⚡ <b>CANAL PREMIUM — ACCESO COMPLETO</b>\n\n"
        f"En el canal gratuito ves 4 picks/dia...\n\n"
        f"En premium tienes:\n"
        f"📡 Escaneo 4 veces al dia\n"
        f"💎 Bankers de alta confianza\n"
        f"2️⃣ Doble oportunidad\n"
        f"🟨 Tarjetas y 🚩 Corners\n"
        f"📊 Gestion de banca personalizada\n"
        f"📸 Resultados con imagen\n"
        f"🎰 Boton directo a Rushbet por pick\n\n"
        f"💵 <b>$50.000 COP/mes</b>\n"
    )


def build_free_pick_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💎 Canal Premium — $50.000/mes", callback_data="buy_vip")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─────────────────────────────────────────────
# Envios al canal gratuito
# ─────────────────────────────────────────────

async def send_free_picks(context, picks: list):
    """
    Envia 4 picks al canal gratuito:
    - 1 mejor pick (mayor EV)
    - 3 picks de calidad media
    Cada pick incluye imagen y boton de ir a Rushbet.
    """
    if not config.CHANNEL_ID_FREE:
        return

    from modules.image_generator import generate_pick_image

    max_picks = getattr(config, 'FREE_CHANNEL_MAX_PICKS_PER_DAY', 4)
    min_ev    = getattr(config, 'FREE_CHANNEL_MIN_EV', 0.03) * 100

    # Ordenar por EV y tomar distribucion: 1 top + resto variados
    eligible = sorted(
        [p for p in picks if p.get("ev", 0) >= min_ev],
        key=lambda x: x.get("ev", 0),
        reverse=True
    )

    if not eligible:
        return

    # Seleccion: el mejor + los siguientes hasta max_picks
    selected = eligible[:max_picks]

    for i, pick in enumerate(selected, 1):
        # Calcular stake
        max_stake  = config.BANKROLL_INICIAL * config.MAX_STAKE_PERCENT
        stake_lvl  = max(1, min(10, int(round((pick.get('stake_amount', 0) / max_stake) * 10))))
        stake_str  = f"{stake_lvl}/10"
        stake_cop  = int(pick.get("stake_amount", 0))
        pick["stake_level"] = stake_str

        msg      = build_free_pick_message(pick, i, len(selected))
        keyboard = build_pick_keyboard(pick)

        # Generar imagen del pick
        img_bytes = generate_pick_image(
            home=pick.get("home", ""),
            away=pick.get("away", ""),
            market=pick.get("market", ""),
            odds=pick.get("odds", 0),
            prob=pick.get("prob", 0),
            ev=pick.get("ev", 0),
            stake_level="",
            stake_cop=0,
            confidence=pick.get("confidence", "MEDIA"),
            sport_icon=pick.get("sport", "⚽"),
            match_time=pick.get("time", ""),
            channel_name=f"⚡ {config.BOT_NAME} — GRATIS",
        )

        try:
            if img_bytes:
                await context.bot.send_photo(
                    chat_id=config.CHANNEL_ID_FREE,
                    photo=img_bytes,
                    caption=msg,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await context.bot.send_message(
                    chat_id=config.CHANNEL_ID_FREE,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            logger.info(f"Pick gratuito {i}/{len(selected)} enviado.")
        except Exception as e:
            logger.error(f"Error enviando pick gratuito {i}: {e}")


async def send_result_to_free_channel(context, pick: dict, result: str):
    if not config.CHANNEL_ID_FREE:
        return

    from modules.image_generator import generate_result_image
    img_bytes = generate_result_image(
        home=pick.get("home", ""), away=pick.get("away", ""),
        market=pick.get("market", ""), odds=pick.get("odds", 0),
        result=result, channel_name=f"⚡ {config.BOT_NAME}",
    )
    msg      = build_result_notification(pick, result)
    keyboard = build_free_pick_keyboard()

    try:
        if img_bytes:
            await context.bot.send_photo(
                chat_id=config.CHANNEL_ID_FREE, photo=img_bytes,
                caption=msg, parse_mode="HTML", reply_markup=keyboard)
        else:
            await context.bot.send_message(
                chat_id=config.CHANNEL_ID_FREE, text=msg,
                parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error enviando resultado canal gratuito: {e}")


async def send_daily_recap_to_free_channel(context, date_str, wins, losses, voids, profit_units):
    if not config.CHANNEL_ID_FREE:
        return

    from modules.image_generator import generate_daily_recap_image
    img_bytes = generate_daily_recap_image(
        date_str=date_str, wins=wins, losses=losses,
        voids=voids, profit_units=profit_units,
        channel_name=f"⚡ {config.BOT_NAME}",
    )
    total    = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    caption  = (
        f"🌙 <b>CIERRE DE MERCADO — {date_str}</b>\n\n"
        f"✅ {wins} ganadas  |  ❌ {losses} perdidas\n"
        f"🎯 Win Rate: {win_rate:.0f}%\n\n"
        f"💎 Analisis completo en canal premium:"
    )
    try:
        if img_bytes:
            await context.bot.send_photo(
                chat_id=config.CHANNEL_ID_FREE, photo=img_bytes,
                caption=caption, parse_mode="HTML",
                reply_markup=build_free_pick_keyboard())
        else:
            await context.bot.send_message(
                chat_id=config.CHANNEL_ID_FREE, text=caption,
                parse_mode="HTML", reply_markup=build_free_pick_keyboard())
    except Exception as e:
        logger.error(f"Error recap canal gratuito: {e}")


async def send_monthly_recap(context, month_str, wins, losses, voids, profit_units):
    from modules.image_generator import generate_monthly_recap_image
    img_bytes = generate_monthly_recap_image(
        month_str=month_str, wins=wins, losses=losses,
        voids=voids, profit_units=profit_units,
        channel_name=f"⚡ {config.BOT_NAME}",
    )
    total    = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    sign     = "+" if profit_units >= 0 else ""

    caption_premium = (
        f"🏆 <b>RESUMEN MENSUAL — {month_str}</b>\n\n"
        f"✅ {wins} ganadas  ❌ {losses} perdidas  🔄 {voids} nulas\n"
        f"🎯 Win Rate: {win_rate:.1f}%\n"
        f"📈 Balance: <b>{sign}{profit_units:.2f} Unidades</b>"
    )

    for channel_id in [config.CHANNEL_ID_BANKERS, config.CHANNEL_ID_PARLAYS]:
        if channel_id:
            try:
                if img_bytes:
                    await context.bot.send_photo(chat_id=channel_id, photo=img_bytes,
                                                  caption=caption_premium, parse_mode="HTML")
                else:
                    await context.bot.send_message(chat_id=channel_id,
                                                    text=caption_premium, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error recap mensual canal {channel_id}: {e}")

    if config.CHANNEL_ID_FREE:
        caption_free = caption_premium + (
            f"\n\n💎 Unete al canal premium para el proximo mes:\n$50.000 COP/mes"
        )
        try:
            if img_bytes:
                await context.bot.send_photo(
                    chat_id=config.CHANNEL_ID_FREE, photo=img_bytes,
                    caption=caption_free, parse_mode="HTML",
                    reply_markup=build_free_pick_keyboard())
        except Exception as e:
            logger.error(f"Error recap mensual canal gratuito: {e}")