"""SQLite store for the backend: action runs, their steps, mainframe master data and predictions.

The mainframe stays the system of record. These tables are a local copy of what the
batch produced, so the dashboard can be served quickly and still work offline.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from pipeline.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT NOT NULL,
    params       TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL,              -- running | ok | failed
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT,
    summary      TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS run_steps (
    run_id       INTEGER NOT NULL REFERENCES runs(id),
    seq          INTEGER NOT NULL,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL,              -- pending | running | ok | failed | skipped
    started_at   TEXT,
    finished_at  TEXT,
    detail       TEXT,
    data         TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS customers (
    cust_id TEXT PRIMARY KEY, name TEXT, city TEXT, emp_type TEXT, age INTEGER,
    monthly_income REAL, credit_score INTEGER, open_date INTEGER, status TEXT
);
CREATE TABLE IF NOT EXISTS loans (
    loan_id TEXT PRIMARY KEY, cust_id TEXT, loan_type TEXT, principal REAL, int_rate REAL,
    tenure INTEGER, start_date INTEGER, emi_amt REAL, due_day INTEGER, outstanding REAL, status TEXT
);
CREATE INDEX IF NOT EXISTS loans_cust ON loans(cust_id);
CREATE TABLE IF NOT EXISTS monthly (
    cust_id TEXT, yyyymm INTEGER, credits REAL, debits REAL, salary REAL,
    min_bal REAL, avg_bal REAL, bounces INTEGER, cc_util REAL,
    PRIMARY KEY (cust_id, yyyymm)
);
CREATE TABLE IF NOT EXISTS predictions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL,
    cust_id       TEXT NOT NULL,
    as_of         INTEGER NOT NULL,
    probability   REAL NOT NULL,
    tier          TEXT NOT NULL,
    action        TEXT NOT NULL,
    top_factor    TEXT,
    reasoning     TEXT,
    features      TEXT NOT NULL,
    shap          TEXT NOT NULL,
    model_version TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS pred_cust ON predictions(cust_id, id DESC);
CREATE INDEX IF NOT EXISTS pred_run ON predictions(run_id);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_lock = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def tx():
    """Serialized write transaction (the runner thread and API threads share the file)."""
    with _lock:
        con = connect()
        try:
            yield con
            con.commit()
        finally:
            con.close()


def init() -> None:
    with tx() as con:
        con.executescript(SCHEMA)
        # A run cannot survive a backend restart: mark leftovers as failed.
        con.execute("UPDATE runs SET status='failed', error='Backend restarted while the run was active', "
                    "finished_at=? WHERE status='running'", (now(),))
        con.execute("UPDATE run_steps SET status='failed' WHERE status='running'")


def query(sql: str, args: tuple = ()) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def kv_get(key: str, default=None):
    rows = query("SELECT value FROM kv WHERE key=?", (key,))
    return json.loads(rows[0]["value"]) if rows else default


def kv_set(key: str, value) -> None:
    with tx() as con:
        con.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)))
