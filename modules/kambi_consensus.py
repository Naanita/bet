# modules/kambi_consensus.py
# Modelo de consenso usando SOLO cuotas de Rushbet/Kambi
# Estrategia: inferir lambda Poisson desde la linea Over/Under
# y comparar contra los mercados 1X2/BTTS/DC para encontrar inconsistencias

import math
import logging
from scipy.stats import poisson
from scipy.optimize import brentq

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Promedios historicos por liga (goles/partido)
# Fuente: datos estadisticos de temporadas 2022-2025
# ─────────────────────────────────────────────
LEAGUE_GOAL_AVERAGES = {
    # Europa elite
    "ENG-Premier League":   {"home": 1.53, "away": 1.19},
    "ESP-La Liga":          {"home": 1.57, "away": 1.15},
    "ITA-Serie A":          {"home": 1.55, "away": 1.18},
    "GER-Bundesliga":       {"home": 1.76, "away": 1.36},
    "FRA-Ligue 1":          {"home": 1.44, "away": 1.10},
    # Europa secundaria
    "ENG-Championship":     {"home": 1.42, "away": 1.08},
    "ESP-La Liga 2":        {"home": 1.38, "away": 1.04},
    "ITA-Serie B":          {"home": 1.35, "away": 1.02},
    "GER-2 Bundesliga":     {"home": 1.54, "away": 1.18},
    "FRA-Ligue 2":          {"home": 1.32, "away": 1.00},
    "POR-Primeira Liga":    {"home": 1.48, "away": 1.12},
    "NED-Eredivisie":       {"home": 1.68, "away": 1.30},
    "BEL-First Division A": {"home": 1.52, "away": 1.15},
    "TUR-Super Lig":        {"home": 1.60, "away": 1.22},
    "SCO-Premiership":      {"home": 1.45, "away": 1.08},
    # America
    "BRA-Serie A":          {"home": 1.45, "away": 1.05},
    "ARG-Primera Division": {"home": 1.48, "away": 1.08},
    "COL-Liga BetPlay":     {"home": 1.42, "away": 1.00},
    "MEX-Liga MX":          {"home": 1.50, "away": 1.10},
    "USA-MLS":              {"home": 1.55, "away": 1.20},
    "CHI-Primera Division": {"home": 1.40, "away": 1.00},
    "URU-Primera Division": {"home": 1.44, "away": 1.06},
    # Copas
    "UEFA-Champions League":  {"home": 1.72, "away": 1.38},
    "UEFA-Europa League":     {"home": 1.58, "away": 1.22},
    "UEFA-Conference League": {"home": 1.50, "away": 1.15},
    "CONMEBOL-Libertadores":  {"home": 1.55, "away": 1.10},
    "DEFAULT":              {"home": 1.48, "away": 1.10},
}

# Vig tipico de Kambi por tipo de mercado
KAMBI_VIG = {
    "1x2":      0.055,   # ~5.5% en mercados 3-way
    "2way":     0.045,   # ~4.5% en mercados 2-way (OU, BTTS)
    "basketball": 0.050, # ~5.0% NBA/Euroliga
    "tennis":   0.040,   # ~4.0% tenis (2-way muy competitivo)
}


def remove_vig(odds_dict: dict) -> dict:
    """
    Elimina el margen del bookmaker de un grupo completo de cuotas.
    Retorna probabilidades 'justas' que suman exactamente 1.0.
    """
    implied = {k: 1 / v for k, v in odds_dict.items() if v and v > 1.0}
    total   = sum(implied.values())
    if total <= 0:
        return {}
    vig = total - 1.0
    fair = {k: v / total for k, v in implied.items()}
    logger.debug(f"Vig detectado: {vig*100:.2f}% | Mercados: {list(odds_dict.keys())}")
    return fair


def infer_lambda_from_ou(over_odds: float, under_odds: float, line: float = 2.5) -> float | None:
    """
    Infiere el lambda total esperado de goles a partir de la linea Over/Under.
    Resuelve: P(Poisson(lambda) > line) = fair_over_prob

    Esta es la tecnica de 'market-implied lambda':
    Si Rushbet pone Over 2.5 a 1.75, el mercado espera ~2.7 goles totales.
    """
    if not over_odds or not under_odds or over_odds <= 1.0 or under_odds <= 1.0:
        return None

    # Remover vig del mercado 2-way
    fair = remove_vig({"over": over_odds, "under": under_odds})
    if not fair:
        return None
    fair_over_prob = fair.get("over", 0.5)

    if fair_over_prob <= 0.01 or fair_over_prob >= 0.99:
        return None

    # Resolver numericamente: P(Poisson(lambda) > line) = fair_over_prob
    # P(X > 2.5) = 1 - P(X <= 2) = 1 - CDF(2)
    floor_line = int(line)

    def equation(lam):
        return (1.0 - poisson.cdf(floor_line, lam)) - fair_over_prob

    try:
        # Buscar lambda en [0.1, 15.0]
        lam = brentq(equation, 0.1, 15.0, xtol=1e-4)
        return round(lam, 3)
    except Exception:
        return None


def split_lambda(total_lambda: float, league: str = "DEFAULT") -> tuple[float, float]:
    """
    Divide el lambda total en home/away usando el ratio historico de la liga.
    Incluye ventaja de local.
    """
    avgs = LEAGUE_GOAL_AVERAGES.get(league, LEAGUE_GOAL_AVERAGES["DEFAULT"])
    total_avg  = avgs["home"] + avgs["away"]
    home_ratio = avgs["home"] / total_avg if total_avg > 0 else 0.575

    home_lambda = round(total_lambda * home_ratio, 3)
    away_lambda = round(total_lambda * (1 - home_ratio), 3)

    # Clamp a rangos realistas
    home_lambda = max(0.3, min(home_lambda, 4.5))
    away_lambda = max(0.3, min(away_lambda, 3.5))

    return home_lambda, away_lambda


def get_soccer_probs_from_rushbet(odds: dict, league: str = "DEFAULT") -> dict | None:
    """
    Genera probabilidades de todos los mercados usando SOLO las cuotas de Rushbet.

    Estrategia:
    1. Extrae lambda total desde la linea Over/Under 2.5 de Rushbet
    2. Divide en home/away con ratio historico de la liga
    3. Corre el modelo Poisson para obtener 1X2, BTTS, DC, etc.
    4. Esto es INDEPENDIENTE de las cuotas 1X2 de Rushbet → permite detectar EV

    Si no hay OU 2.5, usa el vig de 1X2 directamente como fallback.
    """
    from modules.advanced_model import AdvancedPoissonModel

    # Intento 1: inferir desde Over/Under 2.5 (mas preciso)
    over_25  = odds.get("Mas de 2.5")
    under_25 = odds.get("Menos de 2.5")

    if over_25 and under_25:
        total_lambda = infer_lambda_from_ou(over_25, under_25, line=2.5)
    else:
        total_lambda = None

    # Intento 2: si hay Over 1.5 o 3.5, usar como respaldo
    if total_lambda is None:
        for line, over_key, under_key in [
            (1.5, "Mas de 1.5", "Menos de 1.5"),
            (3.5, "Mas de 3.5", "Menos de 3.5"),
        ]:
            o = odds.get(over_key)
            u = odds.get(under_key)
            if o and u:
                total_lambda = infer_lambda_from_ou(o, u, line=line)
                if total_lambda:
                    break

    # Intento 3: inferir desde 1X2 con vig removal (menos preciso)
    if total_lambda is None:
        local  = odds.get("Gana Local")
        empate = odds.get("Empate")
        visita = odds.get("Gana Visita")
        if local and empate and visita:
            fair = remove_vig({"local": local, "empate": empate, "visita": visita})
            if fair:
                p_home = fair["local"]
                # Aproximar lambda desde probabilidad de victoria
                # P(home wins) ≈ 0.45 + 0.5*log(lambda_home/lambda_away)/3
                # Aproximacion simple: lambda promedio ~2.5 si hay empate probable
                total_lambda = 2.5  # fallback conservador
        else:
            return None

    if total_lambda is None or total_lambda < 0.5:
        return None

    home_lambda, away_lambda = split_lambda(total_lambda, league)

    model = AdvancedPoissonModel(
        base_home_xg=home_lambda,
        base_away_xg=away_lambda,
    )
    probs = model.get_all_markets()
    probs["_lambda_home"] = home_lambda
    probs["_lambda_away"] = away_lambda
    probs["_total_lambda"] = total_lambda
    return probs


def get_basketball_probs(odds: dict) -> dict | None:
    """
    Probabilidades para basquetbol:
    - Ganador del partido (2-way)
    - Totales de puntos (Over/Under)

    Sin modelo externo disponible, usa vig removal del propio Rushbet.
    El EV viene de comparar con el modelo de Ball Don't Lie cuando está disponible.
    """
    local  = odds.get("Gana Local")
    visita = odds.get("Gana Visita")

    if not local or not visita:
        return None

    fair = remove_vig({"Gana Local": local, "Gana Visita": visita})
    if not fair:
        return None

    probs = dict(fair)

    # Totales de puntos: buscar cualquier linea disponible dinamicamente
    over_keys  = [k for k in odds if k.startswith("Mas de ") and "pts" in k]
    under_keys = [k for k in odds if k.startswith("Menos de ") and "pts" in k]
    for over_key in over_keys:
        line_part  = over_key.replace("Mas de ", "").replace(" pts", "")
        under_key  = f"Menos de {line_part} pts"
        o = odds.get(over_key)
        u = odds.get(under_key)
        if o and u:
            fair_ou = remove_vig({over_key: o, under_key: u})
            probs.update(fair_ou)

    return probs


def get_tennis_probs(odds: dict) -> dict | None:
    """
    Probabilidades para tenis (2-way).
    Vig removal directo: mercado muy limpio en Kambi (~4%).
    """
    p1 = odds.get("Gana Local")   # jugador 1 (primero en el cartel)
    p2 = odds.get("Gana Visita")  # jugador 2

    if not p1 or not p2:
        return None

    return remove_vig({"Gana Local": p1, "Gana Visita": p2})


def evaluate_picks(game: dict, true_probs: dict, min_ev: float, min_prob: float,
                   min_odds: float, current_bankroll: float,
                   sport: str = "soccer") -> list:
    """
    Evalua todos los mercados disponibles de un partido y retorna picks con EV positivo.
    """
    from modules.risk import RiskEngine

    home    = game["home"]
    away    = game["away"]
    odds    = game.get("odds", {})
    time    = game.get("time", "")
    date    = game.get("date", "")
    ev_data = game.get("event_id")

    picks = []

    MARKET_ICONS = {
        "Gana Local":        "🏆",
        "Gana Visita":       "🏆",
        "Empate":            "🤝",
        "Mas de 2.5":        "🎯",
        "Menos de 2.5":      "🎯",
        "Mas de 1.5":        "🎯",
        "Menos de 1.5":      "🎯",
        "Mas de 3.5":        "🎯",
        "Menos de 3.5":      "🎯",
        "Ambos Anotan: Si":  "⚽",
        "Ambos Anotan: No":  "⚽",
        "1X":                "2️⃣",
        "X2":                "2️⃣",
        "12":                "2️⃣",
        "Corners Mas de 9.5":  "🚩",
        "Corners Mas de 10.5": "🚩",
        "Tarjetas Mas de 3.5": "🟨",
        "Tarjetas Mas de 4.5": "🟨",
    }

    SPORT_ICONS = {"soccer": "⚽", "basketball": "🏀", "tennis": "🎾"}
    sport_icon = SPORT_ICONS.get(sport, "⚽")

    for market, true_prob in true_probs.items():
        if market.startswith("_"):
            continue
        if true_prob < min_prob:
            continue

        rb_odds = odds.get(market)
        if not rb_odds or rb_odds < min_odds:
            continue

        ev = RiskEngine.expected_value(true_prob, rb_odds)
        if ev < min_ev:
            continue
        # EV >25% casi siempre indica error de modelo (ej. futsal, reservas con lambda mal inferido)
        if ev > 0.25:
            continue

        stake = RiskEngine.calculate_kelly_stake(true_prob, rb_odds, current_bankroll)
        if stake <= 0:
            continue

        outcome_id = str(odds.get(f"__oid_{market}", ""))

        if true_prob >= 0.75:   confidence = "🔥 MUY ALTA"
        elif true_prob >= 0.68: confidence = "✅ ALTA"
        elif true_prob >= 0.65: confidence = "🟡 MEDIA-ALTA"
        else:                   confidence = "⚪ MEDIA"

        lambda_info = ""
        if sport == "soccer":
            lh = true_probs.get("_lambda_home", 0)
            la = true_probs.get("_lambda_away", 0)
            if lh and la:
                lambda_info = f"Lambda inferido: {lh:.2f}H / {la:.2f}A | "

        picks.append({
            "sport":        sport_icon,
            "home":         home,
            "away":         away,
            "time":         time,
            "date":         date,
            "market":       market,
            "odds":         rb_odds,
            "prob":         round(true_prob * 100, 1),
            "ev":           round(ev * 100, 1),
            "stake_amount": stake,
            "confidence":   confidence,
            "source":       "rushbet",
            "event_id":     ev_data,
            "outcome_id":   outcome_id,
            "reason": (
                f"{lambda_info}"
                f"Prob real: {true_prob*100:.1f}% | "
                f"Implicita Rushbet: {(1/rb_odds)*100:.1f}% | "
                f"EV: +{ev*100:.1f}%"
            ),
        })

    return picks
