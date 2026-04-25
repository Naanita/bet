# modules/advanced_model.py v2
# Modelos de probabilidad calibrados correctamente

import numpy as np
from scipy.stats import poisson
import logging

logger = logging.getLogger(__name__)


class AdvancedPoissonModel:
    HOME_ADVANTAGE = 0.25

    def __init__(self,
                 base_home_xg: float,
                 base_away_xg: float,
                 home_form_score: float = 0.5,
                 away_form_score: float = 0.5,
                 home_injury_impact: float = 1.0,
                 away_injury_impact: float = 1.0,
                 h2h_data: dict = None,
                 apply_home_advantage: bool = True):
        """
        Args:
            apply_home_advantage: True cuando base_xg viene de datos reales (Understat/FBref).
                                  False cuando viene de KambiConsensus — en ese caso split_lambda()
                                  ya incorporó la ventaja de local vía el ratio histórico de la liga,
                                  y sumar HOME_ADVANTAGE×0.5 sería double-counting.
        """
        home_form_adj = 1.0 + (home_form_score - 0.5) * 0.30
        away_form_adj = 1.0 + (away_form_score - 0.5) * 0.30

        adj_home_xg = base_home_xg * home_form_adj * home_injury_impact
        adj_away_xg = base_away_xg * away_form_adj * away_injury_impact

        if h2h_data and h2h_data.get("total_games", 0) >= 3:
            h2h_avg = h2h_data.get("avg_goals", 2.5)
            total   = (adj_home_xg + adj_away_xg) * 0.8 + h2h_avg * 0.2
            ratio   = total / max(adj_home_xg + adj_away_xg, 0.01)
            adj_home_xg *= ratio
            adj_away_xg *= ratio

        home_adv = (self.HOME_ADVANTAGE * 0.5) if apply_home_advantage else 0.0
        self.lambda_home = max(0.3, adj_home_xg + home_adv)
        self.lambda_away = max(0.3, adj_away_xg)
        self.h2h = h2h_data or {}

    def _score_matrix(self, max_goals: int = 8) -> np.ndarray:
        """Matriz de probabilidades de marcador. Vectorizado con np.outer (10-50x más rápido)."""
        goals = np.arange(max_goals + 1)
        return np.outer(
            poisson.pmf(goals, self.lambda_home),
            poisson.pmf(goals, self.lambda_away),
        )

    def get_1x2_probs(self) -> dict:
        matrix   = self._score_matrix()
        home_win = float(np.sum(np.tril(matrix, -1)))
        draw     = float(np.sum(np.diag(matrix)))
        away_win = float(np.sum(np.triu(matrix, 1)))
        total    = home_win + draw + away_win
        return {
            "Gana Local":  round(home_win / total, 4),
            "Empate":      round(draw     / total, 4),
            "Gana Visita": round(away_win / total, 4),
        }

    def get_double_chance_probs(self) -> dict:
        p = self.get_1x2_probs()
        return {
            "1X": round(p["Gana Local"] + p["Empate"],     4),
            "X2": round(p["Empate"]     + p["Gana Visita"], 4),
            "12": round(p["Gana Local"] + p["Gana Visita"], 4),
        }

    def get_over_under_probs(self, line: float = 2.5) -> dict:
        matrix  = self._score_matrix()
        i_idx, j_idx = np.mgrid[0:matrix.shape[0], 0:matrix.shape[1]]
        over = float(matrix[i_idx + j_idx > line].sum())
        return {
            f"Mas de {line}":   round(over,       4),
            f"Menos de {line}": round(1.0 - over, 4),
        }

    def get_btts_prob(self) -> dict:
        p_home = 1.0 - self._prob_goals(self.lambda_home, 0)
        p_away = 1.0 - self._prob_goals(self.lambda_away, 0)
        yes    = p_home * p_away
        return {
            "Ambos Anotan: Si": round(yes,       4),
            "Ambos Anotan: No": round(1.0 - yes, 4),
        }

    def get_asian_handicap_probs(self, handicap: float = -0.5) -> dict:
        matrix     = self._score_matrix()
        home_cover = 0.0
        away_cover = 0.0
        push       = 0.0
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                diff = (i - j) + handicap
                p    = matrix[i][j]
                if diff > 0:   home_cover += p
                elif diff < 0: away_cover += p
                else:          push       += p
        total    = home_cover + away_cover + push
        hc       = (home_cover + push / 2) / total
        ac       = (away_cover + push / 2) / total
        # Nombres alineados con el scraper: "AH Local -0.5" / "AH Visita +0.5"
        h_sign   = f"{handicap:+.1f}"
        a_sign   = f"{-handicap:+.1f}"
        h_label  = f"AH Local {h_sign}"
        a_label  = f"AH Visita {a_sign}"
        return {h_label: round(hc, 4), a_label: round(ac, 4)}

    def get_halftime_probs(self) -> dict:
        ht_model = AdvancedPoissonModel(
            base_home_xg=self.lambda_home * 0.42,
            base_away_xg=self.lambda_away * 0.42,
        )
        p = ht_model.get_1x2_probs()
        return {
            "HT Gana Local":  p["Gana Local"],
            "HT Empate":      p["Empate"],
            "HT Gana Visita": p["Gana Visita"],
        }

    def get_team_goals_probs(self) -> dict:
        """P(equipo anota >= n goles) usando Poisson individual por equipo."""
        result = {}
        for prefix, lam in [("Local", self.lambda_home), ("Visita", self.lambda_away)]:
            for line in (0.5, 1.5, 2.5):
                p_over  = 1.0 - poisson.cdf(int(line), lam)
                p_under = poisson.cdf(int(line), lam)
                result[f"{prefix}: Mas de {line} Goles"]   = round(p_over,  4)
                result[f"{prefix}: Menos de {line} Goles"] = round(p_under, 4)
        return result

    def get_all_markets(self) -> dict:
        markets = {}
        markets.update(self.get_1x2_probs())
        markets.update(self.get_double_chance_probs())
        markets.update(self.get_over_under_probs(0.5))
        markets.update(self.get_over_under_probs(1.5))
        markets.update(self.get_over_under_probs(2.5))
        markets.update(self.get_over_under_probs(3.5))
        markets.update(self.get_over_under_probs(4.5))
        markets.update(self.get_btts_prob())
        markets.update(self.get_asian_handicap_probs(-0.5))
        markets.update(self.get_asian_handicap_probs(+0.5))
        markets.update(self.get_asian_handicap_probs(-1.5))
        markets.update(self.get_asian_handicap_probs(+1.5))
        markets.update(self.get_halftime_probs())
        markets.update(self.get_team_goals_probs())
        return markets


class CornerModel:
    """Modelo de corners calibrado con promedios reales de ligas."""

    # Promedios TOTALES por partido (ambos equipos) — fuente: Understat/FBref historico
    LEAGUE_AVERAGES = {
        "ENG-Premier League": 10.1,
        "ESP-La Liga":         9.7,
        "ITA-Serie A":         9.4,
        "GER-Bundesliga":      9.8,
        "FRA-Ligue 1":         9.2,
        "DEFAULT":             9.8,
    }

    def __init__(self, home_corners_avg: float = 5.0, away_corners_avg: float = 5.0,
                 league: str = "DEFAULT"):
        league_avg = self.LEAGUE_AVERAGES.get(league, self.LEAGUE_AVERAGES["DEFAULT"])
        # Ponderar 60% liga, 40% datos del partido
        self.lambda_corners = league_avg * 0.6 + (home_corners_avg + away_corners_avg) * 0.4
        self.lambda_corners = max(7.0, min(self.lambda_corners, 13.0))

    def get_over_under_probs(self, line: float = 9.5) -> dict:
        over  = 1.0 - poisson.cdf(int(line), self.lambda_corners)
        under = poisson.cdf(int(line), self.lambda_corners)
        return {
            f"Corners Mas de {line}":   round(over,  4),
            f"Corners Menos de {line}": round(under, 4),
        }


class CardModel:
    """
    Modelo de tarjetas calibrado con promedios REALES de ligas.
    Usa estadisticas totales por partido (ambos equipos combinados).

    Promedios reales verificados:
    - Premier League: ~3.5 tarjetas/partido total
    - La Liga:        ~4.2 tarjetas/partido total
    - Serie A:        ~4.0 tarjetas/partido total
    - Bundesliga:     ~3.4 tarjetas/partido total
    - Ligue 1:        ~3.8 tarjetas/partido total

    Probabilidades calibradas:
    - +3.5 tarjetas: ~45-55% segun liga (NO 75%+)
    - +4.5 tarjetas: ~25-35% segun liga
    """

    # Promedios TOTALES por partido (ambos equipos) — valores calibrados con datos reales
    LEAGUE_CARD_AVERAGES = {
        "ENG-Premier League": 3.5,
        "ESP-La Liga":        4.2,
        "ITA-Serie A":        4.0,
        "GER-Bundesliga":     3.4,
        "FRA-Ligue 1":        3.8,
        "DEFAULT":            3.8,
    }

    def __init__(self,
                 total_cards_avg: float = 3.8,
                 league: str = "DEFAULT",
                 rivalry_factor: float = 1.0):
        """
        total_cards_avg: promedio TOTAL de tarjetas por partido (ambos equipos)
        rivalry_factor: 1.0=normal, 1.15=derbi/rivalidad
        """
        league_avg = self.LEAGUE_CARD_AVERAGES.get(league, self.LEAGUE_CARD_AVERAGES["DEFAULT"])

        # 70% peso al promedio de la liga (mas fiable), 30% al dato especifico
        self.lambda_cards = (league_avg * 0.7 + total_cards_avg * 0.3) * rivalry_factor
        # Clamp a rango realista
        self.lambda_cards = max(2.5, min(self.lambda_cards, 5.5))

    def get_over_under_probs(self, line: float = 3.5) -> dict:
        over  = 1.0 - poisson.cdf(int(line), self.lambda_cards)
        under = poisson.cdf(int(line), self.lambda_cards)
        return {
            f"Tarjetas Mas de {line}":   round(over,  4),
            f"Tarjetas Menos de {line}": round(under, 4),
        }


class MatchAnalyzer:
    """Motor de analisis completo de un partido."""

    def __init__(self,
                 home_team: str, away_team: str,
                 base_home_xg: float, base_away_xg: float,
                 league: str = "DEFAULT",
                 home_form: dict = None, away_form: dict = None,
                 home_corner_stats: dict = None, away_corner_stats: dict = None,
                 home_card_stats: dict = None,   away_card_stats: dict = None,
                 injury_impact_home: float = 1.0, injury_impact_away: float = 1.0,
                 h2h_data: dict = None):

        self.home_team = home_team
        self.away_team = away_team
        self.league    = league
        self.h2h       = h2h_data or {}

        home_form = home_form or {}
        away_form = away_form or {}

        self.poisson = AdvancedPoissonModel(
            base_home_xg=base_home_xg,
            base_away_xg=base_away_xg,
            home_form_score=home_form.get("form_score", 0.5),
            away_form_score=away_form.get("form_score", 0.5),
            home_injury_impact=injury_impact_home,
            away_injury_impact=injury_impact_away,
            h2h_data=h2h_data,
        )

        # Corners — suma de ambos equipos
        hca = (home_corner_stats or {}).get("corners_for_avg", 5.0)
        aca = (away_corner_stats or {}).get("corners_for_avg", 5.0)
        self.corners = CornerModel(
            home_corners_avg=hca,
            away_corners_avg=aca,
            league=league,
        )

        # Tarjetas — usar total de la liga como base
        # total_cards_avg ya es el TOTAL del partido (no por equipo)
        hcards_total = (home_card_stats or {}).get("total_cards_avg", 2.0)
        acards_total = (away_card_stats or {}).get("total_cards_avg", 2.0)
        # Estos son por equipo, sumarlos para el total del partido
        total_cards = hcards_total + acards_total

        self.cards = CardModel(
            total_cards_avg=total_cards,
            league=league,
        )

    def get_all_probabilities(self) -> dict:
        probs = {}
        probs.update(self.poisson.get_all_markets())
        probs.update(self.corners.get_over_under_probs(9.5))
        probs.update(self.corners.get_over_under_probs(10.5))
        probs.update(self.cards.get_over_under_probs(3.5))
        probs.update(self.cards.get_over_under_probs(4.5))
        return probs

    def get_confidence_score(self, market: str, prob: float) -> str:
        base = prob
        if self.h2h.get("total_games", 0) >= 3:
            if "Mas de 2.5" in market:
                base = base * 0.7 + self.h2h.get("over25_pct", 0.5) * 0.3
            elif "Ambos Anotan" in market:
                base = base * 0.7 + self.h2h.get("btts_pct", 0.5) * 0.3
        if base >= 0.75:   return "🔥 MUY ALTA"
        elif base >= 0.65: return "✅ ALTA"
        elif base >= 0.60: return "🟡 MEDIA-ALTA"
        else:              return "⚪ MEDIA"

    def build_analysis_text(self, market: str, prob: float, odds: float, ev: float) -> str:
        implied    = (1 / odds) * 100
        confidence = self.get_confidence_score(market, prob)
        parts      = [f"{confidence} | Implicita: {implied:.1f}% vs Real: {prob*100:.1f}%"]

        if self.h2h.get("total_games", 0) >= 3:
            if "Mas de 2.5" in market:
                h2h_pct = self.h2h.get("over25_pct", 0) * 100
                parts.append(f"H2H: Over2.5 en {h2h_pct:.0f}% de {self.h2h['total_games']} partidos")
            elif "Ambos Anotan" in market:
                h2h_pct = self.h2h.get("btts_pct", 0) * 100
                parts.append(f"H2H: BTTS en {h2h_pct:.0f}% de {self.h2h['total_games']} partidos")

        parts.append(f"EV: +{ev:.1f}%")
        return " | ".join(parts)


# ─────────────────────────────────────────────
# Test de calibracion
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Test de calibracion CardModel ===\n")
    for league, avg in [
        ("ENG-Premier League", 3.5),
        ("ESP-La Liga",        4.2),
        ("ITA-Serie A",        4.0),
        ("GER-Bundesliga",     3.4),
    ]:
        model = CardModel(total_cards_avg=avg, league=league)
        probs = model.get_over_under_probs(3.5)
        probs2 = model.get_over_under_probs(4.5)
        print(f"{league:25} lambda={model.lambda_cards:.2f} | "
              f"+3.5: {probs[f'Tarjetas Mas de 3.5']*100:.1f}% | "
              f"+4.5: {probs2[f'Tarjetas Mas de 4.5']*100:.1f}%")

    print("\n=== Test CornerModel ===\n")
    for league, avg in [
        ("ENG-Premier League", 10.1),
        ("ESP-La Liga",         9.7),
    ]:
        model = CornerModel(league=league)
        probs = model.get_over_under_probs(9.5)
        print(f"{league:25} lambda={model.lambda_corners:.2f} | "
              f"+9.5: {probs[f'Corners Mas de 9.5']*100:.1f}%")