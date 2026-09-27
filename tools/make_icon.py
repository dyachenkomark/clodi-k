"""Иконка приложения из головы персонажа по умолчанию.

uv run python tools/make_icon.py build/cloDICK.ico
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from clodick.characters import DEFAULT_CHARACTER, builtin_dir, load_character
from clodick.desktop.sprites import SpriteBook
from clodick.desktop.themes import DEFAULT_THEME


def main(out: str) -> None:
    QApplication([])
    book = SpriteBook(
        1, character=load_character(builtin_dir() / DEFAULT_CHARACTER), theme=DEFAULT_THEME
    )
    if not book.icon_image(256).save(out):
        raise SystemExit(f"не удалось сохранить {out}")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cloDICK.ico")
