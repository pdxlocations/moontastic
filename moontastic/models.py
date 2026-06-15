from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    callsign TEXT NOT NULL,
    target TEXT NOT NULL,
    channel INTEGER NOT NULL,
    interval_seconds REAL NOT NULL,
    packet_count INTEGER NOT NULL,
    timeout_seconds REAL NOT NULL,
    payload_prefix TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER,
    sequence INTEGER,
    direction TEXT NOT NULL,
    payload TEXT NOT NULL,
    node_id TEXT,
    channel INTEGER,
    rssi REAL,
    snr REAL,
    ack INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    raw_json TEXT,
    FOREIGN KEY(test_id) REFERENCES tests(id)
);

CREATE TABLE IF NOT EXISTS listeners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    callsign TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    elevation_m REAL NOT NULL DEFAULT 0,
    rx_gain_dbi REAL NOT NULL DEFAULT 12,
    rx_sensitivity_dbm REAL NOT NULL DEFAULT -137,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.connect() as conn:
            return conn.execute(sql, params)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None
