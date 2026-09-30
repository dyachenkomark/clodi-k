from datetime import date

import pytest

from clodick.core.quickadd import Parsed, parse, parse_date, parse_time

TODAY = date(2026, 9, 30)  # среда
PROJECTS = {"Maga": ("мага", "maga"), "Turkov": ("турков",)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "мага: отчёт до пт в 15:00",
            Parsed("отчёт", "Maga", date(2026, 10, 2), "15:00"),
        ),
        ("Turkov: fix login by 2.10", Parsed("fix login", "Turkov", date(2026, 10, 2))),
        ("написать скрипт", Parsed("написать скрипт")),
        ("зарядка каждый день", Parsed("зарядка", daily=True)),
        ("позвонить Анне завтра", Parsed("позвонить Анне", due=date(2026, 10, 1))),
        ("встреча 10:30", Parsed("встреча", time="10:30")),
        ("сдать 5 октября отчёт", Parsed("сдать отчёт", due=date(2026, 10, 5))),
        ("личное: бег через 3 дня", Parsed("бег", "личное", date(2026, 10, 3))),
        ("в пятницу к врачу", Parsed("к врачу", due=date(2026, 10, 2))),
        ("релиз 2026-10-15", Parsed("релиз", due=date(2026, 10, 15))),
        ("почта и отчёт", Parsed("почта и отчёт")),
        ("обновить до версии 2.10 сервер", Parsed("обновить до версии 2.10 сервер")),
        ("report on friday", Parsed("report", due=date(2026, 10, 2))),
        ("сегодня среда: созвон в ср", Parsed("сегодня среда: созвон", due=TODAY)),
    ],
)
def test_parse(text, expected):
    assert parse(text, TODAY, PROJECTS) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("пт", date(2026, 10, 2)),
        ("завтра", date(2026, 10, 1)),
        ("02.10", date(2026, 10, 2)),
        ("02.10.2026", date(2026, 10, 2)),
        ("2026-10-02", date(2026, 10, 2)),
        ("2 октября", date(2026, 10, 2)),
        ("15.01", date(2027, 1, 15)),  # давно прошедшая дата без года — это следующий год
        ("25.09", date(2026, 9, 25)),  # недавно прошедшая — просрочка в этом году
        ("31.02", None),
        ("чушь", None),
        ("", None),
    ],
)
def test_parse_date(cell, expected):
    assert parse_date(cell, TODAY) == expected


def test_parse_time():
    assert parse_time("9:30") == "09:30"
    assert parse_time("23.05") == "23:05"
    assert parse_time("25:00") == ""
    assert parse_time("soon") == ""
