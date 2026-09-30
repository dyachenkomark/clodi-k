"""Работа с отметками, задачами, заметками и фокусами.

Это локальный кэш. Если включена синхронизация, главная копия данных — Google Таблица.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
from datetime import date, datetime

from clodick.core.models import TASK_PREFIX, Note, Task


def new_uid() -> str:
    """Короткий случайный id, одинаково пригодный на любом устройстве."""
    return secrets.token_hex(4)


def _stamp(moment: datetime | None) -> str:
    return moment.isoformat(timespec="seconds") if moment else ""


def _moment(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


TASK_COLUMNS = "id, project, title, due, time, repeat, status, note, done_at, created_at"
# Обновление на месте: строка сохраняет свой порядок добавления.
TASK_UPSERT = (
    f"INSERT INTO tasks ({TASK_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
    "ON CONFLICT(id) DO UPDATE SET project=excluded.project, title=excluded.title, "
    "due=excluded.due, time=excluded.time, repeat=excluded.repeat, status=excluded.status, "
    "note=excluded.note, done_at=excluded.done_at, created_at=excluded.created_at"
)


def _task(row: tuple) -> Task:
    tid, project, title, due, time, repeat, status, note, done_at, created_at = row
    return Task(
        id=tid,
        title=title,
        daily=repeat == "daily",
        project=project,
        due=_day(due),
        time=time,
        done=status == "done",
        done_at=_moment(done_at),
        note=note,
        created_at=_moment(created_at),
    )


class CompletionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # Интерфейс и синхронизация работают из разных потоков.
        self.lock = threading.Lock()

    # --- отметки ---

    def add(self, key: str, day: date, done_at: datetime, source: str, title: str = "") -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO completions (category_key, day, done_at, source, title) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, day.isoformat(), _stamp(done_at), source, title),
            )
            return cur.rowcount == 1

    def remove(self, key: str, day: date) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "DELETE FROM completions WHERE category_key = ? AND day = ?",
                (key, day.isoformat()),
            )
            return cur.rowcount == 1

    def completions_for(self, day: date) -> dict[str, datetime]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT category_key, done_at FROM completions WHERE day = ?",
                (day.isoformat(),),
            ).fetchall()
        return {key: datetime.fromisoformat(done_at) for key, done_at in rows}

    def fill_titles(self, titles: dict[str, str]) -> None:
        """Дописать названия старым отметкам, сделанным до появления колонки title."""
        with self.lock, self.conn:
            self.conn.executemany(
                "UPDATE completions SET title = ? WHERE category_key = ? AND title = ''",
                [(title, key) for key, title in titles.items()],
            )

    def completion_titles(self) -> dict[str, str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT category_key, title FROM completions WHERE title != '' ORDER BY done_at"
            ).fetchall()
        return dict(rows)

    # --- задачи ---

    def save_task(self, task: Task) -> Task:
        """Добавить задачу или заменить существующую с тем же id."""
        with self.lock, self.conn:
            self.conn.execute(
                TASK_UPSERT,
                (
                    task.id,
                    task.project,
                    task.title,
                    task.due.isoformat() if task.due else "",
                    task.time,
                    "daily" if task.daily else "",
                    "done" if task.done else "todo",
                    task.note,
                    _stamp(task.done_at),
                    _stamp(task.created_at),
                ),
            )
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self.lock:
            row = self.conn.execute(
                f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _task(row) if row else None

    def remove_task(self, task_id: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.conn.execute(
                "DELETE FROM completions WHERE category_key = ?", (f"{TASK_PREFIX}{task_id}",)
            )
            return cur.rowcount == 1

    def tasks(self) -> list[Task]:
        with self.lock:
            rows = self.conn.execute(
                f"SELECT {TASK_COLUMNS} FROM tasks ORDER BY created_at, rowid"
            ).fetchall()
        return [_task(row) for row in rows]

    # --- фокусы Pomodoro ---

    def add_focus(self, day: date, key: str | None, started_at: datetime, minutes: int) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO focus_sessions (day, task_key, started_at, minutes, uid) "
                "VALUES (?, ?, ?, ?, ?)",
                (day.isoformat(), key, _stamp(started_at), minutes, new_uid()),
            )

    def focus_count(self, day: date) -> int:
        with self.lock:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM focus_sessions WHERE day = ?", (day.isoformat(),)
            ).fetchone()
        return row[0]

    # --- заметки ---

    def add_note(
        self, day: date, key: str, title: str, text: str, created_at: datetime, source: str
    ) -> Note:
        stamp = _stamp(created_at)
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO notes (day, item_key, item_title, text, created_at, source, uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day.isoformat(), key, title, text, stamp, source, new_uid()),
            )
        return Note(cur.lastrowid, day, key, title, text, datetime.fromisoformat(stamp))

    def delete_note(self, note_id: int) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return cur.rowcount == 1

    def notes_between(self, first: date, last: date) -> list[Note]:
        """Заметки с first по last включительно, по времени записи."""
        with self.lock:
            rows = self.conn.execute(
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
        with self.lock:
            rows = self.conn.execute(
                "SELECT day, category_key, done_at FROM completions "
                "WHERE day BETWEEN ? AND ? ORDER BY day, done_at",
                (first.isoformat(), last.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(d), k, datetime.fromisoformat(at)) for d, k, at in rows]

    def focus_between(self, first: date, last: date) -> list[tuple[date, str | None, int]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT day, task_key, minutes FROM focus_sessions "
                "WHERE day BETWEEN ? AND ? ORDER BY started_at",
                (first.isoformat(), last.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(d), k, m) for d, k, m in rows]

    def first_day(self) -> date | None:
        """Самый ранний день, о котором что-то записано."""
        with self.lock:
            row = self.conn.execute(
                "SELECT MIN(day) FROM (SELECT day FROM completions UNION ALL "
                "SELECT day FROM notes UNION ALL SELECT day FROM focus_sessions)"
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None
