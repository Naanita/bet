# modules/pipeline_v5.py — Pipeline multi-deporte 100% Rushbet
# Sin dependencia de OddsAPI
# Deportes: Futbol (todas las ligas), Baloncesto, Tenis

import asyncio
import logging
import re as _re
import pandas as pd

logger = logging.getLogger(__name__)

# ── Filtros de partidos reales (fuera de la función para no recrearlos en cada llamada) ──
_EXCLUDE_TAGS = (
    "(f)", "(b)", "futsal", "beach", "sala", "indoor",
    "e-sports", "esports", "virtual", "cyber",
)
_ESPORTS_RE = _re.compile(r"\([A-Za-z0-9_]+\)")  # tags como (Rodja), (borees)


def _is_real_match(g: dict) -> bool:
    home_l = g["home"].lower()
    away_l = g["away"].lower()
    if any(tag in home_l or tag in away_l for tag in _EXCLUDE_TAGS):
        return False
    if _ESPORTS_RE.search(g["home"]) or _ESPORTS_RE.search(g["away"]):
        return False
    return True


def _match_is_future(game: dict, now_local: "pd.Timestamp", tz_str: str, buffer_min: int = 30) -> bool:
    """True si el partido aún no ha comenzado (con buffer en minutos)."""
    try:
        kickoff = pd.Timestamp(f"{game['date']} {game.get('time', '00:00')}", tz=tz_str)
        return kickoff > now_local + pd.Timedelta(minutes=buffer_min)
    except Exception:
        return True


async def run_pipeline_v5(target_date: str, current_bankroll: float) -> list:
    """
    Pipeline v5 — Rushbet-only, multi-deporte.

    Flujo:
    1. Scraping completo de Rushbet (todos los deportes)
    2. Para futbol elite (5 ligas): Poisson + xG de Understat si disponible
    3. Para futbol resto: KambiConsensus (lambda inferido del OU)
    4. Para basketball: KambiConsensus + Ball Dont Lie blend (si hay API key)
    5. Para tenis: KambiConsensus 2-way
    6. Filtrar por EV >= MIN_EV_THRESHOLD y prob >= MIN_PROBABILITY
    7. Ordenar por EV desc
    """
    import config
    now_local = pd.Timestamp.now(tz=config.TIMEZONE)

    from modules.rushbet_scraper import get_rushbet_odds_async
    from modules.kambi_consensus import (
        get_soccer_probs_from_rushbet,
        get_basketball_probs,
        get_tennis_probs,
        evaluate_picks,
        LEAGUE_GOAL_AVERAGES,
    )
    from modules.risk import RiskEngine, get_rolling_win_rate
    from modules.rushbet_scraper import _match_rushbet_game

    opportunities = []

    # Leer historial una sola vez para toda la ejecución del pipeline
    _rolling_wr, _db_count = get_rolling_win_rate()
    _n_samples = max(_db_count, 20)

    # ─────────────────────────────────────────────
    # 1. Scraping Rushbet — TODOS los deportes
    # ─────────────────────────────────────────────
    logger.info("Scraping Rushbet (todos los deportes)...")
    rushbet_data = await get_rushbet_odds_async(sport_filter=None, fetch_full_markets=True)

    soccer_games     = rushbet_data.get("soccer", [])
    basketball_games = rushbet_data.get("basketball", [])
    tennis_games     = rushbet_data.get("tennis", [])

    logger.info(
        f"Rushbet — Futbol: {len(soccer_games)} | "
        f"Basketball: {len(basketball_games)} | "
        f"Tenis: {len(tennis_games)}"
    )

    # ─────────────────────────────────────────────
    # 2. Understat / Poisson elite (opcional)
    # ─────────────────────────────────────────────
    elite_pairs = set()
    try:
        from modules.data import DataEngine
        from modules.advanced_model import MatchAnalyzer
        from modules.fbref_engine import fbref_engine
        from modules.injuries_engine import get_injuries_engine

        data_engine = DataEngine(season='2025')
        stats_df    = data_engine.get_season_xg_stats()
        injuries_e  = get_injuries_engine()

        schedule = data_engine.understat.read_schedule().reset_index()
        schedule.columns = [str(c).lower() for c in schedule.columns]
        date_col = 'datetime' if 'datetime' in schedule.columns else 'date'
        schedule['match_time_local'] = (
            pd.to_datetime(schedule[date_col], utc=True).dt.tz_convert(config.TIMEZONE)
        )
        schedule['date_str'] = schedule['match_time_local'].dt.strftime('%Y-%m-%d')
        elite_today = schedule[
            (schedule['date_str'] == target_date) &
            (schedule['match_time_local'] > now_local + pd.Timedelta(minutes=30))
        ]

        logger.info(f"Partidos elite Understat ({target_date}): {len(elite_today)}")

        for _, match in elite_today.iterrows():
            home = match['home_team']
            away = match['away_team']

            h_stats = stats_df[stats_df['team'] == home]
            a_stats = stats_df[stats_df['team'] == away]
            if h_stats.empty or a_stats.empty:
                continue

            match_time   = match['match_time_local'].strftime('%H:%M')
            base_home_xg = (h_stats['xG_avg'].values[0] + a_stats['xGA_avg'].values[0]) / 2
            base_away_xg = (a_stats['xG_avg'].values[0] + h_stats['xGA_avg'].values[0]) / 2

            from modules.pipeline_v4 import _get_league_for_team
            league = _get_league_for_team(home, away, schedule)

            home_corner = fbref_engine.get_corner_stats(home, league)
            away_corner = fbref_engine.get_corner_stats(away, league)
            home_card   = fbref_engine.get_card_stats(home, league)
            away_card   = fbref_engine.get_card_stats(away, league)
            h2h         = injuries_e.get_h2h(home, away) if injuries_e else {}

            analyzer   = MatchAnalyzer(
                home_team=home, away_team=away,
                base_home_xg=base_home_xg, base_away_xg=base_away_xg,
                league=league,
                home_corner_stats=home_corner, away_corner_stats=away_corner,
                home_card_stats=home_card,     away_card_stats=away_card,
                h2h_data=h2h,
            )
            true_probs = analyzer.get_all_probabilities()

            # ELO Banker
            elo_prob = data_engine.get_elo_prob(home, away)
            if elo_prob > 0.75:
                rb_game = _match_rushbet_game(home, away, soccer_games)
                if rb_game:
                    rb_local = rb_game.get("odds", {}).get("Gana Local", 0)
                    if rb_local >= config.MIN_ODDS:
                        ev = RiskEngine.expected_value(elo_prob, rb_local)
                        if ev >= config.MIN_EV_THRESHOLD:
                            stake = RiskEngine.calculate_kelly_stake(elo_prob, rb_local, current_bankroll)
                            opportunities.append({
                                "sport": "💎", "time": match_time, "home": home, "away": away,
                                "market": "Gana Local (BANKER)",
                                "odds": rb_local, "prob": round(elo_prob * 100, 1),
                                "ev": round(ev * 100, 1), "stake_amount": stake,
                                "reason": f"BANKER ELO: {elo_prob*100:.1f}% historico",
                                "confidence": "🔥 MUY ALTA", "source": "rushbet",
                                "event_id": rb_game.get("event_id"),
                            })

            # Buscar en Rushbet y evaluar
            rb_game = _match_rushbet_game(home, away, soccer_games)
            if rb_game:
                picks = evaluate_picks(
                    game={**rb_game, "time": match_time},
                    true_probs=true_probs,
                    min_ev=config.MIN_EV_THRESHOLD,
                    min_prob=config.MIN_PROBABILITY,
                    min_odds=config.MIN_ODDS,
                    current_bankroll=current_bankroll,
                    sport="soccer",
                    resolved_count=_n_samples,
                )
                opportunities.extend(picks)
                elite_pairs.add(f"{home} vs {away}")

    except Exception as e:
        logger.warning(f"Understat no disponible, continuando con Rushbet-only: {e}")

    # ─────────────────────────────────────────────
    # 3. Futbol — resto de ligas (KambiConsensus)
    # ─────────────────────────────────────────────
    logger.info(f"Evaluando futbol Rushbet ({len(soccer_games)} partidos)...")
    today_soccer = [
        g for g in soccer_games
        if g.get("date") == target_date
        and f"{g['home']} vs {g['away']}" not in elite_pairs
        and _is_real_match(g)
        and _match_is_future(g, now_local, config.TIMEZONE)
    ]
    logger.info(f"  Futbol hoy (no elite): {len(today_soccer)}")

    for game in today_soccer:
        odds  = game.get("odds", {})
        # Detectar liga aproximada por nombre de equipos
        league = _infer_league(game["home"], game["away"])

        true_probs = get_soccer_probs_from_rushbet(odds, league)
        if not true_probs:
            continue

        # Usar siempre el umbral global de config
        ev_min = config.MIN_EV_THRESHOLD

        picks = evaluate_picks(
            game=game,
            true_probs=true_probs,
            min_ev=config.MIN_EV_THRESHOLD,
            min_prob=config.MIN_PROBABILITY,
            min_odds=config.MIN_ODDS,
            current_bankroll=current_bankroll,
            sport="soccer",
            resolved_count=_n_samples,
        )
        opportunities.extend(picks)

    # ─────────────────────────────────────────────
    # 4. Basketball — vig removal sobre cuotas Rushbet
    # ─────────────────────────────────────────────
    today_bball = [
        g for g in basketball_games
        if g.get("date") == target_date
        and _match_is_future(g, now_local, config.TIMEZONE)
    ]
    logger.info(f"Basketball hoy: {len(today_bball)}")

    for game in today_bball:
        true_probs = get_basketball_probs(game.get("odds", {}))
        if not true_probs:
            continue
        picks = evaluate_picks(
            game=game,
            true_probs=true_probs,
            min_ev=config.MIN_EV_THRESHOLD,
            min_prob=config.MIN_PROBABILITY,
            min_odds=config.MIN_ODDS,
            current_bankroll=current_bankroll,
            sport="basketball",
            resolved_count=_n_samples,
        )
        opportunities.extend(picks)

    # ─────────────────────────────────────────────
    # 5. Tenis — vig removal sobre cuotas Rushbet
    # ─────────────────────────────────────────────
    today_tennis = [
        g for g in tennis_games
        if g.get("date") == target_date
        and _match_is_future(g, now_local, config.TIMEZONE)
    ]
    logger.info(f"Tenis hoy: {len(today_tennis)}")

    for game in today_tennis:
        true_probs = get_tennis_probs(game.get("odds", {}))
        if not true_probs:
            continue
        picks = evaluate_picks(
            game=game,
            true_probs=true_probs,
            min_ev=config.MIN_EV_THRESHOLD,
            min_prob=config.MIN_PROBABILITY,
            min_odds=config.MIN_ODDS,
            current_bankroll=current_bankroll,
            sport="tennis",
            resolved_count=_n_samples,
        )
        opportunities.extend(picks)

    # ─────────────────────────────────────────────
    # 7. Deduplicar y ordenar (múltiples mercados por partido)
    # ─────────────────────────────────────────────
    # Deduplicar por home+away+market (un pick por mercado por partido)
    seen   = set()
    unique = []
    for p in opportunities:
        key = f"{p['home']} vs {p['away']}_{p['market']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Ordenar por EV desc
    unique.sort(key=lambda x: x["ev"], reverse=True)

    # Limitar a máximo 3 mercados por partido (evita sobrecargar con picks del mismo juego)
    markets_per_game: dict = {}
    filtered = []
    for p in unique:
        game_key = f"{p['home']} vs {p['away']}"
        count = markets_per_game.get(game_key, 0)
        if count < 3:
            markets_per_game[game_key] = count + 1
            filtered.append(p)
    unique = filtered

    # Limitar a los TOP 40 picks individuales del dia (mayor EV)
    MAX_DAILY_PICKS = 40
    unique = unique[:MAX_DAILY_PICKS]

    # ─────────────────────────────────────────────
    # 6. Apuestas combinadas (parlays / acumuladores)
    # ─────────────────────────────────────────────
    try:
        from modules.parlay_engine import generate_parlays
        parlays = generate_parlays(unique, current_bankroll=current_bankroll)
        if parlays:
            logger.info(f"Combinadas generadas: {len(parlays)}")
            unique = unique + parlays
    except Exception as e:
        logger.warning(f"Parlay engine falló: {e}")

    logger.info(
        f"Pipeline v5 — Total picks: {len(unique)} | "
        f"Individuales: {sum(1 for p in unique if not p.get('is_parlay'))} | "
        f"Combinadas: {sum(1 for p in unique if p.get('is_parlay'))} | "
        f"Basketball: {sum(1 for p in unique if p.get('sport') == '🏀')} | "
        f"Tenis: {sum(1 for p in unique if p.get('sport') == '🎾')}"
    )
    return unique


def _infer_league(home: str, away: str) -> str:
    """Detecta la liga aproximada por nombre de equipos conocidos."""
    from modules.pipeline_v4 import _get_league_for_team
    import pandas as pd
    try:
        return _get_league_for_team(home, away, pd.DataFrame())
    except Exception:
        return "DEFAULT"
