# modules/nba_data.py
from nba_api.stats.endpoints import playergamelog, leaguedashplayerstats
from nba_api.stats.static import players
import pandas as pd
import time

class NBAEngine:
    def __init__(self):
        self.season = '2024-25'

    def get_hot_players(self):
        """
        Busca jugadores que estén superando sus promedios en los últimos 5 juegos.
        Ideal para apuestas de: "Más de X Puntos" o "PRA (Puntos+Rebotes+Asistencias)".
        """
        print("🏀 Analizando tendencias de jugadores NBA...")
        try:
            # 1. Obtenemos stats generales de la temporada
            general = leaguedashplayerstats.LeagueDashPlayerStats(season=self.season).get_data_frames()[0]
            top_players = general[general['MIN'] > 25] # Solo jugadores con >25 min de juego
            
            hot_props = []
            
            # Analizamos solo el Top 20 por eficiencia para no saturar la API
            for _, player in top_players.sort_values('PTS', ascending=False).head(20).iterrows():
                p_id = player['PLAYER_ID']
                p_name = player['PLAYER_NAME']
                
                # 2. Obtenemos sus últimos 5 juegos
                logs = playergamelog.PlayerGameLog(player_id=p_id, season=self.season).get_data_frames()[0].head(5)
                
                avg_pts_L5 = logs['PTS'].mean()
                season_pts = player['PTS']
                
                # Si en los últimos 5 promedia un 15% más que en la temporada -> RACHA
                if avg_pts_L5 > (season_pts * 1.15):
                    hot_props.append({
                        "player": p_name,
                        "market": "Puntos",
                        "line": round(season_pts + 1.5), # Línea estimada
                        "avg_L5": avg_pts_L5,
                        "reason": f"🔥 Racha: Promedia {avg_pts_L5:.1f} pts en últimos 5 (Media: {season_pts:.1f})"
                    })
                
                time.sleep(0.6) # Respetar límites de API
                
            return hot_props
        except Exception as e:
            print(f"[!] Error NBA API: {e}")
# modules/nba_data.py
from nba_api.stats.endpoints import playergamelog, leaguedashplayerstats
from nba_api.stats.static import players
import pandas as pd
import time

class NBAEngine:
    def __init__(self):
        self.season = '2024-25'

    def get_hot_players(self):
        """
        Busca jugadores que estén superando sus promedios en los últimos 5 juegos.
        Ideal para apuestas de: "Más de X Puntos" o "PRA (Puntos+Rebotes+Asistencias)".
        """
        print("🏀 Analizando tendencias de jugadores NBA...")
        try:
            # 1. Obtenemos stats generales de la temporada
            general = leaguedashplayerstats.LeagueDashPlayerStats(season=self.season).get_data_frames()[0]
            if general.empty:
                print(f"   ⚠️ NBA API: No hay datos para la temporada {self.season}. (Verifica la fecha)")
                return []
            top_players = general[general['MIN'] > 25] # Solo jugadores con >25 min de juego
            
            hot_props = []
            
            # Analizamos solo el Top 20 por eficiencia para no saturar la API
            for _, player in top_players.sort_values('PTS', ascending=False).head(20).iterrows():
                p_id = player['PLAYER_ID']
                p_name = player['PLAYER_NAME']
                
                # 2. Obtenemos sus últimos 5 juegos
                logs = playergamelog.PlayerGameLog(player_id=p_id, season=self.season).get_data_frames()[0].head(5)
                
                avg_pts_L5 = logs['PTS'].mean()
                season_pts = player['PTS']
                
                # Si en los últimos 5 promedia un 15% más que en la temporada -> RACHA
                if avg_pts_L5 > (season_pts * 1.15):
                    hot_props.append({
                        "player": p_name,
                        "market": "Puntos",
                        "line": round(season_pts + 1.5), # Línea estimada
                        "avg_L5": avg_pts_L5,
                        "reason": f"🔥 Racha: Promedia {avg_pts_L5:.1f} pts en últimos 5 (Media: {season_pts:.1f})"
                    })
                
                time.sleep(0.6) # Respetar límites de API
                
            return hot_props
        except Exception as e:
            print(f"[!] Error NBA API: {e}")
            return []
            return []
