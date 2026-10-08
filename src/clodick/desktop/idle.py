"""Сколько секунд человек не трогал мышь и клавиатуру. Нужно, чтобы понять, вставал ли он."""

from __future__ import annotations

import sys


def idle_seconds() -> float:
    """Время без ввода. Где узнать нельзя, 0: считаем, что человек за компьютером."""
    if sys.platform != "win32":
        return 0.0
    import ctypes
    from ctypes import wintypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

    info = LastInputInfo(ctypes.sizeof(LastInputInfo), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    # Оба счётчика в миллисекундах с загрузки, 32 бита: разность по модулю переживает переполнение.
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000
