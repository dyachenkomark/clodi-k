"""Мастер первого запуска: персонаж знакомится, подключает таблицу и модель для анализа.

Шаги: привет и выбор персонажа → Google Таблица → модель по API → готово.
Окно только показывает и собирает ввод, всю работу делает контроллер.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from clodick.desktop.themes import THEMES, Theme
from clodick.desktop.widgets import checklist_style

HELLO, SHEET, MODEL, DONE, GUIDE, RECONNECT = range(6)

# Где в Google Cloud перевести приложение из Testing в рабочее (Publish app).
AUDIENCE_URL = "https://console.developers.google.com/auth/audience"

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"

# Помощник для входа через Google: шаги для человека, который в Google Cloud впервые.
# (текст, адрес для кнопки Open или None)
GUIDE_STEPS = (
    (
        "Create a project. Name it cloDICK and press Create. Already have one? Skip this.",
        "https://console.cloud.google.com/projectcreate",
    ),
    (
        "Turn on Google Sheets: press the blue Enable button.",
        "https://console.cloud.google.com/apis/library/sheets.googleapis.com",
    ),
    (
        "Turn on Google Drive the same way: press Enable.",
        "https://console.cloud.google.com/apis/library/drive.googleapis.com",
    ),
    (
        "Name the app. Press Get started, type cloDICK and your email, press Next. "
        "Choose External, press Next, type your email again, tick the box, press Create.",
        "https://console.developers.google.com/auth/branding",
    ),
    (
        "Own files only. Press Copy, then Open. Press «Add or remove scopes», "
        "paste at the bottom, press Update, then Save.",
        "https://console.developers.google.com/auth/scopes",
    ),
    (
        "Let yourself in. Under Test users press «Add users», type your Gmail, press Save.",
        "https://console.developers.google.com/auth/audience",
    ),
    (
        "Make the key. Press «Create client», choose Desktop app, press Create. "
        "In the window that opens press Download JSON.",
        "https://console.developers.google.com/auth/clients",
    ),
    ("Give me the file. I'll look for it in your Downloads.", None),
)


def setup_style(theme: Theme) -> str:
    t = theme
    return (
        checklist_style(theme)
        + f"""
QLabel#text {{ color: {t.text}; font-size: 13px; }}
QLabel#status {{ color: {t.muted}; font-size: 12px; }}
QLabel#statusok {{ color: {t.accent}; font-size: 12px; font-weight: 600; }}
QPushButton {{
    color: {t.text}; background: {t.box_bg}; border: 1px solid {t.muted};
    border-radius: 7px; padding: 5px 12px; font-size: 13px; font-family: {t.body_font};
}}
QPushButton:hover {{ border-color: {t.text}; }}
QPushButton:disabled {{ color: {t.muted}; border-color: {t.muted}; }}
QPushButton#primary {{ color: {t.panel_bg}; background: {t.accent}; border-color: {t.accent}; }}
QPushButton#link {{ border: none; background: transparent; color: {t.muted}; padding: 2px 0; }}
QPushButton#link:hover {{ color: {t.text}; }}
QPushButton#small {{ padding: 2px 8px; font-size: 12px; }}
QLabel#step {{ color: {t.accent}; font-weight: 700; font-size: 13px; }}
QLabel#steptext {{ color: {t.text}; font-size: 12px; }}
QToolButton#pick {{
    color: {t.text}; background: transparent; border: 2px solid transparent;
    border-radius: 8px; padding: 4px; font-size: 12px; font-family: {t.body_font};
}}
QToolButton#pick:checked {{ border-color: {t.accent}; }}
QToolButton#pick:hover {{ border-color: {t.muted}; }}
QScrollArea#pagescroll, QScrollArea#pagescroll > QWidget > QWidget {{ background: transparent; }}
QComboBox {{
    color: {t.text}; background: {t.box_bg}; font-size: 13px; font-family: {t.body_font};
    border: 1px solid {t.muted}; border-radius: 6px; padding: 3px 6px;
}}
QComboBox:focus {{ border-color: {t.accent}; }}
QComboBox QAbstractItemView {{ color: {t.text}; background: {t.panel_bg}; }}
"""
    )


class Pages(QWidget):
    """Страницы мастера. Видна одна, остальные скрыты и места не занимают,
    поэтому окно само подстраивается под высоту текущей страницы."""

    def __init__(self) -> None:
        super().__init__()
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._pages: list[QWidget] = []
        self._current = 0

    def addWidget(self, page: QWidget) -> None:
        page.setVisible(not self._pages)
        self._pages.append(page)
        self._box.addWidget(page)

    def setCurrentIndex(self, index: int) -> None:
        self._current = index
        for i, page in enumerate(self._pages):
            page.setVisible(i == index)

    def currentIndex(self) -> int:
        return self._current

    def currentWidget(self) -> QWidget:
        return self._pages[self._current]

    def count(self) -> int:
        return len(self._pages)


class SetupDialog(QWidget):
    character_chosen = Signal(str)
    google_requested = Signal()
    service_requested = Signal(str, str)  # путь к ключу, ссылка на таблицу
    llm_check_requested = Signal(str, str, str)  # адрес, модель, ключ
    llm_save_requested = Signal(str, str, str)
    finished = Signal()
    closed = Signal()
    # Помощник входа через Google: открыть страницу, найти файл сам, выбрать файл руками.
    open_url_requested = Signal(str)
    client_find_requested = Signal()
    client_file_chosen = Signal(str)
    reconnect_requested = Signal()

    WIDTH = 330

    def __init__(self, theme: Theme = THEMES["classic"]) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(setup_style(theme))
        panel = QFrame(self, objectName="panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 8, 10, 12)
        # Крестик: закрыть мастер в любой момент. Вернуть — Setup в меню.
        self.close_button = QToolButton(objectName="remove", text="×")
        self.close_button.setToolTip("Close. Setup in the menu brings me back")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.closed)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch()
        top.addWidget(self.close_button)
        layout.addLayout(top)
        self.pages = Pages()
        self.pages.setContentsMargins(0, 0, 6, 0)
        # Страница выше экрана прокручивается внутри окна, а окно остаётся на экране.
        self.scroll = QScrollArea(objectName="pagescroll")
        self.scroll.setWidget(self.pages)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll)
        # Где стоит персонаж и какой экран: окно держится у него и в пределах экрана.
        self._anchor: QRect | None = None
        self._screen: QRect | None = None
        self._moved = False
        self._drag_offset = None
        self.pick_buttons: dict[str, QToolButton] = {}
        self._build_hello()
        self._build_sheet()
        self._build_model()
        self._build_done()
        self._build_guide()
        self._build_reconnect()
        self.setFixedWidth(self.WIDTH)

    # --- страницы ---

    def _page(self, title: str, text: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(9)
        box.addWidget(QLabel(title, objectName="title", wordWrap=True))
        box.addWidget(QLabel(text, objectName="text", wordWrap=True))
        self.pages.addWidget(page)
        return page, box

    @staticmethod
    def _row(*widgets, stretch_first: bool = False) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        if not stretch_first:
            row.addStretch()
        for widget in widgets:
            row.addWidget(widget)
        return row

    def _build_hello(self) -> None:
        _, box = self._page(
            "Hi! I'm your desk buddy.",
            "I keep your tasks and deadlines, remind you in time and cheer you on. "
            "Who should I be?",
        )
        self._picks = QHBoxLayout()
        self._picks.setSpacing(6)
        self._pick_group = QButtonGroup(self)
        box.addLayout(self._picks)
        self.hello_next = QPushButton("Next", objectName="primary")
        self.hello_next.clicked.connect(lambda: self.show_page(SHEET))
        box.addLayout(self._row(self.hello_next))

    def set_characters(self, characters: list[tuple[str, str, object]], current: str) -> None:
        """Кнопки выбора персонажа: (id, имя, картинка QPixmap)."""
        for character_id, name, pixmap in characters:
            # «Raccoon (classic)» не влезает под картинку: подпись — то, что в скобках.
            short = name
            if "(" in name and ")" in name:
                short = name[name.index("(") + 1 : name.rindex(")")].capitalize()
            button = QToolButton(objectName="pick", text=short, checkable=True)
            button.setToolTip(name)
            button.setIcon(pixmap)
            button.setIconSize(pixmap.size())
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setChecked(character_id == current)
            button.clicked.connect(
                lambda _=False, cid=character_id: self.character_chosen.emit(cid)
            )
            self._pick_group.addButton(button)
            self._picks.addWidget(button)
            self.pick_buttons[character_id] = button

    def _build_sheet(self) -> None:
        _, box = self._page(
            "Where should I keep your tasks?",
            "In a Google Sheet in your own Drive. You can open it on any device, even your "
            "phone, and edit tasks right there. I only get access to the sheet I create.",
        )
        self.google_button = QPushButton("Sign in with Google", objectName="primary")
        self.google_button.clicked.connect(self._google)
        box.addWidget(self.google_button)
        self.no_google = QLabel(
            "Google sign-in needs a one-time setup, about 10 minutes. I'll walk you through it.",
            objectName="status",
            wordWrap=True,
        )
        box.addWidget(self.no_google)
        self.guide_button = QPushButton("Set up Google sign-in", objectName="primary")
        self.guide_button.clicked.connect(lambda: self.show_page(GUIDE))
        box.addWidget(self.guide_button)

        self.service_toggle = QPushButton("Use my own key and an existing sheet", objectName="link")
        self.service_toggle.clicked.connect(lambda: self._service_box.setVisible(True))
        box.addWidget(self.service_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self._service_box = QWidget()
        service = QVBoxLayout(self._service_box)
        service.setContentsMargins(0, 0, 0, 0)
        self.key_path = QLineEdit(placeholderText="Token or service account key (.json)")
        browse = QPushButton("…")
        browse.setFixedWidth(34)
        browse.clicked.connect(self._browse)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_path, 1)
        key_row.addWidget(browse)
        service.addLayout(key_row)
        self.sheet_link = QLineEdit(placeholderText="Link to your sheet")
        service.addWidget(self.sheet_link)
        self.service_button = QPushButton("Connect")
        self.service_button.clicked.connect(self._service)
        service.addLayout(self._row(self.service_button))
        self._service_box.hide()
        box.addWidget(self._service_box)

        self.sheet_status = QLabel("", objectName="status", wordWrap=True)
        self.sheet_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.sheet_status.setOpenExternalLinks(True)
        self.sheet_status.hide()
        box.addWidget(self.sheet_status)
        self.sheet_skip = QPushButton("Later")
        self.sheet_skip.clicked.connect(lambda: self.show_page(MODEL))
        self.sheet_next = QPushButton("Next", objectName="primary")
        self.sheet_next.clicked.connect(lambda: self.show_page(MODEL))
        self.sheet_next.hide()
        box.addLayout(self._row(self.sheet_skip, self.sheet_next))

    def set_google_available(self, available: bool) -> None:
        self.google_button.setVisible(available)
        self.no_google.setVisible(not available)
        self.guide_button.setVisible(not available)

    def _google(self) -> None:
        self.set_sheet_status("A browser tab opens: choose your Google account and allow access.")
        self.google_button.setEnabled(False)
        self.google_requested.emit()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Google key or token", "", "JSON (*.json)")
        if path:
            self.key_path.setText(path)

    def _service(self) -> None:
        key, link = self.key_path.text().strip(), self.sheet_link.text().strip()
        if not key or not link:
            self.set_sheet_status("Choose the file and paste the link to your sheet.")
            return
        self.set_sheet_status("Connecting…")
        self.service_button.setEnabled(False)
        self.service_requested.emit(key, link)

    def set_sheet_status(self, text: str, ok: bool | None = None, url: str = "") -> None:
        """ok=None — в процессе, True — подключено, False — ошибка (кнопки снова доступны)."""
        if ok and url:
            text = f'{text} <a href="{url}">Open the sheet</a>'
        self.sheet_status.setText(text)
        self.sheet_status.setVisible(bool(text))
        self.sheet_status.setObjectName("statusok" if ok else "status")
        self.sheet_status.setStyleSheet("")  # перечитать стиль после смены имени
        if ok is not None:
            self.google_button.setEnabled(True)
            self.service_button.setEnabled(True)
        if ok:
            self.sheet_skip.hide()
            self.sheet_next.show()
        self._fit()

    def _build_model(self) -> None:
        _, box = self._page(
            "Want me smarter?",
            "Give me the address of an OpenAI-compatible API (vLLM, Ollama, LM Studio or a "
            "cloud one) and its key. I'll plan your day from your tasks and notes. "
            "The model I'll find on the server myself.",
        )
        self.llm_url = QLineEdit(placeholderText="Address, e.g. http://localhost:11434/v1")
        self.llm_key = QLineEdit(placeholderText="API key, if the server needs one")
        self.llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        # Модель не обязательна: пусто — спросим список у сервера и выберем сами.
        self.llm_model = QComboBox(editable=True)
        self.llm_model.lineEdit().setPlaceholderText("Model: leave empty, I'll find it")
        for field in (self.llm_url, self.llm_key, self.llm_model):
            box.addWidget(field)
        self.llm_status = QLabel("", objectName="status", wordWrap=True)
        self.llm_status.hide()
        box.addWidget(self.llm_status)
        self.llm_skip = QPushButton("Skip")
        self.llm_skip.clicked.connect(lambda: self.show_page(DONE))
        self.llm_check = QPushButton("Check")
        self.llm_check.clicked.connect(lambda: self._llm(self.llm_check_requested))
        self.llm_save = QPushButton("Save", objectName="primary")
        self.llm_save.clicked.connect(lambda: self._llm(self.llm_save_requested))
        box.addLayout(self._row(self.llm_skip, self.llm_check, self.llm_save))

    def set_llm_fields(self, url: str, model: str, has_key: bool) -> None:
        self.llm_url.setText(url)
        self.llm_model.setEditText(model)
        if has_key:
            self.llm_key.setPlaceholderText("Saved key is kept. Type to replace it")

    def _llm(self, signal) -> None:
        url, model = self.llm_url.text().strip(), self.llm_model.currentText().strip()
        if not url:
            self.set_llm_status("Fill in the address of the API.", False)
            return
        self.set_llm_status("Asking the server… If it's asleep, I'll wait for it to wake up.")
        self.llm_check.setEnabled(False)
        self.llm_save.setEnabled(False)
        signal.emit(url, model, self.llm_key.text())

    def set_models(self, models: list[str], current: str) -> None:
        """Модели с сервера в выпадающий список; выбранная — current."""
        self.llm_model.clear()
        self.llm_model.addItems(models)
        self.llm_model.setEditText(current)

    def set_llm_status(self, text: str, ok: bool | None = None) -> None:
        self.llm_status.setText(text)
        self.llm_status.setVisible(bool(text))
        self.llm_status.setObjectName("statusok" if ok else "status")
        self.llm_status.setStyleSheet("")
        if ok is not None:
            self.llm_check.setEnabled(True)
            self.llm_save.setEnabled(True)
        self._fit()

    def _build_done(self) -> None:
        _, box = self._page(
            "All set!",
            "Click me for today's list. Add tasks there like «work: report by fri 15:00». "
            "Double-click scares me off. Right-click or the tray icon opens the menu, "
            "Setup brings this window back.",
        )
        self.finish_button = QPushButton("Let's go", objectName="primary")
        self.finish_button.clicked.connect(self.finished)
        box.addLayout(self._row(self.finish_button))

    def _build_reconnect(self) -> None:
        _, box = self._page(
            "My Google access expired",
            "Google asks to confirm access from time to time. Press Reconnect, choose the "
            "same account in the browser and allow access. Your sheet and tasks stay as they "
            "are, and nothing is lost: I kept every change on this computer.",
        )
        self.reconnect_status = QLabel("", objectName="status", wordWrap=True)
        self.reconnect_status.hide()
        box.addWidget(self.reconnect_status)
        self.reconnect_later = QPushButton("Later")
        self.reconnect_later.clicked.connect(self.hide)
        self.reconnect_button = QPushButton("Reconnect", objectName="primary")
        self.reconnect_button.clicked.connect(self._reconnect)
        box.addLayout(self._row(self.reconnect_later, self.reconnect_button))
        hint = QLabel(
            "Google asks every 7 days? Your app in Google Cloud is in Testing mode. "
            "Open Audience there and press «Publish app» once.",
            objectName="status",
            wordWrap=True,
        )
        box.addWidget(hint)
        self.audience_open = QPushButton("Open Audience", objectName="small")
        self.audience_open.clicked.connect(lambda: self.open_url_requested.emit(AUDIENCE_URL))
        box.addLayout(self._row(self.audience_open))

    def _reconnect(self) -> None:
        self.set_reconnect_status("A browser tab opens: choose your account and allow access.")
        self.reconnect_button.setEnabled(False)
        self.reconnect_requested.emit()

    def set_reconnect_status(self, text: str, ok: bool | None = None) -> None:
        self.reconnect_status.setText(text)
        self.reconnect_status.setVisible(bool(text))
        self.reconnect_status.setObjectName("statusok" if ok else "status")
        self.reconnect_status.setStyleSheet("")
        if ok is not None:
            self.reconnect_button.setEnabled(True)
        self._fit()

    def _build_guide(self) -> None:
        _, box = self._page(
            "Set up Google sign-in",
            "Once, about 10 minutes. Do the steps in order: each Open button takes you to "
            "the right page. Sign in there with your usual Google account.",
        )
        self.guide_open: list[QPushButton] = []
        self._step_labels: list[QLabel] = []
        # Точная ширина текста: иначе Qt неверно считает высоту строк с переносами
        # и последняя строка шага обрезается.
        # Минус отступы, номер, кнопка и место под полосу прокрутки на низком экране.
        text_width = self.WIDTH - 32 - 16 - 60 - 16 - 14
        for number, (text, url) in enumerate(GUIDE_STEPS, start=1):
            row = QHBoxLayout()
            row.setSpacing(8)
            number_label = QLabel(str(number), objectName="step")
            number_label.setFixedWidth(16)
            row.addWidget(number_label, 0, Qt.AlignmentFlag.AlignTop)
            label = QLabel(text, objectName="steptext", wordWrap=True)
            label.setFixedWidth(text_width if url else text_width + 68)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self._step_labels.append(label)
            row.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
            if url:
                buttons = QVBoxLayout()
                buttons.setSpacing(4)
                if "scopes" in url:
                    self.copy_scope = QPushButton("Copy", objectName="small")
                    self.copy_scope.setFixedWidth(60)
                    self.copy_scope.clicked.connect(self._copy_scope)
                    buttons.addWidget(self.copy_scope)
                button = QPushButton("Open", objectName="small")
                button.setFixedWidth(60)
                button.clicked.connect(lambda _=False, u=url: self.open_url_requested.emit(u))
                buttons.addWidget(button)
                buttons.addStretch()
                row.addLayout(buttons)
                self.guide_open.append(button)
            row.addStretch()
            box.addLayout(row)
        self.find_client = QPushButton("Find it", objectName="primary")
        self.find_client.clicked.connect(self._find_client)
        self.choose_client = QPushButton("Choose file…")
        self.choose_client.clicked.connect(self._choose_client)
        box.addLayout(self._row(self.choose_client, self.find_client))
        self.guide_status = QLabel("", objectName="status", wordWrap=True)
        self.guide_status.hide()
        box.addWidget(self.guide_status)
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.show_page(SHEET))
        box.addLayout(self._row(back))

    def _copy_scope(self) -> None:
        QGuiApplication.clipboard().setText(DRIVE_FILE_SCOPE)
        self.copy_scope.setText("Copied")

    def _find_client(self) -> None:
        self.set_guide_status("Looking in Downloads…")
        self.client_find_requested.emit()

    def _choose_client(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "The downloaded JSON", "", "JSON (*.json)")
        if path:
            self.client_file_chosen.emit(path)

    def set_guide_status(self, text: str, ok: bool | None = None) -> None:
        self.guide_status.setText(text)
        self.guide_status.setVisible(bool(text))
        self.guide_status.setObjectName("statusok" if ok else "status")
        self.guide_status.setStyleSheet("")
        self._fit()

    # --- показ ---

    def show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self._fit()

    def _fit(self, again: bool = True) -> None:
        """Окно по размеру видимой страницы.

        Новая страница или строка статуса получает стиль только в следующем цикле событий,
        поэтому размер пересчитывается ещё раз чуть позже.
        """
        if again:
            QTimer.singleShot(0, lambda: self._fit(again=False))
        # Высоту строк с переносами считаем, когда стиль со шрифтом уже применён.
        # QLabel.heightForWidth здесь завышает высоту, поэтому меряем текст шрифтом сами.
        for label in getattr(self, "_step_labels", []):
            label.ensurePolished()
            box = QFontMetrics(label.font()).boundingRect(
                QRect(0, 0, label.width(), 10_000), Qt.TextFlag.TextWordWrap, label.text()
            )
            label.setFixedHeight(box.height() + 2)
        current = self.pages.currentWidget()
        # Только что показанная страница: раскладку пересчитать заново, иначе размер старый.
        current.layout().invalidate()
        current.layout().activate()
        current.adjustSize()
        wanted = current.layout().sizeHint().height()
        # Сколько места под страницу: высота экрана минус рамка, крестик и запас.
        limit = self._screen.height() - 70 if self._screen is not None else wanted
        self.scroll.setFixedHeight(max(80, min(wanted, limit)))
        self.scroll.verticalScrollBar().setValue(0)
        self.layout().activate()
        self.adjustSize()
        if self.isVisible():
            self._place()

    def open_near(self, anchor: QRect, screen: QRect) -> None:
        """Над персонажем, как чек-лист: не закрывает его и не вылезает за экран."""
        self._anchor, self._screen, self._moved = anchor, screen, False
        self.show()
        self.raise_()
        self.activateWindow()
        self._fit()

    def _place(self) -> None:
        """Поставить окно у персонажа, а если его двигали — оставить, где поставили.
        В любом случае целиком в пределах экрана: страницы бывают разной высоты."""
        if self._screen is None:
            return
        screen = self._screen
        if self._moved or self._anchor is None:
            x, y = self.x(), self.y()
        else:
            anchor = self._anchor
            x = anchor.center().x() - self.width() // 2
            y = anchor.top() - self.height() - 6
            if y < screen.top():
                y = anchor.bottom() + 6
        x = max(screen.left(), min(x, screen.right() + 1 - self.width()))
        y = max(screen.top(), min(y, screen.bottom() + 1 - self.height()))
        self.move(x, y)

    # --- перетаскивание за пустое место ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._moved = True

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self._place()
