"""Окна: персонаж, пузырь с текстом, чек-лист дня."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from clodick.core.models import DayStatus
from clodick.desktop.themes import THEMES, Theme


def font_families(css: str) -> list[str]:
    """'Georgia, "DejaVu Serif", serif' → ['Georgia', 'DejaVu Serif', 'serif']."""
    return [name.strip().strip("'\"") for name in css.split(",") if name.strip()]


def make_font(css: str, pixel_size: int, *, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(font_families(css))
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    return font


OVERLAY_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
)


# Пиксельный шрифт 3×5 для надписи на пузе: цифры и знак процента.
PIXEL_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "%": ("101", "001", "010", "100", "101"),
}

# Сердечко над головой, когда персонажа гладят курсором.
HEART = (".X.X.", "XXXXX", ".XXX.", "..X..")
HEART_COLOR = "#e0525f"


def pixel_text_width(text: str, pixel: int) -> int:
    return (4 * len(text) - 1) * pixel


class PetWindow(QWidget):
    """Прозрачное окно персонажа поверх всех окон.

    Клик — сигнал clicked, перетаскивание двигает окно и шлёт drag_moved.
    Поверх кадра рисует надпись на пузе и сердечко.
    """

    clicked = Signal()
    context_requested = Signal(QPoint)
    drag_moved = Signal()
    drag_finished = Signal()

    def __init__(self, scale: int = 4) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._scale = scale
        self._pixmap: QPixmap | None = None
        self._belly_text: str | None = None
        self._belly_rect = QRect()
        self._belly_color = QColor("#26262e")
        self.heart_visible = False
        self._heart_timer = QTimer(self, singleShot=True, timeout=self._hide_heart)
        self._press: QPoint | None = None
        self._grab_offset = QPoint()
        self._dragging = False

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.setFixedSize(pixmap.deviceIndependentSize().toSize())
        self.update()

    @property
    def pressed(self) -> bool:
        """Кнопка мыши зажата на персонаже: его тащат или вот-вот кликнут."""
        return self._press is not None

    @property
    def belly_text(self) -> str | None:
        return self._belly_text

    def set_belly(
        self, text: str | None, rect: QRect | None = None, color: str = "#26262e"
    ) -> None:
        """Надпись на пузе в прямоугольнике rect (логические пиксели окна). None — убрать."""
        rect = rect or QRect()
        if (text, rect, QColor(color)) == (self._belly_text, self._belly_rect, self._belly_color):
            return
        self._belly_text, self._belly_rect, self._belly_color = text, rect, QColor(color)
        self.update()

    def show_heart(self, seconds: float) -> None:
        self.heart_visible = True
        self._heart_timer.start(int(seconds * 1000))
        self.update()

    def _hide_heart(self) -> None:
        self.heart_visible = False
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)
        if self._belly_text:
            self._paint_belly(painter)
        if self.heart_visible:
            left = self.width() - len(HEART[0]) * self._scale
            self._paint_pixels(painter, HEART, left, 0, self._scale, QColor(HEART_COLOR))

    def _paint_belly(self, painter: QPainter) -> None:
        text, rect = self._belly_text, self._belly_rect
        # Самый крупный пиксель шрифта, при котором надпись влезает в пузо.
        pixel = self._scale
        while pixel > 1 and (
            pixel_text_width(text, pixel) > rect.width() or 5 * pixel > rect.height()
        ):
            pixel -= 1
        x = rect.x() + (rect.width() - pixel_text_width(text, pixel)) // 2
        y = rect.y() + (rect.height() - 5 * pixel) // 2
        for char in text:
            glyph = PIXEL_FONT.get(char)
            if glyph:
                self._paint_pixels(painter, glyph, x, y, pixel, self._belly_color)
            x += 4 * pixel

    @staticmethod
    def _paint_pixels(painter, rows, left: int, top: int, pixel: int, color: QColor) -> None:
        for dy, row in enumerate(rows):
            for dx, cell in enumerate(row):
                if cell not in ".0":
                    painter.fillRect(left + dx * pixel, top + dy * pixel, pixel, pixel, color)

    def mousePressEvent(self, event) -> None:
        pos = event.globalPosition().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = pos
            self._grab_offset = pos - self.pos()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(pos)

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        pos = event.globalPosition().toPoint()
        if not self._dragging and (pos - self._press).manhattanLength() > 4:
            self._dragging = True
        if self._dragging:
            self.move(pos - self._grab_offset)
            self.drag_moved.emit()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.drag_finished.emit()
        else:
            self.clicked.emit()
        self._press = None
        self._dragging = False


class BubbleWindow(QWidget):
    """Пузырь с репликой персонажа. Хвостик указывает вниз, на него."""

    clicked = Signal()

    MAX_WIDTH = 240
    PADDING = 10
    TAIL = 8

    def __init__(self, theme: Theme = THEMES["classic"]) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._theme = theme
        self._text = ""
        self._font = make_font(theme.body_font, 14)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    @property
    def text(self) -> str:
        return self._text

    def say(self, text: str, seconds: float = 12.0) -> None:
        self._text = text
        metrics = QFontMetrics(self._font)
        inner = metrics.boundingRect(
            QRect(0, 0, self.MAX_WIDTH - 2 * self.PADDING, 1000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        self.setFixedSize(
            inner.width() + 2 * self.PADDING + 2,
            inner.height() + 2 * self.PADDING + self.TAIL + 2,
        )
        self.update()
        self.show()
        self.raise_()
        self._hide_timer.start(int(seconds * 1000))

    def place_above(self, anchor: QRect, screen_rect: QRect) -> None:
        """Ставит пузырь над anchor (окном персонажа), не вылезая за экран."""
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() + 2
        x = max(screen_rect.left(), min(x, screen_rect.right() - self.width()))
        y = max(screen_rect.top(), y)
        self.move(x, y)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(1, 1, self.width() - 2, self.height() - self.TAIL - 2)
        path = QPainterPath()
        radius = min(self._theme.radius, 12)
        path.addRoundedRect(body, radius, radius)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - self.TAIL, body.bottom() - 1)
        tail.lineTo(cx, body.bottom() + self.TAIL)
        tail.lineTo(cx + self.TAIL, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        painter.setPen(QPen(QColor(self._theme.bubble_border), 2))
        painter.setBrush(QColor(self._theme.bubble_bg))
        painter.drawPath(path)
        painter.setFont(self._font)
        painter.setPen(QColor(self._theme.bubble_text))
        text_rect = body.adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, self._text)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            self.clicked.emit()


def checklist_style(theme: Theme) -> str:
    t = theme
    return f"""
#panel {{
    background: {t.panel_bg}; border: 2px solid {t.panel_border};
    border-radius: {t.radius}px;
}}
QLabel {{ color: {t.text}; font-size: 13px; font-family: {t.body_font}; }}
QLabel#title {{ font-weight: 600; font-size: 16px; font-family: {t.title_font}; }}
QLabel#progress {{
    color: {t.progress}; font-weight: 700; font-size: 15px; font-family: {t.title_font};
}}
QLabel#footer {{ color: {t.muted}; font-size: 11px; }}
QCheckBox {{
    color: {t.text}; font-size: 14px; spacing: 9px; padding: 3px 0;
    font-family: {t.body_font};
}}
QCheckBox:checked {{ color: {t.muted}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 2px solid {t.muted}; border-radius: 4px;
    background: {t.box_bg};
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QCheckBox::indicator:hover {{ border-color: {t.text}; }}
QCheckBox#daily {{ color: {t.muted}; font-size: 12px; spacing: 6px; }}
QCheckBox#daily::indicator {{ width: 10px; height: 10px; border-radius: 3px; }}
QLineEdit {{
    color: {t.text}; background: {t.box_bg}; font-size: 13px; font-family: {t.body_font};
    border: 1px solid {t.muted}; border-radius: 6px; padding: 3px 6px;
}}
QLineEdit:focus {{ border-color: {t.accent}; }}
QToolButton#remove {{
    color: {t.muted}; background: transparent; border: none; font-size: 20px;
    font-family: {t.body_font}; min-width: 18px; padding: 0;
}}
QToolButton#remove:hover {{ color: {t.text}; }}
"""


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ChecklistPopup(QWidget):
    """Чек-лист дня. Закрывается кликом мимо.

    Внизу строка для своей задачи: Enter добавляет её, галочка daily — каждый день.
    У своих задач справа крестик, он удаляет задачу.
    """

    toggled = Signal(str, bool)
    task_added = Signal(str, bool)
    task_removed = Signal(str)

    def __init__(self, theme: Theme = THEMES["classic"]) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(checklist_style(theme))
        panel = QFrame(self)
        panel.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self._title = QLabel(objectName="title")
        self._progress = QLabel(objectName="progress")
        header = QHBoxLayout()
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(self._progress)

        self._items = QVBoxLayout()
        self._items.setSpacing(2)

        self.new_task = QLineEdit(placeholderText="Add a task…")
        self.new_task.returnPressed.connect(self._submit)
        self.new_task_daily = QCheckBox("daily", objectName="daily")
        self.new_task_daily.setToolTip("Repeat every day")
        adder = QHBoxLayout()
        adder.setSpacing(8)
        adder.addWidget(self.new_task, 1)
        adder.addWidget(self.new_task_daily)

        self._footer = QLabel(objectName="footer")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addLayout(self._items)
        layout.addLayout(adder)
        layout.addWidget(self._footer)
        self._boxes: dict[str, QCheckBox] = {}
        self._rows: list[QWidget] = []
        self.remove_buttons: dict[str, QToolButton] = {}
        self.setMinimumWidth(240)

    @property
    def boxes(self) -> dict[str, QCheckBox]:
        return self._boxes

    def set_status(self, status: DayStatus, ram: int | None) -> None:
        self._title.setText(f"Today, {MONTHS[status.day.month - 1]} {status.day.day}")
        self._progress.setText(f"{status.done_count}/{status.total}")
        keys = [item.category.key for item in status.items]
        if list(self._boxes) != keys:
            self._rebuild(status)
        for item in status.items:
            box = self._boxes[item.category.key]
            box.blockSignals(True)
            box.setChecked(item.done)
            box.blockSignals(False)
        self._footer.setText("" if ram is None else f"RAM: {ram}%")
        self.adjustSize()

    def open_near(self, anchor: QRect, screen_rect: QRect) -> None:
        """Открывает над anchor, прижимая к краям экрана."""
        self.adjustSize()
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 6
        if y < screen_rect.top():
            y = anchor.bottom() + 6
        x = max(screen_rect.left(), min(x, screen_rect.right() - self.width()))
        self.move(x, y)
        self.show()
        self.activateWindow()

    def _submit(self) -> None:
        title = self.new_task.text().strip()
        if not title:
            return
        self.new_task.clear()
        self.task_added.emit(title, self.new_task_daily.isChecked())

    def _rebuild(self, status: DayStatus) -> None:
        for row in self._rows:
            self._items.removeWidget(row)
            row.deleteLater()
        self._rows = []
        self._boxes = {}
        self.remove_buttons = {}
        for item in status.items:
            key = item.category.key
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            box = QCheckBox(item.category.title)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            box.toggled.connect(lambda checked, key=key: self.toggled.emit(key, checked))
            line.addWidget(box, 1)
            if item.category.custom:
                remove = QToolButton(objectName="remove", text="×")
                remove.setToolTip("Delete task")
                remove.setCursor(Qt.CursorShape.PointingHandCursor)
                remove.clicked.connect(lambda _=False, key=key: self.task_removed.emit(key))
                line.addWidget(remove)
                self.remove_buttons[key] = remove
            self._items.addWidget(row)
            self._rows.append(row)
            self._boxes[key] = box
