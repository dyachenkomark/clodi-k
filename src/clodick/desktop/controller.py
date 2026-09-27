"""Связывает трекер, поведение персонажа, окна, напоминания и трей."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from clodick import paths
from clodick.characters import DEFAULT_CHARACTER, Character, builtin_dir, discover
from clodick.config import Config
from clodick.core.pomodoro import Event, Phase, Pomodoro
from clodick.core.reminders import (
    DONE_TEXT,
    ReminderClock,
    greeting_text,
    parse_times,
    reminder_text,
)
from clodick.core.tracker import Tracker
from clodick.desktop.art import GROUND_ROW, YARD_X
from clodick.desktop.brain import (
    DOWN,
    DOWN_LEFT,
    DOWN_RIGHT,
    FIDGETS,
    UP,
    UP_LEFT,
    UP_RIGHT,
    Area,
    Brain,
    Mode,
)
from clodick.desktop.sprites import SpriteBook
from clodick.desktop.themes import THEMES
from clodick.desktop.widgets import BOTTOM_PAD, BubbleWindow, ChecklistPopup, PetWindow
from clodick.storage.state import StateStore

log = logging.getLogger(__name__)

# Сколько длится кадр анимации, секунды. Для сидения первый кадр длится случайно 2.5–6 с.
FRAME_SECONDS = {
    "sleep": 0.9,
    "wave": 0.3,
    "walk": 0.18,
    "wash": 0.22,
    "stretch": 0.8,
    "eat": 0.35,
}
BLINK_SECONDS = 0.15
ACTIVE_TICK_MS = 80
IDLE_TICK_MS = 1000
RAM_REFRESH_MS = 5000
REMINDER_CHECK_MS = 30_000
GREETING_DELAY_MS = 3000
# Отступ енота от правого края экрана при первом запуске.
START_MARGIN = 24

# Игривость. Курсор проверяется раз в CURSOR_POLL_MS.
CURSOR_POLL_MS = 100
# Курсор пролетает рядом быстрее этого (пикселей в секунду) — енот отбегает.
DODGE_SPEED = 1500
DODGE_COOLDOWN = 4.0
# Курсор стоит на еноте почти неподвижно (медленнее PET_SPEED) PET_SECONDS — это поглаживание.
PET_SPEED = 60
PET_SECONDS = 1.5
PET_COOLDOWN = 8.0
HEART_SECONDS = 2.0
# Прыжок радости: высота по кадрам, в пикселях арта.
HOP = (1, 2, 3, 3, 2, 1, 0)
HOP_FRAME_MS = 40
# Ночью, с NIGHT_FROM до NIGHT_TO часов, енот сонный.
NIGHT_FROM, NIGHT_TO = 23, 6
# Курсор ближе этого к центру енота — он на него косится.
LOOK_RADIUS = 220
# Сколько секунд енот грызёт печеньку за отмеченную задачу.
EAT_SECONDS = 3.0
# Какие кадры показывать на ходу по диагонали: (анимация, отражать ли).
DIAGONALS = {
    DOWN_RIGHT: ("walk_down_right", 1),
    DOWN_LEFT: ("walk_down_right", -1),
    UP_RIGHT: ("walk_up_right", 1),
    UP_LEFT: ("walk_up_right", -1),
}
# В каких позах пузо видно спереди и на нём пишется RAM.
BELLY_MODES = (Mode.SIT, Mode.WAVE)


def crosses(rect: QRect, start: QPoint, end: QPoint) -> bool:
    """Проходит ли отрезок start–end через rect. Быстрый курсор между замерами пролетает
    зону целиком, поэтому смотрим весь путь, а не одну точку."""
    steps = max(1, (end - start).manhattanLength() // 4)
    for i in range(steps + 1):
        x = start.x() + (end.x() - start.x()) * i // steps
        y = start.y() + (end.y() - start.y()) * i // steps
        if rect.contains(x, y):
            return True
    return False


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
        cursor: Callable[[], QPoint] = QCursor.pos,
    ) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._tracker = tracker
        self._state = state
        self._read_ram = ram_reader
        self._clock = clock
        self._cursor = cursor
        self._scale = config.desktop.scale
        self._ram: int | None = None

        self.theme = THEMES[config.desktop.theme]
        self.characters = discover([builtin_dir(), paths.data_dir() / "characters"])
        self.character = self._pick_character(state.get("character") or config.desktop.character)
        self._book = self._make_book(self.character)

        self.pet = PetWindow(self._scale)
        self.bubble = BubbleWindow(self.theme)
        self.checklist = ChecklistPopup(self.theme)

        home = self._restore_position()
        self._move_window(*home)
        self.brain = Brain(
            (float(home[0]), float(home[1])),
            self._area(),
            speed=10.0 * self._scale,
            walks=bool(state.get("walks", config.desktop.walks)),
            roam=float(config.desktop.roam),
            rng=rng,
            fidgets=self._fidgets(),
        )
        self._reminders_on = bool(state.get("reminders_on", True))
        self.pomodoro = Pomodoro.from_dict(config.pomodoro, state.get("pomodoro"))
        self._shown_minutes: int | None = None
        if self.pomodoro.phase is Phase.FOCUS:
            self.brain.set_walks(False)
        self._playful = bool(state.get("playful", True))
        self._belly_ram = bool(state.get("belly_ram", True))
        self._last_cursor: QPoint | None = None
        self._last_cursor_time = 0.0
        self._pet_since: float | None = None
        self._dodge_ready = 0.0
        self._pet_ready = 0.0
        self._hop: list[int] = []
        # Куда косится: 0 — влево, 1 — вправо, None — прямо.
        self._look: int | None = None
        self._reminder_clock = ReminderClock(parse_times(config.reminders), clock())

        self._frame_index = 0
        self._shown_mode: Mode | None = None
        self._shown_anim: tuple[str, int] | None = None
        self._last_tick = time.monotonic()

        self._anim_timer = QTimer(self, singleShot=True, timeout=self._next_frame)
        self._tick_timer = QTimer(self, timeout=self._tick)
        self._ram_timer = QTimer(self, interval=RAM_REFRESH_MS, timeout=self._refresh_ram)
        self._reminder_timer = QTimer(
            self, interval=REMINDER_CHECK_MS, timeout=self._check_reminders
        )
        self._cursor_timer = QTimer(self, interval=CURSOR_POLL_MS, timeout=self._watch_cursor)
        self._hop_timer = QTimer(self, interval=HOP_FRAME_MS, timeout=self._hop_step)

        self.pet.clicked.connect(self._pet_clicked)
        self.bubble.clicked.connect(self.open_checklist)
        self.pet.drag_moved.connect(self._pet_dragged)
        self.pet.drag_finished.connect(self._save_position)
        self.pet.context_requested.connect(self._show_menu)
        self.checklist.toggled.connect(self._toggle)
        self.checklist.task_added.connect(self._add_task)
        self.checklist.task_removed.connect(self._remove_task)
        self.checklist.focus_requested.connect(self.start_focus)
        self.checklist.focus_stopped.connect(self.stop_focus)

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
        if self._playful:
            self._cursor_timer.start()
        self._pomodoro_changed(save=False)
        QTimer.singleShot(GREETING_DELAY_MS, self._greet)

    def quit(self) -> None:
        self._save_position()
        if self.tray is not None:
            self.tray.hide()
        self._app.quit()

    @property
    def visible(self) -> bool:
        return self.pet.isVisible()

    def set_visible(self, visible: bool) -> None:
        self._state.set("hidden", not visible)
        if visible:
            self._show_windows()
        else:
            for window in (self.pet, self.bubble, self.checklist):
                window.hide()
        self._visible_action.setChecked(visible)

    def set_walks(self, walks: bool) -> None:
        self._state.set("walks", walks)
        self.brain.set_walks(walks)
        self._walks_action.setChecked(walks)
        self._after_brain_change()

    def set_playful(self, on: bool) -> None:
        """Уворачиваться от быстрого курсора и радоваться поглаживанию."""
        self._state.set("playful", on)
        self._playful = on
        if on:
            self._cursor_timer.start()
        else:
            self._cursor_timer.stop()
        self._playful_action.setChecked(on)

    def set_belly_ram(self, on: bool) -> None:
        self._state.set("belly_ram", on)
        self._belly_ram = on
        self._update_belly()
        self._belly_action.setChecked(on)

    # --- Pomodoro ---

    def start_focus(self, key: str | None = None) -> None:
        """Фокус на пункте чек-листа или просто фокус. Енот сидит тихо и не гуляет."""
        self.pomodoro.start_focus(self._clock(), key)
        self.brain.set_walks(False)
        title = self._tracker.title_of(key) if key else None
        minutes = self.pomodoro.config.focus
        log.info("фокус %s мин: %s", minutes, key or "-")
        self._pomodoro_changed()
        self.say(f"Focus{f' on {title}' if title else ''}: {minutes} min. I'll keep quiet.", 5)

    def stop_focus(self) -> None:
        self.pomodoro.stop()
        self.brain.set_walks(self._walks_wanted())
        log.info("фокус остановлен")
        self._pomodoro_changed()

    def _walks_wanted(self) -> bool:
        return bool(self._state.get("walks", self._config.desktop.walks))

    def _check_pomodoro(self) -> None:
        key, started = self.pomodoro.key, self.pomodoro.started
        event = self.pomodoro.check(self._clock())
        if event is Event.FOCUS_DONE:
            minutes = self.pomodoro.config.focus
            self._tracker.add_focus(key, started, minutes)
            if key and self._tracker.title_of(key) is not None:
                self._tracker.mark_done(key, source="focus")
            self.brain.set_walks(self._walks_wanted())
            log.info("фокус закончен: %s", key or "-")
            self._pomodoro_changed()
            self.hop()
            self.say(f"Focus done! Take a {self.pomodoro.break_minutes} min break.", 10)
        elif event is Event.BREAK_DONE:
            self._pomodoro_changed()
            self.say("Break's over. Another round?", 10)
        elif self.pomodoro.minutes_left(self._clock()) != self._shown_minutes:
            self._pomodoro_changed(save=False)

    def _pomodoro_changed(self, *, save: bool = True) -> None:
        """Обновить всё, где видно Pomodoro: пузо, чек-лист, подсказку трея, меню."""
        if save:
            self._state.set("pomodoro", self.pomodoro.to_dict())
        self._shown_minutes = self.pomodoro.minutes_left(self._clock())
        self._update_belly()
        self._update_tooltip()
        self.checklist.set_focus(self._focus_text())
        if self.checklist.isVisible():
            self._refresh_checklist()
        self._stop_focus_action.setEnabled(self.pomodoro.active)

    def _focus_text(self) -> str | None:
        p = self.pomodoro
        if p.phase is Phase.FOCUS:
            title = self._tracker.title_of(p.key) if p.key else None
            return f"Focus{f': {title}' if title else ''} · {self._shown_minutes} min left"
        if p.phase is Phase.BREAK:
            return f"Break · {self._shown_minutes} min left"
        return None

    def _update_tooltip(self) -> None:
        if self.tray is None:
            return
        parts = ["cloDICK"]
        focus = self._focus_text()
        if focus:
            parts.append(focus)
        if self._ram is not None:
            parts.append(f"RAM {self._ram}%")
        self.tray.setToolTip(" · ".join(parts))

    def set_reminders(self, on: bool) -> None:
        self._state.set("reminders_on", on)
        self._reminders_on = on
        self._reminders_action.setChecked(on)

    # --- реплики и чек-лист ---

    def set_character(self, character_id: str) -> None:
        """Сменить персонажа на лету. Выбор запоминается."""
        character = self._pick_character(character_id)
        self._state.set("character", character.id)
        # Лапы остаются на том же уровне, даже если новый персонаж выше или ниже.
        dy = (self.character.height - character.height) * self._scale
        self.character = character
        self._book = self._make_book(character)
        self.brain.fidgets = self._fidgets()
        hx, hy = self.brain.home
        self.brain.place(hx, hy + dy)
        self.brain.set_area(self._area())
        self._after_brain_change()
        self._save_position()
        self._apply_frame(restart=True)
        for action in self._character_actions.actions():
            action.setChecked(action.data() == character.id)
        log.info("персонаж: %s", character.id)

    def _pick_character(self, character_id: str) -> Character:
        if character_id in self.characters:
            return self.characters[character_id]
        log.warning("персонаж %r не найден, беру %s", character_id, DEFAULT_CHARACTER)
        return self.characters[DEFAULT_CHARACTER]

    def _make_book(self, character: Character) -> SpriteBook:
        return SpriteBook(
            self._scale,
            QGuiApplication.primaryScreen().devicePixelRatio(),
            character=character,
            theme=self.theme.key,
        )

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
        self.checklist.set_status(self._tracker.status(), self._ram, self._tracker.focus_count())
        self.checklist.open_near(self.pet.geometry(), self._screen_rect())

    def check_reminders_now(self) -> None:
        """Для тестов и отладки: проверить напоминания немедленно."""
        self._check_reminders()

    def _toggle(self, key: str, checked: bool) -> None:
        if checked:
            self._tracker.mark_done(key, source="desktop")
            self.hop()
            if "eat" in self.character.animations:
                self.brain.act(Mode.EAT, EAT_SECONDS)
                self._after_brain_change()
        else:
            self._tracker.unmark(key)
        status = self._tracker.status()
        self.checklist.set_status(status, self._ram, self._tracker.focus_count())
        log.info("%s %s через окно", "done" if checked else "undo", key)
        if checked and status.all_done:
            self.say(DONE_TEXT, seconds=6)

    def _add_task(self, title: str, daily: bool) -> None:
        task = self._tracker.add_task(title, daily)
        log.info("своя задача %s: %s", "ежедневная" if daily else "разовая", task.id)
        self._refresh_checklist()

    def _remove_task(self, key: str) -> None:
        if self._tracker.remove_task(key):
            log.info("задача удалена: %s", key)
        self._refresh_checklist()

    def _refresh_checklist(self) -> None:
        """Список изменился: перерисовать и заново прижать к еноту, размер мог поменяться."""
        self.checklist.set_status(self._tracker.status(), self._ram, self._tracker.focus_count())
        self.checklist.open_near(self.pet.geometry(), self._screen_rect())

    def _greet(self) -> None:
        if not self._reminders_on or self.pomodoro.phase is Phase.FOCUS:
            return
        text = greeting_text(self._tracker.status())
        if text:
            self.say(text, seconds=8)

    def _check_reminders(self) -> None:
        due = self._reminder_clock.check(self._clock())
        if self.pomodoro.phase is Phase.FOCUS:
            return  # во время фокуса енот молчит
        if not (due and self._reminders_on):
            return
        text = reminder_text(self._tracker.status())
        if text:
            log.info("напоминание: %s", text)
            self.say(text)

    def _pet_clicked(self) -> None:
        self.brain.wake()
        self._after_brain_change()
        self.open_checklist()

    # --- персонаж ---

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        hour = self._clock().hour
        self.brain.sleepy = hour >= NIGHT_FROM or hour < NIGHT_TO
        if self.pomodoro.active:
            self._check_pomodoro()
        self.brain.tick(min(dt, 2.0))
        self._after_brain_change()

    def _after_brain_change(self) -> None:
        self._place_pet()
        restart = self.brain.mode is not self._shown_mode
        if restart or self._animation() != self._shown_anim:
            self._apply_frame(restart=restart)
        interval = ACTIVE_TICK_MS if self.brain.is_active else IDLE_TICK_MS
        if self._tick_timer.interval() != interval:
            self._tick_timer.setInterval(interval)

    def _animation(self) -> tuple[str, int]:
        """Какую анимацию показать сейчас и отражать ли её: (имя, 1 или -1).

        На ходу берутся кадры своего направления: walk_down, walk_up, walk_down_right,
        walk_up_right (влево — отражённые), если они есть у персонажа.
        Иначе обычный walk, повёрнутый туда, куда он шёл по горизонтали.
        """
        mode = self.brain.mode
        animations = self.character.animations
        if mode is Mode.WALK:
            facing = self.brain.facing
            if facing in (UP, DOWN) and f"walk_{facing}" in animations:
                return f"walk_{facing}", 1
            if facing in DIAGONALS and DIAGONALS[facing][0] in animations:
                return DIAGONALS[facing]
            return "walk", self.brain.side
        if mode is Mode.SIT and self._look is not None and "look" in animations:
            return "look", 1
        return mode.value, 1

    def _apply_frame(self, *, restart: bool) -> None:
        if restart:
            self._frame_index = 0
        self._shown_mode = self.brain.mode
        name, flip = self._shown_anim = self._animation()
        index = self._look if name == "look" else self._frame_index % self._book.frame_count(name)
        self.pet.set_pixmap(
            self._book.character_frame(name, index, flip), self._book.feet(name, index, flip)
        )
        self._update_belly()
        if restart:
            self._schedule_frame()

    def _next_frame(self) -> None:
        name = self._animation()[0]
        count = 2 if name == "look" else self._book.frame_count(name)
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

    def _place_pet(self) -> None:
        # Шаги кратны пикселю арта, считая от его места: на месте он стоит ровно там, где поставили.
        hx, hy = (round(v) for v in self.brain.home)
        x = hx + round((self.brain.x - hx) / self._scale) * self._scale
        y = hy + round((self.brain.y - hy) / self._scale) * self._scale
        self.pet.set_lift(self._hop[0] if self._hop else 0)
        if self._sprite_pos() != QPoint(x, y):
            self._move_window(x, y)
            if self.bubble.isVisible():
                self._place_bubble()

    def _sprite_pos(self) -> QPoint:
        """Левый верхний угол кадра на экране. Окно выше на запас под прыжок."""
        return self.pet.pos() + QPoint(0, self.pet.sprite_offset)

    def _move_window(self, x: int, y: int) -> None:
        self.pet.move(x, y - self.pet.sprite_offset)

    def _place_bubble(self) -> None:
        self.bubble.place_above(self.pet.geometry(), self._screen_rect())

    # --- игривость ---

    def hop(self) -> None:
        """Подпрыгнуть от радости."""
        self._hop = list(HOP)
        self._hop_timer.start()
        self._place_pet()

    def _hop_step(self) -> None:
        if self._hop:
            self._hop.pop(0)
        if not self._hop:
            self._hop_timer.stop()
        self._place_pet()

    def _watch_cursor(self, now: float | None = None) -> None:
        """Смотрит на курсор: быстрый рядом — отбежать, неподвижный на еноте — гладят."""
        now = time.monotonic() if now is None else now
        pos = self._cursor()
        last, last_time = self._last_cursor, self._last_cursor_time
        self._last_cursor, self._last_cursor_time = pos, now
        if last is None or now <= last_time or not self.visible or self.pet.pressed:
            return
        self._update_look(pos)
        speed = (pos - last).manhattanLength() / (now - last_time)
        rect = self.pet.geometry()
        mode = self.brain.mode
        if (
            speed > DODGE_SPEED
            and now >= self._dodge_ready
            and mode not in (Mode.WALK, Mode.WAVE)
            and crosses(rect.adjusted(-16, -16, 16, 16), last, pos)
        ):
            # Курсор будто толкает: енот отбегает туда, куда тот летел.
            push = pos - last
            length = max(1.0, (push.x() ** 2 + push.y() ** 2) ** 0.5)
            distance = rect.width() * 1.5
            dx, dy = push.x() / length * distance, push.y() / length * distance
            x, y = self.brain.x, self.brain.y
            if not self.brain.dodge(x + dx, y + dy):
                # Упёрся в край экрана — бежит в другую сторону.
                self.brain.dodge(x - dx, y - dy)
            self._dodge_ready = now + DODGE_COOLDOWN
            self._pet_since = None
            self._after_brain_change()
            return
        if rect.contains(pos) and speed < PET_SPEED and mode is Mode.SIT:
            if self._pet_since is None:
                self._pet_since = now
            elif now - self._pet_since >= PET_SECONDS and now >= self._pet_ready:
                self.pet.show_heart(HEART_SECONDS)
                self._pet_ready = now + PET_COOLDOWN
        else:
            self._pet_since = None

    def _update_look(self, pos: QPoint) -> None:
        center = self.pet.geometry().center()
        near = (pos - center).manhattanLength() < LOOK_RADIUS and not self.pet.geometry().contains(
            pos
        )
        look = (0 if pos.x() < center.x() else 1) if near else None
        if look != self._look:
            self._look = look
            if self.brain.mode is Mode.SIT:
                self._apply_frame(restart=False)

    def _fidgets(self) -> tuple[Mode, ...]:
        return tuple(m for m in FIDGETS if m.value in self.character.animations)

    def _update_belly(self) -> None:
        """Загрузка RAM на пузе. Когда пузо сбоку или закрыто лапами, надписи нет."""
        belly = self.character.belly
        if belly is None or self.brain.mode not in BELLY_MODES:
            self.pet.set_belly(None)
            return
        palette = self.character.palette_for(self.theme.key)
        color = palette.get("g") or palette.get("K") or "#26262e"
        rect = QRect(*(v * self._scale for v in belly))
        # Во время Pomodoro на пузе минуты: фокус цветом акцента, перерыв обычным.
        if self.pomodoro.active:
            focus = self.pomodoro.phase is Phase.FOCUS
            minutes = self.pomodoro.minutes_left(self._clock())
            self.pet.set_belly(str(minutes), rect, self.theme.accent if focus else color)
        elif self._belly_ram and self._ram is not None:
            self.pet.set_belly(f"{self._ram}%", rect, color)
        else:
            self.pet.set_belly(None)

    # --- место персонажа ---

    def _pet_dragged(self) -> None:
        """Енота тащат мышью: где окно, там и его место."""
        pos = self._sprite_pos()
        self.brain.area = self._area()
        self.brain.place(float(pos.x()), float(pos.y()))
        self._after_brain_change()
        if self.bubble.isVisible():
            self._place_bubble()

    def _pet_size(self) -> QSize:
        return QSize(self.character.width * self._scale, self.character.height * self._scale)

    def _area(self) -> Area:
        """Пол для персонажа: рабочая область экрана без панели задач. Тень тоже влезает."""
        screen = self._screen_rect()
        size = self._pet_size()
        shadow = BOTTOM_PAD * self._scale
        return Area(
            screen.left(),
            screen.top(),
            screen.right() + 1 - size.width(),
            screen.bottom() + 1 - size.height() - shadow,
        )

    def _screen_rect(self) -> QRect:
        center = QRect(self._sprite_pos(), self._pet_size()).center()
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _restore_position(self) -> tuple[int, int]:
        """Место енота: сохранённое, затем место у старого домика, иначе правый нижний угол."""
        size = self._pet_size()
        saved = self._state.get("pet_pos")
        if not saved and (house := self._state.get("house_pos")):
            saved = [
                house[0] + YARD_X * self._scale,
                house[1] + (GROUND_ROW + 1 - self.character.height) * self._scale,
            ]
        if saved:
            point = QPoint(int(saved[0]), int(saved[1]))
            rect = QRect(point, size)
            if any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens()):
                return point.x(), point.y()
        area = QGuiApplication.primaryScreen().availableGeometry()
        return (
            area.right() + 1 - size.width() - START_MARGIN,
            area.bottom() + 1 - size.height() - BOTTOM_PAD * self._scale,
        )

    def _save_position(self) -> None:
        self._state.set("pet_pos", [round(v) for v in self.brain.home])

    def _show_windows(self) -> None:
        self._place_pet()
        self.pet.show()
        self.pet.raise_()

    def _refresh_ram(self) -> None:
        try:
            self._ram = self._read_ram()
        except Exception:  # мониторинг не должен ронять приложение
            log.exception("не удалось прочитать RAM")
            return
        self._update_tooltip()
        self._update_belly()

    # --- меню и трей ---

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Today's checklist", self.open_checklist)
        menu.addAction("Start focus", lambda: self.start_focus())
        self._stop_focus_action = menu.addAction("Stop focus", self.stop_focus)
        self._stop_focus_action.setEnabled(self.pomodoro.active)
        menu.addSeparator()
        self._character_actions = QActionGroup(menu)
        characters_menu = menu.addMenu("Character")
        for character in sorted(self.characters.values(), key=lambda c: c.name):
            action = QAction(character.name, characters_menu, checkable=True)
            action.setData(character.id)
            action.setChecked(character.id == self.character.id)
            action.triggered.connect(lambda _=False, cid=character.id: self.set_character(cid))
            self._character_actions.addAction(action)
            characters_menu.addAction(action)
        self._visible_action = QAction("Show character", menu, checkable=True)
        self._visible_action.setChecked(not self._state.get("hidden", False))
        self._visible_action.toggled.connect(self.set_visible)
        self._walks_action = QAction("Let it walk", menu, checkable=True)
        self._walks_action.setChecked(self.brain.walks)
        self._walks_action.toggled.connect(self.set_walks)
        self._reminders_action = QAction("Reminders", menu, checkable=True)
        self._reminders_action.setChecked(self._reminders_on)
        self._reminders_action.toggled.connect(self.set_reminders)
        self._playful_action = QAction("Playful", menu, checkable=True)
        self._playful_action.setChecked(self._playful)
        self._playful_action.toggled.connect(self.set_playful)
        self._belly_action = QAction("RAM on belly", menu, checkable=True)
        self._belly_action.setChecked(self._belly_ram)
        self._belly_action.toggled.connect(self.set_belly_ram)
        for action in (
            self._visible_action,
            self._walks_action,
            self._reminders_action,
            self._playful_action,
            self._belly_action,
        ):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
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
