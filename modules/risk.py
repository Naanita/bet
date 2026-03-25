# modules/risk.py
import config

class RiskEngine:
    # Constantes de calibración para Parlays
    PARLAY_XG_DIFF_THRESHOLD = 1.2
    PARLAY_CORRELATION_BOOST = 1.15
    PARLAY_BOOKMAKER_PENALTY = 0.85
    PARLAY_MAX_PROB_CAP = 0.95

    @staticmethod
    def expected_value(probability, odds):
        """Calcula el Expected Value (EV) de una apuesta."""
        return (probability * odds) - 1.0

    @staticmethod
    def calculate_kelly_stake(probability, odds, bankroll, fraction=config.BASE_KELLY_FRACTION):
        """Calcula el tamaño de la apuesta usando el Criterio de Kelly fraccional."""
        q = 1.0 - probability
        b = odds - 1.0
        if b <= 0: return 0.0
        
        kelly_pct = (b * probability - q) / b
        if kelly_pct <= 0: return 0.0
        
        adj_kelly = kelly_pct * fraction
        adj_kelly = min(adj_kelly, config.MAX_STAKE_PERCENT)
        
        return round(bankroll * adj_kelly, 2)
        
    @staticmethod
    def evaluate_correlated_parlay(home_xg, away_xg, home_team, away_team, match_odds, true_probs):
        """
        Genera un Same Game Parlay si hay dominancia absoluta (>1.2 xG de diferencia).
        Cruza la victoria del favorito con el Over 2.5 Goles.
        """
        xg_diff = home_xg - away_xg
        
        if xg_diff >= RiskEngine.PARLAY_XG_DIFF_THRESHOLD:
            winner_market = "Gana Local"
            dominant = home_team
        elif xg_diff <= -RiskEngine.PARLAY_XG_DIFF_THRESHOLD:
            winner_market = "Gana Visita"
            dominant = away_team
        else:
            return None
            
        over_market = "Más de 2.5 Goles"
        
        if winner_market not in match_odds or over_market not in match_odds:
            return None
            
        odds_winner = match_odds[winner_market]
        odds_over = match_odds[over_market]
        
        p_winner = true_probs.get(winner_market, 0)
        p_over = true_probs.get(over_market, 0)
        
        # Filtro estricto: Ambos eventos deben ser muy probables por sí solos
        if p_winner > 0.50 and p_over > 0.50:
            # Boost de correlación: Si el dominante golea, el Over es casi un hecho
            raw_combined_prob = (p_winner * p_over) * RiskEngine.PARLAY_CORRELATION_BOOST
            combined_prob = min(raw_combined_prob, RiskEngine.PARLAY_MAX_PROB_CAP)
            
            # Penalización de la casa de apuestas (saben que está correlacionado)
            combined_odds = (odds_winner * odds_over) * RiskEngine.PARLAY_BOOKMAKER_PENALTY
            
            ev = RiskEngine.expected_value(combined_prob, combined_odds)
            
            if ev > config.MIN_EV_THRESHOLD:
                return {
                    "market": f"{winner_market} + {over_market}",
                    "odds": round(combined_odds, 2),
                    "prob": combined_prob,
                    "ev": ev,
                    "dominant": dominant
                }
        return None