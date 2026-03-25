# modules/data.py
import soccerdata as sd
import pandas as pd
import config

class DataEngine:
    def __init__(self, season='2025'):
        self.understat = sd.Understat(leagues=config.UNDERSTAT_LEAGUES, seasons=season)
        self.clubelo = sd.ClubElo() # 🆕 Fuente añadida: Rankings de fuerza ELO
        
    def _apply_time_decay_and_volatility(self, group):
        """Pondera al 65% reciente, 35% histórico Y calcula la consistencia."""
        group = group.sort_values('date')
        if len(group) <= 5:
            return pd.Series({
                'xG_avg': group['xg'].mean(), 
                'xGA_avg': group['xga'].mean(),
                'xG_volatility': group['xg'].std() if len(group) > 1 else 0.5 # Volatilidad por defecto si hay poca data
            })
            
        recent = group.tail(5)
        hist = group.iloc[:-5]
        
        recent_mean = recent.mean(numeric_only=True)
        hist_mean = hist.mean(numeric_only=True)
        
        # 🛡️ EXTRACCIÓN DE VOLATILIDAD: Desviación estándar de los últimos 5 partidos
        xg_volatility = recent['xg'].std()
        
        xg_weighted = (recent_mean['xg'] * 0.65) + (hist_mean['xg'] * 0.35)
        xga_weighted = (recent_mean['xga'] * 0.65) + (hist_mean['xga'] * 0.35)
        
        return pd.Series({'xG_avg': xg_weighted, 'xGA_avg': xga_weighted, 'xG_volatility': xg_volatility})

    def get_season_xg_stats(self) -> pd.DataFrame:
        schedule = self.understat.read_schedule().reset_index()
        
        if isinstance(schedule.columns, pd.MultiIndex):
            schedule.columns = ['_'.join(str(i) for i in col if i).strip().lower() for col in schedule.columns]
        else:
            schedule.columns = [str(c).lower() for c in schedule.columns]
            
        played = schedule.dropna(subset=['home_xg', 'away_xg']).copy()
        
        home_df = played[['date', 'home_team', 'home_xg', 'away_xg']].rename(columns={'home_team': 'team', 'home_xg': 'xg', 'away_xg': 'xga'})
        away_df = played[['date', 'away_team', 'away_xg', 'home_xg']].rename(columns={'away_team': 'team', 'away_xg': 'xg', 'home_xg': 'xga'})
        
        team_stats = pd.concat([home_df, away_df], ignore_index=True)
        
        # Agregamos la nueva función que incluye volatilidad
        return team_stats.groupby('team').apply(self._apply_time_decay_and_volatility, include_groups=False).reset_index()

    def get_advanced_stats(self):
        """
        Descarga estadísticas avanzadas de FBref para Props (Tiros, Córners).
        Retorna un DataFrame con: Posesión, Tiros al Arco (SoT), Córners a favor.
        """
        try:
            # Obtenemos estadísticas de temporada por equipo
            stats = self.fbref.read_team_season_stats(stat_type="standard")
            shooting = self.fbref.read_team_season_stats(stat_type="shooting")
            
            # Unimos y limpiamos (simplificado para el ejemplo)
            # Nota: soccerdata devuelve MultiIndex, hay que aplanar
            return stats, shooting
        except Exception as e:
            print(f"[!] Error FBref: {e}")
            return None, None

    def get_elo_prob(self, home, away):
        """Retorna la probabilidad de victoria del Local según ClubElo."""
        try:
            elo_df = self.clubelo.read_by_date()
            if elo_df is None or elo_df.empty:
                print(f"   ⚠️ ClubElo: No se pudieron descargar datos para la fecha actual.")
                return 0.5

            # 🛠️ CORRECCIÓN: Normalizamos columnas a minúsculas y reseteamos índice
            elo_df = elo_df.reset_index()
            elo_df.columns = [c.lower() for c in elo_df.columns]

            # Normalizamos nombres (esto suele requerir un diccionario de mapeo en producción)
            h_rows = elo_df[elo_df['team'].str.contains(home, case=False, na=False)]
            a_rows = elo_df[elo_df['team'].str.contains(away, case=False, na=False)]
            
            if h_rows.empty: print(f"   ⚠️ ClubElo: No se encontró el equipo '{home}'")
            if a_rows.empty: print(f"   ⚠️ ClubElo: No se encontró el equipo '{away}'")

            if not h_rows.empty and not a_rows.empty:
                h_val = h_rows['elo'].values[0] + 100 # +100 Home Advantage
                a_val = a_rows['elo'].values[0]
                return 1 / (1 + 10 ** ((a_val - h_val) / 400))
            return 0.5
        except Exception as e: 
            print(f"   ❌ Error interno ClubElo: {e}")
            return 0.5

    def get_elo_probability(self, home_team, away_team):
        """
        Calcula la probabilidad de victoria basada puramente en el ranking ELO.
        Fórmula: P(A) = 1 / (1 + 10 ^ ((Elo_B - Elo_A) / 400))
        """
        try:
            # Obtenemos los ratings actuales (esto descarga un CSV pequeño)
            elo_df = self.clubelo.read_by_date()
            elo_df = elo_df.reset_index()
            elo_df.columns = [c.lower() for c in elo_df.columns]
            
            elo_home = elo_df.loc[elo_df['team'] == home_team, 'elo'].values[0]
            elo_away = elo_df.loc[elo_df['team'] == away_team, 'elo'].values[0]
            
            # Ajuste por localía (normalmente +100 puntos Elo al local)
            elo_home += 100 
            
            prob_home = 1 / (1 + 10 ** ((elo_away - elo_home) / 400))
            return prob_home
        except:
            return None # Si no encuentra el equipo (nombres diferentes)