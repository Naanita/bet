# config.py — v5
# Lee credenciales desde .env — NO hardcodear keys aqui

import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CREDENCIALES (desde .env)
# ==========================================
ODDS_API_KEY      = os.getenv("ODDS_API_KEY", "")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "")
API_FOOTBALL_KEY  = os.getenv("API_FOOTBALL_KEY") or None
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY") or None  # Opcional (tier gratuito no requiere key)

# ==========================================
# ZONA HORARIA
# ==========================================
TIMEZONE = "America/Bogota"

# ==========================================
# GOOGLE SHEETS
# ==========================================
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "DB_BET")

# ==========================================
# CONTROL DE ACCESO
# ==========================================
ADMIN_CHAT_ID    = os.getenv("ADMIN_CHAT_ID", "")
SUPPORT_CHAT_ID  = os.getenv("SUPPORT_CHAT_ID", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "SupQRbot")

# ==========================================
# CANALES DE TELEGRAM
# ==========================================
CHANNEL_ID_BANKERS = os.getenv("CHANNEL_ID_BANKERS", "")
CHANNEL_ID_FREE    = os.getenv("CHANNEL_ID_FREE", "")

# ==========================================
# LIGAS (Understat + FBref)
# ==========================================
UNDERSTAT_LEAGUES = [
    'ENG-Premier League', 'ESP-La Liga', 'ITA-Serie A',
    'GER-Bundesliga', 'FRA-Ligue 1'
]

FBREF_LEAGUES = [
    'ENG-Premier League', 'ESP-La Liga', 'ITA-Serie A',
    'GER-Bundesliga', 'FRA-Ligue 1'
]

SOCCER_LEAGUES = {
    # Ligas elite (modelo Poisson + xG)
    'ENG-Premier League':      'soccer_epl',
    'ESP-La Liga':             'soccer_spain_la_liga',
    'ITA-Serie A':             'soccer_italy_serie_a',
    'GER-Bundesliga':          'soccer_germany_bundesliga',
    'FRA-Ligue 1':             'soccer_france_ligue_one',
    # Ligas segunda division
    'ENG-Championship':        'soccer_efl_champ',
    'ESP-La Liga 2':           'soccer_spain_segunda_division',
    'ITA-Serie B':             'soccer_italy_serie_b',
    'GER-2 Bundesliga':        'soccer_germany_bundesliga2',
    'FRA-Ligue 2':             'soccer_france_ligue_two',
    # Ligas internacionales
    'POR-Primeira Liga':       'soccer_portugal_primeira_liga',
    'NED-Eredivisie':          'soccer_netherlands_eredivisie',
    'BEL-First Division A':    'soccer_belgium_first_div',
    'TUR-Super Lig':           'soccer_turkey_super_league',
    'GRE-Super League':        'soccer_greece_super_league',
    'SCO-Premiership':         'soccer_scotland_premiership',
    # America
    'BRA-Serie A':             'soccer_brazil_campeonato',
    'ARG-Primera Division':    'soccer_argentina_primera_division',
    'COL-Liga BetPlay':        'soccer_colombia_primera_a',
    'MEX-Liga MX':             'soccer_mexico_ligamx',
    'USA-MLS':                 'soccer_usa_mls',
    'CHI-Primera Division':    'soccer_chile_primera_division',
    'URU-Primera Division':    'soccer_uruguay_primera_division',
    # Copa / Europa
    'UEFA-Champions League':   'soccer_uefa_champs_league',
    'UEFA-Europa League':      'soccer_uefa_europa_league',
    'UEFA-Conference League':  'soccer_uefa_europa_conference_league',
    'CONMEBOL-Libertadores':   'soccer_conmebol_libertadores',
    'CONMEBOL-Sudamericana':   'soccer_conmebol_sudamericana',
    # FIFA (selecciones)
    'FIFA-World Cup Qual CONMEBOL': 'soccer_conmebol_world_cup_qualifying',
    'FIFA-World Cup Qual UEFA':     'soccer_uefa_european_championship_qualification',
}

# EV minimo por tipo de liga
EV_ELITE   = 0.03   # 3% para ligas elite
EV_REGULAR = 0.04   # 4% para ligas menores (mas estricto por menos datos)

BASKETBALL_LEAGUES = {'NBA': 'basketball_nba', 'Euroleague': 'basketball_euroleague'}
TENNIS_LEAGUES     = {'ATP': 'tennis_atp', 'WTA': 'tennis_wta'}

# ==========================================
# RISK ENGINE
# ==========================================
# ==========================================
# TIKTOK (Content Posting API v2)
# ==========================================
TIKTOK_CLIENT_KEY    = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
TIKTOK_ACCESS_TOKEN  = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_REFRESH_TOKEN = os.getenv("TIKTOK_REFRESH_TOKEN", "")
TIKTOK_ENABLED       = os.getenv("TIKTOK_ENABLED", "false").lower() == "true"

# ==========================================
# RISK ENGINE
# ==========================================
BANKROLL_INICIAL    = 1_000_000
BASE_KELLY_FRACTION = 0.25
MAX_STAKE_PERCENT   = 0.05

# ==========================================
# CALIBRACIÓN DEL MODELO
# ==========================================
# Win Rate histórico móvil (se actualiza desde SQLite en producción).
# Valor inicial conservador basado en 20 picks resueltos (12W/8L).
ROLLING_WIN_RATE = 0.60

# ==========================================
# FILTROS DEL MODELO (v2 — calibrados)
# ==========================================
# EV se calcula SOBRE la probabilidad calibrada, no la del modelo crudo.
# Umbral bajado a 5%: la calibración ya penaliza el edge; exigir 10% crudo
# era rechazar picks válidos mientras aceptaba falsos positivos altos.
MIN_EV_THRESHOLD = 0.05    # EV mínimo post-calibración
MIN_PROBABILITY  = 0.62    # Prob. mínima POST-calibración
# MIN_ODDS ahora lo calcula RollingOddsFilter dinámicamente.
# Este valor es el HARD FLOOR de respaldo (nunca apostar debajo de aquí).
MIN_ODDS         = 1.65    # piso absoluto (antes 1.40 — era la causa directa del -8.7% yield)

# ==========================================
# MERCADOS HABILITADOS
# ==========================================
ENABLED_MARKETS = {
    "1X2":        True,
    "OVER_UNDER": True,
    "BTTS":       True,
    "BANKER":     True,
}

# Lineas de Over/Under a evaluar
OVER_UNDER_LINES = [1.5, 2.5, 3.5]

# ==========================================
# CANAL GRATUITO
# ==========================================
FREE_CHANNEL_MAX_PICKS_PER_DAY = 5
FREE_CHANNEL_MIN_EV             = 0.05

# ==========================================
# PERSONALIZACION
# ==========================================
BOT_NAME        = "Quant Signals"
BOT_DESCRIPTION = "Sistema cuantitativo de analisis deportivo"

# ==========================================
# DATOS DE PAGO (para el flujo de suscripcion)
# ==========================================
PRECIO_SUSCRIPCION = os.getenv("PRECIO_SUSCRIPCION", "$50.000 COP/mes")
NEQUI_NUMERO       = os.getenv("NEQUI_NUMERO",       "")
DAVIPLATA_NUMERO   = os.getenv("DAVIPLATA_NUMERO",   "")
BANCOLOMBIA_CUENTA = os.getenv("BANCOLOMBIA_CUENTA", "")
