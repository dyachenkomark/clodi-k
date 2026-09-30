"""Разбор короткой записи задачи без LLM: «мага: отчёт до пт в 15:00».

Проект — слово перед двоеточием. Срок — дата, день недели, «завтра», «через 3 дня».
Время — ЧЧ:ММ. «каждый день» или daily делает задачу ежедневной. Всё остальное — название.
Даты считает код: позже LLM сможет готовить ту же структуру из свободного текста,
но календарную арифметику ей доверять не будем.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

_WEEKDAY_PREFIX = {
    "пн": 0, "по": 0, "вт": 1, "ср": 2, "чт": 3, "че": 3, "пт": 4, "пя": 4,
    "сб": 5, "су": 5, "вс": 6, "во": 6,
    "mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
}  # fmt: skip
_MONTH_PREFIX = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

_WEEKDAY = (
    r"понедельник\w*|вторник\w*|сред[ауы]|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*"
    r"|пн|вт|ср|чт|пт|сб|вс"
    r"|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?"
)
_MONTH = (
    r"янв\w*|фев\w*|мар\w*|апр\w*|ма[йя]|июн\w*|июл\w*|авг\w*|сен\w*|окт\w*|ноя\w*|дек\w*"
    r"|jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*"
)
_DATE = re.compile(
    r"(?<!\w)(?:(?P<prep>до|к|ко|на|в|во|by|due|on|until)\s+)?"
    r"(?:(?P<iso>\d{4}-\d{1,2}-\d{1,2})"
    r"|(?P<dmy>\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)"
    r"|(?P<day>\d{1,2})\s+(?P<month>" + _MONTH + r")"
    r"|(?:через|in)\s+(?P<shift>\d+)\s+(?:дн\w*|день|дня|days?)"
    r"|(?P<word>сегодня|завтра|послезавтра|today|tomorrow)"
    r"|(?P<weekday>" + _WEEKDAY + r"))(?!\w)",
    re.IGNORECASE,
)
_TIME = re.compile(r"(?:\b(?:в|во|at)\s+)?(?<![\d.:])(\d{1,2}):(\d{2})(?![\d:])", re.IGNORECASE)
_DAILY = re.compile(r"\b(?:каждый\s+день|ежедневно|daily|every\s+day)\b", re.IGNORECASE)
_PROJECT = re.compile(r"^\s*([^\s:]{1,24})\s*:\s+(\S.*)$", re.DOTALL)
_WORDS = {"сегодня": 0, "today": 0, "завтра": 1, "tomorrow": 1, "послезавтра": 2}


@dataclass(frozen=True)
class Parsed:
    title: str
    project: str = ""
    due: date | None = None
    time: str = ""
    daily: bool = False


def _resolve(match: re.Match, today: date) -> date | None:
    try:
        if match["iso"]:
            return date.fromisoformat("-".join(p.zfill(2) for p in match["iso"].split("-")))
        if match["dmy"]:
            parts = re.split(r"[./]", match["dmy"])
            day, month = int(parts[0]), int(parts[1])
            if len(parts) == 3:
                year = int(parts[2])
                return date(year + 2000 if year < 100 else year, month, day)
            return _nearest(day, month, today)
        if match["day"]:
            return _nearest(int(match["day"]), _MONTH_PREFIX[match["month"][:3].lower()], today)
        if match["shift"]:
            return today + timedelta(days=int(match["shift"]))
        if match["word"]:
            return today + timedelta(days=_WORDS[match["word"].lower()])
        weekday = _WEEKDAY_PREFIX[match["weekday"][:2].lower()]
        return today + timedelta(days=(weekday - today.weekday()) % 7)
    except (ValueError, KeyError):
        return None


def _nearest(day: int, month: int, today: date) -> date:
    """Дата без года: этот год, а если она уже больше месяца как прошла — следующий."""
    result = date(today.year, month, day)
    return result if result >= today - timedelta(days=30) else date(today.year + 1, month, day)


def parse_date(text: str, today: date) -> date | None:
    """Дата из ячейки или фразы целиком: «пт», «завтра», «02.10», «2026-10-02», «2 октября»."""
    match = _DATE.fullmatch(text.strip())
    return _resolve(match, today) if match else None


def parse_time(text: str) -> str:
    """«9:30» → «09:30». Пустая строка, если это не время."""
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        return ""
    return f"{int(match[1]):02d}:{match[2]}"


def match_project(name: str, projects: Mapping[str, Sequence[str]]) -> str:
    """Имя проекта по любому из его псевдонимов. Незнакомое имя остаётся как написано."""
    wanted = name.strip().casefold()
    for project, aliases in projects.items():
        if wanted == project.casefold() or wanted in (a.casefold() for a in aliases):
            return project
    return name.strip()


def parse(text: str, today: date, projects: Mapping[str, Sequence[str]] | None = None) -> Parsed:
    projects = projects or {}
    rest = " ".join(text.split())
    project = ""
    head = _PROJECT.match(rest)
    if head and not head[1].isdigit():
        project, rest = match_project(head[1], projects), head[2]

    daily = bool(_DAILY.search(rest))
    rest = _DAILY.sub(" ", rest)

    time = ""
    for found in _TIME.finditer(rest):
        value = parse_time(f"{found[1]}:{found[2]}")
        if value:
            time = value
            rest = rest[: found.start()] + " " + rest[found.end() :]
            break

    # Срок — последняя дата с предлогом («до пт») или дата в самом конце («отчёт завтра»).
    due = None
    for found in reversed(list(_DATE.finditer(rest))):
        at_end = not rest[found.end() :].strip(" .,;!")
        standalone = found.start() == 0 or rest[found.start() - 1].isspace()
        # Дата с месяцем или годом однозначна и годится в любом месте фразы.
        explicit = bool(found["iso"] or found["day"])
        if standalone and (found["prep"] or at_end or explicit):
            resolved = _resolve(found, today)
            if resolved is not None:
                due = resolved
                rest = rest[: found.start()] + " " + rest[found.end() :]
                break

    title = " ".join(rest.split()).strip(" ,.;-—")
    return Parsed(title=title, project=project, due=due, time=time, daily=daily)
