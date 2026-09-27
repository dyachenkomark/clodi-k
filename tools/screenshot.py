"""Скриншот сцены без настоящего рабочего стола: енот, пузырь и чек-лист.

    QT_QPA_PLATFORM=offscreen uv run python tools/screenshot.py scene.png

Данные берутся из временной папки, настоящие отметки не трогаются.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CLODICK_HOME"] = tempfile.mkdtemp(prefix="clodick-shot-")

from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication

from clodick import paths
from clodick.config import load_config
from clodick.core.tracker import Tracker
from clodick.desktop.controller import DesktopApp
from clodick.desktop.sprites import SpriteBook
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.storage.state import StateStore

WALLPAPER = {
    "classic": "#3a6ea5",
    "claude": "#e6e1d4",
    "claude_orange": "#ece8de",
    "claude_night": "#1b1a19",
}


def main(out: str) -> None:
    app = QApplication([])
    config = load_config(paths.config_path())
    conn = connect(paths.db_path())
    tracker = Tracker(config, CompletionRepository(conn))
    tracker.mark_done("language")
    desktop = DesktopApp(
        app, config, tracker, StateStore(conn), ram_reader=lambda: 63, rng=random.Random(1)
    )
    desktop.start()
    if "--checklist" in sys.argv:
        desktop.open_checklist()
    else:
        desktop.say("Hey! Still to do: Sport, Study.")
    app.processEvents()

    screen = QGuiApplication.primaryScreen().geometry()
    canvas = QImage(screen.size(), QImage.Format.Format_ARGB32)
    canvas.fill(QColor(WALLPAPER.get(desktop.theme.key, "#3a6ea5")))
    painter = QPainter(canvas)
    for window in (desktop.pet, desktop.bubble, desktop.checklist):
        if window.isVisible():
            painter.drawPixmap(window.pos(), window.grab())

    # Все кадры енота в ряд сверху — посмотреть анимации.
    book = SpriteBook(4, character=desktop.character, theme=desktop.theme.key)
    x = 16
    for mode in ("sit", "sleep", "wave", "walk"):
        for index in range(book.frame_count(mode)):
            for facing in (1, -1) if mode == "walk" else (1,):
                pixmap = book.character_frame(mode, index, facing)
                painter.drawPixmap(x, 16, pixmap)
                x += pixmap.width() + 12
    painter.end()
    canvas.save(out)
    conn.close()
    print(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "scene.png")
