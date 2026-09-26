"""Макет вечернего поста бота в группе: улица компании с домиками друзей.

    uv run python tools/street_card.py street.png

Окно горит, если сделано хоть что-то. Табличка показывает счёт дня.
Кто закрыл всё — машет, кто ещё ничего — спит. Данные выдуманы для примера.
"""

from __future__ import annotations

import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication

from clodick.characters import builtin_dir, load_character
from clodick.desktop.art import GROUND_ROW, YARD_X
from clodick.desktop.sprites import SpriteBook
from clodick.desktop.themes import SERIF, THEMES
from clodick.desktop.widgets import RAM_SIGN, make_font

FRIENDS = [
    ("Марк", 3, 12),
    ("Маша", 2, 5),
    ("Петя", 0, 0),
    ("Лена", 3, 21),
]
TOTAL = 3
SCALE = 4
W, H = 1120, 520
WINDOW_OFF = "#2a2926"


def main(out: str) -> None:
    QApplication([])
    theme = THEMES["claude_night"]
    raccoon = load_character(builtin_dir() / "raccoon")

    card = QImage(W, H, QImage.Format.Format_ARGB32)
    p = QPainter(card)
    sky = QLinearGradient(0, 0, 0, H)
    sky.setColorAt(0, QColor("#15141a"))
    sky.setColorAt(1, QColor("#2b2733"))
    p.fillRect(0, 0, W, H, sky)
    rng = random.Random(4)
    for _ in range(80):
        x, y = rng.randrange(W), rng.randrange(0, 260)
        if y < 110 and x < 760:
            continue  # не мешать заголовку
        p.fillRect(x, y, 2, 2, QColor("#e9e4d6"))

    lit = sum(1 for _, done, _ in FRIENDS if done)
    p.setPen(QColor("#f0eee6"))
    p.setFont(make_font(SERIF, 30, bold=True))
    p.drawText(QRect(32, 22, W, 40), Qt.AlignmentFlag.AlignLeft, "Улица компании · 26 сентября")
    p.setFont(make_font(SERIF, 18))
    p.setPen(QColor("#b0aea5"))
    p.drawText(
        QRect(32, 64, W, 30),
        Qt.AlignmentFlag.AlignLeft,
        f"Горит у {lit} из {len(FRIENDS)}. Петя, ждём тебя до полуночи!",
    )

    ground = H - 70
    p.fillRect(0, ground, W, 70, QColor("#343b27"))
    slot = W // len(FRIENDS)
    for i, (name, done, streak) in enumerate(FRIENDS):
        palette = dict(theme.palette)
        if done == 0:
            palette["Y"] = WINDOW_OFF
        book = SpriteBook(SCALE, character=raccoon, theme=theme.key, house_palette=palette)
        house = book.house()
        x = i * slot + (slot - house.width()) // 2
        y = ground - (GROUND_ROW + 1) * SCALE
        p.drawPixmap(x, y, house)

        mode = "wave" if done == TOTAL else "sleep" if done == 0 else "sit"
        pet = book.character_frame(mode, 0)
        p.drawPixmap(
            x + YARD_X * SCALE,
            y + (GROUND_ROW + 1 - raccoon.height) * SCALE,
            pet,
        )

        sx, sy, sw, sh = (v * SCALE for v in RAM_SIGN)
        sign = QRect(x + sx, y + sy, sw, sh)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(theme.sign_border), 1))
        p.setBrush(QColor(theme.sign_bg))
        p.drawRoundedRect(sign, 3, 3)
        p.setPen(QColor(theme.sign_text if done else "#8f8d85"))
        p.setFont(make_font("'DejaVu Sans'", 12, bold=True))
        p.drawText(sign, Qt.AlignmentFlag.AlignCenter, f"{done}/{TOTAL}")

        column = QRect(i * slot, ground + 8, slot, 28)
        p.setPen(QColor("#f0eee6"))
        p.setFont(make_font(SERIF, 20, bold=True))
        p.drawText(column, Qt.AlignmentFlag.AlignCenter, name)
        p.setPen(QColor("#f3c98b" if streak else "#8f8d85"))
        p.setFont(make_font(SERIF, 15))
        streak_text = f"{streak} дн. подряд" if streak else "начнёт завтра"
        p.drawText(column.translated(0, 28), Qt.AlignmentFlag.AlignCenter, streak_text)
    p.end()
    card.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "street.png")
