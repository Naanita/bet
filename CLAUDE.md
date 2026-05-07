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

## Principios Cuantitativos del Sistema

### Value Betting (+EV)
El objetivo NO es acertar quién gana sino encontrar cuotas donde la probabilidad real supera la implícita del bookmaker. Un pick solo se emite cuando `EV = (prob_modelo × cuota) - 1 > 0`. Las picks deben tener EV consistentemente positivo, no simplemente alta probabilidad.

### Closing Line Value (CLV)
Indicador definitivo de ventaja estructural a largo plazo. Se mide comparando la cuota obtenida vs. la cuota de cierre (justo antes del partido). CLV > 0 de forma sostenida demuestra que el modelo identifica valor real antes de que el mercado lo corrija. El sistema guarda `odds` y `closing_odds` en el historial para trackear CLV.

### Gestión de Banca (Bankroll Management)
- **Kelly Fraccionado (25%)**: el sistema usa `BASE_KELLY_FRACTION = 0.25` para reducir volatilidad
- **Flat Betting como ancla**: stake máximo del 5% del bankroll independientemente de la confianza
- **Escala de Stake 1–10**: derivada del Kelly — stakes altos (7-10) solo para ventajas evidentes (EV > 8%)
- El bankroll es capital separado de finanzas personales; debe poder perderse en su totalidad sin impacto vital

### Modelos Estadísticos
- **Poisson Bivariado**: modela goles de fútbol por equipo independientemente, luego suma para partido
- **Dixon-Coles**: ajuste de dependencia para marcadores bajos (0-0, 1-1) y ponderación temporal
- **Poisson avanzado**: incorpora xG (Understat), forma reciente (±30%), lesiones e historial H2H
- **Monte Carlo (5,000 escenarios)**: valida drawdown antes de publicar; descarta si drawdown > 15%
- **Normal Bivariada (NBA)**: predice puntajes usando eFG%, TOV%, rebotes ofensivos/defensivos

### Fuentes de Datos e Integración
- **Kambi API (Rushbet)**: fuente primaria de cuotas y mercados
- **Understat / FBref**: xG histórico por partido y jugador para ligas elite
- **API-Football**: lesiones y suspensiones en tiempo real (100 req/día gratis)
- **Ball Don't Lie**: stats NBA gratuita
- **Line Shopping**: comparar cuotas entre casas para siempre tomar el mejor precio disponible

### Principio de Validación de Mercados (crítico)
Las cuotas O/U de partido completo deben ser CONSISTENTES entre líneas. Si el lambda inferido desde O/U 2.5 predice P(>1.5) = 78% pero la cuota almacenada implica solo 60%, hay contaminación por mercado de equipo individual. El sistema valida esta consistencia en `kambi_consensus.py` y elimina cuotas inconsistentes (tolerancia ±15% en probabilidad).

## Mercados Disponibles en Kambi/Rushbet

### Fútbol — Actualmente capturados
| Mercado | Clave interna | Descripción |
|---------|--------------|-------------|
| 1X2 | `Gana Local`, `Empate`, `Gana Visita` | Resultado 90 min |
| Doble Oportunidad | `1X`, `X2`, `12` | Dos resultados posibles |
| O/U Goles Total | `Mas de X.5`, `Menos de X.5` | Líneas 0.5–5.5 |
| O/U Goles por Equipo | `Local: Mas de X.5 Goles` | Líneas 0.5–2.5 |
| BTTS | `Ambos Anotan: Si/No` | Ambos anotan |
| Hándicap Asiático | `AH Local ±X.5`, `AH Visita ∓X.5` | Líneas ±0.5, ±1.5 |
| Corners O/U | `Corners Mas/Menos de X.5` | Líneas 7.5–12.5 |
| Tarjetas O/U | `Tarjetas Mas/Menos de X.5` | Líneas 1.5–6.5 |
| Medio tiempo | `HT Gana Local`, `HT Empate`, `HT Gana Visita` | Resultado 45 min |

### Fútbol — Pendientes de implementar (Kambi los expone)
| Mercado | criterion_en Kambi | Valor para el modelo |
|---------|-------------------|---------------------|
| Marcador Exacto | `Correct Score` | Poisson predice directamente cada marcador |
| Descanso/Final (HT/FT) | `Half Time/Full Time` | 9 combinaciones, Poisson calcula cada una |
| O/U 1er Tiempo | `1st Half Total Goals` | Modelar como ~42% del lambda total |
| BTTS 1er Tiempo | `1st Half Both Teams To Score` | Poisson con λ×0.42 |
| Handicap Europeo | `European Handicap` | Ganador con ventaja de goles fija |
| Goles Exactos | `Exact Goals` | Suma marginal de la matriz Poisson |
| Sin Recibir Gol | `Clean Sheet` | P(local no recibe) = e^(-λ_away) |
| Gana de X a X | `Winning Margin` | Diferencia de goles en matriz Poisson |

### Basketball — Actualmente capturados
| Mercado | Clave interna |
|---------|--------------|
| Ganador | `Gana Local`, `Gana Visita` |
| Total Puntos O/U | `Mas/Menos de X pts` |

### Basketball — Pendientes de implementar
| Mercado | criterion_en Kambi |
|---------|-------------------|
| Hándicap (Spread) | `Handicap` / `Point Spread` |
| Total por Equipo | `Team Total Points` |
| Props de jugador | `Player Points`, `Player Rebounds`, `Player Assists` |
| Resultado por cuarto | `1st Quarter Result` / `1st Quarter Total` |
