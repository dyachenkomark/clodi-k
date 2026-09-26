import dataclasses
import random
from datetime import datetime

import pytest

pytest.importorskip("PySide6.QtWidgets")

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
        for window in (desktop.house, desktop.pet, desktop.bubble, desktop.checklist):
            window.close()
            window.deleteLater()
    qapp.processEvents()


def test_starts_with_house_and_raccoon(make_desktop):
    desktop, _, _ = make_desktop()
    assert desktop.house.isVisible()
    assert desktop.pet.isVisible()
    dx, dy = desktop.home_offset
    assert desktop.pet.x() == desktop.house.x() + dx
    assert desktop.pet.y() == desktop.house.y() + dy
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
    assert not desktop.pet.isVisible()
    desktop.set_visible(True)
    assert desktop.house.isVisible()


def test_house_position_is_remembered(make_desktop):
    first, _, _ = make_desktop()
    first.house.move(100, 200)
    first.house.drag_moved.emit()
    first.house.drag_finished.emit()
    assert first.pet.x() == 100 + first.home_offset[0]

    second, _, _ = make_desktop()
    assert (second.house.x(), second.house.y()) == (100, 200)


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
    assert not desktop.house.grab().isNull()
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
    desktop.set_character("blob")
    assert desktop.character.id == "blob"
    scale = desktop._scale
    assert desktop.pet.size().width() == 4 * scale
    assert desktop.pet.y() + desktop.pet.height() == desktop.house.y() + 30 * scale

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
