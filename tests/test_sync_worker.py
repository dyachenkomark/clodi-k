"""Фоновый поток синхронизации и ошибки подключения к Google — без сети."""

import time
from datetime import datetime

import pytest
from fakes import FakeSheet

from clodick.core.tracker import Tracker
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.sync import worker
from clodick.sync.google import GoogleSheetClient, SheetsError, column_letter


def wait_for(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def db(tmp_path, config):
    path = tmp_path / "cache.db"
    conn = connect(path)
    tracker = Tracker(config, CompletionRepository(conn), clock=lambda: datetime(2026, 9, 30, 12))
    yield path, tracker
    conn.close()


def test_worker_pushes_local_changes_and_reports_incoming(db, monkeypatch):
    monkeypatch.setattr(worker, "DEBOUNCE_SECONDS", 0.01)
    path, tracker = db
    sheet = FakeSheet()
    sync = worker.SheetSync(path, lambda: sheet, period=60)
    sync.start()
    try:
        assert wait_for(lambda: sync.last_ok is not None)
        assert sync.status.startswith("Sheet synced")
        assert not sync.pop_changed()

        tracker.add_task("Buy milk")
        sync.request()
        assert wait_for(lambda: any(r["title"] == "Buy milk" for r in sheet.rows("Tasks")))

        # Строка, дописанная в таблицу руками, приезжает в кэш.
        sheet.tabs["Tasks"].append(["", "Maga", "From the phone", "", "", "", "", "", "", ""])
        sync.request()
        assert wait_for(sync.pop_changed)
        assert "From the phone" in [i.category.title for i in tracker.status().items]
        assert not sync.pop_changed()
    finally:
        sync.stop()
        sync._thread.join(timeout=5)
    assert not sync._thread.is_alive()


def test_worker_survives_errors_and_recovers(db, monkeypatch):
    monkeypatch.setattr(worker, "DEBOUNCE_SECONDS", 0.01)
    path, _ = db
    sheet = FakeSheet()
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise SheetsError("No access. Share the sheet with bot@example.com as an editor.")
        return sheet

    sync = worker.SheetSync(path, factory, period=60)
    sync.start()
    try:
        assert wait_for(lambda: sync.error is not None)
        assert "No access" in sync.status
        sync.request()
        assert wait_for(lambda: sync.last_ok is not None)
        assert sync.error is None
    finally:
        sync.stop()
        sync._thread.join(timeout=5)


def test_google_client_explains_key_problems(tmp_path):
    with pytest.raises(SheetsError, match="Key file not found"):
        GoogleSheetClient.service_account(tmp_path / "missing.json", "abc")
    junk = tmp_path / "junk.json"
    junk.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(SheetsError, match="not a service account key"):
        GoogleSheetClient.service_account(junk, "abc")


def test_column_letters():
    assert [column_letter(n) for n in (1, 10, 26, 27, 52)] == ["A", "J", "Z", "AA", "AZ"]
