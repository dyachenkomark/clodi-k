"""Превращает текстовые карты из art.py в картинки Qt.

Каждый пиксель арта рисуется квадратом целого числа физических пикселей,
поэтому пиксель-арт остаётся чётким при любом масштабе Windows.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage, QPixmap, QTransform

from clodick.desktop.art import HOUSE, PALETTE, RACCOON

RACCOON_SIZE = (len(RACCOON["sit"][0][0]), len(RACCOON["sit"][0]))
HOUSE_SIZE = (len(HOUSE[0]), len(HOUSE))


def art_to_image(rows: list[str], palette: dict[str, str | None] = PALETTE) -> QImage:
    image = QImage(len(rows[0]), len(rows), QImage.Format.Format_ARGB32)
    image.fill(0)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            color = palette[char]
            if color:
                image.setPixelColor(x, y, QColor(color))
    return image


class SpriteBook:
    """Готовые картинки енота и домика для заданного масштаба. Кэширует всё."""

    def __init__(
        self,
        scale: int,
        device_pixel_ratio: float = 1.0,
        palette: dict[str, str | None] = PALETTE,
    ) -> None:
        self.scale = scale
        self._palette = palette
        self._physical = max(1, round(scale * device_pixel_ratio))
        self._cache: dict[tuple, QPixmap] = {}

    def frame_count(self, mode: str) -> int:
        return len(RACCOON[mode])

    def raccoon(self, mode: str, index: int, facing: int = 1) -> QPixmap:
        key = ("raccoon", mode, index, facing)
        if key not in self._cache:
            image = art_to_image(RACCOON[mode][index], self._palette)
            if facing < 0:
                image = image.transformed(QTransform().scale(-1, 1))
            self._cache[key] = self._scaled(image)
        return self._cache[key]

    def house(self) -> QPixmap:
        key = ("house",)
        if key not in self._cache:
            self._cache[key] = self._scaled(art_to_image(HOUSE, self._palette))
        return self._cache[key]

    def icon_image(self, size: int = 64) -> QImage:
        """Голова енота для иконки в трее."""
        head = art_to_image(RACCOON["sit"][0][:10], self._palette).copy(1, 0, 18, 10)
        side = max(head.width(), head.height())
        square = QImage(side, side, QImage.Format.Format_ARGB32)
        square.fill(0)
        for y in range(head.height()):
            for x in range(head.width()):
                square.setPixelColor(x, y + (side - head.height()) // 2, head.pixelColor(x, y))
        return square.scaled(size, size)

    def _scaled(self, image: QImage) -> QPixmap:
        big = image.scaled(image.width() * self._physical, image.height() * self._physical)
        pixmap = QPixmap.fromImage(big)
        pixmap.setDevicePixelRatio(self._physical / self.scale)
        return pixmap
