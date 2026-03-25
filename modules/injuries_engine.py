# modules/injuries_engine.py v2
# Lesiones, suspensiones y Head-to-Head via API-Football
# Endpoint: https://v3.football.api-sports.io
# Plan gratuito: 100 requests/dia

import requests
import logging

logger = logging.getLogger(__name__)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

# ─────────────────────────────────────────────
# Mapa completo de equipos -> ID en API-Football
# ─────────────────────────────────────────────
TEAM_ID_MAP = {
    # Premier League
    "Manchester United":   33,
    "Newcastle United":    34,
    "Newcastle":           34,
    "Bournemouth":         35,
    "Fulham":              36,
    "Wolves":              39,
    "Wolverhampton":       39,
    "Liverpool":           40,
    "Southampton":         41,
    "Arsenal":             42,
    "Everton":             45,
    "Leicester":           46,
    "Tottenham":           47,
    "Tottenham Hotspur":   47,
    "West Ham":            48,
    "West Ham United":     48,
    "Chelsea":             49,
    "Manchester City":     50,
    "Brighton":            51,
    "Brighton and Hove Albion": 51,
    "Crystal Palace":      52,
    "Brentford":           55,
    "Ipswich":             57,
    "Nottingham Forest":   65,
    "Aston Villa":         66,
    # Ligue 1
    "Angers":              77,
    "Lille":               79,
    "Lyon":                80,
    "Olympique Lyonnais":  80,
    "Marseille":           81,
    "Olympique Marseille": 81,
    "Montpellier":         82,
    "Nantes":              83,
    "Nice":                84,
    "Niza":                84,
    "Paris Saint Germain": 85,
    "PSG":                 85,
    "Paris Saint-Germain": 85,
    "Monaco":              91,
    "AS Monaco":           91,
    "AS Mónaco":           91,
    "Reims":               93,
    "Rennes":              94,
    "Strasbourg":          95,
    "Toulouse":            96,
    "Brest":               106,
    "Stade Brestois 29":   106,
    "Auxerre":             108,
    "Le Havre":            111,
    "Metz":                112,
    "Lens":                116,
    "Saint Etienne":       1063,
    "Paris FC":            None,  # No estaba en Ligue 1 2024
    # La Liga
    "Barcelona":           529,
    "Atletico Madrid":     530,
    "Atlético de Madrid":  530,
    "Athletic Club":       531,
    "Valencia":            532,
    "Villarreal":          533,
    "Las Palmas":          534,
    "Sevilla":             536,
    "Leganes":             537,
    "Celta Vigo":          538,
    "Espanyol":            540,
    "Real Madrid":         541,
    "Alaves":              542,
    "Real Betis":          543,
    "Getafe":              546,
    "Girona":              547,
    "Real Sociedad":       548,
    "Valladolid":          720,
    "Osasuna":             727,
    "Rayo Vallecano":      728,
    "Mallorca":            798,
    # Serie A
    "Lazio":               487,
    "AC Milan":            489,
    "Milan":               489,
    "Cagliari":            490,
    "Napoli":              492,
    "Nápoles":             492,
    "Udinese":             494,
    "Genoa":               495,
    "Juventus":            496,
    "Roma":                497,
    "AS Roma":             497,
    "Atalanta":            499,
    "Bologna":             500,
    "Fiorentina":          502,
    "Torino":              503,
    "Hellas Verona":       504,
    "Verona":              504,
    "Inter":               505,
    "Empoli":              511,
    "Venezia":             517,
    "Parma":               523,
    "Parma Calcio 1913":   523,
    "Lecce":               867,
    "Como":                895,
    "Pisa":                None,
    "Monza":               1579,
    # Bundesliga
    "Bayern Munich":       157,
    "Bayern München":      157,
    "SC Freiburg":         160,
    "Freiburg":            160,
    "St. Pauli":           186,
    "FC St. Pauli":        186,
    "Wolfsburg":           161,
    "VfL Wolfsburg":       161,
    "Werder Bremen":       162,
    "Borussia M.Gladbach": 163,
    "Borussia Mönchengladbach": 163,
    "Mainz 05":            164,
    "FSV Mainz 05":        164,
    "Borussia Dortmund":   165,
    "Hoffenheim":          167,
    "Bayer Leverkusen":    168,
    "Eintracht Frankfurt": 169,
    "Augsburg":            170,
    "FC Augsburg":         170,
    "VfB Stuttgart":       172,
    "Stuttgart":           172,
    "RB Leipzig":          173,
    "Bochum":              176,
    "FC Heidenheim":       180,
    "Union Berlin":        182,
    "Holstein Kiel":       191,
    # Liga BetPlay Colombia
    "Millonarios":         1125,
    "Deportivo Pasto":     1126,
    "Deportivo Cali":      1127,
    "Independiente Medellin": 1128,
    "Envigado":            1129,
    "Bucaramanga":         1131,
    "Junior":              1135,
    "Once Caldas":         1136,
    "Atletico Nacional":   1137,
    "America de Cali":     1138,
    "América":             1138,
    "Santa Fe":            1139,
    "Deportes Tolima":     1142,
    "Deportivo Pereira":   1462,
}

# Mapeo de ligas -> ID API-Football
LEAGUE_ID_MAP = {
    "ENG-Premier League": {"id": 39,  "season": 2025},
    "ESP-La Liga":        {"id": 140, "season": 2025},
    "ITA-Serie A":        {"id": 135, "season": 2025},
    "GER-Bundesliga":     {"id": 78,  "season": 2025},
    "FRA-Ligue 1":        {"id": 61,  "season": 2025},
    "COL-Liga BetPlay":   {"id": 239, "season": 2025},
}


class InjuriesEngine:

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._cache  = {}

    def _headers(self) -> dict:
        key = self.api_key
        if not key:
            try:
                import config
                key = getattr(config, 'API_FOOTBALL_KEY', None)
            except Exception:
                pass
        if not key:
            return {}
        return {"x-apisports-key": key}

    def _get(self, endpoint: str, params: dict):
        cache_key = f"{endpoint}_{sorted(params.items())}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        headers = self._headers()
        if not headers:
            return None

        try:
            url = f"{API_FOOTBALL_BASE}/{endpoint}"
            r   = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self._cache[cache_key] = data
                return data
            else:
                logger.warning(f"API-Football {endpoint}: {r.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Error API-Football {endpoint}: {e}")
            return None

    def _find_team_id(self, team_name: str) -> int | None:
        """Busca el ID de un equipo con matching flexible."""
        # Busqueda exacta
        if team_name in TEAM_ID_MAP:
            return TEAM_ID_MAP[team_name]

        # Busqueda case-insensitive
        team_lower = team_name.lower()
        for k, v in TEAM_ID_MAP.items():
            if k.lower() == team_lower:
                return v

        # Busqueda por contenido
        for k, v in TEAM_ID_MAP.items():
            if team_lower in k.lower() or k.lower() in team_lower:
                return v

        return None


    def get_injuries(self, league_name: str) -> list:
        """
        Plan gratuito no tiene datos en tiempo real de lesiones.
        Retorna lista vacia — el impacto se calcula por H2H y forma reciente.
        Para lesiones en tiempo real, upgrade a plan Pro en api-football.com
        """
        logger.debug(f"Lesiones en tiempo real no disponibles en plan gratuito")
        return []

    def get_injury_impact(self, team: str, league_name: str) -> float:
        """Sin datos de lesiones en tiempo real -> sin ajuste."""
        return 1.0

    def get_h2h(self, home: str, away: str, last_n: int = 5) -> dict:
        """Estadisticas head-to-head entre dos equipos."""
        default = {
            "total_games": 0, "over25_pct": 0.5,
            "btts_pct": 0.5, "avg_goals": 2.5,
            "avg_corners": 10.0, "avg_cards": 4.0,
        }

        id_home = self._find_team_id(home)
        id_away = self._find_team_id(away)

        if not id_home or not id_away:
            logger.debug(f"IDs no encontrados: {home}({id_home}) vs {away}({id_away})")
            return default

        # Intentar con last=10 para tener mas chances de encontrar partidos
        data = self._get("fixtures/headtohead", {
            "h2h":  f"{id_home}-{id_away}",
            "last": 10,
        })

        if not data:
            return default

        fixtures = data.get("response", [])

        # Si no hay resultados, intentar con temporadas anteriores
        if not fixtures:
            data2 = self._get("fixtures/headtohead", {
                "h2h":    f"{id_home}-{id_away}",
                "season": 2023,
            })
            if data2:
                fixtures = data2.get("response", [])[:last_n]

        if not fixtures:
            logger.info(f"H2H {home} vs {away}: sin datos historicos")
            return default

        total = len(fixtures)
        over25, btts, total_goals = 0, 0, 0

        for f in fixtures:
            gh = f.get("goals", {}).get("home", 0) or 0
            ga = f.get("goals", {}).get("away", 0) or 0
            total_goals += gh + ga
            if gh + ga > 2.5: over25 += 1
            if gh > 0 and ga > 0: btts += 1

        result = {
            "total_games":  total,
            "over25_pct":   round(over25 / total, 3) if total else 0.5,
            "btts_pct":     round(btts   / total, 3) if total else 0.5,
            "avg_goals":    round(total_goals / total, 2) if total else 2.5,
            "avg_corners":  10.0,
            "avg_cards":    4.0,
        }

        logger.info(
            f"H2H {home} vs {away}: {total} partidos | "
            f"Over2.5: {result['over25_pct']*100:.0f}% | "
            f"BTTS: {result['btts_pct']*100:.0f}% | "
            f"Avg goles: {result['avg_goals']}"
        )
        return result


# Instancia global
_engine = None

def get_injuries_engine():
    global _engine
    if _engine is None:
        try:
            import config
            key = getattr(config, 'API_FOOTBALL_KEY', None)
            _engine = InjuriesEngine(api_key=key)
        except Exception:
            _engine = InjuriesEngine()
    return _engine