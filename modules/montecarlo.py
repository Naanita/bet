# modules/montecarlo.py
import numpy as np

class MonteCarloEngine:
    @staticmethod
    def validate_risk(edge, win_prob, stake, current_bankroll, sims=5000, max_drawdown=0.15):
        """
        Simula 5,000 escenarios de 10 apuestas seguidas con este edge.
        Si la probabilidad de perder el 15% del bankroll es mayor al 5%, rechaza.
        Vectorizado con NumPy — ~100x más rápido que el bucle Python original.
        """
        # Matriz (sims × 10): True = apuesta ganada
        outcomes = np.random.rand(sims, 10) < win_prob
        # P&L por apuesta: +stake*edge si gana, -stake si pierde
        pnl = np.where(outcomes, stake * edge, -stake)
        # Drawdown acumulado al final de las 10 apuestas
        final_br   = current_bankroll + pnl.sum(axis=1)
        drawdowns  = (current_bankroll - final_br) / current_bankroll
        # Percentil 95 → peor 5% de escenarios
        worst_case = float(np.percentile(drawdowns, 95))
        return worst_case <= max_drawdown