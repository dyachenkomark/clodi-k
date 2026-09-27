"""Pomodoro: фокус, короткий перерыв, после нескольких раундов — длинный. Без Qt.

Состояние сохраняется словарём, чтобы сессия пережила перезапуск приложения.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Phase(Enum):
    IDLE = "idle"
    FOCUS = "focus"
    BREAK = "break"


class Event(Enum):
    FOCUS_DONE = "focus_done"
    BREAK_DONE = "break_done"


@dataclass(frozen=True)
class PomodoroConfig:
    focus: int = 25
    short_break: int = 5
    long_break: int = 15
    # Сколько фокусов до длинного перерыва.
    rounds: int = 4


class Pomodoro:
    def __init__(self, config: PomodoroConfig) -> None:
        self.config = config
        self.phase = Phase.IDLE
        self.ends: datetime | None = None
        self.started: datetime | None = None
        # На какой пункт чек-листа фокус, например "sport" или "task:3". None — просто фокус.
        self.key: str | None = None
        # Сколько фокусов подряд закончено: от него зависит длина перерыва.
        self.streak = 0

    @property
    def active(self) -> bool:
        return self.phase is not Phase.IDLE

    def start_focus(self, now: datetime, key: str | None = None) -> None:
        self.phase = Phase.FOCUS
        self.key = key
        self.started = now
        self.ends = now + timedelta(minutes=self.config.focus)

    def stop(self) -> None:
        """Прервать фокус или перерыв. Незаконченный фокус не засчитывается."""
        self.phase = Phase.IDLE
        self.ends = self.started = None
        self.key = None

    def minutes_left(self, now: datetime) -> int:
        """Сколько минут осталось, с округлением вверх: 24:10 → 25."""
        if self.ends is None:
            return 0
        return max(0, math.ceil((self.ends - now).total_seconds() / 60))

    def check(self, now: datetime) -> Event | None:
        """Вызывать периодически. Возвращает событие, если фаза закончилась."""
        if self.ends is None or now < self.ends:
            return None
        if self.phase is Phase.FOCUS:
            self.streak += 1
            long = self.streak % self.config.rounds == 0
            minutes = self.config.long_break if long else self.config.short_break
            self.phase = Phase.BREAK
            self.started = self.ends
            self.ends = self.ends + timedelta(minutes=minutes)
            return Event.FOCUS_DONE
        self.phase = Phase.IDLE
        self.ends = self.started = None
        self.key = None
        return Event.BREAK_DONE

    @property
    def break_minutes(self) -> int:
        """Длина текущего перерыва в минутах."""
        if self.phase is not Phase.BREAK or self.ends is None or self.started is None:
            return 0
        return round((self.ends - self.started).total_seconds() / 60)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "ends": self.ends.isoformat() if self.ends else None,
            "started": self.started.isoformat() if self.started else None,
            "key": self.key,
            "streak": self.streak,
        }

    @classmethod
    def from_dict(cls, config: PomodoroConfig, data: dict | None) -> Pomodoro:
        pomodoro = cls(config)
        if not data:
            return pomodoro
        try:
            pomodoro.phase = Phase(data.get("phase", "idle"))
            ends, started = data.get("ends"), data.get("started")
            pomodoro.ends = datetime.fromisoformat(ends) if ends else None
            pomodoro.started = datetime.fromisoformat(started) if started else None
            pomodoro.key = data.get("key")
            pomodoro.streak = int(data.get("streak", 0))
        except (ValueError, TypeError):
            return cls(config)
        if pomodoro.phase is not Phase.IDLE and pomodoro.ends is None:
            return cls(config)
        return pomodoro
