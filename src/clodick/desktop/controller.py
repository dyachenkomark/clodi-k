"""Связывает трекер, поведение персонажа, окна, напоминания и трей."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from clodick import llm, paths
from clodick.characters import DEFAULT_CHARACTER, Character, builtin_dir, discover
from clodick.config import Config
from clodick.core.chatter import idle_line
from clodick.core.pomodoro import Event, Phase, Pomodoro
from clodick.core.reminders import (
    DONE_TEXT,
    ReminderClock,
    greeting_text,
    parse_times,
    reminder_text,
    timed_text,
)
from clodick.core.tracker import Tracker
from clodick.desktop.actions import ACTIONS, TASK_LINES, TASK_REACTION_POOL, TASK_REACTIONS
from clodick.desktop.art import GROUND_ROW, YARD_X
from clodick.desktop.brain import (
    CALM,
    DOWN,
    DOWN_LEFT,
    DOWN_RIGHT,
    LIVELY,
    NORMAL,
    UP,
    UP_LEFT,
    UP_RIGHT,
    Area,
    Brain,
    Mode,
)
from clodick.desktop.onboarding import DONE, HELLO, SHEET, SetupDialog
from clodick.desktop.sprites import SpriteBook
from clodick.desktop.themes import THEMES
from clodick.desktop.widgets import BOTTOM_PAD, BubbleWindow, ChecklistPopup, PetWindow
from clodick.storage.state import StateStore
from clodick.sync import google

log = logging.getLogger(__name__)

# Сколько длится кадр анимации, секунды. Для сидения первый кадр длится случайно 2.5–6 с.
# Кадры действий — в actions.py.
FRAME_SECONDS = {"sleep": 0.9, "wave": 0.3, "walk": 0.18, "climb": 0.28, "climb_hang": 1.0}
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
# Болтовня: реплика раз в столько минут, и шанс сказать что-то, начиная действие.
CHAT_MINUTES = (10.0, 25.0)
ACTION_LINE_CHANCE = 0.35
REACTION_LINE_CHANCE = 0.3
# Курсор долго стоит рядом — енот подходит посмотреть.
CURIOUS_RADIUS = 320
CURIOUS_SECONDS = 6.0
CURIOUS_COOLDOWN = 90.0
# Какие кадры показывать на ходу по диагонали: (анимация, отражать ли).
DIAGONALS = {
    DOWN_RIGHT: ("walk_down_right", 1),
    DOWN_LEFT: ("walk_down_right", -1),
    UP_RIGHT: ("walk_up_right", 1),
    UP_LEFT: ("walk_up_right", -1),
}
# В каких позах пузо видно спереди и на нём пишется RAM.
BELLY_MODES = (Mode.SIT, Mode.WAVE)
# Цвет цифр RAM на пузе: оранжевый.
RAM_COLOR = "#e8792b"


@dataclass
class SetupEnv:
    """Всё, что мастеру нужно снаружи. В тестах подменяется, чтобы не ходить в сеть."""

    data_dir: Path
    oauth_client: Path | None
    sign_in: Callable = google.sign_in
    find_or_create: Callable = google.find_or_create_sheet
    authorize: Callable = google.authorize
    open_link: Callable = google.open_by_link
    llm_client: Callable = llm.LLMClient
    load_key: Callable = llm.load_key
    save_key: Callable = llm.save_key
    # Где искать скачанный файл клиента и чем открывать ссылки из помощника.
    downloads: Path = Path.home() / "Downloads"
    open_url: Callable = None

    @classmethod
    def default(cls) -> SetupEnv:
        data_dir = paths.data_dir()
        return cls(data_dir, google.oauth_client_file(data_dir))


class _Job(QObject):
    """Результат фоновой работы: приходит в поток интерфейса очередью Qt."""

    done = Signal(object, object)


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
        sync=None,
        sync_factory: Callable | None = None,
        setup_env: SetupEnv | None = None,
    ) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._tracker = tracker
        self._state = state
        self._read_ram = ram_reader
        self._clock = clock
        self._cursor = cursor
        # Фоновая синхронизация с Google Таблицей (sync.worker.SheetSync) или None.
        self.sync = sync
        # Как запустить синхронизацию, когда таблицу подключили в мастере: link → SheetSync.
        self._sync_factory = sync_factory
        self._env = setup_env or SetupEnv.default()
        self.setup: SetupDialog | None = None
        self._jobs: set[_Job] = set()
        # Тесты ставят True: фоновая работа выполняется сразу, без потоков.
        self.inline_jobs = False
        self._llm = self._load_llm(state)
        self._rng = rng or random.Random()
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
            rng=self._rng,
            actions=self._available_actions(),
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
        self._pet_ready = 0.0
        self._hop: list[int] = []
        self._chatty = bool(state.get("chatty", True))
        self._next_chat = time.monotonic() + self._chat_delay()
        self._still_since: float | None = None
        self._curious_ready = 0.0
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
        self.pet.double_clicked.connect(self._pet_double_clicked)
        self.bubble.clicked.connect(self.open_checklist)
        self.pet.drag_moved.connect(self._pet_dragged)
        self.pet.drag_finished.connect(self._save_position)
        self.pet.context_requested.connect(self._show_menu)
        self.checklist.toggled.connect(self._toggle)
        self.checklist.task_added.connect(self._add_task)
        self.checklist.task_removed.connect(self._remove_task)
        self.checklist.focus_requested.connect(self.start_focus)
        self.checklist.focus_stopped.connect(self.stop_focus)
        self.checklist.note_added.connect(self._add_note)
        self.checklist.note_deleted.connect(self._delete_note)
        self.checklist.resized.connect(self._reanchor_checklist)

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
        # Первый запуск: вместо приветствия персонаж знакомится и помогает настроиться.
        first_run = not self._state.get("onboarding_done", False)
        QTimer.singleShot(GREETING_DELAY_MS, self.open_setup if first_run else self._greet)

    def quit(self) -> None:
        self._save_position()
        if self.sync is not None:
            self.sync.stop()
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
            self._data_changed()
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
        if self.sync is not None:
            parts.append(self.sync.status)
        self.tray.setToolTip(" · ".join(parts))

    def _data_changed(self) -> None:
        """Данные поменялись локально: пора отправить их в таблицу."""
        if self.sync is not None:
            self.sync.request()

    def sync_now(self) -> None:
        if self.sync is not None:
            self.sync.request()
            self.say("Syncing with the sheet…", 3, wave=False)

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
        self.brain.actions = self._available_actions()
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

    def say(self, text: str, seconds: float = 12.0, *, wave: bool = True) -> None:
        """Пузырь с репликой. wave=False — сказать между делом, не отвлекаясь от занятия.

        Если персонаж спрятан, важное (wave=True) приходит уведомлением трея, болтовня молчит.
        """
        if not self.visible:
            if wave and self.tray is not None:
                self.tray.showMessage("cloDICK", text, self._tray_icon(), int(seconds * 1000))
            return
        if wave:
            self.brain.wave(min(seconds, 6.0))
            self._after_brain_change()
        self.bubble.say(text, seconds)
        self._place_bubble()

    def chat(self, text: str, seconds: float = 5.0) -> None:
        """Болтовня: только если она включена и сейчас не фокус."""
        if self._chatty and self.pomodoro.phase is not Phase.FOCUS and not self.bubble.isVisible():
            self.say(text, seconds, wave=False)

    def set_chatty(self, on: bool) -> None:
        self._state.set("chatty", on)
        self._chatty = on
        self._chatty_action.setChecked(on)

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
            self._react_to_done(key)
        else:
            self._tracker.unmark(key)
        status = self._tracker.status()
        self.checklist.set_status(status, self._ram, self._tracker.focus_count())
        log.info("%s %s через окно", "done" if checked else "undo", key)
        self._data_changed()
        if checked and status.all_done:
            self.say(DONE_TEXT, seconds=6)
        if checked:
            # Сразу предложить записать результат. Не обязательно: можно просто закрыть.
            self.checklist.ask_note(key)

    def _add_task(self, text: str, daily: bool) -> None:
        """Задача из строки чек-листа: «мага: отчёт до пт в 15:00»."""
        try:
            task = self._tracker.add_from_text(text, daily)
        except ValueError:
            return  # в строке были только срок или проект, названия нет
        log.info("задача %s: проект %r, срок %s", task.id, task.project, task.due)
        self._data_changed()
        self._refresh_checklist()

    def _remove_task(self, key: str) -> None:
        if self._tracker.remove_task(key):
            log.info("задача удалена: %s", key)
        self._data_changed()
        self._refresh_checklist()

    def _refresh_checklist(self) -> None:
        """Список изменился: перерисовать и заново прижать к еноту, размер мог поменяться."""
        self.checklist.set_status(self._tracker.status(), self._ram, self._tracker.focus_count())
        self.checklist.open_near(self.pet.geometry(), self._screen_rect())

    def _add_note(self, key: str, text: str) -> None:
        try:
            self._tracker.add_note(key, text, source="desktop")
        except (KeyError, ValueError):
            log.exception("заметка не сохранилась")
            return
        log.info("заметка к %s", key)
        self._data_changed()
        self._refresh_checklist()
        if self._rng.random() < REACTION_LINE_CHANCE:
            self.chat(self._rng.choice(("Noted!", "Written down.", "Nice result!")), 3)

    def _delete_note(self, note_id: int) -> None:
        if self._tracker.delete_note(note_id):
            log.info("заметка удалена: %s", note_id)
        self._data_changed()
        self._refresh_checklist()

    def _reanchor_checklist(self) -> None:
        if self.checklist.isVisible():
            self.checklist.open_near(self.pet.geometry(), self._screen_rect())

    def _react_to_done(self, key: str) -> None:
        """Отметили дело: спорт — мускулы, учёба — книжка, язык — песня, иначе что-то радостное."""
        name = TASK_REACTIONS.get(key) or self._rng.choice(TASK_REACTION_POOL)
        if name not in self.character.animations:
            name = "eat" if "eat" in self.character.animations else None
        if name is None:
            return
        self.brain.act(name, max(ACTIONS[name].seconds))
        self._after_brain_change()
        lines = TASK_LINES.get(name)
        if lines and self._rng.random() < REACTION_LINE_CHANCE * 2:
            self.chat(self._rng.choice(lines), 4)

    def _greet(self) -> None:
        if not self._reminders_on or self.pomodoro.phase is Phase.FOCUS:
            return
        if self._llm is not None:
            self.plan_my_day(quiet=True)
            return
        text = greeting_text(self._tracker.status())
        if text:
            self.say(text, seconds=8)

    # --- модель для анализа ---

    def _load_llm(self, state: StateStore):
        settings = llm.LLMSettings.from_dict(state.get("llm"))
        if settings is None:
            return None
        return self._env.llm_client(settings, self._env.load_key())

    def plan_my_day(self, quiet: bool = False) -> None:
        """План на день от модели по задачам и заметкам. Факты собирает код."""
        if self._llm is None:
            self.say("Connect an AI model in Setup and I'll plan your day.", 6, wave=False)
            return
        status, tasks = self._tracker.status(), self._tracker.open_tasks()
        now_text = self._clock().strftime("%A %d %B %Y, %H:%M")
        client = self._llm

        def done(text, error) -> None:
            if error is not None:
                log.warning("модель не ответила: %s", error)
                if quiet:
                    fallback = greeting_text(status)
                    if fallback:
                        self.say(fallback, seconds=8)
                else:
                    self.say(f"I couldn't reach the model: {error}", 8, wave=False)
                return
            if text:
                self.say(text, seconds=max(10, min(30, len(text) / 12)))

        if not quiet:
            self.say("Let me think…", 4, wave=False)
        self._background(lambda: llm.plan_day(client, status, tasks, now_text), done)

    # --- мастер настройки ---

    def _background(self, work: Callable, on_done: Callable) -> None:
        """work() в отдельном потоке, on_done(результат, ошибка) — в потоке интерфейса."""
        if self.inline_jobs:
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, exc
            on_done(result, error)
            return
        job = _Job()
        self._jobs.add(job)

        def finish(result, error) -> None:
            self._jobs.discard(job)
            on_done(result, error)

        job.done.connect(finish, Qt.ConnectionType.QueuedConnection)

        def run() -> None:
            try:
                job.done.emit(work(), None)
            except Exception as exc:  # показать человеку, а не уронить поток
                job.done.emit(None, exc)

        threading.Thread(target=run, name="clodick-job", daemon=True).start()

    def open_setup(self) -> None:
        if self.setup is None:
            self.setup = self._build_setup()
        self.checklist.hide()
        self.bubble.hide()
        self.setup.show_page(HELLO)
        self.setup.open_near(self.pet.geometry(), self._screen_rect())

    def _build_setup(self) -> SetupDialog:
        dialog = SetupDialog(self.theme)
        choices = []
        for character in sorted(self.characters.values(), key=lambda c: c.name):
            book = SpriteBook(2, character=character, theme=self.theme.key)
            choices.append((character.id, character.name, book.character_frame("sit", 0)))
        dialog.set_characters(choices, self.character.id)
        dialog.set_google_available(self._env.oauth_client is not None)
        current = llm.LLMSettings.from_dict(self._state.get("llm"))
        if current is not None:
            dialog.set_llm_fields(current.base_url, current.model, bool(self._env.load_key()))
        link = google.SheetLink.from_dict(self._state.get("sheet_link"))
        if link is not None:
            dialog.set_sheet_status("The sheet is connected.", True, link.url)
        dialog.character_chosen.connect(self.set_character)
        dialog.google_requested.connect(self._setup_google)
        dialog.service_requested.connect(self._setup_service)
        dialog.llm_check_requested.connect(lambda u, m, k: self._setup_llm(u, m, k, save=False))
        dialog.llm_save_requested.connect(lambda u, m, k: self._setup_llm(u, m, k, save=True))
        dialog.finished.connect(self._setup_finished)
        dialog.open_url_requested.connect(self._open_url)
        dialog.client_find_requested.connect(self._find_client_file)
        dialog.client_file_chosen.connect(lambda path: self._install_client(Path(path)))
        return dialog

    def _open_url(self, url: str) -> None:
        if self._env.open_url is not None:
            self._env.open_url(url)
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))

    def _find_client_file(self) -> None:
        found = google.find_downloaded_client(self._env.downloads)
        if found is None:
            self.setup.set_guide_status(
                "I couldn't find it in Downloads. Press Choose file… and pick the JSON you "
                "downloaded in step 7. Its name starts with client_secret.",
                False,
            )
            return
        self._install_client(found)

    def _install_client(self, source: Path) -> None:
        try:
            target = google.install_oauth_client(source, self._env.data_dir)
        except google.SheetsError as exc:
            self.setup.set_guide_status(str(exc), False)
            return
        self._env.oauth_client = target
        log.info("файл OAuth-клиента установлен: %s", target)
        self.setup.set_google_available(True)
        self.setup.set_guide_status("")
        self.setup.show_page(SHEET)
        self.setup.set_sheet_status("Done! Now press «Sign in with Google».", None)

    def _setup_google(self) -> None:
        env = self._env
        token = env.data_dir / google.TOKEN_NAME

        def work():
            gc = env.sign_in(env.oauth_client, token)
            sheet_id, url = env.find_or_create(gc)
            return google.SheetLink("oauth", sheet_id, str(token), url)

        self._background(work, self._sheet_linked)

    def _setup_service(self, key_file: str, sheet: str) -> None:
        env = self._env

        def work():
            gc = env.authorize(google.SheetLink("service", "-", key_file))
            sheet_id, url = env.open_link(gc, sheet)
            return google.SheetLink("service", sheet_id, key_file, url)

        self._background(work, self._sheet_linked)

    def _sheet_linked(self, link, error) -> None:
        if error is not None:
            log.warning("таблица не подключилась: %s", error)
            self.setup.set_sheet_status(f"Didn't work: {error}", False)
            return
        self.connect_sheet(link)
        self.setup.set_sheet_status("Connected! Your tasks now live in the sheet.", True, link.url)

    def connect_sheet(self, link) -> None:
        """Запомнить таблицу и сразу начать с ней сверяться, без перезапуска."""
        self._state.set("sheet_link", link.to_dict())
        if self.sync is not None:
            self.sync.stop()
        self.sync = self._sync_factory(link) if self._sync_factory else None
        if self.sync is not None:
            self.sync.start()
            self.sync.request()
        self._sync_action.setEnabled(self.sync is not None)
        log.info("таблица подключена: %s (%s)", link.spreadsheet_id, link.mode)

    def _setup_llm(self, url: str, model: str, key: str, *, save: bool) -> None:
        settings = llm.LLMSettings(llm.normalize_url(url), model.strip())
        key = key.strip() or self._env.load_key()
        client = self._env.llm_client(settings, key)

        def done(answer, error) -> None:
            if error is not None:
                self.setup.set_llm_status(f"Didn't work: {error}", False)
                return
            if not save:
                self.setup.set_llm_status(f"The model answered: {answer[:60]}", True)
                return
            if key:
                self._env.save_key(key)
            self._state.set("llm", settings.to_dict())
            self._llm = client
            log.info("модель подключена: %s %s", settings.base_url, settings.model)
            self.setup.set_llm_status("Saved. I'll use it for plans.", True)
            self.setup.show_page(DONE)

        self._background(client.check, done)

    def _setup_finished(self) -> None:
        self._state.set("onboarding_done", True)
        self.setup.hide()
        self.say("Nice to meet you! Click me whenever you need today's list.", 8)

    def _check_reminders(self) -> None:
        due = self._reminder_clock.check(self._clock())
        if self.pomodoro.phase is Phase.FOCUS:
            return  # во время фокуса енот молчит
        if not self._reminders_on:
            return
        if self._check_timed():
            return
        if not due:
            return
        text = reminder_text(self._tracker.status())
        if text:
            log.info("напоминание: %s", text)
            self.say(text)

    def _check_timed(self) -> bool:
        """Задачи со временем, которое наступило. О каждой напоминаем один раз в день."""
        day = self._tracker.today().isoformat()
        seen = set((self._state.get("timed_reminded") or {}).get(day, []))
        now_due = self._tracker.due_now(seen)
        if not now_due:
            return False
        self._state.set("timed_reminded", {day: sorted(seen | {c.key for c in now_due})})
        text = timed_text([c.title for c in now_due])
        log.info("напоминание по времени: %s", text)
        self.say(text)
        return True

    def _pet_double_clicked(self) -> None:
        """Двойной клик: енот пугается и убегает, потом возвращается на место."""
        self.checklist.hide()
        pos = self._cursor()
        if self.brain.flee(pos.x(), pos.y(), self._pet_size().width()):
            self._after_brain_change()
            if self._rng.random() < 0.6:
                self.chat(self._rng.choice(("Eek!", "Can't catch me!", "Nope!")), 2.5)

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
        phase = self.pomodoro.phase
        moods = {Phase.FOCUS: CALM, Phase.BREAK: LIVELY}
        self.brain.mood = moods.get(phase, NORMAL)
        self.brain.tick(min(dt, 2.0))
        self._after_brain_change()
        self._after_tick(now)
        if self.sync is not None and self.sync.pop_changed():
            # Из таблицы пришли правки: показать их, если чек-лист открыт.
            log.info("из таблицы пришли изменения")
            if self.checklist.isVisible():
                self._refresh_checklist()

    def _after_tick(self, now: float) -> None:
        """Реплика к только что начатому действию и болтовня по расписанию."""
        started = self.brain.pop_started()
        if started:
            log.info("занятие: %s", started)
        if started and ACTIONS[started].lines and self._rng.random() < ACTION_LINE_CHANCE:
            self.chat(self._rng.choice(ACTIONS[started].lines), 4)
        if now >= self._next_chat:
            self._next_chat = now + self._chat_delay()
            if self.brain.mode is not Mode.SLEEP:
                status = self._tracker.status()
                line = idle_line(self._clock(), status, self._tracker.focus_count(), self._rng)
                self.chat(line, 7)

    def _chat_delay(self) -> float:
        return self._rng.uniform(*CHAT_MINUTES) * 60

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
        if mode is Mode.ACT:
            action = self.brain.action
            if action == "spin":
                return self._walk_animation()
            return (action, 1) if action in animations else ("sit", 1)
        if mode is Mode.WALK:
            return self._walk_animation()
        if mode is Mode.CLIMB:
            hanging = self.brain.climb_phase == "hang" and "climb_hang" in animations
            return ("climb_hang" if hanging else "climb"), 1
        if mode is Mode.SIT and self._look is not None and "look" in animations:
            return "look", 1
        return mode.value, 1

    def _walk_animation(self) -> tuple[str, int]:
        """Кадры ходьбы для текущего направления. Кружась за хвостом, он тоже их показывает."""
        animations = self.character.animations
        facing = self.brain.facing
        if facing in (UP, DOWN) and f"walk_{facing}" in animations:
            return f"walk_{facing}", 1
        if facing in DIAGONALS and DIAGONALS[facing][0] in animations:
            return DIAGONALS[facing]
        if facing in (UP, DOWN):
            return "walk", self.brain.side
        return "walk", 1 if "right" in facing else -1

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
        elif mode == "act" and self.brain.action != "spin":
            seconds = ACTIONS[self.brain.action].frame
        elif mode == "climb":
            seconds = FRAME_SECONDS[self._animation()[0]]
        else:
            seconds = FRAME_SECONDS["walk" if mode == "act" else mode]
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
        """Смотрит на курсор: косится на него, подходит к долго стоящему, а неподвижный
        курсор на еноте — это поглаживание."""
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
        self._watch_still(pos, speed, now)
        if rect.contains(pos) and speed < PET_SPEED and mode is Mode.SIT:
            if self._pet_since is None:
                self._pet_since = now
            elif now - self._pet_since >= PET_SECONDS and now >= self._pet_ready:
                self.pet.show_heart(HEART_SECONDS)
                self._pet_ready = now + PET_COOLDOWN
                if self._rng.random() < REACTION_LINE_CHANCE * 2:
                    self.chat(self._rng.choice(("Purr~", "More, please.", "Hehe.")), 3)
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

    def _watch_still(self, pos: QPoint, speed: float, now: float) -> None:
        """Курсор долго стоит неподалёку — енот подходит посмотреть, что там."""
        rect = self.pet.geometry()
        near = (pos - rect.center()).manhattanLength() < CURIOUS_RADIUS
        if speed >= PET_SPEED or not near or rect.contains(pos):
            self._still_since = None
            return
        if self._still_since is None:
            self._still_since = now
            return
        if (
            now - self._still_since >= CURIOUS_SECONDS
            and now >= self._curious_ready
            and self.pomodoro.phase is not Phase.FOCUS
        ):
            self._curious_ready = now + CURIOUS_COOLDOWN
            self._still_since = None
            size = self._pet_size()
            x = pos.x() - size.width() / 2
            y = pos.y() - size.height() / 2 - self.pet.sprite_offset
            if self.brain.approach(x, y, stop=size.width() * 1.3):
                self._after_brain_change()

    def _available_actions(self) -> dict:
        """Действия, для которых у персонажа есть кадры, и поведение без своих кадров."""
        animations = self.character.animations
        return {
            name: action
            for name, action in ACTIONS.items()
            if action.weight > 0 and (action.kind in ("spin", "zoomies") or name in animations)
        }

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
            self.pet.set_belly(f"{self._ram}%", rect, RAM_COLOR)
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
        return self._corner(QGuiApplication.primaryScreen().availableGeometry())

    def _corner(self, area: QRect) -> tuple[int, int]:
        """Правый нижний угол рабочей области: место по умолчанию."""
        size = self._pet_size()
        return (
            area.right() + 1 - size.width() - START_MARGIN,
            area.bottom() + 1 - size.height() - BOTTOM_PAD * self._scale,
        )

    def climb_now(self) -> None:
        """Из меню: пусть сейчас же лезет по правому краю экрана."""
        self.brain.area = self._area()
        if self.brain.climb():
            log.info("занятие: climb (из меню)")
            self._after_brain_change()
        elif self.brain.mode is not Mode.CLIMB:
            self.say("The edge is too far, or walks are off.", 5, wave=False)

    def summon(self) -> None:
        """Позвать енота на экран, где сейчас курсор: в правый нижний угол.

        Нужно, когда он ушёл на другой монитор или тот монитор выключен.
        """
        screen = QGuiApplication.screenAt(self._cursor()) or QGuiApplication.primaryScreen()
        x, y = self._corner(screen.availableGeometry())
        self._move_window(x, y)
        self.brain.area = self._area()
        self.brain.place(float(x), float(y))
        self._save_position()
        if not self.visible:
            self.set_visible(True)
        self._after_brain_change()
        self.hop()
        log.info("енота позвали на экран %s", screen.name())

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
        menu.addAction("Bring raccoon here", self.summon)
        menu.addAction("Climb the edge", self.climb_now)
        self._sync_action = menu.addAction("Sync with the sheet now", self.sync_now)
        self._sync_action.setEnabled(self.sync is not None)
        menu.addAction("Plan my day", self.plan_my_day)
        menu.addAction("Setup…", self.open_setup)
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
        self._chatty_action = QAction("Chatty", menu, checkable=True)
        self._chatty_action.setChecked(self._chatty)
        self._chatty_action.toggled.connect(self.set_chatty)
        self._belly_action = QAction("RAM on belly", menu, checkable=True)
        self._belly_action.setChecked(self._belly_ram)
        self._belly_action.toggled.connect(self.set_belly_ram)
        for action in (
            self._visible_action,
            self._walks_action,
            self._reminders_action,
            self._playful_action,
            self._chatty_action,
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
