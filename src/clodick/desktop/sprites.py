"""Превращает пиксель-арт в картинки Qt: домик из art.py и кадры персонажа из пакета.

Каждый пиксель арта рисуется квадратом целого числа физических пикселей,
поэтому пиксель-арт остаётся чётким при любом масштабе Windows.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage, QPixmap, QTransform

from clodick.characters import Character, CharacterError
from clodick.desktop.art import HOUSE, PALETTE

HOUSE_SIZE = (len(HOUSE[0]), len(HOUSE))


def art_to_image(rows, palette: dict[str, str | None] = PALETTE) -> QImage:
    image = QImage(len(rows[0]), len(rows), QImage.Format.Format_ARGB32)
    image.fill(0)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            color = palette[char]
            if color:
                image.setPixelColor(x, y, QColor(color))
    return image


class SpriteBook:
    """Готовые картинки персонажа и домика для заданного масштаба. Кэширует всё."""

    def __init__(
        self,
        scale: int,
        device_pixel_ratio: float = 1.0,
        *,
        character: Character,
        theme: str = "classic",
        house_palette: dict[str, str | None] = PALETTE,
    ) -> None:
        self.scale = scale
        self.character = character
        self._character_palette = character.palette_for(theme)
        self._house_palette = house_palette
        self._physical = max(1, round(scale * device_pixel_ratio))
        self._cache: dict[tuple, QPixmap] = {}
        self._sheets: dict[str, QImage] = {}

    @property
    def character_size(self) -> tuple[int, int]:
        return self.character.width, self.character.height

    def frame_count(self, mode: str) -> int:
        return self.character.animations[mode].frame_count

    def character_frame(self, mode: str, index: int, facing: int = 1) -> QPixmap:
        key = ("character", mode, index, facing)
        if key not in self._cache:
            image = self._frame_image(mode, index)
            if facing < 0:
                image = image.transformed(QTransform().scale(-1, 1))
            self._cache[key] = self._scaled(image)
        return self._cache[key]

    def house(self) -> QPixmap:
        key = ("house",)
        if key not in self._cache:
            self._cache[key] = self._scaled(art_to_image(HOUSE, self._house_palette))
        return self._cache[key]

    def icon_image(self, size: int = 64) -> QImage:
        """Верхняя половина первого кадра — голова персонажа — для иконки в трее.

        Голова занимает три четверти квадрата, вокруг прозрачные поля: иконка
        от края до края выглядит слишком крупной рядом с системными.
        """
        frame = self._frame_image("sit", 0)
        head = frame.copy(0, 0, frame.width(), max(1, frame.height() // 2))
        side = -(-max(head.width(), head.height()) * 4 // 3)
        square = QImage(side, side, QImage.Format.Format_ARGB32)
        square.fill(0)
        top = (side - head.height()) // 2
        left = (side - head.width()) // 2
        for y in range(head.height()):
            for x in range(head.width()):
                square.setPixelColor(x + left, y + top, head.pixelColor(x, y))
        return square.scaled(size, size)

    def _frame_image(self, mode: str, index: int) -> QImage:
        animation = self.character.animations[mode]
        if animation.sheet is None:
            return art_to_image(animation.frames[index], self._character_palette)
        sheet_key = str(animation.sheet)
        if sheet_key not in self._sheets:
            sheet = QImage(sheet_key)
            if sheet.isNull():
                raise CharacterError(f"не читается картинка {animation.sheet}")
            sheet = sheet.convertToFormat(QImage.Format.Format_ARGB32)
            need_w = self.character.width * animation.count
            if sheet.width() < need_w or sheet.height() < self.character.height:
                raise CharacterError(
                    f"{animation.sheet.name}: нужно минимум {need_w}×{self.character.height} "
                    f"пикселей, а там {sheet.width()}×{sheet.height()}"
                )
            self._sheets[sheet_key] = sheet
        w, h = self.character_size
        return self._sheets[sheet_key].copy(index * w, 0, w, h)

    def _scaled(self, image: QImage) -> QPixmap:
        big = image.scaled(image.width() * self._physical, image.height() * self._physical)
        pixmap = QPixmap.fromImage(big)
        pixmap.setDevicePixelRatio(self._physical / self.scale)
        return pixmap
