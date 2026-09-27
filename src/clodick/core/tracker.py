"""Логика дня: какой сейчас день, что отмечено, отметить, снять, свои задачи."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from clodick.config import Config
from clodick.core.models import Category, CategoryStatus, DayStatus, Task, task_id, task_key
from clodick.storage.repository import CompletionRepository

Clock = Callable[[], datetime]


def logical_day(moment: datetime, day_start_hour: int) -> date:
    """День, к которому относится момент. До day_start_hour считается вчерашний день."""
    return (moment - timedelta(hours=day_start_hour)).date()


class Tracker:
    def __init__(
        self, config: Config, repo: CompletionRepository, clock: Clock = datetime.now
    ) -> None:
        self._config = config
        self._repo = repo
        self._clock = clock

    def today(self) -> date:
        return logical_day(self._clock(), self._config.day_start_hour)

    def status(self, day: date | None = None) -> DayStatus:
        day = day or self.today()
        done = self._repo.completions_for(day)
        items = tuple(
            CategoryStatus(category=cat, done=cat.key in done, done_at=done.get(cat.key))
            for cat in self._items(day)
        )
        return DayStatus(day=day, items=items)

    def mark_done(self, key: str, source: str = "cli") -> bool:
        """Отмечает пункт выполненным. Возвращает False, если уже было отмечено."""
        self._check_key(key)
        return self._repo.add(key, self.today(), self._clock(), source)

    def unmark(self, key: str) -> bool:
        """Снимает отметку. Возвращает False, если отметки не было."""
        self._check_key(key)
        return self._repo.remove(key, self.today())

    def add_task(self, title: str, daily: bool = False) -> Task:
        """Своя задача. Разовая видна, пока не отмечена, и ещё до конца дня отметки."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("Task title is empty")
        return self._repo.add_task(title, daily, self._clock())

    def remove_task(self, key: str) -> bool:
        tid = task_id(key)
        return tid is not None and self._repo.remove_task(tid)

    def _items(self, day: date) -> list[Category]:
        closed = self._repo.done_before(day)
        items = list(self._config.categories)
        tasks = [
            Category(key=task_key(t.id), title=t.title, daily=t.daily, custom=True)
            for t in self._repo.tasks()
        ]
        tasks = [t for t in tasks if t.daily or t.key not in closed]
        # Сначала всё ежедневное, потом разовое.
        return items + [t for t in tasks if t.daily] + [t for t in tasks if not t.daily]

    def _check_key(self, key: str) -> None:
        keys = [cat.key for cat in self._items(self.today())]
        if key not in keys:
            raise KeyError(f"Unknown item «{key}». Available: {', '.join(keys)}")
