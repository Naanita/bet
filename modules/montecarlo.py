# modules/montecarlo.py
import numpy as np

class MonteCarloEngine:
    @staticmethod
    def validate_risk(edge, win_prob, stake, current_bankroll, sims=5000, max_drawdown=0.15):
        """
        Simula 5,000 escenarios de 10 apuestas seguidas con este edge.
        Si la probabilidad de perder el 15% del bankroll es mayor al 5%, rechaza.
        """
        results = []
        for _ in range(sims):
            br = current_bankroll
            for _ in range(10): # Simular racha corta
                if np.random.rand() < win_prob:
                    br += stake * edge
                else:
                    br -= stake
            results.append((current_bankroll - br) / current_bankroll) # Drawdown final
            
        # Calcula percentil 95 (el peor 5% de los casos)
        worst_case_drawdown = np.percentile(results, 95)
        
        # Si en el peor escenario superamos el límite, no pasa la validación
        return worst_case_drawdown <= max_drawdown