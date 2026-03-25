# modules/image_generator.py v2
# Genera imagenes para picks individuales y recaps

import io
import os
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

COLORS = {
    "bg_dark":     (15, 17, 26),
    "bg_card":     (24, 28, 45),
    "green":       (46, 213, 115),
    "red":         (255, 71, 87),
    "gold":        (255, 200, 0),
    "blue":        (41, 128, 230),
    "purple":      (155, 89, 182),
    "orange":      (230, 126, 34),
    "white":       (255, 255, 255),
    "gray":        (140, 150, 170),
    "light_gray":  (200, 210, 220),
}

SPORT_COLORS = {
    "💎": (255, 200, 0),    # Gold para bankers
    "⚽": (46, 213, 115),   # Verde para goles
    "2️⃣": (41, 128, 230),   # Azul para doble oportunidad
    "🟨": (230, 180, 0),    # Amarillo para tarjetas
    "🚩": (230, 80, 80),    # Rojo para corners
    "🎯": (155, 89, 182),   # Purpura para over/under
    "⏱️": (100, 180, 220),  # Celeste para descanso
}


def _get_font(size: int, bold: bool = False):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_rounded_rect(draw, xy, radius, fill, outline=None, outline_width=2):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill,
                                outline=outline, width=outline_width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


def generate_pick_image(
    home: str,
    away: str,
    market: str,
    odds: float,
    prob: float,
    ev: float,
    stake_level: str,
    stake_cop: int,
    confidence: str,
    sport_icon: str = "⚽",
    match_time: str = "",
    channel_name: str = "Quant Signals",
) -> bytes | None:
    """Genera imagen de un pick individual."""
    if not PIL_AVAILABLE:
        return None

    W, H = 620, 340
    img  = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)

    accent = SPORT_COLORS.get(sport_icon, COLORS["green"])

    # Borde lateral
    draw.rectangle([(0, 0), (6, H)], fill=accent)

    # Card
    _draw_rounded_rect(draw, [16, 12, W-16, H-12], radius=14,
                        fill=COLORS["bg_card"], outline=accent, outline_width=2)

    f_small  = _get_font(12)
    f_med    = _get_font(16, bold=True)
    f_large  = _get_font(22, bold=True)
    f_xlarge = _get_font(28, bold=True)

    # Header
    draw.text((34, 22), channel_name, font=f_small, fill=COLORS["gold"])
    draw.text((W-130, 22), f"⏱ {match_time}", font=f_small, fill=COLORS["gray"])

    # Equipos
    match_str = f"{home}  vs  {away}"
    draw.text((34, 46), match_str, font=f_large, fill=COLORS["white"])

    # Separador
    draw.line([(34, 82), (W-34, 82)], fill=(40, 44, 60), width=1)

    # Mercado
    draw.text((34, 92), "MERCADO", font=f_small, fill=COLORS["gray"])
    draw.text((34, 110), market, font=f_med, fill=COLORS["white"])

    # Cuota
    draw.text((W//2, 92), "CUOTA", font=f_small, fill=COLORS["gray"])
    draw.text((W//2, 108), str(odds), font=f_xlarge, fill=accent)

    # Separador
    draw.line([(34, 155), (W-34, 155)], fill=(40, 44, 60), width=1)

    # Stats row — stake solo si se provee
    if stake_level:
        stats = [
            ("PROBABILIDAD", f"{prob:.1f}%", COLORS["white"]),
            ("EV",           f"+{ev:.1f}%",  COLORS["green"]),
            ("STAKE",        stake_level,     COLORS["gold"]),
        ]
        col_w = (W - 68) // 3
    else:
        stats = [
            ("PROBABILIDAD", f"{prob:.1f}%", COLORS["white"]),
            ("EV",           f"+{ev:.1f}%",  COLORS["green"]),
        ]
        col_w = (W - 68) // 2
    for i, (label, val, color) in enumerate(stats):
        x = 34 + i * col_w
        draw.text((x, 162), label, font=f_small, fill=COLORS["gray"])
        draw.text((x, 178), val,   font=f_med,   fill=color)

    # Separador
    draw.line([(34, 210), (W-34, 210)], fill=(40, 44, 60), width=1)

    # Confianza
    conf_clean = confidence.replace("🔥","").replace("✅","").replace("🟡","").replace("⚪","").strip()
    conf_color = (
        COLORS["gold"]  if "MUY ALTA" in confidence else
        COLORS["green"] if "ALTA" in confidence else
        COLORS["gray"]
    )
    draw.text((34, 220), "CONFIANZA:", font=f_small, fill=COLORS["gray"])
    draw.text((120, 218), conf_clean, font=f_med, fill=conf_color)

    # Timestamp
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    draw.text((W-130, H-28), ts, font=f_small, fill=COLORS["gray"])

    # Indicador de tipo de apuesta
    type_labels = {
        "💎": "BANKER", "⚽": "GOLES", "2️⃣": "DOBLE OP.",
        "🟨": "TARJETAS", "🚩": "CORNERS", "🎯": "OVER/UNDER",
    }
    type_label = type_labels.get(sport_icon, "PICK")
    _draw_rounded_rect(draw, [34, 218+16, 34+len(type_label)*8+16, 218+16+22],
                        radius=4, fill=accent)
    draw.text((42, 220+16), type_label, font=f_small, fill=COLORS["bg_dark"])

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


def generate_result_image(
    home: str, away: str, market: str, odds: float,
    result: str, home_score: int = None, away_score: int = None,
    ev: float = None, stake_level: str = None,
    channel_name: str = "Quant Signals",
) -> bytes | None:
    if not PIL_AVAILABLE:
        return None

    W, H = 600, 320
    img  = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)

    is_win = result.upper() == "W"
    accent = COLORS["green"] if is_win else COLORS["red"]
    result_text = "GANADA" if is_win else "PERDIDA"

    draw.rectangle([(0, 0), (6, H)], fill=accent)
    _draw_rounded_rect(draw, [20, 16, W-20, H-16], radius=14,
                        fill=COLORS["bg_card"], outline=accent, outline_width=2)

    f_small = _get_font(13)
    f_med   = _get_font(17, bold=True)
    f_large = _get_font(26, bold=True)
    f_xl    = _get_font(36, bold=True)

    draw.text((40, 30), channel_name, font=f_small, fill=COLORS["gold"])
    draw.text((40, 55), f"{home}  vs  {away}", font=f_med, fill=COLORS["white"])
    draw.line([(40, 88), (W-40, 88)], fill=(40, 44, 60), width=1)

    if home_score is not None and away_score is not None:
        score_str = f"{home_score}  -  {away_score}"
        bbox      = draw.textbbox((0, 0), score_str, font=f_xl)
        score_w   = bbox[2] - bbox[0]
        draw.text(((W - score_w) // 2, 95), score_str, font=f_xl, fill=COLORS["white"])
        y_mkt = 148
    else:
        y_mkt = 100

    draw.text((40, y_mkt),      f"Mercado: {market}", font=f_small, fill=COLORS["gray"])
    draw.text((40, y_mkt + 22), f"Cuota:   {odds}",   font=f_small, fill=COLORS["gray"])
    if ev is not None:
        draw.text((300, y_mkt), f"EV: {ev:.1f}%", font=f_small, fill=COLORS["gray"])

    draw.text((40, H-80), result_text, font=f_large, fill=accent)
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    draw.text((W-160, H-35), ts, font=f_small, fill=COLORS["gray"])

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


def generate_daily_recap_image(
    date_str: str, wins: int, losses: int, voids: int,
    profit_units: float, channel_name: str = "Quant Signals",
) -> bytes | None:
    if not PIL_AVAILABLE:
        return None

    W, H = 600, 360
    img  = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)

    is_pos = profit_units >= 0
    accent = COLORS["green"] if is_pos else COLORS["red"]

    draw.rectangle([(0, 0), (6, H)], fill=COLORS["gold"])
    _draw_rounded_rect(draw, [20, 16, W-20, H-16], radius=14,
                        fill=COLORS["bg_card"], outline=COLORS["gold"], outline_width=2)

    f_small = _get_font(13)
    f_med   = _get_font(18, bold=True)
    f_large = _get_font(28, bold=True)

    draw.text((40, 30), channel_name, font=f_small, fill=COLORS["gold"])
    draw.text((40, 55), "CIERRE DE MERCADO", font=f_med, fill=COLORS["white"])
    draw.text((40, 82), date_str, font=f_small, fill=COLORS["gray"])
    draw.line([(40, 108), (W-40, 108)], fill=(40, 44, 60), width=1)

    total    = wins + losses + voids
    win_rate = (wins / total * 100) if total > 0 else 0

    stats = [
        ("GANADAS",  str(wins),          COLORS["green"]),
        ("PERDIDAS", str(losses),         COLORS["red"]),
        ("NULAS",    str(voids),          COLORS["gray"]),
        ("WIN RATE", f"{win_rate:.1f}%",  COLORS["white"]),
    ]
    col_w = (W - 80) // 4
    for i, (label, val, color) in enumerate(stats):
        x = 40 + i * col_w
        draw.text((x, 120), label, font=f_small, fill=COLORS["gray"])
        draw.text((x, 140), val,   font=f_med,   fill=color)

    draw.line([(40, 185), (W-40, 185)], fill=(40, 44, 60), width=1)
    draw.text((40, 200), "Win Rate del dia:", font=f_small, fill=COLORS["gray"])
    draw.text((40, 222), f"{win_rate:.1f}%", font=f_large, fill=accent)

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    draw.text((W-160, H-35), ts, font=f_small, fill=COLORS["gray"])

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


def generate_monthly_recap_image(
    month_str: str, wins: int, losses: int, voids: int,
    profit_units: float, channel_name: str = "Quant Signals",
) -> bytes | None:
    if not PIL_AVAILABLE:
        return None

    W, H = 600, 420
    img  = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)

    is_pos = profit_units >= 0
    accent = COLORS["green"] if is_pos else COLORS["red"]

    draw.rectangle([(0, 0), (6, H)], fill=COLORS["gold"])
    _draw_rounded_rect(draw, [20, 16, W-20, H-16], radius=14,
                        fill=COLORS["bg_card"], outline=COLORS["gold"], outline_width=3)

    f_small = _get_font(13)
    f_med   = _get_font(18, bold=True)
    f_large = _get_font(30, bold=True)

    draw.text((40, 30), channel_name, font=f_small, fill=COLORS["gold"])
    draw.text((40, 55), "RESUMEN MENSUAL", font=f_med, fill=COLORS["gold"])
    draw.text((40, 82), month_str, font=f_small, fill=COLORS["gray"])
    draw.line([(40, 108), (W-40, 108)], fill=(40, 44, 60), width=1)

    total    = wins + losses + voids
    win_rate = (wins / total * 100) if total > 0 else 0
    roi      = (profit_units / total * 100) if total > 0 else 0

    rows = [
        ("Ganadas",  str(wins),          COLORS["green"]),
        ("Perdidas", str(losses),         COLORS["red"]),
        ("Total",    str(total),          COLORS["white"]),
        ("Win Rate", f"{win_rate:.1f}%",  COLORS["white"]),
        ("ROI",      f"{roi:+.1f}%",      accent),
    ]
    for i, (label, val, color) in enumerate(rows):
        y = 122 + i * 38
        draw.text((40,  y), label, font=f_small, fill=COLORS["gray"])
        draw.text((220, y), val,   font=f_med,   fill=color)

    draw.line([(40, 318), (W-40, 318)], fill=(40, 44, 60), width=1)
    draw.text((40, 332), "Win Rate Total:", font=f_small, fill=COLORS["gray"])
    draw.text((40, 354), f"{win_rate:.1f}%", font=f_large, fill=accent)

    ts = datetime.now().strftime("%d/%m/%Y")
    draw.text((W-160, H-35), ts, font=f_small, fill=COLORS["gray"])

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()