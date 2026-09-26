"""Макет: яйцо в гнезде греется от выполненных дел и вылупляется в нового персонажа.

uv run python tools/egg_card.py egg.png
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from clodick.desktop.sprites import art_to_image
from clodick.desktop.themes import SERIF
from clodick.desktop.widgets import make_font

PALETTE = {
    ".": None,
    "K": "#2a2926",
    "W": "#faf9f5",
    "w": "#e3dfd3",
    "S": "#d97757",
    "N": "#b08850",
    "n": "#7d5f36",
    "E": "#f3c98b",
    "D": "#141413",
}

EGG = [
    "......KKKK......",
    ".....KWWWWK.....",
    "....KWWWWWWK....",
    "....KWWWWWWK....",
    "...KWWWWWWWwK...",
    "...KWWWWWWWwK...",
    "..KWWWWWWWWWwK..",
    "..KWWWWWWWWWwK..",
    "..KWWWWWWWWWwK..",
    "..KWWWWWWWWwwK..",
    "...KWWWWWWwwK...",
    "..NKKWWWWwwKKN..",
    ".NnNNKKKKKKNNnN.",
    "NnNnNnNnNnNnNnNn",
    ".nNnNnNnNnNnNnN.",
]


def with_rows(base, changes):
    rows = list(base)
    for index, row in changes.items():
        rows[index] = row
    return rows


SPOTS = {
    3: "....KWWSWWWK....",
    5: "...KWSWWWWWwK...",
    7: "..KWWWWWWSWwK...",
    8: "..KWWSWWWWWWwK..",
    9: "..KWWWWWWSWwwK..",
}
SPOTS[7] = "..KWWWWWWSWWwK.."
STAGES = [
    ("Новое яйцо", "0 / 21 тепла", EGG),
    ("Потеплело", "6 / 21", with_rows(EGG, SPOTS)),
    (
        "Трещинка",
        "13 / 21",
        with_rows(EGG, {**SPOTS, 5: "...KWSWKWWWwK...", 6: "..KWWWWKWKWWwK.."}),
    ),
    (
        "Шевелится",
        "19 / 21",
        with_rows(
            EGG,
            {
                **SPOTS,
                4: "...KWWKWWKWwK...",
                5: "...KWSKWKWKwK...",
                6: "..KWWWKWKWKWwK..",
                7: "..KWWWWKWSKWwK..",
            },
        ),
    ),
    (
        "Вылупился!",
        "кто там?",
        with_rows(
            EGG,
            {
                0: "................",
                1: "................",
                2: "................",
                3: "....K.K..K.K....",
                4: "...KWKDKKDKwK...",
                5: "...KDDDDDDDDK...",
                6: "..KWDEDDDDEDwK..",
                7: "..KWDDDDDDDDwK..",
                8: "..KWKWKWWKWKwK..",
            },
        ),
    ),
]
SCALE = 8


def main(out: str) -> None:
    QApplication([])
    col = 200
    w, h = col * len(STAGES) + 40, 330
    card = QImage(w, h, QImage.Format.Format_ARGB32)
    card.fill(QColor("#f0eee6"))
    p = QPainter(card)
    p.setPen(QColor("#141413"))
    p.setFont(make_font(SERIF, 26, bold=True))
    p.drawText(QRect(24, 16, w, 36), Qt.AlignmentFlag.AlignLeft, "Яйцо греется от выполненных дел")
    p.setFont(make_font(SERIF, 16))
    p.setPen(QColor("#6b6a64"))
    p.drawText(
        QRect(24, 54, w, 26),
        Qt.AlignmentFlag.AlignLeft,
        "Каждое сделанное направление — +1 тепла, закрытый день — ещё +1, «вместе» с другом — +1 обоим",
    )
    for i, (title, warmth, rows) in enumerate(STAGES):
        image = art_to_image(rows, PALETTE)
        pix = QPixmap.fromImage(image.scaled(image.width() * SCALE, image.height() * SCALE))
        x = 20 + i * col + (col - pix.width()) // 2
        p.drawPixmap(x, 100, pix)
        p.setPen(QColor("#141413"))
        p.setFont(make_font(SERIF, 18, bold=True))
        p.drawText(QRect(20 + i * col, 232, col, 28), Qt.AlignmentFlag.AlignCenter, title)
        p.setPen(QColor("#b85c3e"))
        p.setFont(make_font(SERIF, 15))
        p.drawText(QRect(20 + i * col, 262, col, 24), Qt.AlignmentFlag.AlignCenter, warmth)
    p.end()
    card.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "egg.png")
