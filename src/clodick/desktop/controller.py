"""Связывает трекер, поведение енота, окна, напоминания и трей."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QRect, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from clodick.config import Config
from clodick.core.reminders import (
    DONE_TEXT,
    ReminderClock,
    greeting_text,
    parse_times,
    reminder_text,
)
from clodick.core.tracker import Tracker
from clodick.desktop.brain import Bounds, Brain, Mode
from clodick.desktop.sprites import HOUSE_SIZE, RACCOON_SIZE, SpriteBook
from clodick.desktop.widgets import BubbleWindow, ChecklistPopup, HouseWindow, RaccoonWindow
from clodick.storage.state import StateStore

log = logging.getLogger(__name__)

# Где сидит енот относительно домика, в пикселях арта: во дворе справа, лапами на траве.
RACCOON_HOME_OFFSET = (36, 12)
# Сколько длится кадр анимации, секунды. Для сидения первый кадр длится случайно 2.5–6 с.
FRAME_SECONDS = {"sleep": 0.9, "wave": 0.3, "walk": 0.18}
BLINK_SECONDS = 0.15
ACTIVE_TICK_MS = 80
IDLE_TICK_MS = 1000
RAM_REFRESH_MS = 5000
REMINDER_CHECK_MS = 30_000
GREETING_DELAY_MS = 3000


class DesktopApp(QObject):
    def __init__(
        self,
        app: QApplication,
        config: Config,
        tracker: Tracker,
        state: StateStore,
        *,
        ram_reader: Callable[[], int],
        clock: Callable[[], datetime] = datetime.now,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._tracker = tracker
        self._state = state
        self._read_ram = ram_reader
        self._clock = clock
        self._scale = config.desktop.scale
        self._ram: int | None = None

        screen = QGuiApplication.primaryScreen()
        self._book = SpriteBook(self._scale, screen.devicePixelRatio())

        self.house = HouseWindow(self._book.house(), self._scale)
        self.raccoon = RaccoonWindow()
        self.bubble = BubbleWindow()
        self.checklist = ChecklistPopup()

        self._restore_house_position()
        home_x, bounds = self._home_geometry()
        self.brain = Brain(
            home_x,
            bounds,
            speed=10.0 * self._scale,
            walks=bool(state.get("walks", config.desktop.walks)),
            rng=rng,
        )
        self._reminders_on = bool(state.get("reminders_on", True))
        self._reminder_clock = ReminderClock(parse_times(config.reminders), clock())

        self._frame_index = 0
        self._shown_mode: Mode | None = None
        self._shown_facing = 1
        self._last_tick = time.monotonic()

        self._anim_timer = QTimer(self, singleShot=True, timeout=self._next_frame)
        self._tick_timer = QTimer(self, timeout=self._tick)
        self._ram_timer = QTimer(self, interval=RAM_REFRESH_MS, timeout=self._refresh_ram)
        self._reminder_timer = QTimer(
            self, interval=REMINDER_CHECK_MS, timeout=self._check_reminders
        )

        self.house.clicked.connect(self.open_checklist)
        self.raccoon.clicked.connect(self._raccoon_clicked)
        self.bubble.clicked.connect(self.open_checklist)
        self.house.drag_moved.connect(self._house_moved)
        self.house.drag_finished.connect(self._save_house_position)
        self.house.context_requested.connect(self._show_menu)
        self.raccoon.context_requested.connect(self._show_menu)
        self.checklist.toggled.connect(self._toggle)

        self.menu = self._build_menu()
        self.tray = self._build_tray()

    # --- запуск и остановка ---

    def start(self) -> None:
        self._refresh_ram()
        if not self._state.get("hidden", False):
            self._show_windows()
        if self.tray is not None:
            self.tray.show()
        self._apply_frame(restart=True)
        self._last_tick = time.monotonic()
        self._tick_timer.start(IDLE_TICK_MS)
        self._ram_timer.start()
        self._reminder_timer.start()
        QTimer.singleShot(GREETING_DELAY_MS, self._greet)

    def quit(self) -> None:
        self._save_house_position()
        if self.tray is not None:
            self.tray.hide()
        self._app.quit()

    @property
    def visible(self) -> bool:
        return self.house.isVisible()

    def set_visible(self, visible: bool) -> None:
        self._state.set("hidden", not visible)
        if visible:
            self._show_windows()
        else:
            for window in (self.house, self.raccoon, self.bubble, self.checklist):
                window.hide()
        self._visible_action.setChecked(visible)

    def set_walks(self, walks: bool) -> None:
        self._state.set("walks", walks)
        self.brain.set_walks(walks)
        self._walks_action.setChecked(walks)
        self._after_brain_change()

    def set_reminders(self, on: bool) -> None:
        self._state.set("reminders_on", on)
        self._reminders_on = on
        self._reminders_action.setChecked(on)

    # --- реплики и чек-лист ---

    def say(self, text: str, seconds: float = 12.0) -> None:
        if not self.visible:
            if self.tray is not None:
                self.tray.showMessage("cloDICK", text, self._tray_icon(), int(seconds * 1000))
            return
        self.brain.wave(min(seconds, 6.0))
        self._after_brain_change()
        self.bubble.say(text, seconds)
        self._place_bubble()

    def open_checklist(self) -> None:
        self.bubble.hide()
        self.checklist.set_status(self._tracker.status(), self._ram)
        anchor = self.house.geometry().united(self.raccoon.geometry())
        self.checklist.open_near(anchor, self._screen_rect())

    def check_reminders_now(self) -> None:
        """Для тестов и отладки: проверить напоминания немедленно."""
        self._check_reminders()

    def _toggle(self, key: str, checked: bool) -> None:
        if checked:
            self._tracker.mark_done(key, source="desktop")
        else:
            self._tracker.unmark(key)
        status = self._tracker.status()
        self.checklist.set_status(status, self._ram)
        log.info("%s %s через окно", "done" if checked else "undo", key)
        if checked and status.all_done:
            self.say(DONE_TEXT, seconds=6)

    def _greet(self) -> None:
        if not self._reminders_on:
            return
        text = greeting_text(self._tracker.status())
        if text:
            self.say(text, seconds=8)

    def _check_reminders(self) -> None:
        due = self._reminder_clock.check(self._clock())
        if not (due and self._reminders_on):
            return
        text = reminder_text(self._tracker.status())
        if text:
            log.info("напоминание: %s", text)
            self.say(text)

    def _raccoon_clicked(self) -> None:
        self.brain.wake()
        self._after_brain_change()
        self.open_checklist()

    # --- енот ---

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        self.brain.tick(min(dt, 2.0))
        self._after_brain_change()

    def _after_brain_change(self) -> None:
        self._place_raccoon()
        restart = self.brain.mode is not self._shown_mode
        if restart or self.brain.facing != self._shown_facing:
            self._apply_frame(restart=restart)
        interval = ACTIVE_TICK_MS if self.brain.is_active else IDLE_TICK_MS
        if self._tick_timer.interval() != interval:
            self._tick_timer.setInterval(interval)

    def _apply_frame(self, *, restart: bool) -> None:
        mode = self.brain.mode
        if restart:
            self._frame_index = 0
        self._shown_mode = mode
        self._shown_facing = self.brain.facing
        facing = self.brain.facing if mode is Mode.WALK else 1
        self.raccoon.set_pixmap(self._book.raccoon(mode.value, self._frame_index, facing))
        if restart:
            self._schedule_frame()

    def _next_frame(self) -> None:
        count = self._book.frame_count(self.brain.mode.value)
        self._frame_index = (self._frame_index + 1) % count
        self._apply_frame(restart=False)
        self._schedule_frame()

    def _schedule_frame(self) -> None:
        mode = self.brain.mode.value
        if mode == "sit":
            seconds = BLINK_SECONDS if self._frame_index else random.uniform(2.5, 6.0)
        else:
            seconds = FRAME_SECONDS[mode]
        self._anim_timer.start(int(seconds * 1000))

    def _place_raccoon(self) -> None:
        y = self.house.y() + RACCOON_HOME_OFFSET[1] * self._scale
        x = round(self.brain.x / self._scale) * self._scale
        if self.raccoon.pos() != QPoint(x, y):
            self.raccoon.move(x, y)
            if self.bubble.isVisible():
                self._place_bubble()

    def _place_bubble(self) -> None:
        self.bubble.place_above(self.raccoon.geometry(), self._screen_rect())

    # --- домик ---

    def _house_moved(self) -> None:
        home_x, bounds = self._home_geometry()
        self.brain.set_home(home_x, bounds)
        self._after_brain_change()

    def _home_geometry(self) -> tuple[float, Bounds]:
        screen = self._screen_rect()
        home_x = self.house.x() + RACCOON_HOME_OFFSET[0] * self._scale
        width = RACCOON_SIZE[0] * self._scale
        return float(home_x), Bounds(screen.left(), screen.right() + 1 - width)

    def _screen_rect(self) -> QRect:
        screen = QGuiApplication.screenAt(self.house.geometry().center())
        screen = screen or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _restore_house_position(self) -> None:
        saved = self._state.get("house_pos")
        if saved:
            point = QPoint(int(saved[0]), int(saved[1]))
            rect = QRect(point, self.house.size())
            if any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens()):
                self.house.move(point)
                return
        area = QGuiApplication.primaryScreen().availableGeometry()
        overhang = max(0, RACCOON_HOME_OFFSET[0] + RACCOON_SIZE[0] - HOUSE_SIZE[0]) * self._scale
        self.house.move(
            area.right() + 1 - self.house.width() - overhang - 24,
            area.bottom() + 1 - self.house.height(),
        )

    def _save_house_position(self) -> None:
        self._state.set("house_pos", [self.house.x(), self.house.y()])

    def _show_windows(self) -> None:
        self.house.show()
        self._place_raccoon()
        self.raccoon.show()
        self.raccoon.raise_()

    def _refresh_ram(self) -> None:
        try:
            self._ram = self._read_ram()
        except Exception:  # мониторинг не должен ронять приложение
            log.exception("не удалось прочитать RAM")
            return
        self.house.set_ram(self._ram)

    # --- меню и трей ---

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Чек-лист дня", self.open_checklist)
        menu.addSeparator()
        self._visible_action = QAction("Показывать енота", menu, checkable=True)
        self._visible_action.setChecked(not self._state.get("hidden", False))
        self._visible_action.toggled.connect(self.set_visible)
        self._walks_action = QAction("Отпускать гулять", menu, checkable=True)
        self._walks_action.setChecked(self.brain.walks)
        self._walks_action.toggled.connect(self.set_walks)
        self._reminders_action = QAction("Напоминания", menu, checkable=True)
        self._reminders_action.setChecked(self._reminders_on)
        self._reminders_action.toggled.connect(self.set_reminders)
        for action in (self._visible_action, self._walks_action, self._reminders_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Выход", self.quit)
        return menu

    def _build_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("системный трей недоступен")
            return None
        tray = QSystemTrayIcon(self._tray_icon(), self)
        tray.setToolTip("cloDICK")
        tray.setContextMenu(self.menu)
        tray.activated.connect(self._tray_activated)
        return tray

    def _tray_icon(self) -> QIcon:
        return QIcon(QPixmap.fromImage(self._book.icon_image()))

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if not self.visible:
                self.set_visible(True)
            self.open_checklist()

    def _show_menu(self, pos: QPoint) -> None:
        self.menu.popup(pos)
