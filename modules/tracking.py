# modules/tracking.py
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'quant_history.db')

def init_db():
    """Inicializa la base de datos relacional para tracking de métricas Quant."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabla core para registro de operaciones
    c.execute("""
        CREATE TABLE IF NOT EXISTS bets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            fixture TEXT,
            market TEXT,
            model_prob REAL,
            odds_taken REAL,
            stake REAL,
            closing_odds REAL,
            result INTEGER,
            ev_expected REAL
        )
    """)
    conn.commit()
    conn.close()
    print("[+] Database tracking engine inicializado correctamente.")

def log_bet(date, fixture, market, model_prob, odds_taken, stake, ev_expected):
    """Inserta una nueva predicción en el histórico."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO bets (date, fixture, market, model_prob, odds_taken, stake, ev_expected)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date, fixture, market, model_prob, odds_taken, stake, ev_expected))
    conn.commit()
    conn.close()