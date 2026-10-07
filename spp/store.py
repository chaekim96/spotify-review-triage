"""SQLite state store. Statuses are explicit: pending, completed, quarantined."""

import sqlite3
from pathlib import Path

STATUSES = ("pending", "completed", "quarantined")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    review_id       TEXT PRIMARY KEY,
    seq             INTEGER NOT NULL,            -- 0-based position in the source CSV
    source_sha256   TEXT NOT NULL,
    text_sha256     TEXT NOT NULL,               -- sha256 of the exact review_text (UTF-8), for exact-duplicate caching
    status          TEXT NOT NULL CHECK (status IN ('pending','completed','quarantined')),
    reason          TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    topic           TEXT,
    intent          TEXT,
    sentiment       REAL CHECK (sentiment IS NULL OR (sentiment >= -1 AND sentiment <= 1)),
    severity        INTEGER CHECK (severity IS NULL OR (severity >= 1 AND severity <= 5)),
    entities        TEXT,                        -- JSON list
    evidence_quote  TEXT,
    needs_review    INTEGER CHECK (needs_review IS NULL OR needs_review IN (0,1)),
    label_config    TEXT,
    cache_source_id TEXT,
    updated_at      TEXT NOT NULL,
    CHECK (status != 'quarantined' OR (reason IS NOT NULL AND reason != ''))
);
CREATE INDEX IF NOT EXISTS records_status ON records(status);
CREATE INDEX IF NOT EXISTS records_text ON records(text_sha256);
"""


def connect(db_path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def status_counts(conn) -> dict:
    counts = {s: 0 for s in STATUSES}
    counts.update(dict(conn.execute("SELECT status, COUNT(*) FROM records GROUP BY status")))
    return counts
