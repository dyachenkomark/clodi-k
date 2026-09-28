"""Работа с отметками и своими задачами."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime

from clodick.core.models import TASK_PREFIX, Note, Task


class CompletionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # Бот и интерфейс будут работать из разных потоков.
        self._lock = threading.Lock()

    def add(self, key: str, day: date, done_at: datetime, source: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO completions (category_key, day, done_at, source) "
                "VALUES (?, ?, ?, ?)",
                (key, day.isoformat(), done_at.isoformat(timespec="seconds"), source),
            )
            return cur.rowcount == 1

    def remove(self, key: str, day: date) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM completions WHERE category_key = ? AND day = ?",
                (key, day.isoformat()),
            )
            return cur.rowcount == 1

    def completions_for(self, day: date) -> dict[str, datetime]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT category_key, done_at FROM completions WHERE day = ?",
                (day.isoformat(),),
            ).fetchall()
        return {key: datetime.fromisoformat(done_at) for key, done_at in rows}

    def add_task(self, title: str, daily: bool, created_at: datetime) -> Task:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO tasks (title, daily, created_at) VALUES (?, ?, ?)",
                (title, int(daily), created_at.isoformat(timespec="seconds")),
            )
        return Task(id=cur.lastrowid, title=title, daily=daily)

    def remove_task(self, task_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.execute(
                "DELETE FROM completions WHERE category_key = ?", (f"{TASK_PREFIX}{task_id}",)
            )
            return cur.rowcount == 1

    def tasks(self) -> list[Task]:
        with self._lock:
            rows = self._conn.execute("SELECT id, title, daily FROM tasks ORDER BY id").fetchall()
        return [Task(id=i, title=title, daily=bool(daily)) for i, title, daily in rows]

    def done_before(self, day: date) -> set[str]:
        """Ключи своих задач, отмеченных раньше этого дня: разовые из них уже закрыты."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT category_key FROM completions "
                "WHERE day < ? AND category_key LIKE ?",
                (day.isoformat(), f"{TASK_PREFIX}%"),
            ).fetchall()
        return {key for (key,) in rows}

    def add_focus(self, day: date, key: str | None, started_at: datetime, minutes: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO focus_sessions (day, task_key, started_at, minutes) "
                "VALUES (?, ?, ?, ?)",
                (day.isoformat(), key, started_at.isoformat(timespec="seconds"), minutes),
            )

    def focus_count(self, day: date) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM focus_sessions WHERE day = ?", (day.isoformat(),)
            ).fetchone()
        return row[0]

    # --- заметки ---

    def add_note(
        self, day: date, key: str, title: str, text: str, created_at: datetime, source: str
    ) -> Note:
        stamp = created_at.isoformat(timespec="seconds")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO notes (day, item_key, item_title, text, created_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (day.isoformat(), key, title, text, stamp, source),
            )
        return Note(cur.lastrowid, day, key, title, text, datetime.fromisoformat(stamp))

    def delete_note(self, note_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return cur.rowcount == 1

    def notes_between(self, first: date, last: date) -> list[Note]:
        """Заметки с first по last включительно, по времени записи."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, day, item_key, item_title, text, created_at FROM notes "
                "WHERE day BETWEEN ? AND ? ORDER BY created_at, id",
                (first.isoformat(), last.isoformat()),
            ).fetchall()
        return [
            Note(i, date.fromisoformat(d), k, t, text, datetime.fromisoformat(at))
            for i, d, k, t, text, at in rows
        ]

    # --- для выгрузки истории ---

    def completions_between(self, first: date, last: date) -> list[tuple[date, str, datetime]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT day, category_key, done_at FROM completions "
                "WHERE day BETWEEN ? AND ? ORDER BY day, done_at",
                (first.isoformat(), last.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(d), k, datetime.fromisoformat(at)) for d, k, at in rows]

    def focus_between(self, first: date, last: date) -> list[tuple[date, str | None, int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT day, task_key, minutes FROM focus_sessions "
                "WHERE day BETWEEN ? AND ? ORDER BY started_at",
                (first.isoformat(), last.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(d), k, m) for d, k, m in rows]

    def first_day(self) -> date | None:
        """Самый ранний день, о котором что-то записано."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(day) FROM (SELECT day FROM completions UNION ALL "
                "SELECT day FROM notes UNION ALL SELECT day FROM focus_sessions)"
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def task_titles(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT id, title FROM tasks").fetchall()
        return {f"{TASK_PREFIX}{i}": title for i, title in rows}
