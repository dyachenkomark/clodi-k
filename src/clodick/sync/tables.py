"""Листы таблицы и как они ложатся на локальный кэш.

| Лист  | Что в нём |
|---|---|
| Tasks | Задачи: проект, название, срок, время, повтор, статус, заметка |
| Log   | Отметки «сделано» по дням: направления, ежедневные и разовые задачи |
| Notes | Заметки и результаты к пунктам |
| Focus | Законченные фокусы Pomodoro |

В ячейках всё хранится текстом. Даты — ГГГГ-ММ-ДД, моменты — ГГГГ-ММ-ДД ЧЧ:ММ:СС.
Руками можно писать свободнее: «пт», «завтра», «02.10», «готово» — normalize приведёт к виду.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from clodick.core.quickadd import parse_date, parse_time
from clodick.storage.repository import TASK_UPSERT, CompletionRepository, new_uid
from clodick.sync.engine import Report, Row, SheetClient, SyncState, sync_table

DONE_WORDS = {"done", "x", "х", "+", "✓", "✔", "yes", "да", "готово", "сделано", "1", "true"}
DAILY_WORDS = {"daily", "day", "every day", "каждый день", "ежедневно", "день"}


def to_sheet(stamp: str | None) -> str:
    """Момент из кэша в ячейку: без буквы T посередине."""
    return (stamp or "").replace("T", " ")


def from_sheet(text: str, now: datetime, *, default_now: bool = False) -> str:
    """Момент из ячейки в кэш. Пусто или непонятно — пусто либо текущее время."""
    try:
        return datetime.fromisoformat(text.strip()).isoformat(timespec="seconds")
    except ValueError:
        return now.isoformat(timespec="seconds") if default_now else ""


def day_cell(text: str, now: datetime) -> str:
    """Дата из ячейки: ГГГГ-ММ-ДД. Непонятный текст остаётся как есть, чтобы не терять."""
    found = parse_date(text, now.date()) if text else None
    return found.isoformat() if found else text


class _SqlTable:
    tab: str
    columns: tuple[str, ...]

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def _all(self, sql: str) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql).fetchall()

    def _run(self, sql: str, args: tuple) -> int:
        with self._lock, self._conn:
            return self._conn.execute(sql, args).rowcount


class TasksTable(_SqlTable):
    tab = "Tasks"
    columns = (
        "id", "project", "title", "due", "time", "repeat", "status", "note", "done_at", "created",
    )  # fmt: skip

    def local_rows(self) -> dict[str, Row]:
        rows = self._all(
            "SELECT id, project, title, due, time, repeat, status, note, done_at, created_at "
            "FROM tasks"
        )
        out = {}
        for row in rows:
            data = dict(zip(self.columns, row, strict=True))
            data["done_at"], data["created"] = to_sheet(data["done_at"]), to_sheet(data["created"])
            out[data["id"]] = data
        return out

    def apply(self, row_id: str, row: Row | None) -> None:
        if row is None:
            self._run("DELETE FROM tasks WHERE id = ?", (row_id,))
            return
        self._run(
            TASK_UPSERT,
            (
                row_id,
                row["project"],
                row["title"],
                row["due"],
                row["time"],
                row["repeat"],
                row["status"],
                row["note"],
                row["done_at"].replace(" ", "T"),
                row["created"].replace(" ", "T"),
            ),
        )

    def normalize(self, row: Row, now: datetime) -> Row | None:
        if not row["title"]:
            return None
        row["id"] = row["id"] or new_uid()
        row["due"] = day_cell(row["due"], now)
        row["time"] = parse_time(row["time"]) or row["time"]
        row["repeat"] = "daily" if row["repeat"].casefold() in DAILY_WORDS else ""
        done = row["status"].casefold() in DONE_WORDS
        row["status"] = "done" if done else "todo"
        # Закрыли руками в таблице — время закрытия ставим сами.
        row["done_at"] = to_sheet(from_sheet(row["done_at"], now, default_now=True)) if done else ""
        row["created"] = to_sheet(from_sheet(row["created"], now, default_now=True))
        return row


class LogTable(_SqlTable):
    tab = "Log"
    columns = ("id", "day", "item", "title", "done_at", "source")

    def local_rows(self) -> dict[str, Row]:
        rows = self._all("SELECT day, category_key, title, done_at, source FROM completions")
        return {
            f"{day}|{key}": {
                "id": f"{day}|{key}",
                "day": day,
                "item": key,
                "title": title,
                "done_at": to_sheet(done_at),
                "source": source,
            }
            for day, key, title, done_at, source in rows
        }

    def apply(self, row_id: str, row: Row | None) -> None:
        day, _, key = row_id.partition("|")
        if row is None:
            self._run("DELETE FROM completions WHERE day = ? AND category_key = ?", (day, key))
            return
        self._run(
            "INSERT OR REPLACE INTO completions (category_key, day, done_at, source, title) "
            "VALUES (?,?,?,?,?)",
            (key, day, row["done_at"].replace(" ", "T"), row["source"], row["title"]),
        )

    def normalize(self, row: Row, now: datetime) -> Row | None:
        row["day"] = day_cell(row["day"], now)
        if not row["day"] or not row["item"]:
            return None
        row["id"] = f"{row['day']}|{row['item']}"
        row["done_at"] = to_sheet(from_sheet(row["done_at"], now, default_now=True))
        row["source"] = row["source"] or "sheet"
        return row


class NotesTable(_SqlTable):
    tab = "Notes"
    columns = ("id", "day", "item", "title", "text", "created", "source")

    def local_rows(self) -> dict[str, Row]:
        rows = self._all(
            "SELECT uid, day, item_key, item_title, text, created_at, source FROM notes"
        )
        out = {}
        for row in rows:
            data = dict(zip(self.columns, row, strict=True))
            data["created"] = to_sheet(data["created"])
            out[data["id"]] = data
        return out

    def apply(self, row_id: str, row: Row | None) -> None:
        if row is None:
            self._run("DELETE FROM notes WHERE uid = ?", (row_id,))
            return
        args = (
            row["day"], row["item"], row["title"], row["text"],
            row["created"].replace(" ", "T"), row["source"], row_id,
        )  # fmt: skip
        changed = self._run(
            "UPDATE notes SET day=?, item_key=?, item_title=?, text=?, created_at=?, source=? "
            "WHERE uid=?",
            args,
        )
        if not changed:
            self._run(
                "INSERT INTO notes (day, item_key, item_title, text, created_at, source, uid) "
                "VALUES (?,?,?,?,?,?,?)",
                args,
            )

    def normalize(self, row: Row, now: datetime) -> Row | None:
        if not row["text"]:
            return None
        row["id"] = row["id"] or new_uid()
        row["day"] = day_cell(row["day"], now) or now.date().isoformat()
        row["title"] = row["title"] or row["item"]
        row["created"] = to_sheet(from_sheet(row["created"], now, default_now=True))
        row["source"] = row["source"] or "sheet"
        return row


class FocusTable(_SqlTable):
    tab = "Focus"
    columns = ("id", "day", "item", "started", "minutes")

    def local_rows(self) -> dict[str, Row]:
        rows = self._all("SELECT uid, day, task_key, started_at, minutes FROM focus_sessions")
        return {
            uid: {
                "id": uid,
                "day": day,
                "item": key or "",
                "started": to_sheet(started),
                "minutes": str(minutes),
            }
            for uid, day, key, started, minutes in rows
        }

    def apply(self, row_id: str, row: Row | None) -> None:
        if row is None:
            self._run("DELETE FROM focus_sessions WHERE uid = ?", (row_id,))
            return
        args = (
            row["day"], row["item"] or None, row["started"].replace(" ", "T"),
            int(row["minutes"]), row_id,
        )  # fmt: skip
        changed = self._run(
            "UPDATE focus_sessions SET day=?, task_key=?, started_at=?, minutes=? WHERE uid=?", args
        )
        if not changed:
            self._run(
                "INSERT INTO focus_sessions (day, task_key, started_at, minutes, uid) "
                "VALUES (?,?,?,?,?)",
                args,
            )

    def normalize(self, row: Row, now: datetime) -> Row | None:
        if not row["minutes"].isdigit():
            return None
        row["id"] = row["id"] or new_uid()
        row["day"] = day_cell(row["day"], now) or now.date().isoformat()
        row["started"] = to_sheet(from_sheet(row["started"], now, default_now=True))
        return row


TABLES = (TasksTable, LogTable, NotesTable, FocusTable)


def sync_all(repo: CompletionRepository, client: SheetClient, now: datetime) -> Report:
    """Сверить все листы с кэшем. Бросает исключение клиента, если таблица недоступна."""
    state = SyncState(repo.conn, repo.lock)
    total = Report()
    for table in TABLES:
        total += sync_table(table(repo.conn, repo.lock), client, state, now)
    return total
