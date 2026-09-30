"""Синхронизация с таблицей: вместо Google — лист в памяти."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from fakes import FakeSheet

from clodick.core.tracker import Tracker
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.sync.engine import merge
from clodick.sync.tables import TasksTable, sync_all

NOW = datetime(2026, 9, 30, 12, 0)  # среда


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def world(config, repo):
    sheet = FakeSheet()
    clock = Clock(NOW)
    tracker = Tracker(config, repo, clock=clock)

    def sync():
        return sync_all(repo, sheet, clock())

    return tracker, repo, sheet, sync, clock


def test_merge_rules():
    cols = ("id", "a", "b")
    base = {"id": "1", "a": "x", "b": "y"}
    mine = {"id": "1", "a": "X", "b": "y"}
    theirs = {"id": "1", "a": "x", "b": "Y"}
    assert merge(mine, theirs, base, cols) == {"id": "1", "a": "X", "b": "Y"}  # разные поля
    both = {"id": "1", "a": "T", "b": "y"}
    assert merge(mine, both, base, cols)["a"] == "T"  # одно поле: побеждает таблица
    assert merge(mine, None, base, cols) is None  # удалили в таблице
    assert merge(None, base, base, cols) is None  # удалили в клодике
    assert merge(None, theirs, base, cols) == theirs  # удалили тут, но там правили
    assert merge(mine, None, None, cols) == mine  # новое локальное
    assert merge(None, theirs, None, cols) == theirs  # новое из таблицы


def test_first_sync_uploads_everything_and_second_is_quiet(world):
    tracker, _, sheet, sync, _ = world
    tracker.add_from_text("maga: report by fri 15:00")
    tracker.mark_done("sport")
    tracker.add_note("sport", "5 km")
    tracker.add_focus("study", NOW, 25)

    report = sync()
    assert (report.pulled, report.pushed) == (0, 4)
    task = sheet.row("Tasks", title="report")
    assert (task["due"], task["time"], task["status"]) == ("2026-10-02", "15:00", "todo")
    log = sheet.row("Log", item="sport")
    assert (log["day"], log["title"]) == ("2026-09-30", "Sport")
    assert log["done_at"] == "2026-09-30 12:00:00"
    assert sheet.row("Notes", item="sport")["text"] == "5 km"
    assert sheet.row("Focus", item="study")["minutes"] == "25"

    writes = sheet.writes
    again = sync()
    assert (again.pulled, again.pushed) == (0, 0)
    assert sheet.writes == writes


def test_new_machine_restores_everything_from_sheet(world, config, tmp_path):
    tracker, _, sheet, sync, clock = world
    tracker.add_from_text("maga: report by fri")
    tracker.mark_done("sport")
    tracker.add_note("sport", "5 km")
    sync()

    conn = connect(tmp_path / "fresh.db")
    fresh_repo = CompletionRepository(conn)
    report = sync_all(fresh_repo, sheet, clock())
    assert report.pushed == 0
    fresh = Tracker(config, fresh_repo, clock=clock)
    status = fresh.status()
    assert status.items[0].done
    assert status.items[0].notes[0].text == "5 km"
    assert [i.category.title for i in status.upcoming] == ["report"]
    conn.close()


def test_row_typed_by_hand_gets_id_and_canonical_values(world):
    tracker, _, sheet, sync, _ = world
    sync()
    sheet.tabs["Tasks"].append(["", "Turkov", "Fix portal", "пт", "9:00", "", "", "", "", ""])

    report = sync()
    assert report.pulled == 1
    row = sheet.row("Tasks", title="Fix portal")
    assert len(row["id"]) == 8
    assert (row["due"], row["time"], row["status"]) == ("2026-10-02", "09:00", "todo")
    assert row["created"] == "2026-09-30 12:00:00"
    item = tracker.status().upcoming[0]
    assert (item.category.project, item.category.due) == ("Turkov", date(2026, 10, 2))


def test_done_typed_by_hand_closes_the_task(world):
    tracker, _, sheet, sync, clock = world
    task = tracker.add_task("Buy milk")
    sync()
    sheet.edit("Tasks", {"id": task.id}, status="готово")
    sync()
    item = tracker.status().items[-1]
    assert item.done
    assert sheet.row("Tasks", id=task.id)["done_at"] == "2026-09-30 12:00:00"
    clock.now = datetime(2026, 10, 1, 12, 0)
    assert task.key not in [i.category.key for i in tracker.status().items]


def test_edits_on_both_sides_are_merged_by_field(world):
    tracker, _, sheet, sync, _ = world
    task = tracker.add_task("Report", project="Maga")
    sync()
    sheet.edit("Tasks", {"id": task.id}, title="Big report")  # на телефоне
    tracker.mark_done(task.key)  # на компьютере без сети
    sync()
    row = sheet.row("Tasks", id=task.id)
    assert (row["title"], row["status"]) == ("Big report", "done")
    item = tracker.status().items[-1]
    assert (item.category.title, item.done) == ("Big report", True)


def test_same_field_conflict_sheet_wins(world):
    tracker, repo, sheet, sync, _ = world
    task = tracker.add_task("Report")
    sync()
    sheet.edit("Tasks", {"id": task.id}, title="From sheet")
    repo.save_task(replace(repo.get_task(task.id), title="From app"))
    sync()
    assert repo.get_task(task.id).title == "From sheet"


def test_row_deleted_in_sheet_disappears_locally(world):
    tracker, repo, sheet, sync, _ = world
    task = tracker.add_task("Old")
    sync()
    sheet.tabs["Tasks"] = [row for row in sheet.tabs["Tasks"] if row[0] != task.id]
    sync()
    assert repo.get_task(task.id) is None


def test_unmark_and_delete_go_to_sheet(world):
    tracker, _, sheet, sync, _ = world
    task = tracker.add_task("Temp")
    tracker.mark_done("sport")
    sync()
    tracker.unmark("sport")
    tracker.remove_task(task.key)
    sync()
    assert sheet.rows("Log") == []
    assert sheet.rows("Tasks") == []


def test_user_columns_and_order_survive(world):
    tracker, _, sheet, sync, _ = world
    task = tracker.add_task("Report")
    sync()
    # Пользователь добавил свою колонку в начало.
    sheet.tabs["Tasks"] = [["my mark", *row] for row in sheet.tabs["Tasks"]]
    sheet.tabs["Tasks"][1][0] = "важно"
    tracker.mark_done(task.key)
    sync()
    row = sheet.row("Tasks", id=task.id)
    assert (row["my mark"], row["status"]) == ("важно", "done")
    assert sheet.tabs["Tasks"][0][0] == "my mark"


def test_checkmark_typed_in_log_sheet_counts(world):
    tracker, _, sheet, sync, _ = world
    sync()
    sheet.tabs["Log"].append(["", "сегодня", "study", "", "", ""])
    sync()
    assert tracker.status().items[1].done
    row = sheet.row("Log", item="study")
    assert (row["id"], row["source"]) == ("2026-09-30|study", "sheet")


def test_blank_rows_and_odd_values_are_tolerated(world):
    tracker, _, sheet, sync, _ = world
    sync()
    sheet.tabs["Tasks"].append([""] * 10)
    sheet.tabs["Tasks"].append(
        ["", "", "Odd", "когда-нибудь", "soon", "often", "maybe", "", "", ""]
    )
    sync()
    row = sheet.row("Tasks", title="Odd")
    assert (row["due"], row["time"]) == ("когда-нибудь", "soon")
    assert (row["repeat"], row["status"]) == ("", "todo")
    assert tracker.status().items[-1].category.due is None


def test_tasks_sheet_starts_with_id_column(repo):
    assert TasksTable(repo.conn, repo.lock).columns[0] == "id"
