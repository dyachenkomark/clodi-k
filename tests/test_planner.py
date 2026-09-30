"""Задачи со сроками: трекер, напоминания, миграция старой базы, настройки, консоль."""

import sqlite3
from datetime import date, datetime

import pytest

from clodick.app import main
from clodick.config import ConfigError, parse_config
from clodick.core.reminders import greeting_text, reminder_text, timed_text
from clodick.core.tracker import Tracker
from clodick.storage.db import MIGRATIONS, connect
from clodick.storage.repository import CompletionRepository


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def tracker(config, repo):
    return Tracker(config, repo, clock=Clock(datetime(2026, 9, 30, 12, 0)))  # среда


def keys(items):
    return [i.category.title for i in items]


def test_tasks_are_split_into_today_and_soon(tracker):
    tracker.add_from_text("maga: report by fri")
    tracker.add_from_text("turkov: deploy today 18:00")
    tracker.add_from_text("pay rent by 25.09")
    tracker.add_from_text("buy milk")
    tracker.add_from_text("release 2026-12-01")
    tracker.add_from_text("stretch daily")

    status = tracker.status()
    assert keys(status.items) == [
        "Sport", "Study", "Language", "stretch", "pay rent", "deploy", "buy milk",
    ]  # fmt: skip
    assert keys(status.upcoming) == ["report"]
    assert status.total == 7  # «скоро» в счёт дня не входит
    rent = status.items[4].category
    assert (rent.due, rent.project) == (date(2026, 9, 25), "")
    assert [t.title for t in tracker.open_tasks()] == [
        "pay rent", "deploy", "report", "release", "buy milk",
    ]  # fmt: skip


def test_soon_task_can_be_done_early_and_undone(tracker):
    task = tracker.add_from_text("report by fri")
    assert tracker.mark_done(task.key) is True
    assert tracker.mark_done(task.key) is False
    assert tracker.status().upcoming[0].done
    assert tracker.unmark(task.key) is True
    assert not tracker.status().upcoming[0].done
    assert tracker.unmark(task.key) is False


def test_daily_task_is_marked_per_day(tracker):
    task = tracker.add_from_text("stretch daily")
    tracker.mark_done(task.key)
    assert tracker.status().items[3].done
    tracker._clock.now = datetime(2026, 10, 1, 12, 0)
    assert not tracker.status().items[3].done


def test_due_now_fires_once_time_has_come(tracker):
    tracker.add_from_text("call Anna 12:30")
    tracker.add_from_text("standup today 11:00")
    tracker.add_from_text("old thing by 25.09 09:00")
    due = tracker.due_now()
    assert [c.title for c in due] == ["standup"]  # 12:30 ещё не наступило, просрочка молчит
    assert tracker.due_now({due[0].key}) == []
    tracker._clock.now = datetime(2026, 9, 30, 12, 31)
    assert [c.title for c in tracker.due_now({due[0].key})] == ["call Anna"]


def test_reminders_mention_overdue_and_tomorrow(tracker):
    for key in ("sport", "study", "language"):
        tracker.mark_done(key)
    assert reminder_text(tracker.status()) is None
    tracker.add_from_text("pay rent by 25.09")
    tracker.add_from_text("report tomorrow")
    text = reminder_text(tracker.status())
    assert text == "Hey! Still to do: pay rent (overdue). Due tomorrow: report."
    assert greeting_text(tracker.status()).startswith("Hi! Today: pay rent (overdue).")
    assert timed_text(["a", "b"]) == "It's time: a, b."


def test_long_reminder_is_shortened(tracker):
    for n in range(4):
        tracker.add_task(f"task {n}")
    text = reminder_text(tracker.status())
    assert text == "Hey! Still to do: Sport, Study, Language, task 0 and 3 more."


def test_migration_keeps_old_checklist_tasks(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for version, sql in enumerate(MIGRATIONS[:5], start=1):
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version = {version}")
    conn.executescript(
        """
        INSERT INTO tasks (id, title, daily, created_at) VALUES
            (1, 'Stretch', 1, '2026-09-27T10:00:00'),
            (2, 'Buy milk', 0, '2026-09-27T10:01:00'),
            (3, 'Call Anna', 0, '2026-09-27T10:02:00');
        INSERT INTO completions (category_key, day, done_at, source) VALUES
            ('task:1', '2026-09-27', '2026-09-27T11:00:00', 'desktop'),
            ('task:2', '2026-09-27', '2026-09-27T12:00:00', 'desktop'),
            ('sport', '2026-09-27', '2026-09-27T13:00:00', 'desktop');
        INSERT INTO notes (day, item_key, item_title, text, created_at, source) VALUES
            ('2026-09-27', 'sport', 'Sport', '5 km', '2026-09-27T13:01:00', 'desktop');
        INSERT INTO focus_sessions (day, task_key, started_at, minutes) VALUES
            ('2026-09-27', 'sport', '2026-09-27T09:00:00', 25);
        """
    )
    conn.commit()
    conn.close()

    conn = connect(path)
    repo = CompletionRepository(conn)
    tasks = {t.id: t for t in repo.tasks()}
    assert (tasks["1"].daily, tasks["1"].done) == (True, False)
    assert (tasks["2"].done, tasks["2"].done_at) == (True, datetime(2026, 9, 27, 12, 0))
    assert (tasks["3"].done, tasks["3"].key) == (False, "task:3")
    uid = conn.execute("SELECT uid FROM notes").fetchone()[0]
    assert len(uid) == 8
    assert len(conn.execute("SELECT uid FROM focus_sessions").fetchone()[0]) == 8
    assert repo.completions_for(date(2026, 9, 27))["sport"] == datetime(2026, 9, 27, 13, 0)
    conn.close()


def test_sheets_and_projects_settings():
    base = {"categories": [{"key": "a", "title": "A"}]}
    config = parse_config(base)
    assert not config.sheets.enabled
    url = "https://docs.google.com/spreadsheets/d/1AbC_dEf-123/edit#gid=0"
    config = parse_config(
        {
            **base,
            "sheets": {"spreadsheet_id": url, "sync_seconds": 30},
            "projects": {"Maga": ["мага"], "Turkov": "турков"},
        }
    )
    assert config.sheets.enabled
    assert (config.sheets.spreadsheet_id, config.sheets.sync_seconds) == ("1AbC_dEf-123", 30)
    assert config.projects == {"Maga": ("мага",), "Turkov": ("турков",)}
    with pytest.raises(ConfigError, match="sync_seconds"):
        parse_config({**base, "sheets": {"sync_seconds": 1}})
    with pytest.raises(ConfigError, match=r"projects\.Maga"):
        parse_config({**base, "projects": {"Maga": 5}})


def test_cli_add_tasks_and_sync_not_set_up(capsys):
    assert main(["add", "work:", "report", "by", "2030-01-15", "10:00"]) == 0
    out = capsys.readouterr().out
    assert "15.01.2030 10:00 [work] report" in out

    assert main(["tasks"]) == 0
    listed = capsys.readouterr().out
    assert "[work] report" in listed
    key = listed.split()[0]

    assert main(["done", key]) == 0
    capsys.readouterr()
    assert main(["tasks"]) == 0
    assert "No open tasks." in capsys.readouterr().out

    assert main(["add", "by", "fri"]) == 2
    assert main(["sync"]) == 2
    assert "not connected" in capsys.readouterr().out
