"""Настройки из TOML-файла. При первом запуске создаётся файл со значениями по умолчанию."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from clodick.core.models import Category
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
# Размер пикселя енота на экране: 3 — мелко, 4 — обычно, 6 — крупно.
scale = 4
# Отпускать енота гулять вдоль края экрана.
walks = true
# Оформление: classic, claude, claude_orange, claude_night.
theme = "claude"

[[categories]]
key = "sport"
title = "Спорт"

[[categories]]
key = "study"
title = "Учёба"

[[categories]]
key = "language"
title = "Язык"
# Ссылка на сайт с уроками. Появится кнопка «открыть сайт».
url = ""
"""


class ConfigError(ValueError):
    """Файл настроек заполнен неправильно."""


@dataclass(frozen=True)
class DesktopConfig:
    scale: int = 4
    walks: bool = True
    theme: str = DEFAULT_THEME


@dataclass(frozen=True)
class Config:
    categories: tuple[Category, ...]
    day_start_hour: int = 4
    daily_goal_minutes: int = 15
    reminders: tuple[str, ...] = field(default_factory=tuple)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)

    def category(self, key: str) -> Category:
        for cat in self.categories:
            if cat.key == key:
                return cat
        known = ", ".join(c.key for c in self.categories)
        raise KeyError(f"Неизвестное направление «{key}». Есть: {known}")


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
    )


def _parse_desktop(raw: dict) -> DesktopConfig:
    scale = raw.get("scale", 4)
    if not isinstance(scale, int) or not 1 <= scale <= 12:
        raise ConfigError("desktop.scale должен быть целым числом от 1 до 12")
    walks = raw.get("walks", True)
    if not isinstance(walks, bool):
        raise ConfigError("desktop.walks должен быть true или false")
    theme = raw.get("theme", DEFAULT_THEME)
    if theme not in THEMES:
        raise ConfigError(f"desktop.theme: неизвестная тема {theme!r}. Есть: {', '.join(THEMES)}")
    return DesktopConfig(scale=scale, walks=walks, theme=theme)


def _validate_hhmm(value: object) -> None:
    if not isinstance(value, str):
        raise ConfigError(f"Время напоминания должно быть строкой ЧЧ:ММ, получено {value!r}")
    parts = value.split(":")
    ok = len(parts) == 2 and all(p.isdigit() for p in parts)
    if not ok or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
        raise ConfigError(f"Неверное время напоминания: {value!r}, нужно ЧЧ:ММ")
