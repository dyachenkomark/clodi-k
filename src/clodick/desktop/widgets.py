"""Окна: персонаж, пузырь с текстом, чек-лист дня."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

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


class PetWindow(QWidget):
    """Прозрачное окно персонажа поверх всех окон.

    Клик — сигнал clicked, перетаскивание двигает окно и шлёт drag_moved.
    """

    clicked = Signal()
    context_requested = Signal(QPoint)
    drag_moved = Signal()
    drag_finished = Signal()

    def __init__(self) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._pixmap: QPixmap | None = None
        self._press: QPoint | None = None
        self._grab_offset = QPoint()
        self._dragging = False

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.setFixedSize(pixmap.deviceIndependentSize().toSize())
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)

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
"""


class ChecklistPopup(QWidget):
    """Чек-лист дня. Закрывается кликом мимо."""

    toggled = Signal(str, bool)

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
        self._footer = QLabel(objectName="footer")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addLayout(self._items)
        layout.addWidget(self._footer)
        self._boxes: dict[str, QCheckBox] = {}
        self.setMinimumWidth(220)

    @property
    def boxes(self) -> dict[str, QCheckBox]:
        return self._boxes

    def set_status(self, status: DayStatus, ram: int | None) -> None:
        self._title.setText(f"Сегодня, {status.day:%d.%m}")
        self._progress.setText(f"{status.done_count}/{status.total}")
        keys = [item.category.key for item in status.items]
        if list(self._boxes) != keys:
            self._rebuild(status)
        for item in status.items:
            box = self._boxes[item.category.key]
            box.blockSignals(True)
            box.setChecked(item.done)
            box.blockSignals(False)
        self._footer.setText("" if ram is None else f"Оперативная память: {ram}%")
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

    def _rebuild(self, status: DayStatus) -> None:
        for box in self._boxes.values():
            self._items.removeWidget(box)
            box.deleteLater()
        self._boxes = {}
        for item in status.items:
            box = QCheckBox(item.category.title)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            key = item.category.key
            box.toggled.connect(lambda checked, key=key: self.toggled.emit(key, checked))
            self._items.addWidget(box)
            self._boxes[key] = box
