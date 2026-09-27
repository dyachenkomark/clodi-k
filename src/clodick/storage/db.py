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
    # 2: состояние интерфейса: место персонажа, переключатели из трея.
    """
    CREATE TABLE kv (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL  -- JSON
    );
    """,
    # 3: свои задачи, добавленные из чек-листа. Отметки лежат в completions с ключом task:<id>.
    """
    CREATE TABLE tasks (
        id         INTEGER PRIMARY KEY,
        title      TEXT NOT NULL,
        daily      INTEGER NOT NULL,  -- 1: каждый день, 0: разовая
        created_at TEXT NOT NULL      -- ISO 8601
    );
    """,
    # 4: законченные фокусы Pomodoro.
    """
    CREATE TABLE focus_sessions (
        id         INTEGER PRIMARY KEY,
        day        TEXT NOT NULL,  -- логический день, ГГГГ-ММ-ДД
        task_key   TEXT,           -- на какой пункт чек-листа был фокус, может не быть
        started_at TEXT NOT NULL,  -- ISO 8601
        minutes    INTEGER NOT NULL
    );
    CREATE INDEX focus_sessions_day ON focus_sessions (day);
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
