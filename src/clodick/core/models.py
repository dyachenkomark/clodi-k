"""Доменные объекты. Не зависят от интерфейсов и хранилища."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Category:
    """Пункт чек-листа: направление из настроек или своя задача из чек-листа."""

    key: str
    title: str
    url: str | None = None
    daily: bool = True
    # Своя задача: добавлена из чек-листа, её можно удалить.
    custom: bool = False


TASK_PREFIX = "task:"


def task_key(task_id: int) -> str:
    return f"{TASK_PREFIX}{task_id}"


def task_id(key: str) -> int | None:
    """task:7 → 7. Для направлений из настроек — None."""
    if not key.startswith(TASK_PREFIX):
        return None
    rest = key.removeprefix(TASK_PREFIX)
    return int(rest) if rest.isdigit() else None


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    daily: bool


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
