"""Окна: персонаж, пузырь с текстом, чек-лист дня."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from clodick.core.models import DayStatus, Topic, in_topic
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

# Запас окна персонажа в пикселях арта: сверху — под прыжок, снизу — под тень.
TOP_PAD = 4
BOTTOM_PAD = 2
SHADOW_COLOR = QColor(0, 0, 0, 60)

# Сердечко над головой, когда персонажа гладят курсором.
HEART = (".X.X.", "XXXXX", ".XXX.", "..X..")
HEART_COLOR = "#e0525f"


def pixel_text_width(text: str, pixel: int) -> int:
    return (4 * len(text) - 1) * pixel


class PetWindow(QWidget):
    """Прозрачное окно персонажа поверх всех окон.

    Клик — сигнал clicked, двойной клик — double_clicked, перетаскивание двигает окно
    и шлёт drag_moved. Одиночный клик приходит с паузой: вдруг за ним будет второй.
    Экран для персонажа — пол: под лапами лежит тень, в прыжке он отрывается от неё.
    Поверх кадра рисует надпись на пузе и сердечко.
    Кадр сдвинут вниз на sprite_offset: над ним запас под прыжок.
    """

    clicked = Signal()
    double_clicked = Signal()
    context_requested = Signal(QPoint)
    drag_moved = Signal()
    drag_finished = Signal()

    # Пауза перед одиночным кликом, мс: не дольше системной для двойного клика.
    CLICK_DELAY_MS = 300

    def __init__(self, scale: int = 4) -> None:
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._scale = scale
        self._pixmap: QPixmap | None = None
        self._belly_text: str | None = None
        self._belly_rect = QRect()
        self._belly_color = QColor("#26262e")
        self._feet: tuple[int, int] | None = None
        self._lift = 0
        self.heart_visible = False
        self._heart_timer = QTimer(self, singleShot=True, timeout=self._hide_heart)
        self._click_timer = QTimer(self, singleShot=True, timeout=self.clicked.emit)
        self._double = False
        self._press: QPoint | None = None
        self._grab_offset = QPoint()
        self._dragging = False

    @property
    def sprite_offset(self) -> int:
        """На сколько логических пикселей кадр ниже верхнего края окна."""
        return TOP_PAD * self._scale

    def set_pixmap(self, pixmap: QPixmap, feet: tuple[int, int] | None = None) -> None:
        """Кадр и лапы для тени: левый край и ширина в пикселях арта."""
        self._pixmap = pixmap
        self._feet = feet
        size = pixmap.deviceIndependentSize().toSize()
        self.setFixedSize(size.width(), size.height() + (TOP_PAD + BOTTOM_PAD) * self._scale)
        self.update()

    def set_lift(self, lift: int) -> None:
        """Высота прыжка в пикселях арта. Тень остаётся на полу."""
        if lift != self._lift:
            self._lift = lift
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
        if self._pixmap is None:
            return
        self._paint_shadow(painter)
        top = self.sprite_offset - self._lift * self._scale
        painter.drawPixmap(0, top, self._pixmap)
        painter.translate(0, top)
        if self._belly_text:
            self._paint_belly(painter)
        if self.heart_visible:
            left = self.width() - len(HEART[0]) * self._scale
            self._paint_pixels(painter, HEART, left, 0, self._scale, QColor(HEART_COLOR))

    def _paint_shadow(self, painter: QPainter) -> None:
        """Пиксельный овал под лапами. Чем выше прыжок, тем он меньше."""
        if self._feet is None:
            return
        s = self._scale
        left, width = self._feet
        width = max(2, width + 2 - self._lift)
        center = left + (self._feet[1]) / 2
        ground = self.sprite_offset + self._pixmap.deviceIndependentSize().height()
        rows = 4
        for row in range(rows):
            dy = (row + 0.5 - rows / 2) / (rows / 2)
            half = round(width / 2 * (1 - dy * dy) ** 0.5)
            if half <= 0:
                continue
            x = round(center - half) * s
            y = int(ground + (row - rows / 2) * s)
            painter.fillRect(x, y, 2 * half * s, s, SHADOW_COLOR)

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
        # Системный порог: дрогнувшая при клике рука — ещё не перетаскивание.
        threshold = QApplication.startDragDistance()
        if not self._dragging and (pos - self._press).manhattanLength() > threshold:
            self._dragging = True
            self._click_timer.stop()
        if self._dragging:
            self.move(pos - self._grab_offset)
            self.drag_moved.emit()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.drag_finished.emit()
        elif self._double:
            self._double = False
        else:
            delay = min(self.CLICK_DELAY_MS, QApplication.doubleClickInterval())
            self._click_timer.start(delay)
        self._press = None
        self._dragging = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._click_timer.stop()
        self._double = True
        self._press = event.globalPosition().toPoint()
        self.double_clicked.emit()


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
QToolButton#focus {{
    color: {t.muted}; background: transparent; border: none; font-size: 12px; padding: 0 2px;
}}
QToolButton#focus:hover {{ color: {t.accent}; }}
QLabel#focusline {{ color: {t.accent}; font-weight: 600; font-size: 13px; }}
QToolButton#stop {{
    color: {t.muted}; background: transparent; border: 1px solid {t.muted};
    border-radius: 5px; font-size: 11px; padding: 1px 6px;
}}
QToolButton#stop:hover {{ color: {t.text}; border-color: {t.text}; }}
QToolButton#note {{
    color: {t.muted}; background: transparent; border: none; font-size: 13px; padding: 0 2px;
}}
QToolButton#note:hover {{ color: {t.accent}; }}
QLabel#notetext {{ color: {t.muted}; font-size: 12px; }}
QLabel#meta {{ color: {t.muted}; font-size: 11px; }}
QLabel#metalate {{ color: {t.accent}; font-size: 11px; font-weight: 600; }}
QLabel#section {{ color: {t.muted}; font-size: 11px; font-weight: 700; padding-top: 4px; }}
QToolButton#notedel {{
    color: {t.muted}; background: transparent; border: none; font-size: 14px; padding: 0;
}}
QToolButton#notedel:hover {{ color: {t.text}; }}
QToolButton#topicall, QToolButton#topicadd {{
    color: {t.muted}; background: transparent; border: 1px solid {t.muted};
    border-radius: 9px; padding: 1px 8px; font-size: 12px; font-family: {t.body_font};
}}
QToolButton#topicadd {{ border-style: dashed; padding: 1px 7px; }}
QToolButton#topicall:checked {{
    color: {t.panel_bg}; background: {t.text}; border-color: {t.text};
}}
QToolButton#topicall:hover, QToolButton#topicadd:hover {{
    color: {t.text}; border-color: {t.text};
}}
"""


def topic_chip_style(color: str, theme: Theme) -> str:
    """Вкладка темы в её цвете: контур, а выбранная — заливка."""
    return (
        f"QToolButton {{ color: {color}; background: transparent; border: 1px solid {color};"
        f" border-radius: 9px; padding: 1px 8px; font-size: 12px;"
        f" font-family: {theme.body_font}; }}"
        f"QToolButton:checked {{ color: {theme.panel_bg}; background: {color}; }}"
        f"QToolButton:hover {{ border-width: 2px; padding: 0px 7px; }}"
    )


def color_icon(color: str, size: int = 12) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def meta_text(category, day, show_project: bool = True) -> tuple[str, bool]:
    """Подпись задачи: проект, срок, время. Второе значение — просрочена ли."""
    parts = [category.project] if category.project and show_project else []
    late = False
    due = category.due
    if due is not None:
        delta = (due - day).days
        if delta < 0:
            late = True
            parts.append(f"overdue {-delta}d")
        elif delta == 0:
            parts.append("today")
        elif delta == 1:
            parts.append("tomorrow")
        else:
            parts.append(f"{WEEKDAYS[due.weekday()]} {due.day} {MONTHS[due.month - 1]}")
    if category.time:
        parts.append(category.time)
    return " · ".join(parts), late


class ChecklistPopup(QWidget):
    """Чек-лист дня. Закрывается кликом мимо.

    Внизу строка для своей задачи: Enter добавляет её, галочка daily — каждый день.
    У своих задач справа крестик, он удаляет задачу.
    Кнопка ✎ открывает поле заметки к пункту: результат, комментарий. Enter сохраняет.
    Сегодняшние заметки видны под пунктом, у каждой крестик.
    """

    toggled = Signal(str, bool)
    # Текст задачи, «каждый день», открытая тема (пусто — все).
    task_added = Signal(str, bool, str)
    task_removed = Signal(str)
    task_moved = Signal(str, str)  # ключ задачи, новая тема
    # Темы: выбрать вкладку (пусто — All), завести, переименовать, удалить, настроить.
    topic_selected = Signal(str)
    topic_added = Signal(str)
    topic_renamed = Signal(str, str)
    topic_removed = Signal(str)
    topic_daily = Signal(str, bool)
    topic_color = Signal(str, str)
    # Pomodoro: запустить фокус на пункте и остановить текущий.
    focus_requested = Signal(str)
    focus_stopped = Signal()
    # Заметки: добавить к пункту, удалить по id. resized — окно поменяло размер.
    note_added = Signal(str, str)
    note_deleted = Signal(int)
    resized = Signal()

    # Отступ заметок слева: под текстом пункта, а не под галочкой.
    NOTE_INDENT = 23
    NOTE_WIDTH = 250
    # Вкладки тем переносятся на новую строку, когда шире этого.
    TOPICS_WIDTH = 330

    def __init__(self, theme: Theme = THEMES["classic"]) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._theme = theme
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

        # Вкладки тем: All, темы, «+». Поле ниже — имя новой темы или новое имя.
        self._topic_rows = QVBoxLayout()
        self._topic_rows.setSpacing(4)
        self.topic_edit = QLineEdit(placeholderText="Topic name, then Enter")
        self.topic_edit.returnPressed.connect(self._submit_topic)
        self.topic_edit.hide()
        self._renaming: str | None = None
        self.topic_buttons: dict[str, QToolButton] = {}
        self._topics: list[Topic] = []
        self._topic = ""
        self._status: DayStatus | None = None
        self._ram: int | None = None
        self._focus_today = 0

        self._items = QVBoxLayout()
        self._items.setSpacing(2)

        self.new_task = QLineEdit(placeholderText="Add a task…  maga: report by fri 15:00")
        self.new_task.setToolTip(
            "project: title, then a deadline — by fri, tomorrow, 02.10, in 3 days — and a time"
        )
        self.new_task.returnPressed.connect(self._submit)
        self.new_task_daily = QCheckBox("daily", objectName="daily")
        self.new_task_daily.setToolTip("Repeat every day")
        adder = QHBoxLayout()
        adder.setSpacing(8)
        adder.addWidget(self.new_task, 1)
        adder.addWidget(self.new_task_daily)

        self.focus_line = QLabel(objectName="focusline")
        self.stop_button = QToolButton(objectName="stop", text="Stop")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.clicked.connect(self.focus_stopped)
        self._focus_row = QWidget()
        focus_layout = QHBoxLayout(self._focus_row)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        focus_layout.addWidget(self.focus_line, 1)
        focus_layout.addWidget(self.stop_button)
        self._focus_row.hide()

        self._footer = QLabel(objectName="footer")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addLayout(self._topic_rows)
        layout.addWidget(self.topic_edit)
        layout.addWidget(self._focus_row)
        layout.addLayout(self._items)
        layout.addLayout(adder)
        layout.addWidget(self._footer)
        self._boxes: dict[str, QCheckBox] = {}
        self._rows: list[QWidget] = []
        self.remove_buttons: dict[str, QToolButton] = {}
        self.focus_buttons: dict[str, QToolButton] = {}
        self.note_buttons: dict[str, QToolButton] = {}
        self.note_editors: dict[str, QLineEdit] = {}
        self.note_labels: dict[str, list[QLabel]] = {}
        self.note_delete_buttons: dict[int, QToolButton] = {}
        self._signature: list = []
        self.meta_labels: dict[str, QLabel] = {}
        self.section_label: QLabel | None = None
        self.setMinimumWidth(240)

    @property
    def boxes(self) -> dict[str, QCheckBox]:
        return self._boxes

    def set_focus(self, text: str | None) -> None:
        """Строка текущего фокуса или перерыва под заголовком. None — спрятать."""
        self.focus_line.setText(text or "")
        self._focus_row.setVisible(bool(text))
        self.adjustSize()

    # --- темы ---

    @property
    def topic(self) -> str:
        """Открытая вкладка: имя темы или пусто — все."""
        return self._topic

    def current_topic(self) -> Topic | None:
        return next((t for t in self._topics if t.name == self._topic), None)

    def set_topics(self, topics: list[Topic], current: str) -> None:
        """Вкладки тем. current — открытая; нет такой темы — открывается All."""
        self._topics = list(topics)
        self._topic = current if any(t.name == current for t in topics) else ""
        while self._topic_rows.count():
            row = self._topic_rows.takeAt(0).layout()
            while row.count():
                widget = row.takeAt(0).widget()
                if widget is not None:
                    widget.deleteLater()
            row.deleteLater()
        self.topic_buttons = {}
        chips = [self._chip("", "All")]
        chips += [self._chip(t.name, t.name, t.color) for t in self._topics]
        add = QToolButton(objectName="topicadd", text="+")
        add.setToolTip("New topic")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(lambda: self.edit_topic(None))
        self.add_topic_button = add
        chips.append(add)
        # Раскладка по строкам: вкладки переносятся, как слова.
        row, used = QHBoxLayout(), 0
        for chip in chips:
            width = chip.sizeHint().width() + 4
            if used and used + width > self.TOPICS_WIDTH:
                row.addStretch()
                self._topic_rows.addLayout(row)
                row, used = QHBoxLayout(), 0
            row.setSpacing(4)
            row.addWidget(chip)
            used += width
        row.addStretch()
        self._topic_rows.addLayout(row)
        self._update_adder()

    def _chip(self, name: str, text: str, color: str = "") -> QToolButton:
        chip = QToolButton(objectName="topicall" if not name else "topic", text=text)
        chip.setCheckable(True)
        chip.setChecked(name == self._topic)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        if name:
            chip.setStyleSheet(topic_chip_style(color or self._theme.accent, self._theme))
            chip.setToolTip("Right-click: rename, color, every day, delete")
            chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda pos, name=name, chip=chip: self.topic_menu(name).exec(chip.mapToGlobal(pos))
            )
        chip.clicked.connect(lambda _=False, name=name: self.select_topic(name))
        self.topic_buttons[name] = chip
        return chip

    def select_topic(self, name: str) -> None:
        self._topic = name
        for key, chip in self.topic_buttons.items():
            chip.setChecked(key == name)
        self._update_adder()
        self.topic_selected.emit(name)
        if self._status is not None:
            self.set_status(self._status, self._ram, self._focus_today)
            self.resized.emit()

    def topic_menu(self, name: str) -> QMenu:
        """Меню темы по правому клику."""
        topic = next(t for t in self._topics if t.name == name)
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.edit_topic(name))
        daily = menu.addAction("Every day")
        daily.setCheckable(True)
        daily.setChecked(topic.daily)
        daily.setToolTip("Tasks here repeat daily. Sport, Study and other habits show here")
        daily.toggled.connect(lambda on: self.topic_daily.emit(name, on))
        colors = menu.addMenu("Color")
        from clodick.core.tracker import TOPIC_COLORS

        for color in TOPIC_COLORS:
            action = colors.addAction(color_icon(color), "")
            action.triggered.connect(lambda _=False, c=color: self.topic_color.emit(name, c))
        menu.addSeparator()
        menu.addAction("Delete topic (tasks stay)", lambda: self.topic_removed.emit(name))
        return menu

    def edit_topic(self, name: str | None) -> None:
        """Поле имени темы: новая (None) или переименовать name."""
        self._renaming = name
        self.topic_edit.setText(name or "")
        self.topic_edit.setPlaceholderText(
            "New name, then Enter" if name else "New topic, e.g. Turkov, then Enter"
        )
        self.topic_edit.show()
        self.adjustSize()
        self.resized.emit()
        self.topic_edit.setFocus()
        self.topic_edit.selectAll()

    def _submit_topic(self) -> None:
        text = " ".join(self.topic_edit.text().split())
        renaming = self._renaming
        self.topic_edit.clear()
        self.topic_edit.hide()
        self._renaming = None
        if text and renaming is None:
            self.topic_added.emit(text)
        elif text and text != renaming:
            self.topic_renamed.emit(renaming, text)
        else:
            self.adjustSize()
            self.resized.emit()

    def task_menu(self, key: str) -> QMenu:
        """Меню задачи по правому клику: перенести в другую тему."""
        menu = QMenu(self)
        move = menu.addMenu("Move to")
        for topic in self._topics:
            action = move.addAction(color_icon(topic.color or self._theme.accent), topic.name)
            action.triggered.connect(
                lambda _=False, name=topic.name: self.task_moved.emit(key, name)
            )
        move.addSeparator()
        move.addAction("No topic", lambda: self.task_moved.emit(key, ""))
        return menu

    def _update_adder(self) -> None:
        topic = self.current_topic()
        if topic is None:
            self.new_task.setPlaceholderText("Add a task…  maga: report by fri 15:00")
        else:
            example = "stretch 10 min" if topic.daily else "report by fri 15:00"
            self.new_task.setPlaceholderText(f"Add to {topic.name}…  {example}")
        # В ежедневной теме всё и так каждый день: галочка не нужна.
        self.new_task_daily.setVisible(topic is None or not topic.daily)

    def _filtered(self, status: DayStatus) -> DayStatus:
        topic = self.current_topic()
        if topic is None:
            return status
        return DayStatus(
            day=status.day,
            items=tuple(i for i in status.items if in_topic(i.category, topic)),
            upcoming=tuple(i for i in status.upcoming if in_topic(i.category, topic)),
        )

    def set_status(self, status: DayStatus, ram: int | None, focus_today: int = 0) -> None:
        self._status, self._ram, self._focus_today = status, ram, focus_today
        status = self._filtered(status)
        self._title.setText(f"Today, {MONTHS[status.day.month - 1]} {status.day.day}")
        self._progress.setText(f"{status.done_count}/{status.total}")
        signature = [
            (
                i.category.key,
                i.category.title,
                i.category.project,
                meta_text(i.category, status.day),
                section,
                *(n.id for n in i.notes),
            )
            for section, items in enumerate((status.items, status.upcoming))
            for i in items
        ]
        signature.append(("topic", self._topic, *(t.color for t in self._topics)))
        if signature != self._signature:
            self._signature = signature
            self._rebuild(status)
        for item in (*status.items, *status.upcoming):
            box = self._boxes[item.category.key]
            box.blockSignals(True)
            box.setChecked(item.done)
            box.blockSignals(False)
        parts = [] if ram is None else [f"RAM: {ram}%"]
        if focus_today:
            parts.append(f"Focus today: {focus_today}")
        self._footer.setText(" · ".join(parts))
        self.adjustSize()

    def open_near(self, anchor: QRect, screen_rect: QRect) -> None:
        """Открывает над anchor, прижимая к краям экрана.

        Размер считается после show(): до показа Qt не знает окончательную раскладку,
        и окно потом вырастает вниз, прямо на персонажа.
        """
        self.show()
        self.layout().activate()
        self.adjustSize()
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 6
        if y < screen_rect.top():
            y = anchor.bottom() + 6
        x = max(screen_rect.left(), min(x, screen_rect.right() - self.width()))
        self.move(x, y)
        self.activateWindow()

    def ask_note(self, key: str) -> None:
        """Открыть поле заметки у пункта: например, сразу после галочки."""
        editor = self.note_editors.get(key)
        if editor is None:
            return
        editor.show()
        self.adjustSize()
        self.resized.emit()
        editor.setFocus()

    def _save_note(self, key: str) -> None:
        editor = self.note_editors[key]
        text = editor.text().strip()
        editor.clear()
        editor.hide()
        if text:
            self.note_added.emit(key, text)
        else:
            self.adjustSize()
            self.resized.emit()

    def _submit(self) -> None:
        title = self.new_task.text().strip()
        if not title:
            return
        self.new_task.clear()
        self.task_added.emit(title, self.new_task_daily.isChecked(), self._topic)

    def _rebuild(self, status: DayStatus) -> None:
        for row in self._rows:
            self._items.removeWidget(row)
            row.deleteLater()
        self._rows = []
        self._boxes = {}
        self.remove_buttons = {}
        self.focus_buttons = {}
        self.note_buttons = {}
        self.note_editors = {}
        self.note_labels = {}
        self.note_delete_buttons = {}
        self.meta_labels = {}
        self.section_label = None
        for item in status.items:
            self._add_row(item, status.day)
        if not status.items and not status.upcoming:
            empty = QLabel("Nothing here yet. Add a task below.", objectName="meta")
            self._items.addWidget(empty)
            self._rows.append(empty)
        if status.upcoming:
            self.section_label = QLabel("SOON", objectName="section")
            self._items.addWidget(self.section_label)
            self._rows.append(self.section_label)
            for item in status.upcoming:
                self._add_row(item, status.day)

    def _add_row(self, item, day) -> None:
        """Строка пункта: галочка, подпись со сроком, кнопки, под ней заметки."""
        key = item.category.key
        row = QWidget()
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        column.addLayout(line)
        box = QCheckBox(item.category.title)
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.toggled.connect(lambda checked, key=key: self.toggled.emit(key, checked))
        line.addWidget(box, 1)
        if item.category.custom:
            box.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            box.customContextMenuRequested.connect(
                lambda pos, key=key, box=box: self.task_menu(key).exec(box.mapToGlobal(pos))
            )
        meta, late = meta_text(item.category, day, show_project=not self._topic)
        if meta:
            label = QLabel(objectName="metalate" if late else "meta")
            project = item.category.project
            color = next((t.color for t in self._topics if t.name == project), "")
            if project and color and not self._topic and meta.startswith(project):
                # Тема в своём цвете: во вкладке All сразу видно, откуда задача.
                label.setText(f'<span style="color:{color}">{project}</span>{meta[len(project) :]}')
            else:
                label.setText(meta)
            label.setContentsMargins(8, 0, 2, 0)
            line.addWidget(label)
            self.meta_labels[key] = label
        note = QToolButton(objectName="note", text="✎")
        note.setToolTip("Add a note or result")
        note.setCursor(Qt.CursorShape.PointingHandCursor)
        note.clicked.connect(lambda _=False, key=key: self.ask_note(key))
        line.addWidget(note)
        self.note_buttons[key] = note
        focus = QToolButton(objectName="focus", text="▶")
        focus.setToolTip("Start a focus session on this")
        focus.setCursor(Qt.CursorShape.PointingHandCursor)
        focus.clicked.connect(lambda _=False, key=key: self.focus_requested.emit(key))
        line.addWidget(focus)
        self.focus_buttons[key] = focus
        if item.category.custom:
            remove = QToolButton(objectName="remove", text="×")
            remove.setToolTip("Delete task")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _=False, key=key: self.task_removed.emit(key))
            line.addWidget(remove)
            self.remove_buttons[key] = remove
        self._add_notes(column, key, item.notes)
        self._items.addWidget(row)
        self._rows.append(row)
        self._boxes[key] = box

    def _add_notes(self, column: QVBoxLayout, key: str, notes) -> None:
        """Заметки под пунктом и скрытое поле для новой."""
        self.note_labels[key] = []
        for note in notes:
            line = QHBoxLayout()
            line.setContentsMargins(self.NOTE_INDENT, 0, 0, 0)
            label = QLabel(note.text, objectName="notetext", wordWrap=True)
            label.setMaximumWidth(self.NOTE_WIDTH)
            line.addWidget(label, 1)
            delete = QToolButton(objectName="notedel", text="×")
            delete.setToolTip("Delete note")
            delete.setCursor(Qt.CursorShape.PointingHandCursor)
            delete.clicked.connect(lambda _=False, nid=note.id: self.note_deleted.emit(nid))
            line.addWidget(delete)
            column.addLayout(line)
            self.note_labels[key].append(label)
            self.note_delete_buttons[note.id] = delete
        editor = QLineEdit(placeholderText="Result or comment… (Enter)")
        editor.returnPressed.connect(lambda key=key: self._save_note(key))
        editor.hide()
        holder = QHBoxLayout()
        holder.setContentsMargins(self.NOTE_INDENT, 0, 0, 2)
        holder.addWidget(editor)
        column.addLayout(holder)
        self.note_editors[key] = editor
