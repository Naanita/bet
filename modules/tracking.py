# modules/tracking.py — v2
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'quant_history.db')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bets(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT,
            fixture     TEXT,
            market      TEXT,
            model_prob  REAL,
            odds_taken  REAL,
            stake       REAL,
            stake_level INTEGER,
            closing_odds REAL,
            clv         REAL,
            result      INTEGER,
            ev_expected REAL,
            event_id    TEXT
        )
    """)
    _migrate_columns(conn, c)
    conn.commit()
    conn.close()


def _migrate_columns(conn, c):
    existing = {row[1] for row in c.execute("PRAGMA table_info(bets)").fetchall()}
    new_cols = {
        "stake_level":  "INTEGER",
        "clv":          "REAL",
        "event_id":     "TEXT",
    }
    for col, typ in new_cols.items():
        if col not in existing:
            c.execute(f"ALTER TABLE bets ADD COLUMN {col} {typ}")
    conn.commit()


def log_bet(date, fixture, market, model_prob, odds_taken, stake,
            ev_expected, stake_level=None, event_id=None) -> int:
    """Inserta una apuesta nueva. Retorna el id generado."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO bets
            (date, fixture, market, model_prob, odds_taken, stake,
             ev_expected, stake_level, event_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date, fixture, market, model_prob, odds_taken, stake,
          ev_expected, stake_level, event_id))
    bet_id = c.lastrowid
    conn.commit()
    conn.close()
    return bet_id


def update_closing_odds(fixture: str, market: str, closing_odds: float) -> int:
    """
    Registra closing_odds y calcula CLV para picks pendientes de ese partido+mercado.

    CLV = (odds_taken / closing_odds) - 1
    Positivo → obtuvimos mejor precio que el cierre de mercado (edge sostenible).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, odds_taken FROM bets WHERE fixture=? AND market=? AND closing_odds IS NULL",
        (fixture, market),
    ).fetchall()
    for bet_id, odds_taken in rows:
        if odds_taken and closing_odds and closing_odds > 1.0:
            clv = round((odds_taken / closing_odds) - 1.0, 4)
        else:
            clv = None
        c.execute(
            "UPDATE bets SET closing_odds=?, clv=? WHERE id=?",
            (closing_odds, clv, bet_id),
        )
    conn.commit()
    conn.close()
    return len(rows)


def settle_bet(fixture: str, market: str, result: int) -> int:
    """
    Actualiza resultado (1=ganada, 0=perdida) para todos los picks
    del partido+mercado que aún no tengan resultado.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE bets SET result=? WHERE fixture=? AND market=? AND result IS NULL",
        (result, fixture, market),
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def get_open_bets(days_back: int = 7) -> list:
    """Picks de los últimos N días sin closing_odds registrado aún."""
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM bets WHERE closing_odds IS NULL AND date >= ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_clv_stats(min_samples: int = 5) -> dict:
    """
    Métricas de Closing Line Value del histórico.

    avg_clv        → CLV promedio en % (+ = batimos el mercado)
    clv_positive_pct → % de picks con CLV positivo
    clv_by_market  → CLV promedio por tipo de mercado (≥ min_samples)
    n_clv_samples  → picks con CLV calculado
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT market, clv FROM bets WHERE clv IS NOT NULL"
    ).fetchall()
    conn.close()

    if not rows:
        return {"avg_clv": None, "clv_positive_pct": None,
                "clv_by_market": {}, "n_clv_samples": 0}

    clv_values = [r[1] for r in rows]
    n          = len(clv_values)
    avg_clv    = round(sum(clv_values) / n * 100, 2)
    pos_pct    = round(sum(1 for c in clv_values if c > 0) / n * 100, 1)

    by_market: dict = {}
    for market, clv in rows:
        by_market.setdefault(market, []).append(clv)
    clv_by_market = {
        mkt: round(sum(vals) / len(vals) * 100, 2)
        for mkt, vals in by_market.items()
        if len(vals) >= min_samples
    }

    return {
        "avg_clv":          avg_clv,
        "clv_positive_pct": pos_pct,
        "clv_by_market":    clv_by_market,
        "n_clv_samples":    n,
    }


def get_performance_report(n_last: int = 100) -> dict:
    """
    Reporte consolidado: Yield, Win Rate, ROI, CLV, P&L en COP.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT odds_taken, stake, result, clv, ev_expected
           FROM bets
           WHERE result IS NOT NULL
           ORDER BY id DESC LIMIT ?""",
        (n_last,),
    ).fetchall()
    conn.close()

    if not rows:
        return {}

    n            = len(rows)
    total_staked = sum(r[1] for r in rows if r[1]) or 0
    wins_pnl     = sum((r[0] - 1) * r[1] for r in rows if r[2] == 1 and r[0] and r[1])
    losses_pnl   = sum(r[1] for r in rows if r[2] == 0 and r[1])
    total_pnl    = wins_pnl - losses_pnl
    win_rate     = round(sum(1 for r in rows if r[2] == 1) / n * 100, 1)
    yield_pct    = round(total_pnl / total_staked * 100, 2) if total_staked else 0

    clv_vals = [r[3] for r in rows if r[3] is not None]
    avg_clv  = round(sum(clv_vals) / len(clv_vals) * 100, 2) if clv_vals else None

    return {
        "n_bets":       n,
        "win_rate":     win_rate,
        "total_staked": round(total_staked, 0),
        "total_pnl":    round(total_pnl, 0),
        "yield_pct":    yield_pct,
        "avg_clv":      avg_clv,
        "n_clv":        len(clv_vals),
    }


def get_rolling_win_rate_from_db(n_last: int = 50) -> tuple:
    """Alias de compatibilidad — idéntico a risk.get_rolling_win_rate()."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT result FROM bets WHERE result IS NOT NULL ORDER BY id DESC LIMIT ?",
            (n_last,),
        ).fetchall()
        conn.close()
    except Exception:
        return 0.60, 0
    if not rows:
        return 0.60, 0
    wins = sum(1 for (r,) in rows if r == 1)
    n    = len(rows)
    return round(wins / n, 4), n
