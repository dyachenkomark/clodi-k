"""Загрузка оперативной памяти."""

from __future__ import annotations

import psutil


def ram_percent() -> int:
    """Процент занятой оперативной памяти, округлённый до целого."""
    return round(psutil.virtual_memory().percent)
