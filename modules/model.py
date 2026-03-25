# modules/model.py
import numpy as np
from scipy.stats import poisson, skellam
from itertools import product

class PoissonModel:
    def __init__(self, home_lambda, away_lambda):
        self.home_lambda = home_lambda
        self.away_lambda = away_lambda

    def matrix(self, max_goals=10):
        m = np.zeros((max_goals, max_goals))
        for i, j in product(range(max_goals), range(max_goals)):
            m[i][j] = poisson.pmf(i, self.home_lambda) * poisson.pmf(j, self.away_lambda)
        return m

    def get_probabilities(self):
        m = self.matrix()
        
        home_win = np.sum(np.tril(m, -1))
        draw = np.sum(np.diag(m))
        away_win = np.sum(np.triu(m, 1))
        
        probs = {
            "Gana Local": home_win, "Empate": draw, "Gana Visita": away_win,
            "Local o Empate (1X)": home_win + draw, "Visita o Empate (X2)": away_win + draw,
        }
        
        # Totales (Over/Under)
        for line in [0.5, 1.5, 2.5, 3.5]:
            over_prob = np.sum([m[i][j] for i in range(10) for j in range(10) if i + j > line])
            probs[f"Más de {line} Goles"] = over_prob
            probs[f"Menos de {line} Goles"] = 1 - over_prob

        # Ambos Anotan (BTTS)
        btts_yes = np.sum([m[i][j] for i in range(1, 10) for j in range(1, 10)])
        probs["Ambos Anotan: Sí"] = btts_yes
        probs["Ambos Anotan: No"] = 1 - btts_yes

        # 🧮 SKELLAM: Hándicaps Asiáticos (Líneas enteras y medias)
        # cdf(k) es la probabilidad de que (Local - Visita) <= k
        
        # Hándicap Local -1.5 (Local gana por 2 o más) -> 1 - P(Local - Visita <= 1)
        probs["Hándicap Asiático -1.5 Local"] = 1 - skellam.cdf(1, self.home_lambda, self.away_lambda)
        # Hándicap Visita +1.5 (Visita gana, empata o pierde por 1)
        probs["Hándicap Asiático +1.5 Visita"] = skellam.cdf(1, self.home_lambda, self.away_lambda)
        
        # Hándicap Local -2.5
        probs["Hándicap Asiático -2.5 Local"] = 1 - skellam.cdf(2, self.home_lambda, self.away_lambda)
        
        # Draw No Bet (Sin Empate)
        if (home_win + away_win) > 0:
            probs["Local sin Empate (DNB)"] = home_win / (home_win + away_win)
            probs["Visita sin Empate (DNB)"] = away_win / (home_win + away_win)
            
        return probs

class MarketConsensusModel:
    """
    Modelo de Valor de Mercado:
    Calcula la probabilidad real eliminando el margen (vig) de las cuotas promedio del mercado.
    """
    @staticmethod
    def get_true_probability(market_key, avg_odds_dict):
        # Identificar el grupo de mercados para normalizar (2-way o 3-way)
        if market_key in ["Gana Local", "Gana Visita", "Empate"]:
            group = ["Gana Local", "Empate", "Gana Visita"]
        elif "Goles" in market_key:
            group = ["Más de 2.5 Goles", "Menos de 2.5 Goles"]
        else:
            return 0.0

        # Obtener las cuotas promedio inversas (Probabilidad Implícita con Vig)
        implied_probs = []
        target_idx = -1
        
        for i, key in enumerate(group):
            if key not in avg_odds_dict: return 0.0 # Falta data para calcular el vig
            if key == market_key: target_idx = i
            implied_probs.append(1 / avg_odds_dict[key])
            
        # Normalización básica (Power Method o Multiplicativo simple)
        total_implied = sum(implied_probs)
        if total_implied == 0: return 0.0
        
        # La probabilidad real es la implícita dividida por la suma total (eliminando el overround)
        true_prob = implied_probs[target_idx] / total_implied
        return true_prob