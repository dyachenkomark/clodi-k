import dataclasses
import random
from datetime import datetime

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from clodick.core.reminders import DONE_TEXT
from clodick.core.tracker import Tracker
from clodick.desktop.brain import Mode
from clodick.desktop.controller import DesktopApp
from clodick.desktop.themes import THEMES
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

    def factory(clock=None, theme="classic"):
        clock = clock or Clock(datetime(2026, 9, 26, 9, 0))
        cfg = dataclasses.replace(config, desktop=dataclasses.replace(config.desktop, theme=theme))
        tracker = Tracker(cfg, repo, clock=clock)
        desktop = DesktopApp(
            qapp,
            cfg,
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
        for window in (desktop.pet, desktop.bubble, desktop.checklist):
            window.close()
            window.deleteLater()
    qapp.processEvents()


def test_starts_with_raccoon_above_taskbar(make_desktop):
    desktop, _, _ = make_desktop()
    assert desktop.pet.isVisible()
    area = desktop._screen_rect()
    assert desktop.pet.geometry().bottom() == area.bottom()
    assert desktop.pet.geometry().right() < area.right()
    assert desktop._ram == 42
    if desktop.tray is not None:
        assert "RAM 42%" in desktop.tray.toolTip()


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
    assert desktop.bubble.text == "Hey! Still to do: Study, Language."


def test_reminders_can_be_turned_off(make_desktop):
    desktop, _, clock = make_desktop()
    desktop.set_reminders(False)
    clock.now = datetime(2026, 9, 26, 10, 0, 30)
    desktop.check_reminders_now()
    assert not desktop.bubble.isVisible()


def test_hide_and_show(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.set_visible(False)
    assert not desktop.pet.isVisible()
    desktop.set_visible(True)
    assert desktop.pet.isVisible()


def test_dragged_raccoon_stays_and_is_remembered(make_desktop):
    first, _, _ = make_desktop()
    first.brain._walk_to(first.brain.x - 200)
    first.brain._outside = True
    first.pet.move(100, 200)
    first.pet.drag_moved.emit()
    first.pet.drag_finished.emit()
    assert first.brain.at_home
    assert first.brain.mode is Mode.SIT
    assert (first.pet.x(), first.pet.y()) == (100, 200)

    second, _, _ = make_desktop()
    assert (second.pet.x(), second.pet.y()) == (100, 200)
    assert second.brain.home_x == 100


def test_raccoon_moves_to_where_old_house_stood(make_desktop):
    first, _, _ = make_desktop()
    first._state.set("house_pos", [100, 200])
    second, _, _ = make_desktop()
    scale = second._scale
    assert second.pet.x() == 100 + 36 * scale
    assert second.pet.y() + second.pet.height() == 200 + 30 * scale


def test_walking_moves_window(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.brain._walk_to(desktop.brain.x - 200)
    desktop.brain._outside = True
    start = desktop.pet.x()
    for _ in range(10):
        desktop.brain.tick(0.1)
        desktop._after_brain_change()
    assert desktop.pet.x() < start


@pytest.mark.parametrize("theme", list(THEMES))
def test_every_theme_starts(make_desktop, theme):
    desktop, _, _ = make_desktop(theme=theme)
    assert desktop.theme.key == theme
    desktop.open_checklist()
    desktop.say("проверка")
    assert not desktop.pet.grab().isNull()
    assert not desktop.checklist.grab().isNull()


def _write_blob(folder):
    folder.mkdir(parents=True)
    frame = "'''\n.KK.\nKKKK\nKKKK\n.KK.\n'''"
    animations = "\n".join(
        f"[animations.{name}]\nframes = [{frame}]" for name in ("sit", "sleep", "wave", "walk")
    )
    (folder / "character.toml").write_text(
        f'id = "blob"\nname = "Капля"\nsize = [4, 4]\n[palette]\nK = "#d97757"\n{animations}',
        encoding="utf-8",
    )


def test_switch_character_at_runtime(make_desktop):
    from clodick import paths

    _write_blob(paths.data_dir() / "characters" / "blob")
    desktop, _, _ = make_desktop()
    assert "blob" in desktop.characters
    feet = desktop.pet.y() + desktop.pet.height()
    desktop.set_character("blob")
    assert desktop.character.id == "blob"
    assert desktop.pet.size().width() == 4 * desktop._scale
    assert desktop.pet.y() + desktop.pet.height() == feet

    again, _, _ = make_desktop()
    assert again.character.id == "blob"


def test_unknown_character_falls_back_to_raccoon(make_desktop):
    desktop, _, _ = make_desktop()
    desktop._state.set("character", "nobody")
    again, _, _ = make_desktop()
    assert again.character.id == "raccoon"


def test_png_sheet_character(qapp, tmp_path):
    from PySide6.QtGui import QColor, QImage

    from clodick.characters import load_character
    from clodick.desktop.sprites import SpriteBook

    sheet = QImage(6, 3, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#d97757"))
    sheet.setPixelColor(3, 0, QColor("#141413"))
    sheet.save(str(tmp_path / "all.png"))
    blocks = "\n".join(
        f'[animations.{name}]\nsheet = "all.png"\ncount = 2'
        for name in ("sit", "sleep", "wave", "walk")
    )
    (tmp_path / "character.toml").write_text(f'id = "png"\nsize = [3, 3]\n{blocks}')

    book = SpriteBook(2, character=load_character(tmp_path))
    first = book.character_frame("walk", 0).toImage()
    second = book.character_frame("walk", 1).toImage()
    assert first.size().width() == 6
    assert first.pixelColor(0, 0) == QColor("#d97757")
    assert second.pixelColor(0, 0) == QColor("#141413")


def test_add_and_remove_task_from_checklist(make_desktop):
    desktop, tracker, _ = make_desktop()
    desktop.open_checklist()
    assert desktop.checklist._title.text() == "Today, Sep 26"
    desktop.checklist.new_task.setText("Buy milk")
    desktop.checklist.new_task.returnPressed.emit()
    assert desktop.checklist.new_task.text() == ""
    key = next(k for k in desktop.checklist.boxes if k.startswith("task:"))
    assert desktop.checklist.boxes[key].text() == "Buy milk"
    assert set(desktop.checklist.remove_buttons) == {key}

    desktop.checklist.boxes[key].setChecked(True)
    assert tracker.status().done_count == 1

    desktop.checklist.remove_buttons[key].click()
    assert key not in desktop.checklist.boxes
    assert tracker.status().total == 3


class FakeCursor:
    def __init__(self):
        self.pos = QPoint(0, 0)

    def __call__(self):
        return self.pos


@pytest.fixture
def playful_desktop(qapp, config, repo):
    state = StateStore(repo._conn)
    cursor = FakeCursor()
    desktop = DesktopApp(
        qapp,
        config,
        Tracker(config, repo),
        state,
        ram_reader=lambda: 42,
        rng=random.Random(3),
        cursor=cursor,
    )
    desktop.start()
    desktop._cursor_timer.stop()
    yield desktop, cursor
    for window in (desktop.pet, desktop.bubble, desktop.checklist):
        window.close()
        window.deleteLater()
    qapp.processEvents()


def test_ram_is_written_on_belly(playful_desktop):
    desktop, _ = playful_desktop
    assert desktop.pet.belly_text == "42%"
    desktop.brain._walk_to(desktop.brain.x - 100)
    desktop._apply_frame(restart=True)
    assert desktop.pet.belly_text is None
    desktop.brain._sit()
    desktop._apply_frame(restart=True)
    desktop.set_belly_ram(False)
    assert desktop.pet.belly_text is None


def test_fast_cursor_makes_raccoon_dodge(playful_desktop):
    desktop, cursor = playful_desktop
    center = desktop.pet.geometry().center()
    cursor.pos = QPoint(center.x() - 300, center.y())
    desktop._watch_cursor(now=10.0)
    cursor.pos = center
    desktop._watch_cursor(now=10.1)
    assert desktop.brain.mode is Mode.WALK
    assert not desktop.brain.at_home


def test_slow_cursor_does_not_scare_and_pets(playful_desktop):
    desktop, cursor = playful_desktop
    center = desktop.pet.geometry().center()
    cursor.pos = center
    for step in range(20):
        desktop._watch_cursor(now=10.0 + step * 0.1)
    assert desktop.brain.at_home
    assert desktop.pet.heart_visible


def test_playful_off_stops_watching(playful_desktop):
    desktop, _ = playful_desktop
    desktop.set_playful(False)
    assert not desktop._cursor_timer.isActive()
    desktop.set_playful(True)
    assert desktop._cursor_timer.isActive()


def test_checking_a_task_makes_raccoon_hop(playful_desktop):
    desktop, _ = playful_desktop
    home_y = desktop.pet.y()
    desktop.open_checklist()
    desktop.checklist.boxes["sport"].setChecked(True)
    assert desktop.pet.y() < home_y
    for _ in range(10):
        desktop._hop_step()
    assert desktop.pet.y() == home_y


def test_raccoon_has_extra_poses(playful_desktop):
    desktop, _ = playful_desktop
    assert set(desktop.brain.fidgets) == {Mode.WASH, Mode.STRETCH}


def test_checking_a_task_gives_a_cookie(playful_desktop):
    desktop, _ = playful_desktop
    desktop.open_checklist()
    desktop.checklist.boxes["study"].setChecked(True)
    assert desktop.brain.mode is Mode.EAT
    assert desktop.pet.belly_text is None


def test_raccoon_looks_at_nearby_cursor(playful_desktop):
    desktop, cursor = playful_desktop
    rect = desktop.pet.geometry()
    sit_frame = desktop.pet._pixmap.toImage()
    cursor.pos = rect.center() + QPoint(-rect.width(), 0)
    desktop._watch_cursor(now=10.0)
    desktop._watch_cursor(now=12.0)
    assert desktop._look == 0
    assert desktop.pet._pixmap.toImage() != sit_frame
    cursor.pos = rect.center() + QPoint(2000, 0)
    desktop._watch_cursor(now=14.0)
    assert desktop._look is None


def test_dodge_catches_cursor_that_jumps_over_raccoon_between_polls(playful_desktop):
    desktop, cursor = playful_desktop
    rect = desktop.pet.geometry()
    y = rect.center().y()
    cursor.pos = QPoint(rect.left() - 150, y)
    desktop._watch_cursor(now=10.0)
    cursor.pos = QPoint(rect.right() + 150, y)
    desktop._watch_cursor(now=10.1)
    assert desktop.brain.mode is Mode.WALK
    assert desktop.brain.facing == 1
