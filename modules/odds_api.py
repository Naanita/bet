# modules/odds_api.py
import requests
import config
import pandas as pd
import json

class OddsAPI:
    def __init__(self):
        self.api_key = config.ODDS_API_KEY
        self.base_url = "https://api.the-odds-api.com/v4/sports"

    def get_all_sports_odds(self):
        if not self.api_key or self.api_key == "TU_API_KEY_DE_THE_ODDS_API":
            print("\n[!] ALERTA: API Key no configurada.")
            return "MOCK"

        print(f"\n[+] Iniciando Line Shopping en TheOddsAPI...")
        all_odds = {'soccer': {}, 'basketball': {}, 'tennis': {}}
        sports_to_fetch = [
            ('soccer', config.SOCCER_LEAGUES.values()),
            ('basketball', config.BASKETBALL_LEAGUES.values()),
            ('tennis', config.TENNIS_LEAGUES.values())
        ]

        for sport_category, sport_keys in sports_to_fetch:
            for sport_key in sport_keys:
                url = f"{self.base_url}/{sport_key}/odds"
                params = {"apiKey": self.api_key, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"}
                try:
                    res = requests.get(url, params=params)
                    if res.status_code in [429, 401]:
                        return "API_LIMIT"
                    if res.status_code != 200: continue
                    
                    for event in res.json():
                        match_name = f"{event['home_team']} vs {event['away_team']}"
                        match_time_utc = pd.to_datetime(event.get('commence_time'))
                        match_time_local = match_time_utc.tz_convert(config.TIMEZONE)
                        
                        match_date = match_time_local.strftime('%Y-%m-%d')
                        match_time = match_time_local.strftime('%H:%M') # ⏱️ NUEVO: Capturamos la hora
                        
                        books = event.get('bookmakers', [])
                        if not books: continue
                        
                        match_odds = {
                            "Gana Local": 0.0, "Gana Visita": 0.0, "Empate": 0.0,
                            "Más de 2.5 Goles": 0.0, "Menos de 2.5 Goles": 0.0
                        }
                        
                        # Listas para calcular el promedio del mercado (Consenso)
                        odds_lists = {k: [] for k in match_odds.keys()}
                        
                        for book in books:
                            for market in book.get('markets', []):
                                if market['key'] == 'h2h':
                                    for out in market['outcomes']:
                                        if out['name'] == event['home_team']: 
                                            match_odds["Gana Local"] = max(match_odds["Gana Local"], out['price'])
                                            odds_lists["Gana Local"].append(out['price'])
                                        elif out['name'] == event['away_team']: 
                                            match_odds["Gana Visita"] = max(match_odds["Gana Visita"], out['price'])
                                            odds_lists["Gana Visita"].append(out['price'])
                                        elif out['name'] == 'Draw': 
                                            match_odds["Empate"] = max(match_odds["Empate"], out['price'])
                                            odds_lists["Empate"].append(out['price'])
                                elif market['key'] == 'totals':
                                    for out in market['outcomes']:
                                        if out['name'] == 'Over' and out['point'] == 2.5: 
                                            match_odds["Más de 2.5 Goles"] = max(match_odds["Más de 2.5 Goles"], out['price'])
                                            odds_lists["Más de 2.5 Goles"].append(out['price'])
                                        elif out['name'] == 'Under' and out['point'] == 2.5: 
                                            match_odds["Menos de 2.5 Goles"] = max(match_odds["Menos de 2.5 Goles"], out['price'])
                                            odds_lists["Menos de 2.5 Goles"].append(out['price'])
                        
                        match_odds = {k: v for k, v in match_odds.items() if v > 0.0}
                        # Calculamos el promedio (Fair Odds con Vig)
                        avg_odds = {k: sum(v)/len(v) for k, v in odds_lists.items() if v}
                        
                        all_odds[sport_category][match_name] = {
                            "date": match_date,
                            "time": match_time, # ⏱️ Guardamos la hora en la matriz
                            "odds": match_odds,     # La mejor cuota disponible (para apostar)
                            "avg_odds": avg_odds    # El promedio del mercado (para analizar)
                        }
                except requests.exceptions.RequestException as e:
                    print(f"[!] ERROR: Request failed for {sport_key}: {e}")
                    continue
                except json.JSONDecodeError:
                    print(f"[!] ERROR: Failed to decode JSON for {sport_key}. Status: {res.status_code}. Response: {res.text}")
                    continue
                    
        return all_odds

    def get_scores(self, days_from=3):
        """Obtiene resultados de partidos terminados en los últimos días."""
        if not self.api_key or "TU_API_KEY" in self.api_key: return {}
        
        scores_data = {}
        sports_to_fetch = []
        if hasattr(config, 'SOCCER_LEAGUES'): sports_to_fetch.extend(config.SOCCER_LEAGUES.values())
        if hasattr(config, 'BASKETBALL_LEAGUES'): sports_to_fetch.extend(config.BASKETBALL_LEAGUES.values())
        
        for sport in sports_to_fetch:
            url = f"{self.base_url}/{sport}/scores"
            params = {"apiKey": self.api_key, "daysFrom": days_from}
            try:
                res = requests.get(url, params=params)
                if res.status_code == 200:
                    events = res.json()
                    for event in events:
                        if event.get('completed'):
                            match_name = f"{event['home_team']} vs {event['away_team']}"
                            scores = event.get('scores', [])
                            if scores and len(scores) == 2:
                                # Intentamos mapear score por nombre, si no, asumimos orden [0]=Home? No, mejor por nombre.
                                home_score = next((s['score'] for s in scores if s['name'] == event['home_team']), None)
                                away_score = next((s['score'] for s in scores if s['name'] == event['away_team']), None)
                                
                                if home_score is not None and away_score is not None:
                                    scores_data[match_name] = {'home': int(home_score), 'away': int(away_score)}
            except: pass
        return scores_data