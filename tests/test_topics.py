"""Темы задач: Turkov, Maga, Personal, Daily — хранение, быстрая запись, синхронизация."""

from dataclasses import replace
from datetime import datetime

import pytest
from fakes import FakeSheet

from clodick.core.models import Category, Topic, in_topic
from clodick.core.tracker import TOPIC_COLORS, Tracker
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.sync.tables import sync_all

NOW = datetime(2026, 9, 30, 12, 0)


@pytest.fixture
def tracker(config, repo):
    return Tracker(config, repo, clock=lambda: NOW)


def names(tracker):
    return [t.name for t in tracker.topics()]


def test_topics_are_created_in_order_with_colors(tracker):
    assert names(tracker) == []
    turkov = tracker.add_topic("Turkov")
    tracker.add_topic("Maga")
    daily = tracker.add_topic("Daily")
    assert names(tracker) == ["Turkov", "Maga", "Daily"]
    assert turkov.color == TOPIC_COLORS[0] and turkov.aliases == ("turkov",)
    assert daily.daily  # «Daily» сразу ежедневная
    assert tracker.add_topic("  turkov ") == turkov  # второй раз не заводится
    with pytest.raises(ValueError):
        tracker.add_topic("   ")


def test_topics_are_seeded_once_from_config_projects(config, repo):
    cfg = replace(config, projects={"Turkov": ("турков",), "Maga": ("мага",)})
    first = Tracker(cfg, repo, clock=lambda: NOW)
    assert names(first) == ["Turkov", "Maga"]
    first.remove_topic("Maga")
    again = Tracker(cfg, repo, clock=lambda: NOW)  # перезапуск: удалённая не воскресает
    assert names(again) == ["Turkov"]


def test_task_goes_to_the_open_topic_unless_the_text_names_one(tracker):
    tracker.add_topic("Turkov")
    tracker.add_topic("Maga")
    assert tracker.add_from_text("fix login", topic="Turkov").project == "Turkov"
    assert tracker.add_from_text("maga: report by fri", topic="Turkov").project == "Maga"
    assert tracker.add_from_text("buy milk").project == ""


def test_task_in_a_daily_topic_repeats_every_day(tracker):
    tracker.add_topic("Daily")
    task = tracker.add_from_text("stretch 10 min", topic="Daily")
    assert task.daily and task.project == "Daily"


def test_rename_moves_tasks_and_keeps_the_old_short_name(tracker):
    tracker.add_topic("Maga")
    task = tracker.add_from_text("report", topic="Maga")
    tracker.update_topic("Maga", name="Okkam")
    assert names(tracker) == ["Okkam"]
    assert tracker.title_of(task.key) == "report"
    assert tracker.add_from_text("maga: slides").project == "Okkam"  # старое имя помнит
    assert {t.project for t in tracker._repo.tasks()} == {"Okkam"}


def test_remove_topic_keeps_its_tasks_without_topic(tracker):
    tracker.add_topic("Maga")
    tracker.add_from_text("report", topic="Maga")
    tracker.remove_topic("Maga")
    assert names(tracker) == []
    assert [t.project for t in tracker._repo.tasks()] == [""]


def test_move_task_and_project_without_topic_still_shows_up(tracker):
    tracker.add_topic("Turkov")
    task = tracker.add_task("call bank", project="Bank")  # например, пришла из таблицы
    assert names(tracker) == ["Turkov", "Bank"]
    tracker.move_task(task.key, "Turkov")
    assert names(tracker) == ["Turkov"]
    with pytest.raises(KeyError):
        tracker.move_task("sport", "Turkov")  # направление из настроек — не задача


def test_change_color_and_daily(tracker):
    tracker.add_topic("Personal")
    tracker.update_topic("Personal", color="#123456", daily=True)
    topic = tracker.topic("personal")
    assert (topic.color, topic.daily) == ("#123456", True)


def test_in_topic_rules():
    daily = Topic("1", "Daily", daily=True)
    work = Topic("2", "Turkov")
    sport = Category("sport", "Sport")  # направление из настроек: ежедневное, без темы
    fix = Category("task:1", "fix", daily=False, custom=True, project="turkov")
    assert in_topic(sport, None) and in_topic(fix, None)
    assert in_topic(sport, daily) and not in_topic(sport, work)
    assert in_topic(fix, work) and not in_topic(fix, daily)


def test_topics_travel_through_the_sheet(tracker, repo, tmp_path, config):
    sheet = FakeSheet()
    tracker.add_topic("Turkov")
    tracker.add_topic("Daily")
    sync_all(repo, sheet, NOW)
    # Порядок строк в листе не важен: порядок тем задаёт колонка position.
    assert {r["name"]: r["position"] for r in sheet.rows("Topics")} == {"Turkov": "0", "Daily": "1"}
    assert sheet.row("Topics", name="Daily")["repeat"] == "daily"

    # Второе устройство: пустой кэш, темы приходят из таблицы.
    other = CompletionRepository(connect(tmp_path / "other.db"))
    try:
        other.set_flag("topics_seeded")
        sync_all(other, sheet, NOW)
        assert [t.name for t in Tracker(config, other, clock=lambda: NOW).topics()] == [
            "Turkov",
            "Daily",
        ]
    finally:
        other.conn.close()

    # Тему дописали в таблицу руками: только имя.
    sheet.tabs["Topics"].append(["", "Sport", "", "", "каждый день", ""])
    sync_all(repo, sheet, NOW)
    assert tracker.topic("Sport").daily
