"""Когда напоминать и что говорить. Без Qt, чтобы переиспользовать в боте."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time, timedelta

from clodick.core.models import DayStatus


def parse_times(values: Iterable[str]) -> tuple[time, ...]:
    """'ЧЧ:ММ' → time. Формат уже проверен при загрузке настроек."""
    result = []
    for value in values:
        hours, minutes = value.split(":")
        result.append(time(int(hours), int(minutes)))
    return tuple(sorted(set(result)))


class ReminderClock:
    """Отвечает на вопрос «пора напомнить?» при периодической проверке.

    Если компьютер спал и пропустил несколько напоминаний, сработает одно.
    """

    def __init__(self, times: Iterable[time], start: datetime) -> None:
        self._times = tuple(times)
        self._last = start

    def check(self, now: datetime) -> bool:
        last, self._last = self._last, max(self._last, now)
        if now <= last:
            return False
        day = last.date()
        while day <= now.date():
            for moment_time in self._times:
                moment = datetime.combine(day, moment_time)
                if last < moment <= now:
                    return True
            day += timedelta(days=1)
        return False


def pending_titles(status: DayStatus) -> list[str]:
    return [item.category.title.lower() for item in status.items if not item.done]


def reminder_text(status: DayStatus) -> str | None:
    """Текст напоминания или None, если всё сделано."""
    pending = pending_titles(status)
    if not pending:
        return None
    return f"Эй! Ещё не сделано: {', '.join(pending)}."


def greeting_text(status: DayStatus) -> str | None:
    pending = pending_titles(status)
    if not pending:
        return None
    return f"Привет! На сегодня: {', '.join(pending)}."


DONE_TEXT = "Всё сделано на сегодня. Горжусь!"
