# modules/rushbet_scraper.py v5.1
# Extrae odds completas de Rushbet via Kambi API
# Incluye: 1X2, Over/Under, BTTS, Corners, Tarjetas, Doble Oportunidad

import json
import re
import asyncio
import logging
import requests
from datetime import datetime
from difflib import SequenceMatcher

import pytz

_BOGOTA = pytz.timezone("America/Bogota")

logger = logging.getLogger(__name__)

KAMBI_BASE     = "https://us1.offering-api.kambicdn.com/offering/v2018/rsico"
KAMBI_LISTVIEW = f"{KAMBI_BASE}/listView/all.json"
KAMBI_BETOFFER = f"{KAMBI_BASE}/betoffer/event/{{event_id}}.json"
KAMBI_PARAMS   = {
    "lang": "es_ES", "market": "CO",
    "client_id": "2", "channel_id": "1",
    "ncid": "1", "useCombined": "true",
}
KAMBI_PARAMS_EVENT = {
    "lang": "es_ES", "market": "CO",
    "client_id": "2", "channel_id": "1",
}
KAMBI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
    "Referer":    "https://www.rushbet.co/",
    "Origin":     "https://www.rushbet.co",
}

SPORT_MAP = {
    "FOOTBALL":   "soccer",
    "BASKETBALL": "basketball",
    "TENNIS":     "tennis",
}

TEAM_NAME_MAP = {
    "Manchester City":     "Manchester City",
    "Manchester United":   "Manchester United",
    "Arsenal":             "Arsenal",
    "Chelsea":             "Chelsea",
    "Liverpool":           "Liverpool",
    "Tottenham Hotspur":   "Tottenham",
    "Tottenham":           "Tottenham",
    "Newcastle United":    "Newcastle United",
    "Aston Villa":         "Aston Villa",
    "West Ham United":     "West Ham",
    "West Ham":            "West Ham",
    "Real Madrid":         "Real Madrid",
    "Barcelona":           "Barcelona",
    "Atletico Madrid":     "Atletico de Madrid",
    "Sevilla":             "Sevilla",
    "Valencia":            "Valencia",
    "Athletic Club":       "Athletic Club",
    "Inter Milan":         "Inter",
    "AC Milan":            "Milan",
    "Juventus":            "Juventus",
    "Napoli":              "Napoles",
    "AS Roma":             "Roma",
    "Roma":                "Roma",
    "Bayern Munich":       "Bayern Munich",
    "Borussia Dortmund":   "Borussia Dortmund",
    "RB Leipzig":          "RB Leipzig",
    "Paris Saint-Germain": "PSG",
    "Paris Saint Germain": "PSG",
    "Nice":                "Niza",
    "Monaco":              "AS Monaco",
    "Lyon":                "Lyon",
    "Marseille":           "Marsella",
    "Atletico Nacional":   "Atletico Nacional",
    "Millonarios":         "Millonarios",
    "Junior":              "Junior",
    "River Plate":         "River Plate",
    "Boca Juniors":        "Boca Juniors",
}


def _rushbet_event_url(event_id: int) -> str:
    """URL directa al partido en Rushbet."""
    if event_id:
        return f"https://www.rushbet.co/?page=sportsbook#event/{event_id}"
    return "https://www.rushbet.co/?page=sportsbook"


def _rushbet_betslip_url(outcome_id: str, event_id: int = None) -> str:
    """
    URL que abre Rushbet con el boleto pre-llenado.
    Kambi soporta: #add-to-betslip/OUTCOME_ID
    """
    if outcome_id:
        return f"https://www.rushbet.co/?page=sportsbook#add-to-betslip/{outcome_id}"
    if event_id:
        return f"https://www.rushbet.co/?page=sportsbook#event/{event_id}"
    return "https://www.rushbet.co/?page=sportsbook"


def _normalize(name: str) -> str:
    replacements = {
        'a': 'áàäâ', 'e': 'éèëê', 'i': 'íìïî',
        'o': 'óòöô', 'u': 'úùüû', 'n': 'ñ',
    }
    name = name.lower().strip()
    for base, variants in replacements.items():
        for v in variants:
            name = name.replace(v, base)
    return re.sub(r'[^a-z0-9]', '', name)


def _team_score(t1: str, t2: str) -> float:
    n1, n2 = _normalize(t1), _normalize(t2)
    if n1 == n2: return 1.0
    if n1 in n2 or n2 in n1: return 0.92
    return SequenceMatcher(None, n1, n2).ratio()


def _translate_team(name: str) -> str:
    return TEAM_NAME_MAP.get(name, name)


def _match_rushbet_game(api_home: str, api_away: str, rushbet_games: list) -> dict | None:
    api_home_rb = _translate_team(api_home)
    api_away_rb = _translate_team(api_away)
    best, best_score = None, 0.0
    for g in rushbet_games:
        sh = _team_score(api_home_rb, g.get("home", ""))
        sa = _team_score(api_away_rb, g.get("away", ""))
        score = min(sh, sa) * 0.5 + (sh + sa) / 2 * 0.5
        if score > best_score:
            best_score = score
            best = g
    if best_score >= 0.65:
        logger.debug(f"Match: {api_home} vs {api_away} -> {best['home']} vs {best['away']} ({best_score:.2f})")
        return best
    return None


def _normalize_market(m: str) -> str:
    m = m.lower().strip()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n')]:
        m = m.replace(a, b)
    return m


def _find_market_in_odds(market: str, odds_dict: dict) -> float | None:
    if not odds_dict: return None
    if market in odds_dict: return odds_dict[market]
    mn = _normalize_market(market)
    for k, v in odds_dict.items():
        if _normalize_market(k) == mn: return v
    for k, v in odds_dict.items():
        kn = _normalize_market(k)
        if mn in kn or kn in mn: return v
    return None


def _kambi_odd_to_decimal(odds_int: int) -> float:
    return round(odds_int / 1000, 3)


def _parse_full_event(home: str, away: str, sport: str,
                       match_time: str, match_date: str,
                       event_id: int, offers: list) -> dict | None:
    """
    Parsea todos los betOffers de un evento.
    Extrae: 1X2, Doble Oportunidad, Over/Under goles, BTTS,
            Corners Over/Under, Tarjetas Over/Under.
    """
    odds_dict   = {}
    outcome_ids = {}

    for offer in offers:
        criterion_label = offer.get("criterion", {}).get("label", "")
        criterion_en    = offer.get("criterion", {}).get("englishLabel", "")
        outcomes        = offer.get("outcomes", [])
        en_lower        = criterion_en.lower()
        es_lower        = criterion_label.lower()

        # ── 1X2 ──
        if criterion_en in ["Full Time", "Match Result"] or \
           criterion_label in ["Resultado Final", "1X2"]:
            for o in outcomes:
                otype = o.get("type", "")
                raw   = o.get("odds", 0)
                if not raw or o.get("status") == "SUSPENDED": continue
                if otype == "OT_ONE":   odds_dict["Gana Local"]  = _kambi_odd_to_decimal(raw)
                elif otype == "OT_CROSS": odds_dict["Empate"]    = _kambi_odd_to_decimal(raw)
                elif otype == "OT_TWO": odds_dict["Gana Visita"] = _kambi_odd_to_decimal(raw)

        # ── Doble Oportunidad ──
        elif criterion_en == "Double Chance" or "doble oportunidad" in es_lower:
            for o in outcomes:
                raw   = o.get("odds", 0)
                label = o.get("label", "")
                if not raw: continue
                if label == "1X":   odds_dict["1X"] = _kambi_odd_to_decimal(raw)
                elif label == "X2": odds_dict["X2"] = _kambi_odd_to_decimal(raw)
                elif label == "12": odds_dict["12"] = _kambi_odd_to_decimal(raw)

        # ── Total de Goles PARTIDO COMPLETO (Over/Under) ──
        # Usa el campo `line` de Kambi. Para distinguir partido vs equipo aplicamos
        # un techo de cuota por línea: el total del partido SIEMPRE es más probable
        # que el de un equipo individual, por lo que su cuota de Over es más baja.
        # Techo conservador:  O/U 0.5 partido ≤1.30 | 1.5 ≤2.10 | 2.5 ≤2.80 | 3.5 ≤7.0 | 4.5 ≤15.0
        elif criterion_en in ["Total Goals", "Goals Over/Under"] or (
             "total goals" in en_lower and "half" not in en_lower and
             "team" not in en_lower and "1st" not in en_lower and "2nd" not in en_lower and
             "home" not in en_lower and "away" not in en_lower):
            _FULL_MATCH_OVER_CAP = {0.5: 1.30, 1.5: 2.10, 2.5: 2.80, 3.5: 7.0, 4.5: 15.0, 5.5: 30.0}
            for o in outcomes:
                raw       = o.get("odds", 0)
                otype     = o.get("type", "")
                line_val  = o.get("line", 0)
                if not raw or not line_val: continue
                decimal  = _kambi_odd_to_decimal(raw)
                line_pts = round(line_val / 1000, 1)
                if line_pts not in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
                    continue
                # Sanity check: rechaza si la cuota de Over supera el cap del partido completo
                if otype == "OT_OVER" and decimal > _FULL_MATCH_OVER_CAP.get(line_pts, 30.0):
                    logger.debug(
                        f"O/U {line_pts} Over={decimal} > cap={_FULL_MATCH_OVER_CAP.get(line_pts)} "
                        f"— probable mercado de equipo, ignorado como total del partido"
                    )
                    continue
                if otype == "OT_OVER":
                    key = f"Mas de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")
                elif otype == "OT_UNDER":
                    key = f"Menos de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")

        # ── Goles por Equipo (Home / Away Team Goals) ──
        # Mercados: "Equipo local anota más/menos de X.5 goles" — cuotas típicas 1.40-2.50
        elif sport == "soccer" and (
             "home" in en_lower or "away" in en_lower or
             "local" in es_lower or "visita" in es_lower) and (
             "goal" in en_lower or "gol" in es_lower):
            is_home = "home" in en_lower or "local" in es_lower
            prefix  = "Local" if is_home else "Visita"
            for o in outcomes:
                raw      = o.get("odds", 0)
                otype    = o.get("type", "")
                line_val = o.get("line", 0)
                if not raw or not line_val: continue
                decimal  = _kambi_odd_to_decimal(raw)
                line_pts = round(line_val / 1000, 1)
                if line_pts not in (0.5, 1.5, 2.5):
                    continue
                if otype == "OT_OVER":
                    key = f"{prefix}: Mas de {line_pts} Goles"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")
                elif otype == "OT_UNDER":
                    key = f"{prefix}: Menos de {line_pts} Goles"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")

        # ── BTTS ──
        elif criterion_en in ["Both Teams to Score"] or \
             "ambos" in es_lower and "anotan" in es_lower:
            for o in outcomes:
                raw   = o.get("odds", 0)
                label = o.get("label", "").lower()
                oid   = o.get("id", 0)
                if not raw: continue
                if "si" in label or "yes" in label or "sí" in label:
                    odds_dict["Ambos Anotan: Si"] = _kambi_odd_to_decimal(raw)
                    outcome_ids["__oid_Ambos Anotan: Si"] = oid
                elif "no" in label:
                    odds_dict["Ambos Anotan: No"] = _kambi_odd_to_decimal(raw)
                    outcome_ids["__oid_Ambos Anotan: No"] = oid

        # ── Corners (Total de Tiros de Esquina — partido completo) ──
        # Usa el campo `line` de Kambi (igual que goles) en lugar de rangos de odds frágiles.
        elif criterion_en.lower() == "total corners" or \
             es_lower == "total de tiros de esquina":
            for o in outcomes:
                raw      = o.get("odds", 0)
                otype    = o.get("type", "")
                line_val = o.get("line", 0)
                if not raw or not line_val: continue
                decimal  = _kambi_odd_to_decimal(raw)
                line_pts = round(line_val / 1000, 1)
                if line_pts not in (7.5, 8.5, 9.5, 10.5, 11.5, 12.5):
                    continue
                if otype == "OT_OVER":
                    key = f"Corners Mas de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")
                elif otype == "OT_UNDER":
                    key = f"Corners Menos de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")

        # ── Tarjetas (Total de tarjetas — partido completo) ──
        # Ídem: usa campo `line` en lugar de rangos de odds hardcodeados.
        elif criterion_en.lower() == "total cards" or \
             es_lower == "total de tarjetas":
            for o in outcomes:
                raw      = o.get("odds", 0)
                otype    = o.get("type", "")
                line_val = o.get("line", 0)
                if not raw or not line_val: continue
                decimal  = _kambi_odd_to_decimal(raw)
                line_pts = round(line_val / 1000, 1)
                if line_pts not in (1.5, 2.5, 3.5, 4.5, 5.5, 6.5):
                    continue
                if otype == "OT_OVER":
                    key = f"Tarjetas Mas de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")
                elif otype == "OT_UNDER":
                    key = f"Tarjetas Menos de {line_pts}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")

        # ── Resultado Descanso ──
        elif criterion_en in ["Half Time", "Half-time Result"] or \
             es_lower == "descanso":
            for o in outcomes:
                otype = o.get("type", "")
                raw   = o.get("odds", 0)
                if not raw: continue
                if otype == "OT_ONE":   odds_dict["HT Gana Local"]  = _kambi_odd_to_decimal(raw)
                elif otype == "OT_CROSS": odds_dict["HT Empate"]    = _kambi_odd_to_decimal(raw)
                elif otype == "OT_TWO": odds_dict["HT Gana Visita"] = _kambi_odd_to_decimal(raw)

        # ── Asian Handicap ──
        # Kambi: criterion_en = "Asian Handicap" | line = handicap × 1000
        # Solo líneas de medio gol (-0.5, +0.5, -1.5, +1.5) para evitar push
        elif sport == "soccer" and (
             "asian handicap" in en_lower or "handicap asiatico" in es_lower):
            for o in outcomes:
                raw       = o.get("odds", 0)
                otype     = o.get("type", "")
                line_val  = o.get("line", 0)
                if not raw or line_val is None: continue
                decimal  = _kambi_odd_to_decimal(raw)
                hcp      = round(line_val / 1000, 1)   # -500 → -0.5
                # Sólo líneas de medio gol
                if abs(hcp) % 1 != 0.5:
                    continue
                hcp_str  = f"{hcp:+.1f}" if hcp != 0 else "0"
                if otype == "OT_ONE":   # home covers
                    key = f"AH Local {hcp_str}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")
                elif otype == "OT_TWO":  # away covers
                    key = f"AH Visita {hcp_str}"
                    if key not in odds_dict:
                        odds_dict[key] = decimal
                        outcome_ids[f"__oid_{key}"] = o.get("id", "")

        # ── Basketball / Tennis: Ganador (2-way, sin empate) ──
        elif sport in ("basketball", "tennis") and \
             (criterion_en in ["Match", "To Win Match", "Full Time", "Match Result",
                                "Moneyline", "Winner", "Match Odds"]
              or "moneyline" in en_lower or "match odds" in en_lower) and len(outcomes) == 2:
            for o in outcomes:
                otype = o.get("type", "")
                raw   = o.get("odds", 0)
                oid   = o.get("id", "")
                if not raw or o.get("status") == "SUSPENDED": continue
                decimal = _kambi_odd_to_decimal(raw)
                if otype == "OT_ONE":
                    odds_dict["Gana Local"]  = decimal
                    outcome_ids["__oid_Gana Local"] = oid
                elif otype == "OT_TWO":
                    odds_dict["Gana Visita"] = decimal
                    outcome_ids["__oid_Gana Visita"] = oid

        # ── Basketball: Total de Puntos ──
        elif sport == "basketball" and (
             "total points" in en_lower or "points o/u" in en_lower or
             "total" in en_lower and "points" in en_lower):
            for o in outcomes:
                raw   = o.get("odds", 0)
                otype = o.get("type", "")
                label = o.get("label", "")
                line_val = o.get("line", 0)
                if not raw or not line_val: continue
                decimal  = _kambi_odd_to_decimal(raw)
                # Kambi encodes lines as integers × 1000 (e.g. 247000 = 247 pts)
                line_pts = line_val / 1000 if line_val > 1000 else float(line_val)
                # Format: if .5 already (e.g. 227.5), keep it; else display as-is
                if line_pts == int(line_pts):
                    line_str = str(int(line_pts))
                else:
                    line_str = str(line_pts)
                key_over  = f"Mas de {line_str} pts"
                key_under = f"Menos de {line_str} pts"
                if otype == "OT_OVER":
                    if key_over not in odds_dict:
                        odds_dict[key_over] = decimal
                elif otype == "OT_UNDER":
                    if key_under not in odds_dict:
                        odds_dict[key_under] = decimal

    # Soccer necesita Gana Local; basketball/tennis pueden tenerlo sin empate
    if sport == "soccer" and not odds_dict.get("Gana Local"):
        return None
    if sport in ("basketball", "tennis") and not odds_dict.get("Gana Local"):
        return None

    return {
        "home":        home,
        "away":        away,
        "time":        match_time,
        "date":        match_date,
        "sport":       sport,
        "odds":        {**odds_dict, **outcome_ids},
        "event_id":    event_id,
    }


def _parse_basic_event(event_data: dict) -> dict | None:
    event     = event_data.get("event", {})
    sport_key = event.get("sport", "")
    if sport_key not in SPORT_MAP: return None
    home = event.get("homeName", "")
    away = event.get("awayName", "")
    if not home or not away: return None

    start_str = event.get("start", "")
    try:
        # Kambi devuelve timestamps en UTC ("Z") — convertir a hora Colombia (COT = UTC-5)
        start_utc  = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        start_cot  = start_utc.astimezone(_BOGOTA)
        match_time = start_cot.strftime("%H:%M")
        match_date = start_cot.strftime("%Y-%m-%d")
    except Exception:
        match_time = "00:00"
        match_date = ""

    return {
        "home":     home,
        "away":     away,
        "time":     match_time,
        "date":     match_date,
        "sport":    SPORT_MAP[sport_key],
        "event_id": event.get("id"),
        "odds":     {},
    }


async def _get_session_cookies_async() -> dict:
    cookies = {}
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page    = await browser.new_page()
            await page.goto("https://www.rushbet.co/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(4)
            all_cookies = await page.context.cookies()
            for c in all_cookies:
                cookies[c["name"]] = c["value"]
            await browser.close()
        logger.info(f"Cookies obtenidas: {len(cookies)}")
    except Exception as e:
        logger.warning(f"Error obteniendo cookies: {e}")
    return cookies


async def get_rushbet_odds_async(sport_filter: str = "soccer",
                                  fetch_full_markets: bool = True) -> dict:
    result = {"soccer": [], "basketball": [], "tennis": []}

    cookies = await _get_session_cookies_async()
    session = requests.Session()
    session.headers.update(KAMBI_HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value)

    try:
        logger.info("Consultando lista de partidos Kambi...")
        r    = session.get(KAMBI_LISTVIEW, params=KAMBI_PARAMS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error(f"Error consultando Kambi listView: {e}")
        return result

    events_raw = data.get("events", [])
    logger.info(f"Total eventos Kambi: {len(events_raw)}")

    basic_events = []
    for ed in events_raw:
        parsed = _parse_basic_event(ed)
        if not parsed: continue
        sport = parsed.get("sport", "")
        if sport_filter and sport != sport_filter: continue
        basic_events.append(parsed)

    logger.info(f"Partidos {sport_filter} para procesar: {len(basic_events)}")

    if not fetch_full_markets:
        for ed in events_raw:
            parsed = _parse_basic_event(ed)
            if not parsed: continue
            sport = parsed.get("sport","")
            if sport_filter and sport != sport_filter: continue
            for offer in ed.get("betOffers", []):
                for o in offer.get("outcomes", []):
                    otype = o.get("type",""); raw = o.get("odds",0)
                    if not raw: continue
                    if otype == "OT_ONE":    parsed["odds"]["Gana Local"]  = _kambi_odd_to_decimal(raw)
                    elif otype == "OT_CROSS": parsed["odds"]["Empate"]     = _kambi_odd_to_decimal(raw)
                    elif otype == "OT_TWO":  parsed["odds"]["Gana Visita"] = _kambi_odd_to_decimal(raw)
            if parsed["odds"].get("Gana Local"):
                result[sport].append(parsed)
        return result

    # ── Fetch paralelo de mercados completos ──────────────────────────────────
    # Máx. 10 requests simultáneos para no sobrecargar Kambi.
    sem = asyncio.Semaphore(10)

    async def _fetch_event(parsed: dict) -> dict | None:
        event_id = parsed.get("event_id")
        if not event_id:
            return None
        url = KAMBI_BETOFFER.format(event_id=event_id)
        async with sem:
            try:
                r2 = await asyncio.to_thread(
                    session.get, url, params=KAMBI_PARAMS_EVENT, timeout=10
                )
                if r2.status_code != 200:
                    return None
                offers = r2.json().get("betOffers", [])
            except Exception as e:
                logger.debug(f"Error mercados {parsed['home']} vs {parsed['away']}: {e}")
                return None
        return _parse_full_event(
            home=parsed["home"], away=parsed["away"],
            sport=parsed["sport"], match_time=parsed["time"],
            match_date=parsed["date"], event_id=event_id,
            offers=offers,
        )

    all_fulls = await asyncio.gather(*[_fetch_event(p) for p in basic_events],
                                      return_exceptions=True)

    for parsed, full in zip(basic_events, all_fulls):
        if not full or isinstance(full, Exception):
            continue

        odds   = full.get("odds", {})
        local  = odds.get("Gana Local", 0)
        visita = odds.get("Gana Visita", 0)
        empate = odds.get("Empate", 0)
        sp     = parsed["sport"]

        if sp == "soccer":
            valid = (1.20 <= local <= 12.0 and 1.20 <= visita <= 12.0 and empate >= 1.40)
        else:
            valid = (1.01 <= local <= 20.0 and 1.01 <= visita <= 20.0)

        if valid:
            result[sp].append(full)

    for sport, games in result.items():
        mkt_sample = games[0]["odds"].keys() if games else []
        logger.info(f"  {sport}: {len(games)} partidos | mercados ejemplo: {list(mkt_sample)[:6]}")

    return result


class RushbetScraper:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout  = timeout

    def get_odds(self, sport_filter: str = "soccer") -> dict:
        try:
            return asyncio.run(get_rushbet_odds_async(sport_filter, fetch_full_markets=True))
        except RuntimeError:
            # Ya hay un event loop corriendo (ej. entorno interactivo / Jupyter)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    get_rushbet_odds_async(sport_filter, fetch_full_markets=True),
                )
                return future.result(timeout=120)
        except Exception as e:
            logger.error(f"Error RushbetScraper: {e}")
            return {"soccer": [], "basketball": [], "tennis": []}


async def align_odds_with_rushbet(api_opportunities: list,
                                    rushbet_games: list = None) -> list:
    # Usar scrape ya hecho si se pasa, sino hacer uno nuevo
    if rushbet_games is not None:
        rushbet_soccer = rushbet_games
        logger.info(f"Usando {len(rushbet_soccer)} partidos Rushbet ya scrapeados")
    else:
        rushbet_data   = await get_rushbet_odds_async(sport_filter=None, fetch_full_markets=True)
        rushbet_soccer = rushbet_data.get("soccer", [])

    if not rushbet_soccer:
        logger.warning("Sin odds de Rushbet. Usando OddsAPI como fallback.")
        return api_opportunities

    logger.info(f"Alineando {len(api_opportunities)} picks contra {len(rushbet_soccer)} partidos Rushbet...")

    aligned, skipped = [], 0

    for opp in api_opportunities:
        home   = opp.get("home", "")
        away   = opp.get("away", "")
        market = opp.get("market", "")
        p_real = opp.get("prob", 0) / 100

        rb_game = _match_rushbet_game(home, away, rushbet_soccer)
        if not rb_game:
            logger.debug(f"Sin match Rushbet: {home} vs {away}")
            skipped += 1
            continue

        rb_odd = _find_market_in_odds(market, rb_game.get("odds", {}))

        if not rb_odd:
            logger.info(f"Mercado '{market}' no en Rushbet -> fallback OddsAPI")
            rb_odd = opp.get("odds")
            if not rb_odd: skipped += 1; continue
            source = "oddsapi_fallback"
        else:
            source = "rushbet"

        real_ev = (p_real * rb_odd) - 1
        try:
            import config as _cfg
            _ev_min = _cfg.MIN_EV_THRESHOLD
        except Exception:
            _ev_min = 0.01
        if real_ev <= _ev_min: skipped += 1; continue

        from modules.risk import RiskEngine
        import config
        new_stake = RiskEngine.calculate_kelly_stake(p_real, rb_odd, config.BANKROLL_INICIAL)
        if new_stake <= 0: skipped += 1; continue

        # Normalizar nombre de mercado para buscar outcome_id
        def _norm(m):
            for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),(" goles","")]:
                m = m.lower().replace(a, b)
            return m.strip()

        market_raw  = opp.get("market", "")
        rb_odds_all = rb_game.get("odds", {})
        rb_event_id = rb_game.get("event_id")

        # Buscar outcome_id por nombre normalizado
        oid = ""
        market_norm = _norm(market_raw)
        for k, v in rb_odds_all.items():
            if k.startswith("__oid_") and _norm(k[6:]) == market_norm:
                oid = str(v)
                break
        # Banker: buscar "Gana Local"
        if not oid and "banker" in market_raw.lower():
            oid = str(rb_odds_all.get("__oid_Gana Local", ""))

        aligned_opp = opp.copy()
        aligned_opp["odds"]           = rb_odd
        aligned_opp["ev"]             = real_ev * 100
        aligned_opp["stake_amount"]   = new_stake
        aligned_opp["source"]         = source
        aligned_opp["odds_api_value"] = opp.get("odds")
        aligned_opp["event_id"]       = rb_event_id
        aligned_opp["outcome_id"]     = oid

        logger.debug(
            f"Link: {opp.get('home')} | event={rb_event_id} | oid={oid or 'none'}"
        )
        aligned.append(aligned_opp)

    logger.info(f"Alineadas: {len(aligned)} validas | {skipped} descartadas")
    return aligned


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Consultando odds completas de Rushbet...\n")

    async def main():
        data  = await get_rushbet_odds_async(sport_filter="soccer", fetch_full_markets=True)
        games = data.get("soccer", [])
        print(f"Partidos con mercados completos: {len(games)}")
        print("-" * 80)
        for g in games[:10]:
            odds = g['odds']
            l    = odds.get('Gana Local','-')
            e    = odds.get('Empate','-')
            v    = odds.get('Gana Visita','-')
            ou   = odds.get('Mas de 2.5','-')
            cor  = odds.get('Corners Mas de 9.5','-')
            tar  = odds.get('Tarjetas Mas de 3.5','-')
            dc   = odds.get('1X','-')
            print(f"{g['home'][:18]:18} vs {g['away'][:18]:18} | 1X2:{l}/{e}/{v} | +2.5:{ou} | C+9.5:{cor} | T+3.5:{tar} | 1X:{dc}")

    asyncio.run(main())