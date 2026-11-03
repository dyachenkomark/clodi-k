"""План дня: три дела. Выбирает код, модель только пересказывает.

У темы есть норма часов в неделю. Сколько часов на самом деле ушло, мы не знаем: таймером
пользуются не всегда. Зато знаем, когда в теме в последний раз было что-то отмечено:
галочка, заметка или фокус. Отсюда долг: дневная норма × дни без отметок.
Так тема на 10 часов в неделю всплывает реже темы на 40, но не теряется совсем.

Сроки идут первыми, но занимают не больше двух мест: иначе работа со сроками навсегда
вытеснит то, у чего сроков не бывает, например языки.
План выбирается один раз на день и дальше не меняется: отмечается, что из него сделано.
"""

from __future__ import annotations

import textwrap
from dataclasses import asdict, dataclass, replace

from clodick.core.models import Category
from clodick.core.tracker import Tracker
from clodick.storage.state import StateStore

PLAN_SIZE = 3
MAX_DEADLINES = 2
# Долг копится не дольше недели: дальше он равен недельной норме.
MAX_IDLE_DAYS = 7
PLAN_KEY = "day_plan"
TITLE_LENGTH = 60


@dataclass(frozen=True)
class Direction:
    """Тема с нормой часов и сколько дней в ней ничего не отмечено."""

    name: str
    hours: int
    idle_days: int

    @property
    def owed(self) -> float:
        return self.hours / 7 * self.idle_days


@dataclass(frozen=True)
class PlanItem:
    key: str  # пустой: в теме нет задачи, её надо выбрать
    title: str
    direction: str
    why: str
    done: bool = False


def enabled(tracker: Tracker) -> bool:
    return any(t.hours > 0 for t in tracker.topics())


def directions(tracker: Tracker) -> list[Direction]:
    """Темы с нормой: у кого больше долг, тот первый."""
    today = tracker.today()
    last = tracker.last_activity(MAX_IDLE_DAYS)
    found = []
    for topic in tracker.topics():
        if topic.hours <= 0:
            continue
        seen = last.get(topic.name.casefold())
        idle = MAX_IDLE_DAYS if seen is None else (today - seen).days
        found.append(Direction(topic.name, topic.hours, idle))
    return sorted(found, key=lambda d: -d.owed)


def _deadline_why(category: Category, day) -> str:
    late = (day - category.due).days
    return f"overdue {late}d" if late > 0 else "due today"


def _idle_why(direction: Direction) -> str:
    days = direction.idle_days
    if days >= MAX_IDLE_DAYS:
        return f"no marks for {MAX_IDLE_DAYS}+ days"
    return f"no marks for {days} day{'s' if days != 1 else ''}"


def _next_in(tracker: Tracker, direction: Direction, status, used: set[str]) -> PlanItem:
    """Следующее дело темы: задача с ближайшим сроком, потом ежедневное, иначе выбрать задачу."""
    name = direction.name.casefold()
    why = _idle_why(direction)
    for task in tracker.open_tasks():
        if task.project.casefold() == name and task.key not in used:
            return PlanItem(task.key, task.title, direction.name, why)
    for item in status.items:
        category = item.category
        if category.daily and not item.done and category.project.casefold() == name:
            return PlanItem(category.key, category.title, direction.name, why)
    return PlanItem("", f"{direction.name}: pick a task", direction.name, why)


def build(tracker: Tracker) -> list[PlanItem]:
    status = tracker.status()
    urgent = sorted(
        (
            i.category
            for i in status.items
            if not i.done and i.category.due is not None and i.category.due <= status.day
        ),
        key=lambda c: c.due,
    )
    plan = [
        PlanItem(c.key, c.title, c.project, _deadline_why(c, status.day))
        for c in urgent[:MAX_DEADLINES]
    ]
    used = {item.key for item in plan}
    covered = {item.direction.casefold() for item in plan}
    for direction in directions(tracker):
        if len(plan) >= PLAN_SIZE:
            break
        if direction.owed <= 0 or direction.name.casefold() in covered:
            continue
        item = _next_in(tracker, direction, status, used)
        plan.append(item)
        used.add(item.key)
    # Места остались: остальные горящие сроки.
    for category in urgent[MAX_DEADLINES:]:
        if len(plan) < PLAN_SIZE:
            plan.append(
                PlanItem(
                    category.key,
                    category.title,
                    category.project,
                    _deadline_why(category, status.day),
                )
            )
    return plan


def todays_plan(tracker: Tracker, state: StateStore) -> list[PlanItem]:
    """План на сегодня: выбранный утром, с отметками, что уже сделано."""
    day = tracker.today().isoformat()
    saved = state.get(PLAN_KEY)
    if saved and saved.get("day") == day:
        items = [PlanItem(**item) for item in saved["items"]]
    else:
        items = build(tracker)
        if items:
            state.set(PLAN_KEY, {"day": day, "items": [asdict(i) for i in items]})
    touched = tracker.last_activity(0)
    result = []
    for item in items:
        if not item.key:
            done = item.direction.casefold() in touched
        else:
            done = tracker.is_done(item.key)
            if done is None:  # задачу удалили
                continue
        result.append(replace(item, done=done))
    return result


def _short(title: str) -> str:
    return textwrap.shorten(title, TITLE_LENGTH, placeholder="…")


def plan_text(items: list[PlanItem]) -> str:
    """План словами, без модели."""
    if not items:
        return ""
    left = [i for i in items if not i.done]
    if not left:
        return "Today's plan is done!"
    listed = "; ".join(f"{_short(i.title)} ({i.why})" for i in left)
    return f"Plan {len(items) - len(left)}/{len(items)}. Left: {listed}."


def plan_line(items: list[PlanItem]) -> str:
    """Строка в чек-листе: сколько сделано и в какой теме надо выбрать задачу."""
    if not items:
        return ""
    done = sum(i.done for i in items)
    parts = [f"★ Plan {done}/{len(items)}"]
    parts += [i.title for i in items if not i.key and not i.done]
    return " · ".join(parts)


def facts(items: list[PlanItem]) -> list[str]:
    """План для модели: порядок и состав уже решены."""
    lines = []
    for item in items:
        mark = "done" if item.done else "not done"
        where = f"{item.direction}, " if item.direction else ""
        lines.append(f"- {item.title} ({where}{item.why}): {mark}")
    return lines
