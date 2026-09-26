"""Галерея тем: для каждой темы — домик, енот с репликой и чек-лист.

    uv run python tools/theme_gallery.py themes.png

Рисуется теми же окнами, что и в приложении, данные — во временной папке.
"""

from __future__ import annotations

import dataclasses
import os
import random
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CLODICK_HOME"] = tempfile.mkdtemp(prefix="clodick-gallery-")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from clodick import paths
from clodick.config import load_config
from clodick.core.tracker import Tracker
from clodick.desktop.brain import Mode
from clodick.desktop.controller import RACCOON_HOME_OFFSET, DesktopApp
from clodick.desktop.themes import THEMES
from clodick.desktop.widgets import make_font
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.storage.state import StateStore

TILE_W, TILE_H = 600, 330
WALLPAPER = {
    "classic": "#3a6ea5",
    "claude": "#e6e1d4",
    "claude_orange": "#ece8de",
    "claude_night": "#1b1a19",
}


def render_tile(app, config, conn, theme_key: str) -> QImage:
    cfg = dataclasses.replace(
        config, desktop=dataclasses.replace(config.desktop, theme=theme_key, walks=False)
    )
    tracker = Tracker(cfg, CompletionRepository(conn))
    desktop = DesktopApp(
        app, cfg, tracker, StateStore(conn), ram_reader=lambda: 63, rng=random.Random(1)
    )
    desktop.start()
    desktop.say("Эй! Ещё не сделано: спорт, учёба.")
    desktop.brain.mode = Mode.WAVE
    desktop._apply_frame(restart=True)
    desktop.checklist.set_status(tracker.status(), 63)
    desktop.checklist.adjustSize()
    app.processEvents()

    theme = THEMES[theme_key]
    tile = QImage(TILE_W, TILE_H, QImage.Format.Format_ARGB32)
    tile.fill(QColor(WALLPAPER[theme_key]))
    p = QPainter(tile)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    label_color = QColor(theme.text if theme_key != "classic" else "#ffffff")
    if theme_key == "claude_night":
        label_color = QColor("#f0eee6")
    p.setPen(label_color)
    p.setFont(make_font(theme.title_font, 20, bold=True))
    p.drawText(QRect(20, 14, 400, 30), Qt.AlignmentFlag.AlignLeft, theme.title)
    p.setFont(make_font(theme.body_font, 12))
    p.setPen(QColor(theme.muted))
    p.drawText(QRect(20, 42, 400, 20), Qt.AlignmentFlag.AlignLeft, f'theme = "{theme_key}"')

    house = desktop.house.grab()
    raccoon = desktop.raccoon.grab()
    bubble = desktop.bubble.grab()
    checklist = desktop.checklist.grab()
    scale = desktop._scale

    hx = TILE_W - house.width() - 20
    hy = TILE_H - house.height() - 10
    p.drawPixmap(hx, hy, house)
    rx = hx + RACCOON_HOME_OFFSET[0] * scale
    ry = hy + RACCOON_HOME_OFFSET[1] * scale
    p.drawPixmap(rx, ry, raccoon)
    bx = min(rx + raccoon.width() // 2 - bubble.width() // 2, TILE_W - bubble.width() - 8)
    p.drawPixmap(bx, ry - bubble.height() + 2, bubble)
    p.drawPixmap(20, TILE_H - checklist.height() - 14, checklist)
    p.end()

    for window in (desktop.house, desktop.raccoon, desktop.bubble, desktop.checklist):
        window.close()
    return tile


def main(out: str) -> None:
    app = QApplication([])
    config = load_config(paths.config_path())
    conn = connect(paths.db_path())
    Tracker(config, CompletionRepository(conn)).mark_done("language")

    keys = list(THEMES)
    cols = 2
    rows = (len(keys) + cols - 1) // cols
    sheet = QImage(
        cols * TILE_W + (cols + 1) * 12,
        rows * TILE_H + (rows + 1) * 12,
        QImage.Format.Format_ARGB32,
    )
    sheet.fill(QColor("#ffffff"))
    painter = QPainter(sheet)
    for i, key in enumerate(keys):
        tile = render_tile(app, config, conn, key)
        painter.drawImage(12 + (i % cols) * (TILE_W + 12), 12 + (i // cols) * (TILE_H + 12), tile)
    painter.end()
    sheet.save(out)
    conn.close()
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "themes.png")
