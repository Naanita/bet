# modules/balldontlie_engine.py
# Ball Don't Lie API — estadisticas NBA completamente gratuitas
# Docs: https://www.balldontlie.io/
# El tier FREE no requiere API key. Con key (gratis) se obtienen mas req/dia.

import requests
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.balldontlie.io/v1"


class BallDontLieEngine:
    """
    Wrapper de la API gratuita de Ball Don't Lie para estadisticas NBA.
    Proporciona:
      - Estadisticas de equipos (puntos, asistencias, rebotes por partido)
      - Estadisticas de jugadores (para props)
      - Partidos proximos y resultados
      - Calculo de probabilidades para Over/Under y ganador
    """

    def __init__(self, api_key: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if api_key:
            self.session.headers["Authorization"] = api_key

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        try:
            resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning("BallDontLie: limite de requests alcanzado.")
            else:
                logger.error(f"BallDontLie HTTP error {e.response.status_code}: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"BallDontLie error: {e}")
            return None

    # ─────────────────────────────────────────────
    # Equipos
    # ─────────────────────────────────────────────

    def get_all_teams(self) -> list:
        """Retorna todos los equipos NBA."""
        data = self._get("teams")
        return data.get("data", []) if data else []

    def find_team(self, name: str) -> Optional[dict]:
        """Busca equipo por nombre (fuzzy). Retorna el dict del equipo o None."""
        teams = self.get_all_teams()
        name_lower = name.lower()
        # Busqueda exacta primero
        for t in teams:
            if name_lower in t.get("full_name", "").lower() or \
               name_lower in t.get("name", "").lower() or \
               name_lower in t.get("abbreviation", "").lower():
                return t
        return None

    # ─────────────────────────────────────────────
    # Partidos
    # ─────────────────────────────────────────────

    def get_upcoming_games(self, days_ahead: int = 2) -> list:
        """Retorna partidos de los proximos N dias."""
        dates = []
        today = datetime.now()
        for i in range(days_ahead + 1):
            dates.append((today + timedelta(days=i)).strftime("%Y-%m-%d"))

        games = []
        for date_str in dates:
            data = self._get("games", params={"dates[]": date_str, "per_page": 100})
            if data:
                games.extend(data.get("data", []))
        return games

    def get_recent_games(self, team_id: int, n: int = 10) -> list:
        """Ultimos N partidos de un equipo (temporada actual)."""
        season = self._current_season()
        data = self._get("games", params={
            "team_ids[]": team_id,
            "seasons[]": season,
            "per_page": n,
        })
        if not data:
            return []
        games = sorted(
            data.get("data", []),
            key=lambda g: g.get("date", ""),
            reverse=True
        )
        return games[:n]

    def _current_season(self) -> int:
        """Retorna la temporada NBA actual (el año de inicio)."""
        now = datetime.now()
        return now.year if now.month >= 10 else now.year - 1

    # ─────────────────────────────────────────────
    # Estadisticas de equipo
    # ─────────────────────────────────────────────

    def get_team_stats(self, team_id: int, n_games: int = 10) -> dict:
        """
        Calcula promedios del equipo en los ultimos N partidos:
        - pts_scored: puntos anotados por partido
        - pts_allowed: puntos recibidos por partido
        - home_pts / away_pts: promedio local/visitante
        - win_rate: % de victorias
        """
        games = self.get_recent_games(team_id, n_games)
        if not games:
            return {"pts_scored": 110.0, "pts_allowed": 110.0, "win_rate": 0.5,
                    "home_pts": 112.0, "away_pts": 108.0, "games_used": 0}

        scored, allowed = [], []
        home_pts, away_pts = [], []
        wins = 0

        for g in games:
            home_id  = g.get("home_team", {}).get("id")
            home_sc  = g.get("home_team_score", 0) or 0
            away_sc  = g.get("visitor_team_score", 0) or 0

            if home_id == team_id:
                scored.append(home_sc)
                allowed.append(away_sc)
                home_pts.append(home_sc)
                if home_sc > away_sc:
                    wins += 1
            else:
                scored.append(away_sc)
                allowed.append(home_sc)
                away_pts.append(away_sc)
                if away_sc > home_sc:
                    wins += 1

        n = len(scored)
        return {
            "pts_scored":  round(sum(scored) / n, 1) if n else 110.0,
            "pts_allowed": round(sum(allowed) / n, 1) if n else 110.0,
            "win_rate":    round(wins / n, 3) if n else 0.5,
            "home_pts":    round(sum(home_pts) / len(home_pts), 1) if home_pts else 112.0,
            "away_pts":    round(sum(away_pts) / len(away_pts), 1) if away_pts else 108.0,
            "games_used":  n,
        }

    # ─────────────────────────────────────────────
    # Prediccion de partido
    # ─────────────────────────────────────────────

    def predict_game(self, home_team_name: str, away_team_name: str) -> Optional[dict]:
        """
        Genera una prediccion cuantitativa para un partido NBA.
        Retorna:
          - predicted_total: puntos totales esperados
          - home_win_prob: probabilidad de victoria local (0-1)
          - away_win_prob: probabilidad de victoria visitante
          - home_projected: puntos proyectados local
          - away_projected: puntos proyectados visitante
          - over_225_prob / over_215_prob / over_235_prob: probabilidad Over/Under
        """
        home_team = self.find_team(home_team_name)
        away_team = self.find_team(away_team_name)

        if not home_team or not away_team:
            logger.warning(f"No se encontraron equipos: {home_team_name} / {away_team_name}")
            return None

        home_stats = self.get_team_stats(home_team["id"])
        away_stats = self.get_team_stats(away_team["id"])

        if home_stats["games_used"] == 0 or away_stats["games_used"] == 0:
            return None

        # Modelo simple basado en eficiencia ofensiva/defensiva
        # Puntos esperados = promedio de lo que el equipo anota vs lo que el rival concede
        home_projected = (home_stats["pts_scored"] + away_stats["pts_allowed"]) / 2
        away_projected = (away_stats["pts_scored"] + home_stats["pts_allowed"]) / 2

        # Ventaja de local: +3 puntos historicamente en NBA
        home_projected += 1.5
        away_projected -= 1.5

        predicted_total = home_projected + away_projected

        # Probabilidad de victoria usando logistica simple
        diff = home_projected - away_projected
        import math
        home_win_prob = 1 / (1 + math.exp(-diff / 8))
        away_win_prob = 1 - home_win_prob

        # Probabilidades Over/Under (usando distribucion normal aproximada)
        std_dev = 12.0  # desviacion estandar tipica del total en NBA
        lines = [215.5, 220.5, 225.5, 230.5, 235.5]
        over_probs = {}
        for line in lines:
            z = (predicted_total - line) / std_dev
            # Aproximacion CDF normal
            over_prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            over_probs[f"over_{int(line)}"] = round(over_prob, 3)

        return {
            "home_team":        home_team["full_name"],
            "away_team":        away_team["full_name"],
            "home_projected":   round(home_projected, 1),
            "away_projected":   round(away_projected, 1),
            "predicted_total":  round(predicted_total, 1),
            "home_win_prob":    round(home_win_prob, 3),
            "away_win_prob":    round(away_win_prob, 3),
            "over_probs":       over_probs,
            "home_stats":       home_stats,
            "away_stats":       away_stats,
        }

    # ─────────────────────────────────────────────
    # Estadisticas de jugadores (para props)
    # ─────────────────────────────────────────────

    def get_player_stats(self, player_name: str, n_games: int = 10) -> Optional[dict]:
        """
        Retorna promedios del jugador en los ultimos N partidos:
        pts, reb, ast, stl, blk, min
        """
        # Buscar jugador
        parts = player_name.strip().split()
        search_params = {
            "search": player_name,
            "per_page": 5,
        }
        data = self._get("players", params=search_params)
        if not data or not data.get("data"):
            return None

        player = data["data"][0]
        player_id = player["id"]

        season = self._current_season()
        stats_data = self._get("stats", params={
            "player_ids[]": player_id,
            "seasons[]": season,
            "per_page": n_games,
        })
        if not stats_data or not stats_data.get("data"):
            return None

        stats = stats_data["data"]
        if not stats:
            return None

        pts  = [s.get("pts", 0) or 0 for s in stats]
        reb  = [s.get("reb", 0) or 0 for s in stats]
        ast  = [s.get("ast", 0) or 0 for s in stats]
        stl  = [s.get("stl", 0) or 0 for s in stats]
        blk  = [s.get("blk", 0) or 0 for s in stats]
        n    = len(pts)

        return {
            "player":     f"{player.get('first_name','')} {player.get('last_name','')}",
            "team":       player.get("team", {}).get("full_name", ""),
            "avg_pts":    round(sum(pts) / n, 1),
            "avg_reb":    round(sum(reb) / n, 1),
            "avg_ast":    round(sum(ast) / n, 1),
            "avg_stl":    round(sum(stl) / n, 1),
            "avg_blk":    round(sum(blk) / n, 1),
            "games_used": n,
            "pts_history": pts,
        }

    def get_nba_picks(self, current_bankroll: float,
                      min_prob: float = 0.65, min_ev: float = 0.03) -> list:
        """
        Genera picks NBA para los proximos partidos con EV positivo.
        Analiza ganador del partido y Over/Under de puntos totales.
        """
        picks = []
        games = self.get_upcoming_games(days_ahead=1)

        for game in games:
            home_name = game.get("home_team", {}).get("full_name", "")
            away_name = game.get("visitor_team", {}).get("full_name", "")
            game_date = game.get("date", "")[:10]

            if not home_name or not away_name:
                continue
            # Solo partidos no iniciados
            if game.get("status") not in [None, "", "scheduled"]:
                continue

            pred = self.predict_game(home_name, away_name)
            if not pred:
                continue

            home_stats = pred["home_stats"]
            away_stats = pred["away_stats"]
            base_reason = (
                f"Proyeccion: {pred['home_projected']} - {pred['away_projected']} pts | "
                f"Forma: {home_stats['win_rate']*100:.0f}% W (local) vs "
                f"{away_stats['win_rate']*100:.0f}% W (visita)"
            )

            # ── Ganador del partido ──
            for prob, team in [
                (pred["home_win_prob"], home_name),
                (pred["away_win_prob"], away_name),
            ]:
                if prob < min_prob:
                    continue
                # Margen del 5% del book como estimacion conservadora
                implied_odds = round(1 / prob * 1.05, 2)
                ev = (prob * implied_odds) - 1
                if ev < min_ev:
                    continue

                # Kelly simplificado: fraccion conservadora del bankroll
                kelly_f = max(0.0, (prob - (1 - prob) / (implied_odds - 1)))
                stake   = int(current_bankroll * min(kelly_f * 0.25, 0.05))

                picks.append({
                    "sport":        "🏀",
                    "home":         home_name,
                    "away":         away_name,
                    "time":         game_date,
                    "market":       f"Gana {team}",
                    "odds":         implied_odds,
                    "prob":         round(prob * 100, 1),
                    "ev":           round(ev * 100, 1),
                    "reason":       base_reason,
                    "confidence":   "✅ ALTA" if prob >= 0.70 else "⚡ MEDIA",
                    "source":       "balldontlie",
                    "stake_amount": stake,
                })

            # ── Over/Under puntos totales ──
            for line_key, over_prob in pred["over_probs"].items():
                line_val   = int(line_key.split("_")[1])
                under_prob = 1 - over_prob

                for direction, prob in [("Over", over_prob), ("Under", under_prob)]:
                    if prob < min_prob:
                        continue
                    implied_odds = round(1 / prob * 1.05, 2)
                    ev = (prob * implied_odds) - 1
                    if ev < min_ev:
                        continue

                    picks.append({
                        "sport":        "🏀",
                        "home":         home_name,
                        "away":         away_name,
                        "time":         game_date,
                        "market":       f"{direction} {line_val + 0.5} puntos NBA",
                        "odds":         implied_odds,
                        "prob":         round(prob * 100, 1),
                        "ev":           round(ev * 100, 1),
                        "reason":       (
                            f"Total proyectado: {pred['predicted_total']} pts | "
                            f"{home_name} anota {pred['home_projected']} | "
                            f"{away_name} anota {pred['away_projected']}"
                        ),
                        "confidence":   "✅ ALTA" if prob >= 0.70 else "⚡ MEDIA",
                        "source":       "balldontlie",
                        "stake_amount": int(current_bankroll * 0.02),
                    })

        return picks
