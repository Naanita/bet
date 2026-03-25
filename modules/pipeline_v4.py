# modules/pipeline_v4.py — v4.1
# Pipeline completo con todos los mercados
# Los mercados de corners/tarjetas se evaluan directamente contra Rushbet

import pandas as pd
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# ── Mercados permitidos (solo goles y resultado) ──
ALLOWED_MARKETS = {
    # Resultado
    "gana local",
    "gana visita",
    "gana local (banker)",
    # Over/Under goles
    "mas de 1.5",
    "menos de 1.5",
    "mas de 2.5",
    "menos de 2.5",
    "mas de 3.5",
    "menos de 3.5",
    # Con tildes (OddsAPI)
    "mas de 1.5 goles",
    "menos de 1.5 goles",
    "mas de 2.5 goles",
    "menos de 2.5 goles",
    "mas de 3.5 goles",
    "menos de 3.5 goles",
    # BTTS
    "ambos anotan: si",
    "ambos anotan: no",
}

def _is_allowed_market(market: str) -> bool:
    """Solo permite goles y resultado 1X2."""
    m = market.lower().strip()
    # Normalizar tildes
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u')]:
        m = m.replace(a, b)
    return m in ALLOWED_MARKETS


def _team_score(t1: str, t2: str) -> float:
    t1, t2 = t1.lower().strip(), t2.lower().strip()
    if t1 == t2: return 1.0
    if t1 in t2 or t2 in t1: return 0.92
    return SequenceMatcher(None, t1, t2).ratio()


def _find_match_odds(home: str, away: str, soccer_odds: dict) -> dict:
    key = f"{home} vs {away}"
    if key in soccer_odds: return soccer_odds[key]
    best_match, best_score = None, 0.0
    for api_key in soccer_odds:
        try: ah, aa = api_key.split(" vs ", 1)
        except: continue
        score = min(_team_score(home, ah), _team_score(away, aa)) * 0.5 + \
                (_team_score(home, ah) + _team_score(away, aa)) / 2 * 0.5
        if score > best_score:
            best_score = score
            best_match = api_key
    if best_score >= 0.72:
        logger.info(f"Fuzzy: '{key}' -> '{best_match}' ({best_score:.2f})")
        return soccer_odds[best_match]
    return {}


def _get_league_for_team(home: str, away: str, schedule_df: pd.DataFrame) -> str:
    try:
        if "league" in schedule_df.columns:
            mask = (schedule_df["home_team"].str.lower() == home.lower()) | \
                   (schedule_df["away_team"].str.lower() == away.lower())
            rows = schedule_df[mask]
            if not rows.empty:
                return str(rows.iloc[0].get("league", "DEFAULT"))
    except Exception:
        pass

    # Detectar liga por equipo conocido
    PL_TEAMS = ["Arsenal","Chelsea","Liverpool","Manchester","Tottenham","Newcastle",
                "Brighton","Aston Villa","West Ham","Brentford","Fulham","Everton",
                "Crystal Palace","Wolves","Bournemouth","Nottingham","Leicester","Ipswich"]
    LALIGA_TEAMS = ["Barcelona","Real Madrid","Atletico","Sevilla","Valencia","Villarreal",
                    "Athletic","Betis","Sociedad","Osasuna","Girona","Celta","Alaves",
                    "Getafe","Rayo","Mallorca","Espanyol","Leganes","Las Palmas"]
    SERIEA_TEAMS = ["Juventus","Inter","Milan","Napoli","Roma","Lazio","Atalanta",
                    "Fiorentina","Bologna","Torino","Udinese","Genoa","Cagliari",
                    "Verona","Empoli","Venezia","Parma","Lecce","Como","Monza"]
    BUNDESLIGA_TEAMS = ["Bayern","Dortmund","Leipzig","Leverkusen","Frankfurt","Stuttgart",
                        "Freiburg","Wolfsburg","Mainz","Hoffenheim","Augsburg","Bremen",
                        "Gladbach","Union Berlin","Bochum","Pauli","Heidenheim","Kiel"]
    LIGUE1_TEAMS = ["PSG","Paris Saint","Marseille","Lyon","Monaco","Lille","Rennes",
                    "Nice","Lens","Strasbourg","Nantes","Toulouse","Reims","Brest",
                    "Auxerre","Le Havre","Metz","Angers","Montpellier","Saint Etienne"]

    for team in [home, away]:
        if any(t.lower() in team.lower() for t in PL_TEAMS):     return "ENG-Premier League"
        if any(t.lower() in team.lower() for t in LALIGA_TEAMS): return "ESP-La Liga"
        if any(t.lower() in team.lower() for t in SERIEA_TEAMS): return "ITA-Serie A"
        if any(t.lower() in team.lower() for t in BUNDESLIGA_TEAMS): return "GER-Bundesliga"
        if any(t.lower() in team.lower() for t in LIGUE1_TEAMS): return "FRA-Ligue 1"

    return "DEFAULT"


def _find_prob_for_market(market: str, true_probs: dict) -> float | None:
    if market in true_probs: return true_probs[market]
    m = market.lower().strip()
    mappings = {
        "mas de 2.5 goles": "Mas de 2.5", "más de 2.5 goles": "Mas de 2.5",
        "mas de 1.5 goles": "Mas de 1.5", "más de 1.5 goles": "Mas de 1.5",
        "mas de 3.5 goles": "Mas de 3.5", "más de 3.5 goles": "Mas de 3.5",
        "menos de 2.5 goles": "Menos de 2.5", "menos de 1.5 goles": "Menos de 1.5",
        "ambos anotan: si": "Ambos Anotan: Si", "ambos anotan: sí": "Ambos Anotan: Si",
        "ambos anotan: no": "Ambos Anotan: No",
        "gana local": "Gana Local", "gana visita": "Gana Visita", "empate": "Empate",
        "1x": "1X", "x2": "X2", "12": "12",
        "ht gana local": "HT Gana Local", "ht empate": "HT Empate",
        "ht gana visita": "HT Gana Visita",
        "corners mas de 9.5": "Corners Mas de 9.5",
        "corners mas de 10.5": "Corners Mas de 10.5",
        "tarjetas mas de 3.5": "Tarjetas Mas de 3.5",
        "tarjetas mas de 4.5": "Tarjetas Mas de 4.5",
    }
    mapped = mappings.get(m)
    if mapped and mapped in true_probs: return true_probs[mapped]
    for key, val in true_probs.items():
        if key.lower() in m or m in key.lower(): return val
    return None


def _get_market_icon(market: str) -> str:
    m = market.lower()
    if "banker" in m:                    return "💎"
    if "nba" in m or "puntos nba" in m:  return "🏀"
    if "mas de" in m or "menos de" in m: return "🎯"
    if "ambos anotan" in m:              return "⚽"
    return "⚽"


async def run_advanced_pipeline(target_date: str, current_bankroll: float) -> list:
    """
    Pipeline v4.1:
    1. Understat xG + ClubElo
    2. H2H via API-Football
    3. AdvancedPoissonModel → probabilidades para TODOS los mercados
    4. Evalua mercados de OddsAPI (1X2, OU, BTTS)
    5. Evalua mercados de Rushbet directamente (corners, tarjetas, doble oportunidad)
    6. Filtra EV+ con prob >= 60%
    7. Alinea odds con Rushbet
    """
    import config
    from modules.advanced_model import MatchAnalyzer
    from modules.risk import RiskEngine
    from modules.odds_api import OddsAPI
    from modules.rushbet_scraper import align_odds_with_rushbet, get_rushbet_odds_async
    from modules.fbref_engine import fbref_engine
    from modules.injuries_engine import get_injuries_engine

    # ── Understat / ClubElo (opcional — si falla continua sin datos xG elite) ──
    xg_matches_today = pd.DataFrame()
    stats_df         = pd.DataFrame()
    injuries_e       = None
    data_engine      = None
    try:
        from modules.data import DataEngine
        data_engine  = DataEngine(season='2025')
        stats_df     = data_engine.get_season_xg_stats()
        injuries_e   = get_injuries_engine()
        schedule     = data_engine.understat.read_schedule().reset_index()
        if isinstance(schedule.columns, pd.MultiIndex):
            schedule.columns = ['_'.join(str(i) for i in col if i).strip().lower()
                                for col in schedule.columns]
        else:
            schedule.columns = [str(c).lower() for c in schedule.columns]
        date_col = 'datetime' if 'datetime' in schedule.columns else 'date'
        schedule['match_time_local'] = (
            pd.to_datetime(schedule[date_col], utc=True)
            .dt.tz_convert(config.TIMEZONE)
        )
        schedule['date_str'] = schedule['match_time_local'].dt.strftime('%Y-%m-%d')
        xg_matches_today     = schedule[schedule['date_str'] == target_date]
        logger.info(f"Partidos elite ({target_date}): {len(xg_matches_today)}")
    except Exception as e:
        logger.warning(f"Understat/ClubElo no disponible (modo Rushbet-only): {e}")

    # ── OddsAPI (opcional — si falla o limite agotado, continua con Rushbet) ──
    soccer_odds = {}
    try:
        odds_api  = OddsAPI()
        live_odds = odds_api.get_all_sports_odds()
        if live_odds not in ["MOCK", "API_LIMIT"]:
            soccer_odds = live_odds.get('soccer', {})
            logger.info(f"OddsAPI: {len(soccer_odds)} partidos de futbol")
        else:
            logger.warning(f"OddsAPI no disponible ({live_odds}) — usando solo Rushbet")
    except Exception as e:
        logger.warning(f"OddsAPI error: {e} — usando solo Rushbet")

    # Rushbet — obtener todos los mercados incluyendo corners y tarjetas
    logger.info("Obteniendo mercados completos de Rushbet (corners, tarjetas, etc.)...")
    rushbet_data   = await get_rushbet_odds_async(sport_filter="soccer", fetch_full_markets=True)
    rushbet_soccer = rushbet_data.get("soccer", [])
    logger.info(f"Rushbet: {len(rushbet_soccer)} partidos con mercados completos")

    opportunities = []
    processed     = set()

    # ── LIGAS ELITE (solo si Understat disponible) ──
    for _, match in (xg_matches_today.iterrows() if not xg_matches_today.empty else iter([])):
        home = match['home_team']
        away = match['away_team']

        h_stats = stats_df[stats_df['team'] == home]
        a_stats = stats_df[stats_df['team'] == away]
        if h_stats.empty or a_stats.empty:
            continue

        match_time   = match['match_time_local'].strftime('%H:%M')
        base_home_xg = (h_stats['xG_avg'].values[0] + a_stats['xGA_avg'].values[0]) / 2
        base_away_xg = (a_stats['xG_avg'].values[0] + h_stats['xGA_avg'].values[0]) / 2
        league       = _get_league_for_team(home, away, schedule)

        # Stats de corners y tarjetas por liga
        home_corner_stats = fbref_engine.get_corner_stats(home, league)
        away_corner_stats = fbref_engine.get_corner_stats(away, league)
        home_card_stats   = fbref_engine.get_card_stats(home, league)
        away_card_stats   = fbref_engine.get_card_stats(away, league)

        # H2H
        h2h = injuries_e.get_h2h(home, away) if injuries_e else {}

        # Odds de OddsAPI
        match_data = _find_match_odds(home, away, soccer_odds)
        match_odds = match_data.get('odds', {})
        processed.add(f"{home} vs {away}")

        # Modelo completo
        analyzer = MatchAnalyzer(
            home_team=home, away_team=away,
            base_home_xg=base_home_xg, base_away_xg=base_away_xg,
            league=league,
            home_corner_stats=home_corner_stats, away_corner_stats=away_corner_stats,
            home_card_stats=home_card_stats,     away_card_stats=away_card_stats,
            h2h_data=h2h,
        )
        true_probs = analyzer.get_all_probabilities()

        # ELO — Banker
        elo_prob = data_engine.get_elo_prob(home, away) if data_engine else 0.0
        if elo_prob > 0.75 and match_odds.get("Gana Local", 0) > 1.25:
            opportunities.append({
                "sport": "💎", "time": match_time,
                "home": home, "away": away,
                "market": "Gana Local (BANKER)", "odds": match_odds["Gana Local"],
                "prob": elo_prob * 100, "ev": 10.0,
                "stake_amount": current_bankroll * 0.05,
                "reason": f"ALTA CONFIANZA ELO: {elo_prob*100:.1f}% probabilidad historica.",
                "confidence": "🔥 MUY ALTA",
            })

        # ── Mercados de OddsAPI (1X2, Over/Under, BTTS) ──
        for market, odds in match_odds.items():
            if odds < config.MIN_ODDS: continue
            if not _is_allowed_market(market): continue  # Solo goles y 1X2
            p_real = _find_prob_for_market(market, true_probs)
            if p_real is None or p_real < config.MIN_PROBABILITY: continue
            ev = RiskEngine.expected_value(p_real, odds)
            if ev <= config.MIN_EV_THRESHOLD: continue
            stake = RiskEngine.calculate_kelly_stake(p_real, odds, current_bankroll)
            if stake <= 0: continue

            confidence = analyzer.get_confidence_score(market, p_real)
            reason     = analyzer.build_analysis_text(market, p_real, odds, ev * 100)
            opportunities.append({
                "sport": _get_market_icon(market), "time": match_time,
                "home": home, "away": away, "market": market,
                "odds": odds, "prob": p_real * 100, "ev": ev * 100,
                "stake_amount": stake, "reason": reason,
                "confidence": confidence, "league": league,
            })

        # ── Mercados de Rushbet (corners, tarjetas, doble oportunidad) ──
        # Buscar el partido en Rushbet
        from modules.rushbet_scraper import _match_rushbet_game
        rb_game = _match_rushbet_game(home, away, rushbet_soccer)

        if rb_game:
            rb_odds = rb_game.get("odds", {})

            # Definir mercados adicionales a evaluar con sus claves en Rushbet
            extra_markets = {
                # Doble oportunidad
                "1X":                    ("1X",                  true_probs.get("1X", 0)),
                "X2":                    ("X2",                  true_probs.get("X2", 0)),
                "12":                    ("12",                  true_probs.get("12", 0)),
                # BTTS
                "Ambos Anotan: Si":      ("Ambos Anotan: Si",    true_probs.get("Ambos Anotan: Si", 0)),
                "Ambos Anotan: No":      ("Ambos Anotan: No",    true_probs.get("Ambos Anotan: No", 0)),
                # Corners
                "Corners Mas de 9.5":    ("Mas de 9.5",          true_probs.get("Corners Mas de 9.5", 0)),
                "Corners Menos de 9.5":  ("Menos de 9.5",        true_probs.get("Corners Menos de 9.5", 0)),
                "Corners Mas de 10.5":   ("Mas de 10.5",         true_probs.get("Corners Mas de 10.5", 0)),
                # Tarjetas
                "Tarjetas Mas de 3.5":   ("Mas de 3.5",          true_probs.get("Tarjetas Mas de 3.5", 0)),
                "Tarjetas Menos de 3.5": ("Menos de 3.5",        true_probs.get("Tarjetas Menos de 3.5", 0)),
                "Tarjetas Mas de 4.5":   ("Mas de 4.5",          true_probs.get("Tarjetas Mas de 4.5", 0)),
            }

            for market_label, (rb_key, p_real) in extra_markets.items():
                if p_real < config.MIN_PROBABILITY: continue

                # Buscar la odd en Rushbet
                rb_odd = None
                for k, v in rb_odds.items():
                    if rb_key.lower() in k.lower() or k.lower() in rb_key.lower():
                        rb_odd = v
                        break

                if not rb_odd or rb_odd < config.MIN_ODDS: continue

                ev = RiskEngine.expected_value(p_real, rb_odd)
                if ev <= config.MIN_EV_THRESHOLD: continue

                stake = RiskEngine.calculate_kelly_stake(p_real, rb_odd, current_bankroll)
                if stake <= 0: continue

                # Evitar duplicados con lo que ya vino de OddsAPI
                already = any(
                    o["home"] == home and o["away"] == away and
                    o["market"].lower() == market_label.lower()
                    for o in opportunities
                )
                if already: continue

                confidence = analyzer.get_confidence_score(market_label, p_real)
                reason     = analyzer.build_analysis_text(market_label, p_real, rb_odd, ev * 100)

                opportunities.append({
                    "sport": _get_market_icon(market_label), "time": match_time,
                    "home": home, "away": away,
                    "market": market_label, "odds": rb_odd,
                    "prob": p_real * 100, "ev": ev * 100,
                    "stake_amount": stake, "reason": reason,
                    "confidence": confidence, "league": league,
                    "source": "rushbet",  # Ya tienen odds de Rushbet
                    "odds_api_value": None,
                })

    # ── RESTO DEL MUNDO (MarketConsensus) — todas las ligas ──
    from modules.model import MarketConsensusModel
    for match_name, match_data in soccer_odds.items():
        if match_data.get('date') != target_date: continue
        if match_name in processed: continue
        match_odds = match_data.get('odds', {})
        avg_odds   = match_data.get('avg_odds', {})
        match_time = match_data.get('time', '00:00')
        league_id  = match_data.get('league', '')
        try: home, away = match_name.split(" vs ")
        except: continue

        # EV minimo: ligas elite 3%, resto 4%
        elite_leagues = {'soccer_epl','soccer_spain_la_liga','soccer_italy_serie_a',
                         'soccer_germany_bundesliga','soccer_france_ligue_one',
                         'soccer_uefa_champs_league'}
        ev_min = config.MIN_EV_THRESHOLD if league_id in elite_leagues else 0.04

        for market, odds in match_odds.items():
            if odds < config.MIN_ODDS: continue
            if not _is_allowed_market(market): continue
            p_real = MarketConsensusModel.get_true_probability(market, avg_odds)
            if p_real >= config.MIN_PROBABILITY:
                ev = RiskEngine.expected_value(p_real, odds)
                if ev > ev_min:
                    stake = RiskEngine.calculate_kelly_stake(p_real, odds, current_bankroll)
                    if stake > 0:
                        implied = (1 / odds) * 100
                        # Detectar si es partido FIFA/selecciones
                        is_fifa = any(x in league_id for x in ['world_cup','qualifying','championship_qual'])
                        sport_icon = "🌍" if is_fifa else _get_market_icon(market)
                        opportunities.append({
                            "sport":      sport_icon,
                            "time":       match_time,
                            "home":       home,
                            "away":       away,
                            "market":     market,
                            "odds":       odds,
                            "prob":       p_real * 100,
                            "ev":         ev * 100,
                            "stake_amount": stake,
                            "reason":     f"Ineficiencia de mercado. Implicita {implied:.1f}% vs Real {p_real*100:.1f}%",
                            "confidence": "🟡 MEDIA-ALTA" if p_real >= 0.65 else "⚪ MEDIA",
                            "league":     league_id,
                        })

    # ── NBA (Ball Don't Lie API — gratuita) ──
    try:
        import asyncio
        from modules.balldontlie_engine import BallDontLieEngine
        bdl = BallDontLieEngine(api_key=config.BALLDONTLIE_API_KEY)
        nba_picks = await asyncio.to_thread(
            bdl.get_nba_picks,
            current_bankroll,
            config.MIN_PROBABILITY,
            config.MIN_EV_THRESHOLD,
        )
        if nba_picks:
            logger.info(f"NBA picks (Ball Don't Lie): {len(nba_picks)}")
            opportunities.extend(nba_picks)
        else:
            logger.info("NBA: sin picks con EV positivo hoy.")
    except Exception as e:
        logger.warning(f"NBA pipeline error (no critico): {e}")

    opportunities.sort(key=lambda x: x["ev"], reverse=True)
    logger.info(f"Oportunidades antes de alineacion final: {len(opportunities)}")

    # Alinear con Rushbet (solo picks de futbol — los de NBA conservan sus odds)
    soccer_opps = [o for o in opportunities if o.get("sport") != "🏀"]
    nba_opps    = [o for o in opportunities if o.get("sport") == "🏀"]

    final_soccer = await align_odds_with_rushbet(soccer_opps, rushbet_games=rushbet_soccer)
    final = final_soccer + nba_opps
    final.sort(key=lambda x: x["ev"], reverse=True)

    logger.info(f"Total picks validos: {len(final)} ({len(final_soccer)} futbol + {len(nba_opps)} NBA)")
    return final