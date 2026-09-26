import random
from datetime import datetime

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from clodick.core.reminders import DONE_TEXT
from clodick.core.tracker import Tracker
from clodick.desktop.brain import Mode
from clodick.desktop.controller import RACCOON_HOME_OFFSET, DesktopApp
from clodick.storage.state import StateStore


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def make_desktop(qapp, config, repo):
    created = []
    state = StateStore(repo._conn)

    def factory(clock=None):
        clock = clock or Clock(datetime(2026, 9, 26, 9, 0))
        tracker = Tracker(config, repo, clock=clock)
        desktop = DesktopApp(
            qapp,
            config,
            tracker,
            state,
            ram_reader=lambda: 42,
            clock=clock,
            rng=random.Random(3),
        )
        desktop.start()
        created.append(desktop)
        return desktop, tracker, clock

    yield factory
    for desktop in created:
        for window in (desktop.house, desktop.raccoon, desktop.bubble, desktop.checklist):
            window.close()
            window.deleteLater()
    qapp.processEvents()


def test_starts_with_house_and_raccoon(make_desktop):
    desktop, _, _ = make_desktop()
    assert desktop.house.isVisible()
    assert desktop.raccoon.isVisible()
    scale = desktop._scale
    assert desktop.raccoon.x() == desktop.house.x() + RACCOON_HOME_OFFSET[0] * scale
    assert desktop.raccoon.y() == desktop.house.y() + RACCOON_HOME_OFFSET[1] * scale
    assert desktop.house._ram == 42


def test_checklist_marks_task(make_desktop):
    desktop, tracker, _ = make_desktop()
    desktop.open_checklist()
    assert desktop.checklist.isVisible()
    assert set(desktop.checklist.boxes) == {"sport", "study", "language"}

    desktop.checklist.boxes["sport"].setChecked(True)
    assert tracker.status().done_count == 1

    desktop.checklist.boxes["sport"].setChecked(False)
    assert tracker.status().done_count == 0


def test_all_done_celebrates(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.open_checklist()
    for box in desktop.checklist.boxes.values():
        box.setChecked(True)
    assert desktop.bubble.isVisible()
    assert desktop.bubble.text == DONE_TEXT
    assert desktop.brain.mode is Mode.WAVE


def test_reminder_shows_pending(make_desktop):
    desktop, tracker, clock = make_desktop()
    tracker.mark_done("sport")
    clock.now = datetime(2026, 9, 26, 10, 0, 30)
    desktop.check_reminders_now()
    assert desktop.bubble.isVisible()
    assert desktop.bubble.text == "Эй! Ещё не сделано: учёба, язык."


def test_reminders_can_be_turned_off(make_desktop):
    desktop, _, clock = make_desktop()
    desktop.set_reminders(False)
    clock.now = datetime(2026, 9, 26, 10, 0, 30)
    desktop.check_reminders_now()
    assert not desktop.bubble.isVisible()


def test_hide_and_show(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.set_visible(False)
    assert not desktop.house.isVisible()
    assert not desktop.raccoon.isVisible()
    desktop.set_visible(True)
    assert desktop.house.isVisible()


def test_house_position_is_remembered(make_desktop):
    first, _, _ = make_desktop()
    first.house.move(100, 200)
    first.house.drag_moved.emit()
    first.house.drag_finished.emit()
    assert first.raccoon.x() == 100 + RACCOON_HOME_OFFSET[0] * first._scale

    second, _, _ = make_desktop()
    assert (second.house.x(), second.house.y()) == (100, 200)


def test_walking_moves_window(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.brain._walk_to(desktop.brain.x - 200)
    desktop.brain._outside = True
    start = desktop.raccoon.x()
    for _ in range(10):
        desktop.brain.tick(0.1)
        desktop._after_brain_change()
    assert desktop.raccoon.x() < start
