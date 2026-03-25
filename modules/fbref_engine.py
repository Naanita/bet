# modules/fbref_engine.py v2
# FBref bloquea scraping con 403.
# Este modulo retorna valores neutrales para no romper el pipeline.
# La forma reciente se calcula via Understat (que si funciona).

import logging
logger = logging.getLogger(__name__)


class FBrefEngine:
    """
    Wrapper que retorna valores neutrales.
    FBref bloquea scraping automatizado (403).
    La forma reciente se obtiene via Understat en DataEngine.
    """

    def __init__(self, season: str = "2025"):
        self.season = season

    def get_team_form(self, team: str, league: str, n_games: int = 5) -> dict:
        """Retorna forma neutra — el ajuste real viene de Understat xG."""
        return {
            "wins": 0, "draws": 0, "losses": 0,
            "goals_scored_avg":   1.3,
            "goals_conceded_avg": 1.3,
            "xg_avg":  1.3,
            "xga_avg": 1.3,
            "form_score": 0.5,  # Neutro — sin ajuste
            "ppda": 11.0,
        }

    def get_corner_stats(self, team: str, league: str, n_games: int = 5) -> dict:
        """Promedio de corners por liga (basado en estadisticas historicas conocidas)."""
        # Promedios reales por liga (fuente: Understat/Wikipedia historico)
        league_corner_avgs = {
            "ENG-Premier League": {"home": 5.1, "away": 4.8},
            "ESP-La Liga":        {"home": 4.9, "away": 4.6},
            "ITA-Serie A":        {"home": 4.7, "away": 4.5},
            "GER-Bundesliga":     {"home": 5.0, "away": 4.7},
            "FRA-Ligue 1":        {"home": 4.6, "away": 4.4},
        }
        avgs = league_corner_avgs.get(league, {"home": 5.0, "away": 4.5})
        return {
            "corners_for_avg":     avgs["home"],
            "corners_against_avg": avgs["away"],
            "total_corners_avg":   avgs["home"] + avgs["away"],
        }

    def get_card_stats(self, team: str, league: str, n_games: int = 5) -> dict:
        """Promedio de tarjetas por liga."""
        league_card_avgs = {
            "ENG-Premier League": 1.9,
            "ESP-La Liga":        2.6,
            "ITA-Serie A":        2.3,
            "GER-Bundesliga":     1.8,
            "FRA-Ligue 1":        2.0,
        }
        yellow = league_card_avgs.get(league, 2.0)
        return {
            "yellow_cards_avg": yellow,
            "red_cards_avg":    0.1,
            "total_cards_avg":  yellow + 0.1,
        }


fbref_engine = FBrefEngine(season='2025')