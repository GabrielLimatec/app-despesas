from __future__ import annotations

from pathlib import Path
import sqlite3


INITIAL_RECURRING = [
    ("ESCOLA",        50000,  "Educação",           1),
    ("CARTAO BMG PF", 100000, "Outros",              2),
    ("RESERVA",       100000, "Outros",              3),
    ("CARRO",         290000, "Transporte",          4),
    ("CAGECE",        10000,  "Contas e Serviços",   5),
    ("INTERNET",      13000,  "Contas e Serviços",   6),
    ("PLANO SAUDE",   86000,  "Saúde",               7),
    ("PLANO CELULAR", 9500,   "Contas e Serviços",   8),
    ("VAN ESCOLAR",   20000,  "Educação",            9),
    ("FACULDADE",     25000,  "Educação",           10),
    ("ENEL",          30000,  "Contas e Serviços",  11),
    ("CONTADOR",      20000,  "Outros",             12),
    ("IMPOSTO",       200000, "Outros",             13),
    ("CREDAMIGO",     65000,  "Outros",             14),
    ("OBRA",          100000, "Moradia",            15),
    ("SEGURO CARRO",  22000,  "Transporte",         16),
    ("PARCELA CASA",  100000, "Moradia",            17),
]


def sqlite_path_from_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
    return database_url.removeprefix("sqlite:///")


def connect_database(database_url: str) -> sqlite3.Connection:
    db_path = sqlite_path_from_url(database_url)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS income (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            description  TEXT NOT NULL,
            month        TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            description  TEXT NOT NULL,
            category     TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            month        TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            description  TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category     TEXT NOT NULL,
            sort_order   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS seeded_months (
            month TEXT PRIMARY KEY
        );
        """
    )

    existing = conn.execute("SELECT COUNT(*) FROM recurring_expenses").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO recurring_expenses (description, amount_cents, category, sort_order) VALUES (?, ?, ?, ?)",
            INITIAL_RECURRING,
        )

    conn.commit()
