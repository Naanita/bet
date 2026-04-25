# modules/tiktok_video.py — v1
# Genera videos verticales 9:16 (1080x1920) para TikTok
# Tipos: pick_reveal (18s), result_reveal (16s), daily_recap (20s)
#
# Dependencias: moviepy==1.0.3, gTTS, imageio-ffmpeg, Pillow, numpy
# Instalar: pip install moviepy==1.0.3 gTTS imageio-ffmpeg httpx

import os
import math
import tempfile
import logging
from datetime import datetime
from PIL import Image, ImageDraw

from modules._draw_utils import (
    COLORS, SPORT_COLORS, get_font, draw_rounded_rect,
    fade_color, alpha_blend, ease_out, ease_in_out, clamp, lerp
)

logger = logging.getLogger(__name__)

try:
    import numpy as np
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False

try:
    from moviepy.editor import VideoClip, AudioFileClip
    MOVIEPY_OK = True
except ImportError:
    MOVIEPY_OK = False
    logger.warning("[TIKTOK] moviepy no instalado — videos deshabilitados")

try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False
    logger.warning("[TIKTOK] gTTS no instalado — videos sin voz")

# ─────────────────────────────────────────────
# Constantes de canvas
# ─────────────────────────────────────────────
VW, VH = 1080, 1920
FPS = 30

# Paleta extendida para TikTok (colores más saturados para pantalla)
TK_COLORS = {
    **COLORS,
    "bg_dark":  (10, 12, 20),
    "bg_card":  (18, 22, 38),
    "bg_card2": (24, 30, 50),
    "accent":   (46, 213, 115),
    "gold":     (255, 200, 0),
    "red":      (255, 60, 80),
    "dim":      (45, 50, 70),
}

SPORT_ACCENT = {
    "💎": TK_COLORS["gold"],
    "⚽": TK_COLORS["accent"],
    "🎯": (41, 128, 230),
    "🏀": (230, 126, 34),
    "🎾": (155, 89, 182),
    "🌍": (46, 180, 100),
    "2️⃣": (41, 128, 230),
    "🟨": (230, 180, 0),
    "🚩": (230, 80, 80),
}

SPORT_LABEL = {
    "💎": "BANKER",
    "⚽": "FUTBOL",
    "🎯": "OVER/UNDER",
    "🏀": "BASKET",
    "🎾": "TENIS",
    "🌍": "FUTBOL",
    "2️⃣": "DOBLE OP.",
    "🟨": "TARJETAS",
    "🚩": "CORNERS",
}


# ─────────────────────────────────────────────
# Renderer de frames
# ─────────────────────────────────────────────

class _FrameRenderer:
    """Renderiza un frame individual para un video TikTok dado."""

    def __init__(self, video_type: str, data: dict):
        self.vtype = video_type
        self.d = data
        self.accent = SPORT_ACCENT.get(data.get("sport_icon", "⚽"), TK_COLORS["accent"])

    def render(self, fi: int) -> Image.Image:
        if self.vtype == "pick":
            return self._render_pick(fi)
        elif self.vtype == "result":
            return self._render_result(fi)
        else:
            return self._render_recap(fi)

    # ── Helpers comunes ──────────────────────────────────────────────

    def _base(self) -> Image.Image:
        return Image.new("RGB", (VW, VH), TK_COLORS["bg_dark"])

    def _draw_brand_header(self, draw: ImageDraw.Draw, alpha: float = 1.0):
        """Cabecera superior con nombre del canal."""
        gold = fade_color(TK_COLORS["gold"], alpha, TK_COLORS["bg_dark"])
        gray = fade_color(TK_COLORS["gray"], alpha * 0.6, TK_COLORS["bg_dark"])
        acc  = fade_color(self.accent, alpha, TK_COLORS["bg_dark"])

        # Logo text
        draw.text((70, 50), "QUANT SIGNALS", font=get_font(52), fill=gold)
        draw.text((70, 114), "Sistema cuantitativo de analisis", font=get_font(32), fill=gray)
        # Accent line
        draw.line([(70, 160), (VW - 70, 160)], fill=acc, width=3)

    def _draw_cta_band(self, draw: ImageDraw.Draw, alpha: float = 1.0):
        """Banda inferior de CTA fija."""
        bg   = fade_color(self.accent, alpha * 0.15, TK_COLORS["bg_dark"])
        acc  = fade_color(self.accent, alpha, TK_COLORS["bg_dark"])
        gold = fade_color(TK_COLORS["gold"], alpha, TK_COLORS["bg_dark"])
        white = fade_color(TK_COLORS["white"], alpha, TK_COLORS["bg_dark"])

        y1, y2 = VH - 220, VH - 20
        draw_rounded_rect(draw, [60, y1, VW - 60, y2], radius=24,
                           fill=bg, outline=acc, outline_width=3)
        draw.text((VW // 2 - 280, y1 + 22), "UNETE AL CANAL PREMIUM", font=get_font(44), fill=gold)
        draw.text((VW // 2 - 220, y1 + 80), "@QuantSignals en Telegram", font=get_font(38), fill=white)
        draw.text((VW // 2 - 180, y1 + 130), f"Solo $50.000 COP/mes", font=get_font(34), fill=acc)

    def _center_x(self, draw: ImageDraw.Draw, text: str, font, y: int, color: tuple):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((VW - w) // 2, y), text, font=font, fill=color)

    # ── PICK REVEAL (18s / 540 frames) ──────────────────────────────
    # Fases: HOOK(0-59) MATCH(60-179) MARKET(180-329) STATS(330-449) CTA(450-539)

    def _render_pick(self, fi: int) -> Image.Image:
        d = self.d
        accent = self.accent

        # ── Base + flash hook ──────────────────
        img = self._base()
        if fi < 60:
            flash = ease_in_out(1 - fi / 60)
            img = alpha_blend(img, accent, flash * 0.55)

        draw = ImageDraw.Draw(img)

        # ── Header (fade in primeros 30 frames) ──
        h_alpha = ease_in_out(clamp((fi - 10) / 25, 0, 1))
        if h_alpha > 0:
            self._draw_brand_header(draw, h_alpha)

        # ── HOOK text (frames 20-59) ──────────
        if fi < 60:
            ht = ease_in_out(clamp((fi - 20) / 25, 0, 1))
            if ht > 0:
                wh = fade_color(TK_COLORS["white"], ht, TK_COLORS["bg_dark"])
                ac = fade_color(accent, ht, TK_COLORS["bg_dark"])
                sport_lbl = SPORT_LABEL.get(d.get("sport_icon", "⚽"), "PICK")
                badge_w = len(sport_lbl) * 28 + 40
                # Badge centrado
                bx = (VW - badge_w) // 2
                draw_rounded_rect(draw, [bx, 820, bx + badge_w, 880], radius=12, fill=ac)
                draw.text((bx + 20, 828), sport_lbl, font=get_font(38), fill=TK_COLORS["bg_dark"])
                # Texto principal
                self._center_x(draw, "SEÑAL DE ALTO VALOR", get_font(68), 900, wh)
                self._center_x(draw, "detectada por el modelo", get_font(40), 988, fade_color(TK_COLORS["gray"], ht, TK_COLORS["bg_dark"]))
            return img

        # ── MATCH CARD (fi 60-179) ─────────────
        if fi < 180:
            t = (fi - 60) / 120
            card_y = int(lerp(VH + 80, 200, ease_out(t)))
        else:
            card_y = 200

        if fi >= 60:
            self._draw_pick_card(draw, card_y, show_content=(fi >= 110))

        # ── MARKET + ODDS (fi 180-329) ─────────
        if fi >= 180:
            mt = (fi - 180) / 150 if fi < 330 else 1.0
            self._draw_market_section(draw, card_y, mt)

        # ── STATS (fi 330-449) ─────────────────
        if fi >= 330:
            st = (fi - 330) / 120 if fi < 450 else 1.0
            self._draw_stats_section(draw, card_y, st)

        # ── CTA band (fi 450+) ─────────────────
        ct = ease_in_out(clamp((fi - 450) / 60, 0, 1))
        if ct > 0:
            self._draw_cta_band(draw, ct)

        return img

    def _draw_pick_card(self, draw, card_y: int, show_content: bool):
        d = self.d
        accent = self.accent
        # Card background (ocupa 90% del ancho)
        x1, x2 = 60, VW - 60
        y1 = card_y
        y2 = card_y + 1340

        draw_rounded_rect(draw, [x1, y1, x2, y2], radius=28,
                           fill=TK_COLORS["bg_card"], outline=accent, outline_width=3)
        # Banner superior de color
        draw_rounded_rect(draw, [x1, y1, x2, y1 + 90], radius=28,
                           fill=accent)
        draw.rectangle([x1, y1 + 60, x2, y1 + 90], fill=accent)
        sport_lbl = SPORT_LABEL.get(d.get("sport_icon", "⚽"), "PICK")
        draw.text((x1 + 30, y1 + 22), f"NUEVA SEÑAL  |  {sport_lbl}", font=get_font(42), fill=TK_COLORS["bg_dark"])

        if show_content:
            home = d.get("home", "").upper()
            away = d.get("away", "").upper()
            match_time = d.get("match_time", "")
            # Equipos
            ty = y1 + 110
            draw.text((x1 + 30, ty), home, font=get_font(70), fill=TK_COLORS["white"])
            draw.text((x1 + 30, ty + 80), "VS", font=get_font(52), fill=accent)
            draw.text((x1 + 30, ty + 150), away, font=get_font(70), fill=TK_COLORS["white"])
            # Hora
            if match_time:
                draw.text((x1 + 30, ty + 240), f"Hora: {match_time}", font=get_font(38), fill=TK_COLORS["gray"])
            # Separador
            sep_y = ty + 300
            draw.line([(x1 + 30, sep_y), (x2 - 30, sep_y)], fill=TK_COLORS["dim"], width=2)

    def _draw_market_section(self, draw, card_y: int, t: float):
        d = self.d
        accent = self.accent
        market = d.get("market", "")
        odds = float(d.get("odds", 1.50))
        ev = float(d.get("ev", 10.0))

        base_y = card_y + 550

        # Market (type-in)
        chars = max(1, int(len(market) * clamp(t * 2, 0, 1)))
        market_vis = market[:chars].upper()
        draw.text((90, base_y), "MERCADO", font=get_font(36), fill=TK_COLORS["gray"])
        draw.text((90, base_y + 44), market_vis, font=get_font(60), fill=TK_COLORS["white"])

        # Odds (count up)
        odds_t = clamp(t * 1.6, 0, 1)
        displayed_odds = 1.0 + (odds - 1.0) * ease_out(odds_t)
        draw.text((90, base_y + 130), "CUOTA EN RUSHBET", font=get_font(36), fill=TK_COLORS["gray"])
        draw.text((90, base_y + 176), f"{displayed_odds:.2f}", font=get_font(140), fill=accent)

        # EV bar (aparece en t > 0.55)
        ev_t = ease_in_out(clamp((t - 0.55) / 0.45, 0, 1))
        if ev_t > 0:
            bar_y = base_y + 360
            bx1, bx2 = 90, VW - 90
            bar_w = bx2 - bx1
            draw.text((bx1, bar_y - 46), "VALOR ESPERADO (EV)", font=get_font(36), fill=TK_COLORS["gray"])
            # Track
            draw.rectangle([bx1, bar_y, bx2, bar_y + 18], fill=TK_COLORS["dim"])
            # Fill (max visual al 50% EV)
            fill_pct = min(ev / 50.0, 1.0) * ev_t
            draw.rectangle([bx1, bar_y, bx1 + int(bar_w * fill_pct), bar_y + 18], fill=TK_COLORS["accent"])
            ev_show = ev * ev_t
            ev_color = TK_COLORS["accent"] if ev_show > 0 else TK_COLORS["red"]
            draw.text((bx1, bar_y + 26), f"+{ev_show:.1f}%", font=get_font(52), fill=ev_color)

    def _draw_stats_section(self, draw, card_y: int, t: float):
        d = self.d
        accent = self.accent
        prob = float(d.get("prob", 72.0))
        stake_level = d.get("stake_level", "5/10")
        confidence = d.get("confidence", "ALTA")
        ev = float(d.get("ev", 10.0))

        base_y = card_y + 960
        draw.line([(90, base_y - 10), (VW - 90, base_y - 10)], fill=TK_COLORS["dim"], width=2)

        alpha_t = ease_in_out(t)
        col_w = (VW - 180) // 3

        stats = [
            ("PROB.", f"{prob:.0f}%", TK_COLORS["white"]),
            ("EV",    f"+{ev:.1f}%", TK_COLORS["accent"]),
            ("STAKE", stake_level,   TK_COLORS["gold"]),
        ]
        for i, (label, val, color) in enumerate(stats):
            x = 90 + i * col_w
            lc = fade_color(TK_COLORS["gray"], alpha_t, TK_COLORS["bg_dark"])
            vc = fade_color(color, alpha_t, TK_COLORS["bg_dark"])
            draw.text((x, base_y + 10), label, font=get_font(34), fill=lc)
            draw.text((x, base_y + 52), val, font=get_font(66), fill=vc)

        # Confidence badge (aparece en t > 0.5)
        conf_t = ease_in_out(clamp((t - 0.5) / 0.5, 0, 1))
        if conf_t > 0:
            conf_clean = confidence.replace("🔥", "").replace("✅", "").replace("🟡", "").strip()
            conf_color = (
                TK_COLORS["gold"] if "MUY" in confidence else
                TK_COLORS["accent"] if "ALTA" in confidence else
                TK_COLORS["gray"]
            )
            badge_y = base_y + 160
            bc = fade_color(conf_color, conf_t * 0.2, TK_COLORS["bg_dark"])
            draw_rounded_rect(draw, [90, badge_y, 90 + 380, badge_y + 60], radius=14, fill=bc,
                               outline=fade_color(conf_color, conf_t, TK_COLORS["bg_dark"]), outline_width=2)
            draw.text((110, badge_y + 12), f"CONFIANZA: {conf_clean}", font=get_font(34),
                       fill=fade_color(conf_color, conf_t, TK_COLORS["bg_dark"]))

    # ── RESULT REVEAL (16s / 480 frames) ────────────────────────────
    # Fases: TENSION(0-89) SCORE(90-239) CONTEXT(240-359) CTA(360-479)

    def _render_result(self, fi: int) -> Image.Image:
        d = self.d
        result = str(d.get("result", "W")).upper()
        is_win = result == "W"
        accent = TK_COLORS["accent"] if is_win else TK_COLORS["red"]

        img = self._base()

        # Flash inicial
        if fi < 30:
            flash = ease_in_out(1 - fi / 30)
            img = alpha_blend(img, accent, flash * 0.6)

        draw = ImageDraw.Draw(img)

        # Header
        h_alpha = ease_in_out(clamp((fi - 10) / 25, 0, 1))
        self._draw_brand_header(draw, h_alpha)

        # ── TENSION / "?" (0-89) ──────────────
        if fi < 90:
            t = fi / 90
            wt = ease_in_out(clamp((fi - 15) / 30, 0, 1))
            if wt > 0:
                wh = fade_color(TK_COLORS["white"], wt, TK_COLORS["bg_dark"])
                self._center_x(draw, "RESULTADO:", get_font(72), 850, wh)
                home = d.get("home", "").upper()
                away = d.get("away", "").upper()
                self._center_x(draw, f"{home} VS {away}", get_font(52), 940, fade_color(TK_COLORS["gray"], wt, TK_COLORS["bg_dark"]))
            # Suspense indicator
            dots = "." * (1 + (fi // 10) % 3)
            self._center_x(draw, dots, get_font(100), 1050, fade_color(accent, t, TK_COLORS["bg_dark"]))
            return img

        # ── SCORE BOARD (90-239) ──────────────
        if fi < 240:
            t = (fi - 90) / 150

            # Card
            x1, x2, y1, y2 = 60, VW - 60, 220, 1420
            draw_rounded_rect(draw, [x1, y1, x2, y2], radius=28,
                               fill=TK_COLORS["bg_card"], outline=accent, outline_width=4)
            # Banner
            draw_rounded_rect(draw, [x1, y1, x2, y1 + 90], radius=28, fill=accent)
            draw.rectangle([x1, y1 + 60, x2, y1 + 90], fill=accent)
            result_word = "GANADA" if is_win else "PERDIDA"
            draw.text((x1 + 30, y1 + 22), f"APUESTA  {result_word}", font=get_font(46), fill=TK_COLORS["bg_dark"])

            # Match
            home = d.get("home", "").upper()
            away = d.get("away", "").upper()
            draw.text((x1 + 30, y1 + 110), home, font=get_font(66), fill=TK_COLORS["white"])
            draw.text((x1 + 30, y1 + 190), "VS", font=get_font(48), fill=accent)
            draw.text((x1 + 30, y1 + 250), away, font=get_font(66), fill=TK_COLORS["white"])

            # Score (aparece en t > 0.3)
            score_t = clamp((t - 0.3) / 0.4, 0, 1)
            if score_t > 0 and d.get("home_score") is not None:
                hs = d.get("home_score", 0)
                as_ = d.get("away_score", 0)
                # Simula count-up del marcador
                h_show = int(hs * ease_out(score_t))
                a_show = int(as_ * ease_out(score_t))
                score_str = f"{h_show}  -  {a_show}"
                score_font = get_font(130)
                bbox = draw.textbbox((0, 0), score_str, font=score_font)
                sw = bbox[2] - bbox[0]
                draw.text(((VW - sw) // 2, y1 + 380), score_str, font=score_font, fill=TK_COLORS["white"])

            # WIN / LOSS badge grande (t > 0.6)
            badge_t = ease_in_out(clamp((t - 0.6) / 0.4, 0, 1))
            if badge_t > 0:
                badge_color = fade_color(accent, badge_t, TK_COLORS["bg_card"])
                badge_font = get_font(100)
                bbox = draw.textbbox((0, 0), result_word, font=badge_font)
                bw = bbox[2] - bbox[0]
                by = y1 + 560 if d.get("home_score") is None else y1 + 640
                draw.text(((VW - bw) // 2, by), result_word, font=badge_font, fill=badge_color)

        # ── CONTEXT (240-359) ─────────────────
        if 240 <= fi < 360:
            t = (fi - 240) / 120
            market = d.get("market", "")
            odds = float(d.get("odds", 1.50))
            ev = d.get("ev", None)

            ct = ease_in_out(t)
            wh = fade_color(TK_COLORS["white"], ct, TK_COLORS["bg_dark"])
            gr = fade_color(TK_COLORS["gray"], ct, TK_COLORS["bg_dark"])
            ac = fade_color(accent, ct, TK_COLORS["bg_dark"])

            draw.text((90, 1470), "MERCADO:", font=get_font(40), fill=gr)
            draw.text((90, 1520), market.upper(), font=get_font(56), fill=wh)
            draw.text((90, 1600), f"Cuota: {odds:.2f}", font=get_font(48), fill=gr)
            if ev is not None:
                draw.text((480, 1600), f"EV: +{ev:.1f}%", font=get_font(48), fill=ac)

        # ── CTA (360+) ────────────────────────
        ct = ease_in_out(clamp((fi - 360) / 60, 0, 1))
        if ct > 0:
            self._draw_cta_band(draw, ct)

        return img

    # ── DAILY RECAP (20s / 600 frames) ──────────────────────────────
    # Fases: HOOK(0-59) STATS(60-299) HISTORY(300-449) CTA(450-599)

    def _render_recap(self, fi: int) -> Image.Image:
        d = self.d
        wins = int(d.get("wins", 0))
        losses = int(d.get("losses", 0))
        voids = int(d.get("voids", 0))
        profit = float(d.get("profit_units", 0.0))
        date_str = d.get("date_str", datetime.now().strftime("%d/%m/%Y"))
        total = wins + losses + voids
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        is_pos = profit >= 0
        accent = TK_COLORS["accent"] if is_pos else TK_COLORS["red"]

        img = self._base()

        # Flash gold
        if fi < 45:
            flash = ease_in_out(1 - fi / 45)
            img = alpha_blend(img, TK_COLORS["gold"], flash * 0.5)

        draw = ImageDraw.Draw(img)

        h_alpha = ease_in_out(clamp((fi - 10) / 25, 0, 1))
        self._draw_brand_header(draw, h_alpha)

        # ── HOOK (0-59) ───────────────────────
        if fi < 60:
            ht = ease_in_out(clamp((fi - 20) / 28, 0, 1))
            if ht > 0:
                gold = fade_color(TK_COLORS["gold"], ht, TK_COLORS["bg_dark"])
                wh   = fade_color(TK_COLORS["white"], ht, TK_COLORS["bg_dark"])
                self._center_x(draw, "CIERRE DE MERCADO", get_font(72), 870, gold)
                self._center_x(draw, date_str, get_font(52), 960, wh)
            return img

        # ── STATS COUNTER (60-299) ────────────
        if fi < 300:
            t = (fi - 60) / 240

            # Card
            x1, x2, y1, y2 = 60, VW - 60, 200, 1450
            draw_rounded_rect(draw, [x1, y1, x2, y2], radius=28,
                               fill=TK_COLORS["bg_card"], outline=TK_COLORS["gold"], outline_width=3)
            draw_rounded_rect(draw, [x1, y1, x2, y1 + 90], radius=28, fill=TK_COLORS["gold"])
            draw.rectangle([x1, y1 + 60, x2, y1 + 90], fill=TK_COLORS["gold"])
            draw.text((x1 + 30, y1 + 22), f"RESUMEN DEL DIA  |  {date_str}", font=get_font(42), fill=TK_COLORS["bg_dark"])

            # Contadores principales
            stats_data = [
                ("GANADAS",  wins,    TK_COLORS["accent"]),
                ("PERDIDAS", losses,  TK_COLORS["red"]),
                ("TOTAL",    total,   TK_COLORS["white"]),
            ]
            col_w = (VW - 180) // 3
            for i, (label, val, color) in enumerate(stats_data):
                st = ease_in_out(clamp((t - i * 0.12) / 0.3, 0, 1))
                x = 90 + i * col_w
                ct = ease_in_out(clamp((t - i * 0.12) / 0.25, 0, 1))
                displayed_val = int(val * ease_out(ct))
                lc = fade_color(TK_COLORS["gray"], st, TK_COLORS["bg_card"])
                vc = fade_color(color, st, TK_COLORS["bg_card"])
                draw.text((x, y1 + 110), label, font=get_font(34), fill=lc)
                draw.text((x, y1 + 152), str(displayed_val), font=get_font(96), fill=vc)

            draw.line([(x1 + 30, y1 + 310), (x2 - 30, y1 + 310)], fill=TK_COLORS["dim"], width=2)

            # Win rate donut (arc)
            arc_t = ease_in_out(clamp((t - 0.2) / 0.5, 0, 1))
            if arc_t > 0:
                cx, cy = VW // 2, y1 + 560
                r = 160
                # Background arc
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=TK_COLORS["dim"], width=20)
                # Filled arc (win rate)
                end_angle = -90 + 360 * (win_rate / 100) * arc_t
                draw.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=end_angle,
                          fill=TK_COLORS["accent"], width=20)
                # Texto en centro
                wr_t = ease_in_out(clamp((t - 0.4) / 0.3, 0, 1))
                if wr_t > 0:
                    wr_str = f"{win_rate * wr_t:.0f}%"
                    wrf = get_font(80)
                    bbox = draw.textbbox((0, 0), wr_str, font=wrf)
                    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    draw.text((cx - bw // 2, cy - bh // 2), wr_str, font=wrf, fill=TK_COLORS["white"])
                    draw.text((cx - 70, cy + 52), "WIN RATE", font=get_font(32), fill=TK_COLORS["gray"])

            # Profit/Loss (t > 0.5)
            pl_t = ease_in_out(clamp((t - 0.5) / 0.35, 0, 1))
            if pl_t > 0:
                draw.line([(x1 + 30, y1 + 790), (x2 - 30, y1 + 790)], fill=TK_COLORS["dim"], width=2)
                pl_color = TK_COLORS["accent"] if profit >= 0 else TK_COLORS["red"]
                sign = "+" if profit >= 0 else ""
                draw.text((90, y1 + 810), "RESULTADO P&L:", font=get_font(38), fill=fade_color(TK_COLORS["gray"], pl_t, TK_COLORS["bg_card"]))
                draw.text((90, y1 + 858), f"{sign}{profit * pl_t:.1f} unidades", font=get_font(78),
                           fill=fade_color(pl_color, pl_t, TK_COLORS["bg_card"]))

        # ── HISTORY / BADGE (300-449) ─────────
        if 300 <= fi < 450:
            t = (fi - 300) / 150
            # Continua mostrando el card con todo visible
            x1, x2, y1, y2 = 60, VW - 60, 200, 1450
            draw_rounded_rect(draw, [x1, y1, x2, y2], radius=28,
                               fill=TK_COLORS["bg_card"], outline=TK_COLORS["gold"], outline_width=3)
            draw.text((x1 + 30, y1 + 22), f"RESUMEN DEL DIA  |  {date_str}", font=get_font(40), fill=TK_COLORS["bg_dark"])

            # Badge de motivacion
            bt = ease_in_out(clamp(t / 0.4, 0, 1))
            badge_y = y1 + 130
            if bt > 0:
                msg = "RENTABILIDAD POSITIVA HOY" if is_pos else "EL EDGE SE DEMUESTRA A LARGO PLAZO"
                bc = fade_color(accent, bt * 0.2, TK_COLORS["bg_card"])
                draw_rounded_rect(draw, [x1 + 30, badge_y, x2 - 30, badge_y + 70], radius=16,
                                   fill=bc, outline=fade_color(accent, bt, TK_COLORS["bg_card"]), outline_width=2)
                msg_font = get_font(32)
                bbox = draw.textbbox((0, 0), msg, font=msg_font)
                bw = bbox[2] - bbox[0]
                draw.text(((VW - bw) // 2, badge_y + 18), msg, font=msg_font,
                           fill=fade_color(accent, bt, TK_COLORS["bg_card"]))

            # Stats resumidas
            lines = [
                (f"Ganadas:  {wins}", TK_COLORS["accent"]),
                (f"Perdidas: {losses}", TK_COLORS["red"]),
                (f"Win Rate: {win_rate:.1f}%", TK_COLORS["white"]),
                (f"P&L: {'+' if profit >= 0 else ''}{profit:.1f} u", TK_COLORS["accent"] if profit >= 0 else TK_COLORS["red"]),
            ]
            for i, (txt, color) in enumerate(lines):
                lt = ease_in_out(clamp((t - 0.1 * i) / 0.4, 0, 1))
                if lt > 0:
                    draw.text((90, badge_y + 90 + i * 88), txt, font=get_font(62),
                               fill=fade_color(color, lt, TK_COLORS["bg_card"]))

        # ── CTA (450+) ─────────────────────────
        ct = ease_in_out(clamp((fi - 450) / 60, 0, 1))
        if ct > 0:
            self._draw_cta_band(draw, ct)

        return img


# ─────────────────────────────────────────────
# Generador principal
# ─────────────────────────────────────────────

class TikTokVideoGenerator:
    """
    Genera videos MP4 9:16 para TikTok con animaciones y voz en español.

    Uso:
        gen = TikTokVideoGenerator()
        path = gen.generate_pick_reveal(
            home="Real Madrid", away="Barcelona",
            market="Mas de 2.5 goles", odds=1.75,
            prob=68.0, ev=19.5, stake_level="6/10",
            match_time="20:45", sport_icon="🎯"
        )
    """

    def __init__(self, output_dir: str = None, dry_run: bool = False):
        if output_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base, "data", "tiktok_videos")
        self.output_dir = output_dir
        self.dry_run = dry_run
        os.makedirs(os.path.join(output_dir, "pick_reveal"),   exist_ok=True)
        os.makedirs(os.path.join(output_dir, "result_reveal"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "daily_recap"),   exist_ok=True)

    # ── Públicos ─────────────────────────────────────────────────────

    def generate_pick_reveal(
        self,
        home: str, away: str, market: str, odds: float,
        prob: float, ev: float, stake_level: str = "5/10",
        match_time: str = "", sport_icon: str = "⚽",
        confidence: str = "ALTA",
    ) -> str | None:
        data = {
            "home": home, "away": away, "market": market,
            "odds": odds, "prob": prob, "ev": ev,
            "stake_level": stake_level, "match_time": match_time,
            "sport_icon": sport_icon, "confidence": confidence,
        }
        script = (
            f"Atencion. Nueva señal de Quant Signals. "
            f"{home} versus {away}. Mercado: {market}. "
            f"Cuota en Rushbet: {odds:.2f}. "
            f"Probabilidad calculada: {prob:.0f} por ciento. "
            f"Valor esperado positivo de {ev:.1f} por ciento. "
            f"Confianza: {confidence}. "
            f"Suscribete a nuestro canal para recibir todas las señales."
        )
        fname = f"pick_reveal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        out = os.path.join(self.output_dir, "pick_reveal", fname)
        return self._build(data, "pick", 540, script, out)

    def generate_result_reveal(
        self,
        home: str, away: str, market: str, odds: float,
        result: str,
        home_score: int = None, away_score: int = None,
        ev: float = None, stake_level: str = None,
    ) -> str | None:
        data = {
            "home": home, "away": away, "market": market,
            "odds": odds, "result": result,
            "home_score": home_score, "away_score": away_score,
            "ev": ev, "stake_level": stake_level,
            "sport_icon": "⚽",
        }
        result_word = "ganada" if result.upper() == "W" else "perdida"
        score_txt = f"El marcador fue {home_score} a {away_score}." if home_score is not None else ""
        script = (
            f"Resultado de Quant Signals. {home} versus {away}. "
            f"El mercado era {market} a cuota {odds:.2f}. "
            f"{score_txt} "
            f"La apuesta fue {result_word}. "
            f"Seguimos generando valor con analisis cuantitativo. Siguenos."
        )
        fname = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        out = os.path.join(self.output_dir, "result_reveal", fname)
        return self._build(data, "result", 480, script, out)

    def generate_daily_recap(
        self,
        date_str: str, wins: int, losses: int, voids: int,
        profit_units: float,
    ) -> str | None:
        data = {
            "date_str": date_str, "wins": wins, "losses": losses,
            "voids": voids, "profit_units": profit_units,
            "sport_icon": "⚽",
        }
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        sign = "positivo" if profit_units >= 0 else "negativo"
        script = (
            f"Cierre de mercado del dia {date_str}. "
            f"{wins} apuestas ganadas, {losses} perdidas. "
            f"Win rate del dia: {win_rate:.0f} por ciento. "
            f"Resultado en unidades: {profit_units:+.1f}, resultado {sign}. "
            f"El sistema cuantitativo Quant Signals sigue generando valor a largo plazo. "
            f"Unete a nuestro canal en Telegram."
        )
        fname = f"recap_{datetime.now().strftime('%Y%m%d')}.mp4"
        out = os.path.join(self.output_dir, "daily_recap", fname)
        return self._build(data, "recap", 600, script, out)

    # ── Internos ─────────────────────────────────────────────────────

    def _build(
        self,
        data: dict,
        vtype: str,
        total_frames: int,
        script: str,
        output_path: str,
    ) -> str | None:
        if not MOVIEPY_OK or not NUMPY_OK:
            logger.error("[TIKTOK] moviepy/numpy no disponibles")
            return None

        logger.info(f"[TIKTOK] Generando {vtype} ({total_frames} frames)...")

        if self.dry_run:
            # Solo renderiza el frame 270 como preview PNG
            renderer = _FrameRenderer(vtype, data)
            preview = renderer.render(total_frames // 2)
            preview_path = output_path.replace(".mp4", "_preview.png")
            preview.save(preview_path)
            logger.info(f"[TIKTOK] dry_run — preview guardado: {preview_path}")
            return preview_path

        # Generar audio
        audio_path = self._make_audio(script)

        # Renderizar video
        try:
            renderer = _FrameRenderer(vtype, data)

            def make_frame(t):
                fi = min(int(t * FPS), total_frames - 1)
                return np.array(renderer.render(fi))

            duration = total_frames / FPS
            clip = VideoClip(make_frame, duration=duration)

            if audio_path and os.path.exists(audio_path):
                try:
                    audio = AudioFileClip(audio_path)
                    if audio.duration > duration:
                        audio = audio.subclip(0, duration)
                    clip = clip.set_audio(audio)
                except Exception as e:
                    logger.warning(f"[TIKTOK] Audio error: {e}")

            clip.write_videofile(
                output_path,
                fps=FPS,
                codec="libx264",
                audio_codec="aac",
                verbose=False,
                logger=None,
            )

            logger.info(f"[TIKTOK] Video guardado: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"[TIKTOK] Error renderizando video: {e}", exc_info=True)
            return None
        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

    def _make_audio(self, text: str) -> str | None:
        if not GTTS_OK:
            return None
        try:
            tts = gTTS(text=text, lang="es", slow=False)
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tts.save(tmp.name)
            return tmp.name
        except Exception as e:
            logger.warning(f"[TIKTOK] gTTS error: {e}")
            return None
