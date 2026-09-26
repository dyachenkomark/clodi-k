"""Доменные объекты. Не зависят от интерфейсов и хранилища."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Category:
    """Направление: спорт, учёба, язык и т. д."""

    key: str
    title: str
    url: str | None = None


@dataclass(frozen=True)
class CategoryStatus:
    category: Category
    done: bool
    done_at: datetime | None = None


@dataclass(frozen=True)
class DayStatus:
    day: date
    items: tuple[CategoryStatus, ...]

    @property
    def done_count(self) -> int:
        return sum(1 for item in self.items if item.done)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def all_done(self) -> bool:
        return self.done_count == self.total
