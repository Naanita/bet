#!/bin/bash
# startup.sh — Script de arranque para Render.com
# Se ejecuta en cada deploy / restart del servicio.

set -e   # detener si cualquier comando falla

echo "========================================="
echo "  Quant Bot — Iniciando en Render"
echo "========================================="

# ── 1. Crear directorio de datos (SQLite) ────────────────────────────────────
mkdir -p data

# ── 2. Decodificar credenciales de Google Sheets ─────────────────────────────
# La variable GOOGLE_CREDENTIALS_BASE64 contiene el contenido de credentials.json
# codificado en Base64. sheets_db.py lo lee directamente desde la env var,
# pero algunas librerías necesitan el archivo en disco. Lo creamos aquí por
# compatibilidad.
if [ -n "$GOOGLE_CREDENTIALS_BASE64" ]; then
    echo "[startup] Decodificando credentials.json desde GOOGLE_CREDENTIALS_BASE64..."
    echo "$GOOGLE_CREDENTIALS_BASE64" | base64 -d > credentials.json
    echo "[startup] credentials.json creado OK"
else
    echo "[startup] ADVERTENCIA: GOOGLE_CREDENTIALS_BASE64 no configurada"
fi

# ── 3. Verificar variables obligatorias ──────────────────────────────────────
if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "[startup] ERROR: TELEGRAM_TOKEN no configurado. Abortando."
    exit 1
fi
if [ -z "$ADMIN_CHAT_ID" ]; then
    echo "[startup] ERROR: ADMIN_CHAT_ID no configurado. Abortando."
    exit 1
fi

echo "[startup] Variables de entorno verificadas OK"
echo "[startup] Iniciando bot..."

# ── 4. Arrancar el bot ───────────────────────────────────────────────────────
exec python main.py
