"""Где приложение хранит данные.

Windows: %LOCALAPPDATA%\\cloDICK. Остальные ОС: ~/.local/share/clodick.
Переменная окружения CLODICK_HOME переопределяет путь (удобно для тестов и разработки).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "cloDICK"


def data_dir() -> Path:
    override = os.environ.get("CLODICK_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        base = base / APP_DIR_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_DIR_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return data_dir() / "config.toml"


def db_path() -> Path:
    return data_dir() / "clodick.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(exist_ok=True)
    return path
