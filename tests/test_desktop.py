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
    first.brain._walk_to(first.brain.x - 200, first.brain.y)
    first.brain._outside = True
    first.pet.move(100, 200)
    first.pet.drag_moved.emit()
    first.pet.drag_finished.emit()
    assert first.brain.at_home
    assert first.brain.mode is Mode.SIT
    assert (first.pet.x(), first.pet.y()) == (100, 200)

    second, _, _ = make_desktop()
    assert (second.pet.x(), second.pet.y()) == (100, 200)
    assert second.brain.home == (100, 200 + second.pet.sprite_offset)


def test_raccoon_moves_to_where_old_house_stood(make_desktop):
    first, _, _ = make_desktop()
    first._state.set("house_pos", [100, 200])
    second, _, _ = make_desktop()
    scale = second._scale
    sprite = second._sprite_pos()
    assert sprite.x() == 100 + 36 * scale
    assert sprite.y() + second.character.height * scale == 200 + 30 * scale


def test_walking_moves_window(make_desktop):
    desktop, _, _ = make_desktop()
    desktop.brain._walk_to(desktop.brain.x - 200, desktop.brain.y - 100)
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
    desktop.brain._walk_to(desktop.brain.x - 100, desktop.brain.y)
    desktop._apply_frame(restart=True)
    assert desktop.pet.belly_text is None
    desktop.brain._sit()
    desktop._apply_frame(restart=True)
    desktop.set_belly_ram(False)
    assert desktop.pet.belly_text is None


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
    assert desktop.pet._lift == 0
    desktop.open_checklist()
    desktop.checklist.boxes["sport"].setChecked(True)
    assert desktop.pet._lift > 0
    assert desktop.pet.y() == home_y  # окно на месте, отрывается только кадр от тени
    for _ in range(10):
        desktop._hop_step()
    assert desktop.pet._lift == 0


def test_raccoon_has_many_actions(playful_desktop):
    desktop, _ = playful_desktop
    actions = set(desktop.brain.actions)
    assert len(actions) >= 20
    assert {"wash", "dance", "trash", "read", "spin", "zoomies"} <= actions
    assert "eat" not in actions  # только в награду


@pytest.mark.parametrize(
    ("key", "action"), [("sport", "flex"), ("study", "read"), ("language", "sing")]
)
def test_checking_a_task_gets_its_own_reaction(playful_desktop, key, action):
    desktop, _ = playful_desktop
    desktop.open_checklist()
    desktop.checklist.boxes[key].setChecked(True)
    assert (desktop.brain.mode, desktop.brain.action) == (Mode.ACT, action)
    assert desktop._shown_anim == (action, 1)
    assert desktop.pet.belly_text is None


def test_own_task_gets_a_happy_reaction(playful_desktop):
    desktop, _ = playful_desktop
    desktop._tracker.add_task("Buy milk")
    desktop.open_checklist()
    key = next(k for k in desktop.checklist.boxes if k.startswith("task:"))
    desktop.checklist.boxes[key].setChecked(True)
    assert desktop.brain.action in ("clap", "dance", "eat")


def test_raccoon_chats_but_not_during_focus(playful_desktop):
    desktop, _ = playful_desktop
    desktop._next_chat = 0
    desktop._after_tick(1.0)
    assert desktop.bubble.isVisible()
    assert desktop.brain.mode is not Mode.WAVE  # болтовня не отвлекает от занятия
    desktop.bubble.hide()

    desktop.start_focus()
    desktop.bubble.hide()
    desktop._next_chat = 0
    desktop._after_tick(2.0)
    assert not desktop.bubble.isVisible()


def test_chatty_can_be_turned_off(playful_desktop):
    desktop, _ = playful_desktop
    desktop.set_chatty(False)
    desktop._next_chat = 0
    desktop._after_tick(1.0)
    assert not desktop.bubble.isVisible()


def test_curious_raccoon_comes_to_resting_cursor(playful_desktop):
    desktop, cursor = playful_desktop
    rect = desktop.pet.geometry()
    cursor.pos = rect.center() + QPoint(-250, 0)
    for step in range(80):
        desktop._watch_cursor(now=100.0 + step * 0.1)
    assert desktop.brain.mode is Mode.WALK
    assert desktop.brain.facing == "left"


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


@pytest.mark.parametrize(
    ("dx", "dy", "animation"),
    [
        (0, 200, ("walk_down", 1)),
        (0, -200, ("walk_up", 1)),
        (-200, 0, ("walk", -1)),
        (200, 200, ("walk_down_right", 1)),
        (-200, 200, ("walk_down_right", -1)),
        (-200, -200, ("walk_up_right", -1)),
    ],
)
def test_walk_animation_follows_direction(playful_desktop, dx, dy, animation):
    desktop, _ = playful_desktop
    desktop.brain._walk_to(desktop.brain.x + dx, desktop.brain.y + dy)
    desktop._after_brain_change()
    assert desktop._shown_anim == animation


def test_raccoon_has_shadow_under_feet(playful_desktop):
    desktop, _ = playful_desktop
    feet = desktop.pet._feet
    assert feet is not None
    left, width = feet
    assert left >= 0 and left + width <= desktop.character.width
    image = desktop.pet.grab().toImage()
    ground = desktop.pet.sprite_offset + desktop.character.height * desktop._scale
    center_x = (left + width // 2) * desktop._scale
    assert image.pixelColor(center_x, ground + 1).alpha() > 0


def test_pomodoro_focus_marks_task_and_starts_break(make_desktop):
    desktop, tracker, clock = make_desktop()
    desktop.open_checklist()
    desktop.checklist.focus_buttons["sport"].click()
    assert desktop.pomodoro.phase.value == "focus"
    assert not desktop.brain.walks
    assert desktop.pet.belly_text == "25"
    assert desktop.checklist.focus_line.text() == "Focus: Sport · 25 min left"

    clock.now = datetime(2026, 9, 26, 9, 10, 30)
    desktop._check_pomodoro()
    assert desktop.pet.belly_text == "15"

    clock.now = datetime(2026, 9, 26, 10, 0, 30)
    desktop.check_reminders_now()
    assert desktop.bubble.text != "Hey! Still to do: Sport, Study, Language."

    clock.now = datetime(2026, 9, 26, 9, 25)
    desktop._check_pomodoro()
    assert desktop.pomodoro.phase.value == "break"
    assert tracker.status().items[0].done
    assert tracker.focus_count() == 1
    assert desktop.brain.walks
    assert desktop.bubble.text == "Focus done! Take a 5 min break."

    clock.now = datetime(2026, 9, 26, 9, 30)
    desktop._check_pomodoro()
    assert not desktop.pomodoro.active
    assert desktop.bubble.text == "Break's over. Another round?"
    assert desktop.pet.belly_text == "42%"


def test_pomodoro_survives_restart_and_can_be_stopped(make_desktop):
    first, _, _ = make_desktop()
    first.start_focus()
    second, _, _ = make_desktop()
    assert second.pomodoro.phase.value == "focus"
    assert not second.brain.walks
    second.checklist.stop_button.click()
    assert not second.pomodoro.active
    assert second.brain.walks


def test_checklist_opens_above_raccoon_without_covering_it(playful_desktop):
    desktop, _ = playful_desktop
    desktop.start_focus("sport")
    desktop.open_checklist()
    assert desktop.checklist.geometry().bottom() < desktop.pet.geometry().top()


def test_summon_brings_raccoon_to_cursor_screen(playful_desktop):
    from PySide6.QtGui import QGuiApplication

    desktop, cursor = playful_desktop
    desktop.pet.move(-5000, -5000)
    desktop.pet.drag_moved.emit()
    desktop.set_visible(False)
    screen = QGuiApplication.primaryScreen().availableGeometry()
    cursor.pos = screen.center()
    desktop.summon()
    assert desktop.pet.isVisible()
    assert screen.contains(desktop.pet.geometry())
    assert screen.contains(QPoint(*desktop._state.get("pet_pos")))


def test_fast_cursor_over_raccoon_does_not_scare_it(playful_desktop):
    """Раньше быстрый курсор сгонял енота прямо из-под клика."""
    desktop, cursor = playful_desktop
    center = desktop.pet.geometry().center()
    cursor.pos = QPoint(center.x() - 300, center.y())
    desktop._watch_cursor(now=10.0)
    cursor.pos = center
    desktop._watch_cursor(now=10.1)
    assert desktop.brain.at_home
    assert desktop.brain.mode is not Mode.WALK


def test_double_click_makes_raccoon_run_away(playful_desktop):
    desktop, cursor = playful_desktop
    cursor.pos = desktop.pet.geometry().center() + QPoint(-5, 0)
    desktop.pet.double_clicked.emit()
    assert desktop.brain.mode is Mode.WALK
    assert desktop.brain.facing == "right"
    assert not desktop.checklist.isVisible()


def test_single_click_opens_checklist_after_short_pause(qapp, playful_desktop):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest

    desktop, _ = playful_desktop
    pet = desktop.pet
    local = QPointF(pet.width() / 2, pet.height() / 2)
    glob = QPointF(pet.mapToGlobal(local.toPoint()))
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(
            kind,
            local,
            glob,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(pet, event)
    assert not desktop.checklist.isVisible()
    QTest.qWait(pet.CLICK_DELAY_MS + 150)
    assert desktop.checklist.isVisible()


def test_raccoon_climbs_right_edge_and_comes_back(playful_desktop):
    desktop, _ = playful_desktop
    brain = desktop.brain
    assert "climb" in brain.actions
    home = brain.home
    assert brain.climb()
    seen = set()
    for _ in range(3000):
        brain.tick(0.1)
        desktop._after_brain_change()
        seen.add((brain.mode, brain.climb_phase))
        if brain.mode is Mode.CLIMB:
            assert brain.x == brain.area.right
            assert desktop._shown_anim[0] in ("climb", "climb_hang")
            assert desktop.pet.belly_text is None
        if brain.at_home and (Mode.CLIMB, "down") in seen:
            break
    assert {(Mode.CLIMB, "up"), (Mode.CLIMB, "hang"), (Mode.CLIMB, "down")} <= seen
    assert brain.at_home
    assert brain.home == home


def test_climb_from_menu_starts_right_away(playful_desktop):
    desktop, _ = playful_desktop
    desktop.climb_now()
    assert desktop.brain.climb_phase in ("to_edge", "up")
    desktop.set_walks(False)
    desktop.brain.place(*desktop.brain.home)
    desktop.climb_now()
    assert desktop.bubble.text == "The edge is too far, or walks are off."
