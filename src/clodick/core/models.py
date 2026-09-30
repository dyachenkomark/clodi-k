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
    # Своя задача: добавлена из чек-листа или таблицы, её можно удалить.
    custom: bool = False
    # У своих задач: проект (Turkov, Maga, …), срок и время напоминания "ЧЧ:ММ".
    project: str = ""
    due: date | None = None
    time: str = ""


TASK_PREFIX = "task:"


def task_key(task_id: str) -> str:
    return f"{TASK_PREFIX}{task_id}"


def task_id(key: str) -> str | None:
    """task:a1b2c3d4 → a1b2c3d4. Для направлений из настроек — None."""
    if not key.startswith(TASK_PREFIX):
        return None
    return key.removeprefix(TASK_PREFIX) or None


@dataclass(frozen=True)
class Task:
    """Своя задача. Ежедневная отмечается по дням, разовая закрывается один раз."""

    id: str
    title: str
    daily: bool = False
    project: str = ""
    due: date | None = None
    time: str = ""
    # Только для разовых: закрыта и когда.
    done: bool = False
    done_at: datetime | None = None
    note: str = ""
    created_at: datetime | None = None

    @property
    def key(self) -> str:
        return task_key(self.id)


@dataclass(frozen=True)
class Note:
    """Заметка к пункту чек-листа: результат, комментарий."""

    id: int
    day: date
    key: str
    title: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class CategoryStatus:
    category: Category
    done: bool
    done_at: datetime | None = None
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class DayStatus:
    day: date
    # Сегодняшнее: направления, ежедневные задачи, разовые без срока, на сегодня и просроченные.
    items: tuple[CategoryStatus, ...]
    # Скоро: разовые задачи со сроком в ближайшие дни.
    upcoming: tuple[CategoryStatus, ...] = ()

    @property
    def done_count(self) -> int:
        return sum(1 for item in self.items if item.done)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def all_done(self) -> bool:
        return self.done_count == self.total
