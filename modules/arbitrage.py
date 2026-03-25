# modules/arbitrage.py
class ArbitrageScanner:
    @staticmethod
    def check_arbitrage(odds_a, odds_b):
        """Devuelve True si existe una ganancia garantizada (Surebet)"""
        if not odds_a or not odds_b: return False
        implied_prob = (1 / odds_a) + (1 / odds_b)
        return implied_prob < 1.0
        
    @staticmethod
    def calculate_arb_stakes(total_investment, odds_a, odds_b):
        """Calcula distribución exacta del capital para equilibrar el beneficio."""
        implied_prob = (1 / odds_a) + (1 / odds_b)
        profit = (total_investment / implied_prob) - total_investment
        stake_a = (total_investment / implied_prob) / odds_a
        stake_b = (total_investment / implied_prob) / odds_b
        return round(stake_a, 2), round(stake_b, 2), round(profit, 2)