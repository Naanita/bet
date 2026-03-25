# config.example.py — v4
# Copia este archivo como config.py y rellena con tus credenciales reales
# NO subas config.py al repositorio

import os

# ==========================================
# CREDENCIALES
# ==========================================
ODDS_API_KEY   = "TU_ODDS_API_KEY_AQUI"
TELEGRAM_TOKEN = "TU_TELEGRAM_BOT_TOKEN_AQUI"

# API-Football (gratuita: 100 req/dia)
# Registro: https://rapidapi.com/api-sports/api/api-football
API_FOOTBALL_KEY = None   # "TU_KEY_AQUI"

# ==========================================
# ZONA HORARIA
# ==========================================
TIMEZONE = "America/Bogota"

# ==========================================
# GOOGLE SHEETS
# ==========================================
GOOGLE_SHEET_NAME = "DB_BET"

# ==========================================
# CONTROL DE ACCESO
# ==========================================
ADMIN_CHAT_ID    = "TU_CHAT_ID_AQUI"
SUPPORT_CHAT_ID  = "TU_CHAT_ID_AQUI"
SUPPORT_USERNAME = "TU_USERNAME_SOPORTE"

# ==========================================
# CANALES DE TELEGRAM
# ==========================================
CHANNEL_ID_BANKERS = "TU_CHANNEL_ID_BANKERS"
CHANNEL_ID_FREE    = "TU_CHANNEL_ID_FREE"

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
BANKROLL_INICIAL    = 1000000
BASE_KELLY_FRACTION = 0.25
MAX_STAKE_PERCENT   = 0.05

# ==========================================
# FILTROS DEL MODELO (v4)
# ==========================================
MIN_EV_THRESHOLD = 0.03
MIN_PROBABILITY  = 0.65
MIN_ODDS         = 1.30

# ==========================================
# MERCADOS HABILITADOS
# ==========================================
ENABLED_MARKETS = {
    "1X2":        True,
    "OVER_UNDER": True,
    "BTTS":       True,
    "BANKER":     True,
}

OVER_UNDER_LINES = [1.5, 2.5, 3.5]

# ==========================================
# CANAL GRATUITO
# ==========================================
FREE_CHANNEL_MAX_PICKS_PER_DAY = 2
FREE_CHANNEL_MIN_EV             = 0.05

# ==========================================
# PERSONALIZACION
# ==========================================
BOT_NAME        = "Quant Signals"
BOT_DESCRIPTION = "Sistema cuantitativo de analisis deportivo"