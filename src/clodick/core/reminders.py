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


# Сколько пунктов называть в реплике: остальные — «and N more».
MAX_LISTED = 4


def _listed(titles: list[str]) -> str:
    if len(titles) <= MAX_LISTED:
        return ", ".join(titles)
    return f"{', '.join(titles[:MAX_LISTED])} and {len(titles) - MAX_LISTED} more"


def pending_titles(status: DayStatus) -> list[str]:
    """Что осталось на сегодня. Просроченные задачи помечены."""
    titles = []
    for item in status.items:
        if item.done:
            continue
        due = item.category.due
        late = due is not None and due < status.day
        titles.append(f"{item.category.title} (overdue)" if late else item.category.title)
    return titles


def tomorrow_titles(status: DayStatus) -> list[str]:
    tomorrow = status.day + timedelta(days=1)
    return [i.category.title for i in status.upcoming if not i.done and i.category.due == tomorrow]


def _tomorrow(status: DayStatus) -> str:
    titles = tomorrow_titles(status)
    return f" Due tomorrow: {_listed(titles)}." if titles else ""


def reminder_text(status: DayStatus) -> str | None:
    """Текст напоминания или None, если всё сделано и на завтра сроков нет."""
    pending = pending_titles(status)
    if not pending:
        return _tomorrow(status).strip() or None
    return f"Hey! Still to do: {_listed(pending)}.{_tomorrow(status)}"


def greeting_text(status: DayStatus) -> str | None:
    pending = pending_titles(status)
    if not pending:
        return _tomorrow(status).strip() or None
    return f"Hi! Today: {_listed(pending)}.{_tomorrow(status)}"


def timed_text(titles: list[str]) -> str:
    """Наступило время задачи."""
    return f"It's time: {_listed(titles)}."


DONE_TEXT = "All done for today. Proud of you!"
