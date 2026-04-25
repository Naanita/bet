# modules/tiktok_uploader.py — v1
# TikTok Content Posting API v2
# Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
#
# SETUP INICIAL (una sola vez):
#   1. Crear app en https://developers.tiktok.com con scope video.publish
#   2. Correr: python -m modules.tiktok_uploader --auth
#      Esto abre el browser para OAuth y guarda los tokens en .env
#   3. Los tokens se refrescan automáticamente cada 23h

import os
import json
import time
import logging
import math
from pathlib import Path
from datetime import datetime

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    try:
        import httpx as requests  # type: ignore
        REQUESTS_OK = True
    except ImportError:
        REQUESTS_OK = False

logger = logging.getLogger(__name__)

BASE_URL  = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{BASE_URL}/oauth/token/"
AUTH_URL  = "https://www.tiktok.com/v2/auth/authorize/"

# Hashtags base para todos los videos
BASE_HASHTAGS = [
    "quantsignals", "apuestasdeportivas", "apuestascolombia",
    "pronosticos", "tipster", "betcolombia", "rushbet",
    "analisisdeportivo", "futbol", "colombia",
]

SPORT_HASHTAGS = {
    "⚽": ["futbol", "soccer", "picks"],
    "💎": ["banker", "seguros", "futbol"],
    "🏀": ["nba", "baloncesto", "basketball"],
    "🎾": ["tenis", "tennis", "atp"],
    "🎯": ["overunder", "goles", "futbol"],
    "🌍": ["futbolinternacional", "picks"],
}


class TikTokUploader:
    """
    Sube videos a TikTok vía Content Posting API v2.

    Tokens se leen desde variables de entorno:
        TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
        TIKTOK_ACCESS_TOKEN, TIKTOK_REFRESH_TOKEN

    Uso:
        up = TikTokUploader()
        result = up.post_video("video.mp4", "Mi caption", ["tag1", "tag2"])
    """

    CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB por chunk

    def __init__(self, dry_run: bool = False):
        self.dry_run        = dry_run
        self.client_key     = os.getenv("TIKTOK_CLIENT_KEY", "")
        self.client_secret  = os.getenv("TIKTOK_CLIENT_SECRET", "")
        self.access_token   = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.refresh_token  = os.getenv("TIKTOK_REFRESH_TOKEN", "")

    # ── Token management ──────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }

    def refresh_access_token(self) -> bool:
        """Refresca el access_token usando el refresh_token. Actualiza .env."""
        if not self.refresh_token or not self.client_key:
            logger.error("[TIKTOK] No hay refresh_token o client_key configurados")
            return False
        try:
            resp = requests.post(TOKEN_URL, data={
                "client_key":     self.client_key,
                "client_secret":  self.client_secret,
                "grant_type":     "refresh_token",
                "refresh_token":  self.refresh_token,
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if "access_token" not in data:
                logger.error(f"[TIKTOK] Refresh fallido: {resp.text}")
                return False
            self.access_token  = data["access_token"]
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            self._save_tokens()
            logger.info("[TIKTOK] Token refrescado OK")
            return True
        except Exception as e:
            logger.error(f"[TIKTOK] Error refresh_token: {e}")
            return False

    def _save_tokens(self):
        """Persiste tokens en .env usando python-dotenv."""
        try:
            from dotenv import set_key
            env_path = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / ".env"
            set_key(str(env_path), "TIKTOK_ACCESS_TOKEN",  self.access_token)
            set_key(str(env_path), "TIKTOK_REFRESH_TOKEN", self.refresh_token)
        except Exception as e:
            logger.warning(f"[TIKTOK] No se pudo guardar tokens en .env: {e}")

    def _ensure_token(self) -> bool:
        """Verifica que haya access_token; intenta refrescar si falta."""
        if self.access_token:
            return True
        return self.refresh_access_token()

    # ── Upload pipeline ───────────────────────────────────────────────

    def _init_upload(self, video_size: int, caption: str) -> dict | None:
        """
        POST /v2/post/publish/video/init/
        Retorna {"publish_id": ..., "upload_url": ...}
        """
        chunk_size  = min(video_size, self.CHUNK_SIZE)
        chunk_count = math.ceil(video_size / chunk_size)
        payload = {
            "post_info": {
                "title":            caption[:2200],
                "privacy_level":    "PUBLIC_TO_EVERYONE",
                "disable_duet":     False,
                "disable_stitch":   False,
                "disable_comment":  False,
            },
            "source_info": {
                "source":            "FILE_UPLOAD",
                "video_size":        video_size,
                "chunk_size":        chunk_size,
                "total_chunk_count": chunk_count,
            },
        }
        try:
            resp = requests.post(
                f"{BASE_URL}/post/publish/video/init/",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if not data.get("upload_url"):
                logger.error(f"[TIKTOK] init_upload sin upload_url: {resp.text}")
                return None
            return data
        except Exception as e:
            logger.error(f"[TIKTOK] _init_upload error: {e}")
            return None

    def _upload_chunks(self, upload_url: str, video_path: str, video_size: int) -> bool:
        """PUT video al upload_url en chunks."""
        chunk_size  = min(video_size, self.CHUNK_SIZE)
        chunk_count = math.ceil(video_size / chunk_size)
        try:
            with open(video_path, "rb") as f:
                for i in range(chunk_count):
                    chunk = f.read(chunk_size)
                    start = i * chunk_size
                    end   = start + len(chunk) - 1
                    headers = {
                        "Content-Type":   "video/mp4",
                        "Content-Range":  f"bytes {start}-{end}/{video_size}",
                        "Content-Length": str(len(chunk)),
                    }
                    resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
                    resp.raise_for_status()
                    logger.info(f"[TIKTOK] Chunk {i+1}/{chunk_count} subido")
            return True
        except Exception as e:
            logger.error(f"[TIKTOK] _upload_chunks error: {e}")
            return False

    def _poll_status(self, publish_id: str, max_wait: int = 90) -> str:
        """
        Consulta /v2/post/publish/status/fetch/ hasta PUBLISH_COMPLETE o FAILED.
        Retorna: "PUBLISH_COMPLETE" | "FAILED" | "TIMEOUT"
        """
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                resp = requests.post(
                    f"{BASE_URL}/post/publish/status/fetch/",
                    headers=self._headers(),
                    json={"publish_id": publish_id},
                    timeout=20,
                )
                resp.raise_for_status()
                status = resp.json().get("data", {}).get("status", "PROCESSING_UPLOAD")
                logger.info(f"[TIKTOK] Publish status: {status}")
                if status in ("PUBLISH_COMPLETE", "FAILED"):
                    return status
            except Exception as e:
                logger.warning(f"[TIKTOK] _poll_status error: {e}")
            time.sleep(8)
        return "TIMEOUT"

    # ── Public API ────────────────────────────────────────────────────

    def post_video(
        self,
        video_path: str,
        caption: str,
        hashtags: list[str] = None,
        retry_on_401: bool = True,
    ) -> dict:
        """
        Sube y publica un video en TikTok.

        Returns:
            {"success": bool, "publish_id": str | None, "status": str, "error": str | None}
        """
        if not REQUESTS_OK:
            return {"success": False, "error": "requests/httpx no instalado"}

        if self.dry_run:
            logger.info(f"[TIKTOK] dry_run — se publicaría: {caption[:80]}...")
            return {"success": True, "publish_id": "dry_run", "status": "DRY_RUN"}

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Video no encontrado: {video_path}"}

        if not self._ensure_token():
            return {"success": False, "error": "Sin access_token"}

        # Construir caption con hashtags
        if hashtags:
            ht_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
            full_caption = f"{caption}\n\n{ht_str}"
        else:
            full_caption = caption

        video_size = os.path.getsize(video_path)
        logger.info(f"[TIKTOK] Subiendo video ({video_size/1024/1024:.1f} MB)...")

        # 1. Init
        init_data = self._init_upload(video_size, full_caption)
        if not init_data:
            return {"success": False, "error": "init_upload falló"}

        publish_id = init_data["publish_id"]
        upload_url = init_data["upload_url"]

        # 2. Upload
        if not self._upload_chunks(upload_url, video_path, video_size):
            if retry_on_401 and self.refresh_access_token():
                return self.post_video(video_path, caption, hashtags, retry_on_401=False)
            return {"success": False, "publish_id": publish_id, "error": "upload_chunks falló"}

        # 3. Poll status
        final_status = self._poll_status(publish_id)
        success = final_status == "PUBLISH_COMPLETE"
        return {
            "success":    success,
            "publish_id": publish_id,
            "status":     final_status,
            "error":      None if success else f"Status final: {final_status}",
        }

    def generate_caption(
        self,
        video_type: str,
        data: dict,
    ) -> tuple[str, list[str]]:
        """
        Genera caption y lista de hashtags para cada tipo de video.

        Returns: (caption_text, hashtags_list)
        """
        sport_icon = data.get("sport_icon", "⚽")
        ht = BASE_HASHTAGS.copy()
        ht.extend(SPORT_HASHTAGS.get(sport_icon, []))

        if video_type == "pick_reveal":
            home  = data.get("home", "")
            away  = data.get("away", "")
            mkt   = data.get("market", "")
            odds  = data.get("odds", 0)
            ev    = data.get("ev", 0)
            caption = (
                f"NUEVA SEÑAL de Quant Signals\n"
                f"{home} vs {away}\n"
                f"Mercado: {mkt} @ {odds:.2f}\n"
                f"EV +{ev:.1f}% — señal de alto valor\n\n"
                f"Suscribete al canal premium por $50.000/mes"
            )
            ht.extend(["señal", "picks", "apuesta"])

        elif video_type == "result_reveal":
            home   = data.get("home", "")
            away   = data.get("away", "")
            result = str(data.get("result", "W")).upper()
            mkt    = data.get("market", "")
            word   = "GANADA" if result == "W" else "PERDIDA"
            caption = (
                f"Resultado Quant Signals — {word}\n"
                f"{home} vs {away}\n"
                f"Mercado: {mkt}\n"
                f"El sistema sigue generando valor con analisis cuantitativo."
            )
            ht.extend(["gano" if result == "W" else "perdio", "resultados", "tips"])

        elif video_type == "daily_recap":
            wins   = data.get("wins", 0)
            losses = data.get("losses", 0)
            date   = data.get("date_str", "")
            wr     = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            caption = (
                f"Cierre de mercado {date}\n"
                f"{wins}W / {losses}L — Win Rate {wr:.0f}%\n"
                f"Sistema cuantitativo Quant Signals\n"
                f"Analisis matematico de apuestas deportivas"
            )
            ht.extend(["resumen", "winrate", "estadisticas", "cierre"])
        else:
            caption = "Quant Signals — Analisis cuantitativo de apuestas deportivas"

        # Dedup hashtags
        seen = set()
        unique_ht = []
        for h in ht:
            h = h.lower().replace(" ", "")
            if h not in seen:
                seen.add(h)
                unique_ht.append(h)

        return caption, unique_ht[:30]  # TikTok max ~30 hashtags


# ─────────────────────────────────────────────
# CLI helper para OAuth inicial
# ─────────────────────────────────────────────

def _run_auth_flow():
    """Flujo OAuth interactivo para obtener los tokens por primera vez."""
    import webbrowser
    from urllib.parse import urlencode, urlparse, parse_qs

    client_key    = input("TikTok Client Key: ").strip()
    client_secret = input("TikTok Client Secret: ").strip()
    redirect_uri  = "https://localhost:8080/callback"

    params = {
        "client_key":     client_key,
        "scope":          "video.publish,user.info.basic",
        "response_type":  "code",
        "redirect_uri":   redirect_uri,
        "state":          "quantsignals",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"\nAbriendo navegador para autorizar...\nURL: {auth_url}\n")
    webbrowser.open(auth_url)

    callback = input("Pega aquí la URL completa del callback: ").strip()
    code = parse_qs(urlparse(callback).query).get("code", [None])[0]
    if not code:
        print("ERROR: No se encontró 'code' en la URL")
        return

    resp = requests.post(TOKEN_URL, data={
        "client_key":    client_key,
        "client_secret": client_secret,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  redirect_uri,
    })
    data = resp.json().get("data", {})
    if "access_token" not in data:
        print(f"ERROR: {resp.text}")
        return

    from dotenv import set_key
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base, ".env")
    set_key(env_path, "TIKTOK_CLIENT_KEY",     client_key)
    set_key(env_path, "TIKTOK_CLIENT_SECRET",  client_secret)
    set_key(env_path, "TIKTOK_ACCESS_TOKEN",   data["access_token"])
    set_key(env_path, "TIKTOK_REFRESH_TOKEN",  data.get("refresh_token", ""))
    set_key(env_path, "TIKTOK_ENABLED",        "true")
    print("\nTokens guardados en .env exitosamente.")
    print(f"  Access token expira en: {data.get('expires_in', 86400)}s")
    print(f"  Refresh token expira en: {data.get('refresh_expires_in', 31536000)}s")


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        _run_auth_flow()
    else:
        print("Uso: python -m modules.tiktok_uploader --auth")
