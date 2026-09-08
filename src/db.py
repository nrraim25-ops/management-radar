"""src/db.py — SQLite schema creation and connection helper."""

import sqlite3
from contextlib import contextmanager
from src.config import DB_PATH

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS companies (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    source_type     TEXT    NOT NULL CHECK (source_type IN ('pdf', 'youtube')),
    title           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    published_date  TEXT,
    local_path      TEXT,
    fetch_status    TEXT    NOT NULL DEFAULT 'pending',
    fetch_error     TEXT,
    fetched_at      TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id),
    text        TEXT    NOT NULL,
    locator     TEXT    NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding   BLOB
);

CREATE TABLE IF NOT EXISTS source_tags (
    id        INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    summary   TEXT    NOT NULL,
    tags      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_log (
    id               INTEGER PRIMARY KEY,
    question         TEXT NOT NULL,
    answer           TEXT NOT NULL,
    cited_source_ids TEXT,
    answered_at      TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create all tables if they don't already exist."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"[db] schema initialised at {DB_PATH}")


@contextmanager
def get_conn():
    """Context manager that yields a sqlite3 connection with FK enforcement."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
