# modules/_draw_utils.py
# Utilidades de dibujo compartidas entre image_generator y tiktok_video

import os
from PIL import ImageFont, ImageDraw, Image

COLORS = {
    "bg_dark":    (15, 17, 26),
    "bg_card":    (24, 28, 45),
    "green":      (46, 213, 115),
    "red":        (255, 71, 87),
    "gold":       (255, 200, 0),
    "blue":       (41, 128, 230),
    "purple":     (155, 89, 182),
    "orange":     (230, 126, 34),
    "white":      (255, 255, 255),
    "gray":       (140, 150, 170),
    "light_gray": (200, 210, 220),
    "dim":        (50, 55, 75),
}

SPORT_COLORS = {
    "💎": (255, 200, 0),
    "⚽": (46, 213, 115),
    "2️⃣": (41, 128, 230),
    "🟨": (230, 180, 0),
    "🚩": (230, 80, 80),
    "🎯": (155, 89, 182),
    "⏱️": (100, 180, 220),
    "🌍": (46, 180, 100),
    "🏀": (230, 126, 34),
    "🎾": (155, 89, 182),
}


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_paths = [
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_rounded_rect(draw, xy, radius, fill, outline=None, outline_width=2):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill,
                                outline=outline, width=outline_width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


def fade_color(color: tuple, alpha: float, bg: tuple = None) -> tuple:
    """Mezcla un color con el fondo para simular transparencia en modo RGB."""
    if bg is None:
        bg = COLORS["bg_dark"]
    alpha = max(0.0, min(1.0, alpha))
    return tuple(int(c * alpha + b * (1 - alpha)) for c, b in zip(color, bg))


def alpha_blend(base: Image.Image, color: tuple, alpha: float) -> Image.Image:
    """Aplica overlay de color sólido sobre base con alpha."""
    if alpha <= 0:
        return base
    overlay = Image.new("RGB", base.size, color)
    return Image.blend(base, overlay, max(0.0, min(1.0, alpha)))


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 2


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * clamp(t, 0, 1)
