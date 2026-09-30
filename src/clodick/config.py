"""Настройки из TOML-файла. При первом запуске создаётся файл со значениями по умолчанию."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from clodick.characters import DEFAULT_CHARACTER
from clodick.core.models import Category
from clodick.core.pomodoro import PomodoroConfig
from clodick.desktop.themes import DEFAULT_THEME, THEMES

DEFAULT_CONFIG = """\
# Настройки cloDICK. Файл можно править руками, изменения применяются после перезапуска.

# Во сколько начинается новый день (0-23). Всё, что отмечено до этого часа,
# засчитывается во вчерашний день.
day_start_hour = 4

# Сколько минут в день — цель по каждому направлению.
daily_goal_minutes = 15

# Время напоминаний, формат ЧЧ:ММ.
reminders = ["10:00", "15:00", "20:00"]

[desktop]
# Размер пикселя персонажа на экране: 3 — мелко, 4 — обычно, 6 — крупно.
scale = 3
# Отпускать персонажа гулять. Экран для него — пол: гуляет во все стороны.
walks = true
# Как далеко от своего места он уходит, в пикселях. 5000 — по всему экрану.
roam = 500
# Оформление: classic, claude, claude_orange, claude_night.
theme = "claude"
# Персонаж. Свои персонажи кладите в папку characters рядом с этим файлом.
character = "raccoon"

[sheets]
# Google Таблица как база: задачи, отметки, заметки. Как подключить — docs/SHEETS.md.
# spreadsheet_id — адрес таблицы или её id из адреса. Пусто — работаем только локально.
spreadsheet_id = ""
# JSON-ключ сервисного аккаунта Google. Путь относительно папки с этим файлом.
key_file = "google-key.json"
# Как часто сверяться с таблицей, секунды.
sync_seconds = 60

# Проекты для задач и их короткие имена: «мага: отчёт до пт» попадёт в проект Maga.
# [projects]
# Work = ["работа", "work"]
# Personal = ["личное"]

[pomodoro]
# Pomodoro: минуты фокуса, короткого и длинного перерыва.
focus = 25
short_break = 5
long_break = 15
# После скольких фокусов длинный перерыв.
rounds = 4

[[categories]]
key = "sport"
title = "Sport"

[[categories]]
key = "study"
title = "Study"

[[categories]]
key = "language"
title = "Language"
# Ссылка на сайт с уроками. Появится кнопка «открыть сайт».
url = ""
"""


class ConfigError(ValueError):
    """Файл настроек заполнен неправильно."""


@dataclass(frozen=True)
class DesktopConfig:
    scale: int = 3
    walks: bool = True
    roam: int = 500
    theme: str = DEFAULT_THEME
    character: str = DEFAULT_CHARACTER


@dataclass(frozen=True)
class SheetsConfig:
    spreadsheet_id: str = ""
    key_file: str = "google-key.json"
    sync_seconds: int = 60

    @property
    def enabled(self) -> bool:
        return bool(self.spreadsheet_id)


@dataclass(frozen=True)
class Config:
    categories: tuple[Category, ...]
    day_start_hour: int = 4
    daily_goal_minutes: int = 15
    reminders: tuple[str, ...] = field(default_factory=tuple)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    pomodoro: PomodoroConfig = field(default_factory=PomodoroConfig)
    sheets: SheetsConfig = field(default_factory=SheetsConfig)
    # Проект → его короткие имена для быстрого ввода.
    projects: dict[str, tuple[str, ...]] = field(default_factory=dict)


def load_config(path: Path) -> Config:
    if not path.exists():
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return parse_config(raw)


def parse_config(raw: dict) -> Config:
    day_start_hour = raw.get("day_start_hour", 4)
    if not isinstance(day_start_hour, int) or not 0 <= day_start_hour <= 23:
        raise ConfigError("day_start_hour должен быть целым числом от 0 до 23")

    goal = raw.get("daily_goal_minutes", 15)
    if not isinstance(goal, int) or goal <= 0:
        raise ConfigError("daily_goal_minutes должен быть положительным целым числом")

    reminders = tuple(raw.get("reminders", []))
    for item in reminders:
        _validate_hhmm(item)

    items = raw.get("categories", [])
    if not items:
        raise ConfigError("Нужно хотя бы одно направление в [[categories]]")
    categories = []
    seen: set[str] = set()
    for item in items:
        key = item.get("key")
        title = item.get("title")
        if not key or not title:
            raise ConfigError("У каждого направления должны быть key и title")
        if key in seen:
            raise ConfigError(f"Направление «{key}» указано дважды")
        seen.add(key)
        categories.append(Category(key=key, title=title, url=item.get("url") or None))

    return Config(
        categories=tuple(categories),
        day_start_hour=day_start_hour,
        daily_goal_minutes=goal,
        reminders=reminders,
        desktop=_parse_desktop(raw.get("desktop", {})),
        pomodoro=_parse_pomodoro(raw.get("pomodoro", {})),
        sheets=_parse_sheets(raw.get("sheets", {})),
        projects=_parse_projects(raw.get("projects", {})),
    )


def _parse_sheets(raw: dict) -> SheetsConfig:
    spreadsheet = raw.get("spreadsheet_id", "")
    key_file = raw.get("key_file", "google-key.json")
    seconds = raw.get("sync_seconds", 60)
    if not isinstance(spreadsheet, str) or not isinstance(key_file, str) or not key_file:
        raise ConfigError("sheets.spreadsheet_id и sheets.key_file должны быть строками")
    if not isinstance(seconds, int) or not 15 <= seconds <= 3600:
        raise ConfigError("sheets.sync_seconds должен быть целым числом от 15 до 3600")
    # Можно вставить адрес таблицы целиком: id стоит между /d/ и следующим слэшем.
    found = re.search(r"/d/([A-Za-z0-9_-]+)", spreadsheet)
    return SheetsConfig(
        spreadsheet_id=found[1] if found else spreadsheet.strip(),
        key_file=key_file,
        sync_seconds=seconds,
    )


def _parse_projects(raw: dict) -> dict[str, tuple[str, ...]]:
    projects = {}
    for name, aliases in raw.items():
        if isinstance(aliases, str):
            aliases = [aliases]
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ConfigError(f"projects.{name}: нужен список коротких имён в кавычках")
        projects[name] = tuple(aliases)
    return projects


def _parse_pomodoro(raw: dict) -> PomodoroConfig:
    limits = {"focus": 180, "short_break": 60, "long_break": 120, "rounds": 12}
    values = {}
    for name, top in limits.items():
        value = raw.get(name, getattr(PomodoroConfig, name))
        if not isinstance(value, int) or not 1 <= value <= top:
            raise ConfigError(f"pomodoro.{name} должен быть целым числом от 1 до {top}")
        values[name] = value
    return PomodoroConfig(**values)


def _parse_desktop(raw: dict) -> DesktopConfig:
    scale = raw.get("scale", 3)
    if not isinstance(scale, int) or not 1 <= scale <= 12:
        raise ConfigError("desktop.scale должен быть целым числом от 1 до 12")
    walks = raw.get("walks", True)
    if not isinstance(walks, bool):
        raise ConfigError("desktop.walks должен быть true или false")
    roam = raw.get("roam", 500)
    if not isinstance(roam, int) or roam < 0:
        raise ConfigError("desktop.roam должен быть целым числом пикселей, 0 или больше")
    theme = raw.get("theme", DEFAULT_THEME)
    if theme not in THEMES:
        raise ConfigError(f"desktop.theme: неизвестная тема {theme!r}. Есть: {', '.join(THEMES)}")
    character = raw.get("character", DEFAULT_CHARACTER)
    if not isinstance(character, str) or not character:
        raise ConfigError("desktop.character должен быть названием папки персонажа")
    return DesktopConfig(scale=scale, walks=walks, roam=roam, theme=theme, character=character)


def _validate_hhmm(value: object) -> None:
    if not isinstance(value, str):
        raise ConfigError(f"Время напоминания должно быть строкой ЧЧ:ММ, получено {value!r}")
    parts = value.split(":")
    ok = len(parts) == 2 and all(p.isdigit() for p in parts)
    if not ok or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
        raise ConfigError(f"Неверное время напоминания: {value!r}, нужно ЧЧ:ММ")
