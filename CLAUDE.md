# Quant System — Bot de Apuestas Deportivas

## Resumen del Proyecto

Sistema cuantitativo de generación de picks deportivos para el mercado colombiano (Rushbet). Calcula valor esperado (EV) usando modelos matemáticos y difunde picks por Telegram (canal premium y gratuito).

## Arquitectura General

```
main.py (Telegram bot)
    └── pipeline_v5.py (orquestador principal)
            ├── rushbet_scraper.py      → scraping de odds via Kambi API
            ├── data.py                 → xG desde Understat/FBref/ClubElo
            ├── advanced_model.py       → Poisson avanzado (forma, lesiones, H2H)
            ├── kambi_consensus.py      → probabilidad implícita del mercado
            ├── risk.py                 → Kelly Criterion + validación EV
            ├── montecarlo.py           → simulación de riesgo (5,000 escenarios)
            ├── injuries_engine.py      → lesiones/suspensiones (API-Football)
            ├── fbref_engine.py         → corners/tarjetas (FBref)
            └── tracking.py / sheets_db.py → logging (SQLite + Google Sheets)
```

## Módulos Clave

| Archivo | Propósito |
|---------|-----------|
| `main.py` | Entry point — bot de Telegram, comandos, suscripciones |
| `config.py` | Parámetros globales, credenciales, ligas habilitadas |
| `pipeline_v5.py` | Pipeline principal (reemplaza v4 que es legacy) |
| `model.py` | Poisson básico + MarketConsensusModel (elimina vig) |
| `advanced_model.py` | Poisson avanzado con forma (±30%), lesiones, H2H |
| `kambi_consensus.py` | Infiere lambda desde odds Over/Under via solver numérico |
| `risk.py` | EV, Kelly fraccionado (25%), validación de apuestas |
| `rushbet_scraper.py` | Scraping Kambi API de Rushbet |
| `odds_api.py` | TheOddsAPI (line shopping, opcional) |
| `arbitrage.py` | Detección de surebets |
| `sheets_db.py` | Google Sheets como base de datos cloud |
| `free_channel.py` | Lógica del canal Telegram gratuito |
| `image_generator.py` | Genera imágenes de picks (Pillow) |
| `balldontlie_engine.py` | Stats NBA (API gratuita) |
| `nba_data.py` | Jugadores en racha NBA |

## Parámetros de Configuración (config.py)

```python
BANKROLL_INICIAL = 1_000_000  # COP (~$250 USD)
BASE_KELLY_FRACTION = 0.25    # Kelly conservador
MAX_STAKE_PERCENT = 0.05      # Máx 5% por apuesta
MIN_EV_THRESHOLD = 0.10       # Mínimo 10% EV
MIN_PROBABILITY = 0.72        # Mínimo 72% de confianza
MIN_ODDS = 1.40               # Evita favoritos extremos
```

## Flujo de Datos

```
Rushbet (Kambi API)
    ↓ scraping
Odds del partido
    ↓
¿Liga elite? (EPL, LaLiga, SerieA, Bundesliga, Ligue1)
    ├── Sí → AdvancedPoissonModel (xG de Understat + FBref + lesiones)
    └── No → KambiConsensus (lambda inferida desde O/U odds)
    ↓
Cálculo EV = (prob_modelo × odds) - 1
    ↓
Filtros: EV ≥ 10%, prob ≥ 72%, odds ≥ 1.40
    ↓
Kelly Criterion → stake = bankroll × 0.25 × kelly_pct (cap 5%)
    ↓
Monte Carlo (5,000 escenarios) → valida drawdown ≤ 15%
    ↓
Broadcast Telegram + log Google Sheets + SQLite
```

## Deportes y Mercados

- **Fútbol**: 25+ ligas (soccer), mercados: 1X2, O/U 1.5/2.5/3.5, BTTS, Hándicap Asiático, Corners
- **Basketball**: NBA, Euroleague
- **Tenis**: ATP, WTA

## Stack Tecnológico

- **Python 3.x** con venv en `./venv/`
- **Telegram**: python-telegram-bot 21.5
- **Scraping**: playwright, requests
- **Datos**: pandas, numpy, scipy, soccerdata
- **APIs**: Understat, FBref, ClubElo, API-Football (100 req/día gratis), Ball Don't Lie (NBA)
- **DB**: SQLite (`data/quant_history.db`) + Google Sheets (`credentials.json`)
- **Imágenes**: Pillow

## Entorno de Ejecución

- Siempre usar `./venv/Scripts/python.exe` (no el Python del sistema)
- Variables de entorno en `.env` (ver `.env.example`)
- Credenciales Google Sheets en `credentials.json`
- Logs en `bot.log`

## Modelo de Negocio

- **Canal gratuito**: 2 mejores picks/día (EV mínimo 5%)
- **Canal premium**: Todos los picks, análisis completo, stake recomendado
- **Precio**: $50,000 COP/mes
- **Pagos**: Nequi, DaviPlata, Bancolombia
- **Gestión suscripciones**: Google Sheets (hoja `Usuarios_Premium`)

## Hojas Google Sheets

| Hoja | Contenido |
|------|-----------|
| `Picks_Hoy` | Picks del día actual |
| `Historial` | Todos los picks históricos con resultado |
| `Usuarios_Premium` | Lista de suscriptores activos |
| `Config` | Parámetros configurables en caliente |
| `Resumen_Mensual` | P&L mensual consolidado |

## Notas Importantes

- `pipeline_v4.py` es legacy — NO modificar, usar `pipeline_v5.py`
- KambiConsensus usa ratios de goles calibrados para 25+ ligas
- El scraper normaliza nombres de equipos para match con Understat/FBref
- Monte Carlo corre ANTES de publicar — si drawdown > 15% el pick se descarta
- La lógica de canal gratuito está en `free_channel.py`, NO en `main.py`
