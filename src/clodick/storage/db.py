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
    # 5: заметки к пунктам чек-листа: результаты, комментарии. Несколько на пункт в день.
    """
    CREATE TABLE notes (
        id         INTEGER PRIMARY KEY,
        day        TEXT NOT NULL,  -- логический день, ГГГГ-ММ-ДД
        item_key   TEXT NOT NULL,  -- sport, task:3 и т. п.
        item_title TEXT NOT NULL,  -- название на момент записи: история не зависит от задач
        text       TEXT NOT NULL,
        created_at TEXT NOT NULL,  -- ISO 8601
        source     TEXT NOT NULL   -- desktop, cli, bot
    );
    CREATE INDEX notes_day ON notes (day);
    """,
    # 6: Google Таблица как база. Задачи получают проект, срок и текстовый id, общий для
    # всех устройств. У отметок появляется название пункта, у заметок и фокусов — uid.
    # sync_state — что было в таблице при прошлой синхронизации: по нему видно, кто что менял.
    """
    CREATE TABLE new_tasks (
        id         TEXT PRIMARY KEY,
        project    TEXT NOT NULL DEFAULT '',
        title      TEXT NOT NULL,
        due        TEXT NOT NULL DEFAULT '',      -- ГГГГ-ММ-ДД или пусто
        time       TEXT NOT NULL DEFAULT '',      -- ЧЧ:ММ или пусто
        repeat     TEXT NOT NULL DEFAULT '',      -- daily или пусто
        status     TEXT NOT NULL DEFAULT 'todo',  -- todo, done: только для разовых
        note       TEXT NOT NULL DEFAULT '',
        done_at    TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    INSERT INTO new_tasks (id, title, repeat, status, done_at, created_at)
    SELECT CAST(t.id AS TEXT), t.title,
           CASE WHEN t.daily THEN 'daily' ELSE '' END,
           CASE WHEN t.daily = 0 AND c.done_at IS NOT NULL THEN 'done' ELSE 'todo' END,
           CASE WHEN t.daily = 0 THEN COALESCE(c.done_at, '') ELSE '' END,
           t.created_at
    FROM tasks t
    LEFT JOIN (
        SELECT category_key, MAX(done_at) AS done_at FROM completions GROUP BY category_key
    ) c ON c.category_key = 'task:' || t.id;
    DROP TABLE tasks;
    ALTER TABLE new_tasks RENAME TO tasks;
    ALTER TABLE completions ADD COLUMN title TEXT NOT NULL DEFAULT '';
    ALTER TABLE notes ADD COLUMN uid TEXT;
    UPDATE notes SET uid = lower(hex(randomblob(4)));
    CREATE UNIQUE INDEX notes_uid ON notes (uid);
    ALTER TABLE focus_sessions ADD COLUMN uid TEXT;
    UPDATE focus_sessions SET uid = lower(hex(randomblob(4)));
    CREATE UNIQUE INDEX focus_sessions_uid ON focus_sessions (uid);
    CREATE TABLE sync_state (
        tab TEXT NOT NULL,
        id  TEXT NOT NULL,
        row TEXT NOT NULL,  -- JSON строки, какой она была в таблице
        PRIMARY KEY (tab, id)
    );
    """,
    # 7: темы задач. Задача ссылается на тему по имени (tasks.project): так её видно
    # и в таблице, и при ручной правке. Одинаковые имена не запрещены: они могут прийти
    # с двух устройств сразу, тогда код берёт первую.
    """
    CREATE TABLE topics (
        id       TEXT PRIMARY KEY,
        name     TEXT NOT NULL,
        aliases  TEXT NOT NULL DEFAULT '',   -- короткие имена через запятую
        color    TEXT NOT NULL DEFAULT '',   -- #rrggbb
        repeat   TEXT NOT NULL DEFAULT '',   -- daily или пусто
        position INTEGER NOT NULL DEFAULT 0
    );
    """,
]


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15)
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
