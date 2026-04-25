# modules/parlay_engine.py
# Motor de apuestas combinadas (parlays / acumuladores)
#
# Genera combinadas de 2 y 3 patas a partir de los picks individuales del pipeline.
# Reglas:
#   - Cada pata debe ser de un partido DISTINTO (sin correlación directa)
#   - Probabilidad de cada pata >= MIN_LEG_PROB
#   - Solo el pick de mayor prob por partido (evita over-fitting al mismo juego)
#   - EV combinado >= MIN_PARLAY_EV (post-penalización de casa)
#   - Máximo MAX_LEGS patas para mantener probabilidad realista

import logging
from itertools import combinations

logger = logging.getLogger(__name__)

# ── Parámetros ────────────────────────────────────────────────────────────────
# La casa aplica un margen extra sobre el producto de cuotas individuales
PARLAY_BOOK_PENALTY = 0.92   # ~8% descuento sobre cuota combinada bruta
MIN_PARLAY_EV       = 0.10   # EV mínimo para publicar una combinada (10%)
MIN_LEG_PROB        = 0.68   # Prob mínima de cada pata (>68% de confianza)
MIN_LEG_ODDS        = 1.30   # Cuota mínima por pata (evita extremos no-value)
MAX_LEGS            = 3      # Máximo de patas
MAX_PARLAYS_OUTPUT  = 6      # Cuántas combinadas publicar como máximo


def _game_key(pick: dict) -> str:
    return f"{pick['home']} vs {pick['away']}"


def _kelly_stake_parlay(prob: float, odds: float, bankroll: float) -> float:
    """Kelly fraccional conservador para parlays (fracción 0.15, cap 2%)."""
    b = odds - 1.0
    if b <= 0:
        return 0.0
    kelly_pct = (b * prob - (1.0 - prob)) / b
    if kelly_pct <= 0:
        return 0.0
    # Fracción más conservadora que singles (0.15 vs 0.25)
    adj = min(kelly_pct * 0.15, 0.02)
    return round(bankroll * adj, 2)


def generate_parlays(picks: list, current_bankroll: float = 1_000_000) -> list:
    """
    Genera apuestas combinadas de 2 y 3 patas.

    Args:
        picks:            Lista de picks individuales del pipeline.
        current_bankroll: Bankroll actual para calcular stake.

    Returns:
        Lista de dicts con la misma estructura que picks individuales.
        Cada dict incluye 'is_parlay': True y 'legs': lista de patas.
    """
    # 1. Filtrar patas elegibles: prob alta, cuota mínima, no es parlay previo
    eligible = [
        p for p in picks
        if (p.get("prob", 0) / 100) >= MIN_LEG_PROB
        and p.get("odds", 0) >= MIN_LEG_ODDS
        and not p.get("is_parlay", False)
    ]

    if len(eligible) < 2:
        return []

    # 2. Un solo pick por partido: el de mayor probabilidad
    best_per_game: dict[str, dict] = {}
    for p in eligible:
        gk = _game_key(p)
        if gk not in best_per_game or p["prob"] > best_per_game[gk]["prob"]:
            best_per_game[gk] = p

    # Ordenar por prob desc y tomar los 12 mejores candidatos
    candidates = sorted(best_per_game.values(), key=lambda x: x["prob"], reverse=True)[:12]

    if len(candidates) < 2:
        return []

    parlays: list[dict] = []

    for n_legs in range(2, min(MAX_LEGS + 1, len(candidates) + 1)):
        for combo in combinations(candidates, n_legs):
            # Probabilidad e odds combinados (eventos independientes)
            combined_prob  = 1.0
            combined_odds  = 1.0
            for leg in combo:
                combined_prob  *= leg["prob"] / 100.0
                combined_odds  *= leg["odds"]

            # Penalización de la casa sobre la cuota combinada
            combined_odds_adj = combined_odds * PARLAY_BOOK_PENALTY

            ev = (combined_prob * combined_odds_adj) - 1.0
            if ev < MIN_PARLAY_EV:
                continue

            # Hora del partido más temprano de la combinada
            times = sorted(l.get("time", "99:99") for l in combo)

            # Descripción legible de cada pata
            legs_desc = " ➕ ".join(
                f"{l['home'].split()[0]} vs {l['away'].split()[0]} "
                f"[{l['market']}] @{l['odds']}"
                for l in combo
            )

            # Nivel de confianza de la combinada
            if combined_prob >= 0.50:   confidence = "🔥 MUY ALTA"
            elif combined_prob >= 0.40: confidence = "✅ ALTA"
            else:                       confidence = "🟡 MEDIA-ALTA"

            stake = _kelly_stake_parlay(combined_prob, combined_odds_adj, current_bankroll)

            parlays.append({
                "sport":        "🎰",
                "home":         combo[0]["home"],
                "away":         combo[0]["away"],
                "time":         times[0],
                "date":         combo[0].get("date", ""),
                "market":       f"COMBINADA {n_legs} PATAS",
                "market_key":   f"parlay_{n_legs}",
                "odds":         round(combined_odds_adj, 2),
                "prob":         round(combined_prob * 100, 1),
                "prob_raw":     round(combined_prob * 100, 1),
                "ev":           round(ev * 100, 1),
                "stake_amount": stake,
                "confidence":   confidence,
                "source":       "rushbet",
                "event_id":     combo[0].get("event_id"),
                "outcome_id":   "",
                "is_parlay":    True,
                "n_legs":       n_legs,
                "legs":         list(combo),
                "reason": (
                    f"Combinada {n_legs} patas | "
                    f"Prob combinada: {combined_prob*100:.1f}% | "
                    f"Cuota neta: {combined_odds_adj:.2f} | "
                    f"EV: +{ev*100:.1f}% | "
                    f"Patas: {legs_desc}"
                ),
            })

    # Ordenar por EV desc y limitar salida
    parlays.sort(key=lambda x: x["ev"], reverse=True)
    return parlays[:MAX_PARLAYS_OUTPUT]
