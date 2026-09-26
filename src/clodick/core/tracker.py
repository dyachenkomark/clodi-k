"""Логика дня: какой сейчас день, что отмечено, отметить или снять отметку."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from clodick.config import Config
from clodick.core.models import CategoryStatus, DayStatus
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
            for cat in self._config.categories
        )
        return DayStatus(day=day, items=items)

    def mark_done(self, key: str, source: str = "cli") -> bool:
        """Отмечает направление выполненным. Возвращает False, если уже было отмечено."""
        self._config.category(key)
        return self._repo.add(key, self.today(), self._clock(), source)

    def unmark(self, key: str) -> bool:
        """Снимает отметку. Возвращает False, если отметки не было."""
        self._config.category(key)
        return self._repo.remove(key, self.today())
