"""Подключение к SQLite и миграции по номеру версии схемы (PRAGMA user_version)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: отметки выполнения. Одна отметка на направление в день.
    """
    CREATE TABLE completions (
        category_key TEXT NOT NULL,
        day          TEXT NOT NULL,  -- логический день, ГГГГ-ММ-ДД
        done_at      TEXT NOT NULL,  -- момент отметки, ISO 8601
        source       TEXT NOT NULL,  -- desktop, bot, cli
        PRIMARY KEY (category_key, day)
    );
    CREATE INDEX completions_day ON completions (day);
    """,
]


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
