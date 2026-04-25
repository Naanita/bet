# modules/risk.py — v2
import math
import sqlite3
import os
import config


def get_rolling_win_rate(n_last: int = 50) -> tuple[float, int]:
    """
    Lee el Win Rate y el conteo de picks resueltos desde SQLite.

    Returns:
        (win_rate, resolved_count)  —  win_rate en [0,1], resolved_count entero
    """
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "quant_history.db"
    )
    try:
        con  = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT result FROM bets WHERE result IS NOT NULL ORDER BY id DESC LIMIT ?",
            (n_last,),
        ).fetchall()
        con.close()
    except Exception:
        return config.ROLLING_WIN_RATE, 0

    if not rows:
        return config.ROLLING_WIN_RATE, 0

    wins = sum(1 for (r,) in rows if r == 1)
    n    = len(rows)
    return round(wins / n, 4), n


class RollingOddsFilter:
    """
    Filtro de cuota mínima dinámica.

    Garantiza que el Break-Even Win Rate se mantenga automáticamente
    entre 3%–5% por debajo del Win Rate histórico móvil, protegiendo
    la banca cuando el modelo sobreestima el edge.

    Matemática:
        break_even_wr  ≤  rolling_wr − safety_margin
        1 / min_odds   ≤  rolling_wr − safety_margin
        min_odds       ≥  1 / (rolling_wr − safety_margin)

    Ejemplo con WR=60%, margen=5%:
        min_odds ≥ 1 / 0.55 ≈ 1.82
        → rechaza automáticamente cuotas ≤ 1.82 (las que generan pérdida con 60% WR)

    HARD_MIN_ODDS es el piso absoluto independiente del WR histórico.
    """

    SAFETY_MARGIN = 0.05   # buffer preferido (5 pp)
    HARD_MIN_ODDS = 1.65   # piso absoluto

    @classmethod
    def min_odds(
        cls,
        rolling_win_rate: float | None = None,
        safety_margin: float = SAFETY_MARGIN,
    ) -> float:
        """
        Cuota mínima de entrada para el ciclo actual.

        Args:
            rolling_win_rate: WR histórico móvil (0–1). Si None, lee de SQLite.
            safety_margin:    buffer de seguridad (default 5%)
        """
        if rolling_win_rate is None:
            rolling_win_rate, _ = get_rolling_win_rate()

        effective_be = rolling_win_rate - safety_margin
        if effective_be <= 0.05:
            return cls.HARD_MIN_ODDS

        computed = 1.0 / effective_be
        return round(max(computed, cls.HARD_MIN_ODDS), 2)

    @classmethod
    def is_acceptable(
        cls,
        odds: float,
        rolling_win_rate: float | None = None,
        safety_margin: float = SAFETY_MARGIN,
    ) -> bool:
        """True si las cuotas superan el umbral dinámico."""
        return odds >= cls.min_odds(rolling_win_rate, safety_margin)

    @classmethod
    def breakeven_at(cls, odds: float) -> float:
        """Break-even Win Rate requerido para una cuota dada (en %)."""
        return round(100.0 / odds, 2) if odds > 1.0 else 100.0


class RiskEngine:
    # ── Calibración ───────────────────────────────────────────────────
    # Fracción máxima del edge del modelo a retener (a n=∞).
    # 0.35 = conservador (recomendado con n < 200), 0.50 = neutro
    MODEL_EDGE_RETENTION = 0.35

    # ── Parlays ───────────────────────────────────────────────────────
    PARLAY_XG_DIFF_THRESHOLD = 1.2
    PARLAY_CORRELATION_BOOST = 1.15
    PARLAY_BOOKMAKER_PENALTY = 0.85
    PARLAY_MAX_PROB_CAP      = 0.95

    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def expected_value(probability: float, odds: float) -> float:
        """EV = (p × odds) − 1"""
        return (probability * odds) - 1.0

    # Prior para la escala Bayesiana de confianza.
    # Representa "cuántos picks resueltos equivale a confiar completamente
    # en el modelo desde el inicio". Con k=20, a n=20 picks solo retenemos
    # el 50% del edge_retention base; a n=100 retenemos el 83%.
    BAYESIAN_PRIOR_K = 20

    @staticmethod
    def calibrate_probability(
        p_model: float,
        market_odds: float,
        n_samples: int = 20,
        edge_retention: float = MODEL_EDGE_RETENTION,
    ) -> float:
        """
        Calibración Bayesiana del edge para eliminar falsos positivos de EV alto.

        Fórmula:
            confidence         = n / (n + k)          # escala 0→1 con el historial
            effective_retention = edge_retention × confidence
            p_cal              = p_market + edge × effective_retention

        Donde:
            edge    = p_model − p_market   (ventaja bruta del modelo)
            k       = BAYESIAN_PRIOR_K = 20 (prior equivalente a 20 picks)

        Comportamiento según historial:
            n=0  →  confidence=0.00  →  p_cal=p_market  →  EV=0  (modo ultra-conservador)
            n=20 →  confidence=0.50  →  retiene 17.5% del edge
            n=50 →  confidence=0.71  →  retiene 24.9% del edge
            n=100 → confidence=0.83  →  retiene 29.2% del edge
            n=∞   → confidence=1.00  →  retiene 35.0% del edge

        Efecto sobre el umbral de cuota mínima (p_raw=76%, n=20):
            odds=1.52 → p_cal=0.676 → EV=2.7%  → RECHAZADO (MIN_EV=5%) ✓
            odds=1.72 → p_cal=0.612 → EV=5.3%  → ACEPTADO                ✓
            odds=1.85 → p_cal=0.579 → EV=7.1%  → ACEPTADO                ✓

        A medida que crece n, el umbral de cuota mínima baja gradualmente,
        recompensando el historial sin exponerse desde el primer día.

        Args:
            p_model:        probabilidad bruta del modelo Poisson (0–1)
            market_odds:    cuota decimal de la casa (e.g. 1.52)
            n_samples:      picks resueltos en el histórico (≥0)
            edge_retention: fracción máxima del edge a retener a n=∞ (default 0.35)

        Returns:
            probabilidad calibrada en [p_market, p_model]
        """
        if market_odds <= 1.0:
            return p_model

        p_market = 1.0 / market_odds   # prob. implícita cruda (incluye vig)
        edge     = p_model - p_market

        if edge <= 0:
            return max(p_market, p_model)

        # Escala Bayesiana de confianza
        k          = RiskEngine.BAYESIAN_PRIOR_K
        confidence = n_samples / (n_samples + k)
        p_cal      = p_market + edge * edge_retention * confidence

        # Límites hard: nunca bajar del precio del mercado ni superar el modelo
        return round(max(p_market, min(p_model, p_cal)), 4)

    @staticmethod
    def calculate_kelly_stake(
        probability: float,
        odds: float,
        bankroll: float,
        fraction: float = config.BASE_KELLY_FRACTION,
    ) -> float:
        """
        Kelly Fraccional — stake óptimo en COP.

        stake = bankroll × min(kelly_pct × fraction, MAX_STAKE_PERCENT)
        donde kelly_pct = (b×p − q) / b

        Siempre pasar la probabilidad CALIBRADA, no la del modelo crudo.
        """
        q = 1.0 - probability
        b = odds - 1.0
        if b <= 0:
            return 0.0
        kelly_pct = (b * probability - q) / b
        if kelly_pct <= 0:
            return 0.0
        adj_kelly = min(kelly_pct * fraction, config.MAX_STAKE_PERCENT)
        return round(bankroll * adj_kelly, 2)

    @staticmethod
    def stake_level(stake_amount: float, bankroll: float,
                    max_stake_pct: float = 0.05) -> int:
        """
        Mapea el stake de Kelly a una escala 1-10 para display.
        1 = edge mínimo aceptable, 10 = stake máximo permitido.
        """
        max_stake = bankroll * max_stake_pct
        if max_stake <= 0 or stake_amount <= 0:
            return 1
        return max(1, min(10, round((stake_amount / max_stake) * 10)))

    @staticmethod
    def evaluate_correlated_parlay(
        home_xg: float, away_xg: float,
        home_team: str, away_team: str,
        match_odds: dict, true_probs: dict,
    ) -> dict | None:
        """
        Genera un Same Game Parlay si hay dominancia absoluta (>1.2 xG de diferencia).
        Cruza la victoria del favorito con el Over 2.5 Goles.
        """
        xg_diff = home_xg - away_xg

        if xg_diff >= RiskEngine.PARLAY_XG_DIFF_THRESHOLD:
            winner_market = "Gana Local"
            dominant      = home_team
        elif xg_diff <= -RiskEngine.PARLAY_XG_DIFF_THRESHOLD:
            winner_market = "Gana Visita"
            dominant      = away_team
        else:
            return None

        over_market = "Más de 2.5 Goles"

        if winner_market not in match_odds or over_market not in match_odds:
            return None

        odds_winner = match_odds[winner_market]
        odds_over   = match_odds[over_market]
        p_winner    = true_probs.get(winner_market, 0)
        p_over      = true_probs.get(over_market, 0)

        if p_winner > 0.50 and p_over > 0.50:
            raw_combined_prob = (p_winner * p_over) * RiskEngine.PARLAY_CORRELATION_BOOST
            combined_prob     = min(raw_combined_prob, RiskEngine.PARLAY_MAX_PROB_CAP)
            combined_odds     = (odds_winner * odds_over) * RiskEngine.PARLAY_BOOKMAKER_PENALTY
            ev                = RiskEngine.expected_value(combined_prob, combined_odds)

            if ev > config.MIN_EV_THRESHOLD:
                return {
                    "market":   f"{winner_market} + {over_market}",
                    "odds":     round(combined_odds, 2),
                    "prob":     combined_prob,
                    "ev":       ev,
                    "dominant": dominant,
                }
        return None
