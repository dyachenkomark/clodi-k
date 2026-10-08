"""Запуск вместе с Windows: запись в HKCU\\...\\Run, только для этого пользователя.

Права администратора не нужны. Выключить — снять галочку в меню или удалить запись
cloDICK в «Диспетчере задач → Автозагрузка».
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "cloDICK"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    """Чем запускать: оконный clodick-gui.exe рядом с интерпретатором, без консоли."""
    scripts = Path(sys.executable).parent
    gui = scripts / "clodick-gui.exe"
    if gui.is_file():
        return f'"{gui}"'
    pythonw = scripts / "pythonw.exe"
    runner = pythonw if pythonw.is_file() else Path(sys.executable)
    return f'"{runner}" -c "from clodick.app import gui_main; gui_main()"'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if not supported():
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, VALUE_NAME)
