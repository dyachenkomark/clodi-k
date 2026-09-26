"""Окна: домик, енот, пузырь с текстом, чек-лист дня."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from clodick.core.models import DayStatus

OVERLAY_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
)

# Где на стене домика висит табличка с RAM, в пикселях арта: x, y, ширина, высота.
RAM_SIGN = (5, 14, 19, 4)


class SpriteWindow(QWidget):
    """Прозрачное окно поверх всех окон, рисует одну картинку."""

    clicked = Signal()
    context_requested = Signal(QPoint)
    drag_moved = Signal()
    drag_finished = Signal()

    def __init__(self, *, draggable: bool) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._draggable = draggable
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
        self.paint_overlay(painter)

    def paint_overlay(self, painter: QPainter) -> None:
        pass

    def mousePressEvent(self, event) -> None:
        pos = event.globalPosition().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = pos
            self._grab_offset = pos - self.pos()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(pos)

    def mouseMoveEvent(self, event) -> None:
        if self._press is None or not self._draggable:
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


class HouseWindow(SpriteWindow):
    """Домик с табличкой, на которой написана загрузка RAM."""

    def __init__(self, pixmap: QPixmap, scale: int) -> None:
        super().__init__(draggable=True)
        self._scale = scale
        self._ram: int | None = None
        self.set_pixmap(pixmap)

    def set_ram(self, percent: int) -> None:
        if percent != self._ram:
            self._ram = percent
            self.update()

    def paint_overlay(self, painter: QPainter) -> None:
        if self._ram is None:
            return
        x, y, w, h = (v * self._scale for v in RAM_SIGN)
        rect = QRect(x, y, w, h)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#26262e"), max(1, self._scale // 2)))
        painter.setBrush(QColor("#3b2a1f"))
        painter.drawRoundedRect(rect, self._scale, self._scale)
        text = f"RAM {self._ram}%"
        font = QFont()
        font.setBold(True)
        size = max(7, int(h * 0.7))
        font.setPixelSize(size)
        while size > 7 and QFontMetrics(font).horizontalAdvance(text) > w - 2 * self._scale:
            size -= 1
            font.setPixelSize(size)
        painter.setFont(font)
        painter.setPen(QColor("#f2d16b"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class RaccoonWindow(SpriteWindow):
    def __init__(self) -> None:
        super().__init__(draggable=False)


class BubbleWindow(QWidget):
    """Пузырь с репликой енота. Хвостик указывает вниз, на енота."""

    clicked = Signal()

    MAX_WIDTH = 240
    PADDING = 10
    TAIL = 8

    def __init__(self) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = ""
        self._font = QFont()
        self._font.setPixelSize(13)
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
        """Ставит пузырь над anchor (окном енота), не вылезая за экран."""
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
        path.addRoundedRect(body, 8, 8)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - self.TAIL, body.bottom() - 1)
        tail.lineTo(cx, body.bottom() + self.TAIL)
        tail.lineTo(cx + self.TAIL, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        painter.setPen(QPen(QColor("#26262e"), 2))
        painter.setBrush(QColor("#fbfaf6"))
        painter.drawPath(path)
        painter.setFont(self._font)
        painter.setPen(QColor("#26262e"))
        text_rect = body.adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, self._text)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            self.clicked.emit()


CHECKLIST_STYLE = """
#panel { background: #2b2d35; border: 2px solid #16161b; border-radius: 10px; }
QLabel { color: #ecebef; font-size: 13px; }
QLabel#title { font-weight: 600; font-size: 14px; }
QLabel#progress { color: #f2d16b; font-weight: 700; font-size: 14px; }
QLabel#footer { color: #8b909b; font-size: 11px; }
QCheckBox { color: #ecebef; font-size: 14px; spacing: 9px; padding: 3px 0; }
QCheckBox:checked { color: #8b909b; }
QCheckBox::indicator {
    width: 14px; height: 14px; border: 2px solid #8b909b; border-radius: 4px;
    background: #1f2026;
}
QCheckBox::indicator:checked { background: #6fae4a; border-color: #6fae4a; }
QCheckBox::indicator:hover { border-color: #ecebef; }
"""


class ChecklistPopup(QWidget):
    """Чек-лист дня. Закрывается кликом мимо."""

    toggled = Signal(str, bool)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(CHECKLIST_STYLE)
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
