"""План дня: сроки первыми, потом отстающие темы; выбран один раз на день."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from fakes import FakeSheet

from clodick.config import load_config
from clodick.core import plan
from clodick.core.tracker import Tracker
from clodick.mcp_server import Desk
from clodick.storage.state import StateStore
from clodick.sync.tables import sync_all

NOW = datetime(2026, 9, 30, 12, 0)  # среда


class World:
    def __init__(self, config, repo):
        self.now = NOW
        self.tracker = Tracker(config, repo, clock=lambda: self.now)
        self.state = StateStore(repo.conn)
        self.repo = repo

    def norm(self, name, percent):
        self.tracker.add_topic(name)
        self.tracker.update_topic(name, percent=percent)

    def touch(self, task, days_ago):
        """Заметка к задаче days_ago дней назад."""
        self.now = NOW - timedelta(days=days_ago)
        self.tracker.add_note(task.key, "worked")
        self.now = NOW

    def plan(self):
        return plan.todays_plan(self.tracker, self.state)


@pytest.fixture
def world(config, repo):
    return World(config, repo)


def test_topic_behind_its_norm_comes_first(world):
    world.norm("Turkov", 40)
    world.norm("Languages", 10)
    turkov = world.tracker.add_from_text("portal", topic="Turkov")
    english = world.tracker.add_from_text("english lesson", topic="Languages")
    world.touch(turkov, 1)  # долг 40×1
    world.touch(english, 4)  # долг 10×4: столько же, обе в плане
    items = world.plan()
    assert {i.title for i in items} == {"portal", "english lesson"}
    assert next(i for i in items if i.title == "english lesson").why == "no marks for 4 days"

    found = plan.directions(world.tracker)
    assert [d.idle_days for d in sorted(found, key=lambda d: d.name)] == [4, 1]


def test_small_norm_loses_to_big_one_until_it_has_waited(world):
    world.norm("Turkov", 40)
    world.norm("Languages", 10)
    turkov = world.tracker.add_from_text("portal", topic="Turkov")
    english = world.tracker.add_from_text("english lesson", topic="Languages")
    world.touch(turkov, 2)
    world.touch(english, 2)
    assert [d.name for d in plan.directions(world.tracker)] == ["Turkov", "Languages"]
    world.touch(turkov, 0)
    assert [d.name for d in plan.directions(world.tracker)] == ["Languages", "Turkov"]


def test_deadlines_first_but_they_leave_room_for_what_is_behind(world):
    world.norm("Maga", 30)
    world.norm("Languages", 10)
    for name in ("report", "slides", "review"):
        world.tracker.add_from_text(f"maga: {name} today")
    world.tracker.add_from_text("english lesson", topic="Languages")
    items = world.plan()
    assert [i.title for i in items] == ["report", "slides", "english lesson"]
    assert items[0].why == "due today"
    assert items[2].why == "no marks for 7+ days"


def test_free_places_go_to_the_other_deadlines(world):
    world.norm("Maga", 30)
    task = None
    for name in ("report", "slides", "review"):
        task = world.tracker.add_from_text(f"maga: {name} today")
    world.touch(task, 0)
    assert [i.title for i in world.plan()] == ["report", "slides", "review"]


def test_direction_without_a_task_asks_to_pick_one(world):
    world.norm("IT", 20)
    items = world.plan()
    assert [(i.key, i.title) for i in items] == [("", "IT: pick a task")]
    assert plan.plan_line(items) == "★ Plan 0/1 · IT: pick a task"
    # Что-то отмечено в теме: пункт закрыт, хотя задачи в плане не было.
    task = world.tracker.add_from_text("async lesson", topic="IT")
    world.touch(task, 0)
    assert world.plan()[0].done


def test_habit_counts_for_its_topic(config, repo):
    study = next(c for c in config.categories if c.key == "study")
    categories = tuple(replace(c, project="IT") if c is study else c for c in config.categories)
    world = World(replace(config, categories=categories), repo)
    world.norm("IT", 20)
    assert [i.key for i in world.plan()] == ["study"]  # следующее дело темы — привычка
    world.tracker.mark_done("study")
    assert world.plan()[0].done
    assert world.tracker.last_activity(0) == {"it": NOW.date()}


def test_plan_stays_the_same_all_day_and_changes_the_next_day(world):
    world.norm("Turkov", 40)
    world.norm("Maga", 30)
    portal = world.tracker.add_from_text("portal", topic="Turkov")
    report = world.tracker.add_from_text("report", topic="Maga")
    assert [i.key for i in world.plan()] == [portal.key, report.key]

    world.tracker.mark_done(portal.key)
    world.tracker.add_from_text("urgent today", topic="Maga")
    first, second = world.plan()
    assert first.done and not second.done and first.key == portal.key
    assert plan.plan_text([first, second]).startswith("Plan 1/2. Left: report (")

    world.now = NOW + timedelta(days=1)
    assert world.plan()[0].title == "urgent"


def test_deleted_task_leaves_the_plan(world):
    world.norm("Turkov", 40)
    task = world.tracker.add_from_text("portal", topic="Turkov")
    assert world.plan()
    world.tracker.remove_task(task.key)
    assert world.plan() == []
    assert plan.plan_text([]) == ""


def test_all_done_text(world):
    world.norm("Turkov", 40)
    task = world.tracker.add_from_text("portal", topic="Turkov")
    world.plan()
    world.tracker.mark_done(task.key)
    assert plan.plan_text(world.plan()) == "Today's plan is done!"


def test_config_habit_can_name_its_topic(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[[categories]]\nkey = "study"\ntitle = "Study"\nproject = "IT"\n', encoding="utf-8"
    )
    assert load_config(path).categories[0].project == "IT"


def test_percent_travel_through_the_sheet(world, repo):
    world.norm("Turkov", 40)
    world.tracker.add_topic("Personal")
    sheet = FakeSheet()
    sync_all(repo, sheet, NOW)
    assert sheet.row("Topics", name="Turkov")["percent"] == "40"
    assert sheet.row("Topics", name="Personal")["percent"] == ""


def test_mcp_plan_and_percent(world):
    desk = Desk(world.tracker, world.state)
    world.tracker.add_topic("IT")
    assert "No plan for today" in desk.plan()
    assert desk.set_percent("nope", 5).startswith("No topic")
    assert "between 0 and 100" in desk.set_percent("IT", 500)
    assert desk.set_percent("it", 20) == "IT: 20% of time."
    assert "- IT, 20% of time" in desk.list_topics()
    text = desk.plan()
    assert "«IT: pick a task» — IT, no marks for 7+ days" in text
    assert "- IT: 20%, no marks for 7d" in text
