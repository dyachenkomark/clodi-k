"""Доступ к Google Таблице. gspread грузится только здесь и только когда он нужен.

Два способа войти:

- **Вход через Google (OAuth)** — для всех. Пользователь нажимает кнопку, в браузере
  разрешает доступ, клодик сам создаёт у него таблицу «cloDICK». Права — `drive.file`:
  клодик видит только созданные им файлы, остальной Диск ему недоступен. Нужен файл
  OAuth-клиента приложения `google-oauth-client.json`, его один раз делает разработчик.
- **Сервисный аккаунт** — для продвинутых: свой JSON-ключ и таблица, открытая аккаунту.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Сколько ждать ответа Google, секунды: сеть не должна подвешивать синхронизацию.
TIMEOUT_SECONDS = 20
# Только файлы, созданные самим клодиком. Google относит эти права к несекретным.
OAUTH_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
SHEET_TITLE = "cloDICK"
# Файл OAuth-клиента приложения: в пакете (его кладёт разработчик) или в папке данных.
OAUTH_CLIENT_NAME = "google-oauth-client.json"
# Токен входа пользователя: в папке данных, рядом с кэшем.
TOKEN_NAME = "google-token.json"


def column_letter(index: int) -> str:
    """Номер колонки с единицы в букву: 1 → A, 27 → AA."""
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


class SheetsError(Exception):
    """Таблица недоступна. Текст уже понятен человеку."""


@dataclass(frozen=True)
class SheetLink:
    """Как клодик ходит в таблицу. Сохраняется мастером настройки.

    mode: "oauth" — вход через Google, "service" — ключ сервисного аккаунта.
    key_file: для service — путь к ключу; для oauth — путь к токену входа.
    """

    mode: str
    spreadsheet_id: str
    key_file: str
    url: str = ""

    def to_dict(self) -> dict:
        return {"mode": self.mode, "spreadsheet_id": self.spreadsheet_id,
                "key_file": self.key_file, "url": self.url}  # fmt: skip

    @classmethod
    def from_dict(cls, data: dict | None) -> SheetLink | None:
        if not data or data.get("mode") not in ("oauth", "service"):
            return None
        if not data.get("spreadsheet_id") or not data.get("key_file"):
            return None
        return cls(data["mode"], data["spreadsheet_id"], data["key_file"], data.get("url", ""))


def oauth_client_file(data_dir: Path) -> Path | None:
    """Файл OAuth-клиента приложения, если он есть: сначала в папке данных, потом в пакете."""
    for folder in (data_dir, Path(__file__).resolve().parents[1] / "assets"):
        candidate = folder / OAUTH_CLIENT_NAME
        if candidate.is_file():
            return candidate
    return None


# Какие бывают JSON-файлы Google и что клодик с ними делает.
SERVICE_ACCOUNT, OAUTH_CLIENT, WEB_CLIENT, TOKEN, UNKNOWN = (
    "service_account", "oauth_client", "web_client", "token", "unknown",
)  # fmt: skip
IMPORTED_TOKEN_NAME = "google-token-imported.json"


def key_kind(path: Path) -> str:
    """Что за файл выбрал человек: ключ сервисного аккаунта, клиент для входа, токен."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UNKNOWN
    if not isinstance(data, dict):
        return UNKNOWN
    if data.get("type") == "service_account" and data.get("client_email"):
        return SERVICE_ACCOUNT
    if isinstance(data.get("installed"), dict):
        return OAUTH_CLIENT
    if isinstance(data.get("web"), dict):
        return WEB_CLIENT
    if data.get("refresh_token") and data.get("client_id"):
        return TOKEN
    return UNKNOWN


def import_token(source: Path, data_dir: Path) -> Path:
    """Скопировать готовый токен входа в папку данных: ссылка на чужую папку может пропасть."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / IMPORTED_TOKEN_NAME
    if source.resolve() != target.resolve():
        target.write_bytes(source.read_bytes())
    return target


def check_oauth_client(path: Path) -> dict:
    """Проверить скачанный файл клиента. Ошибки — простыми словами для человека."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SheetsError("This file is not the one from Google Cloud. Download it again.") from exc
    if "web" in data:
        raise SheetsError(
            "This key is for a website. In Google Cloud create a new one with type Desktop app."
        )
    installed = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(installed, dict) or not installed.get("client_id"):
        if isinstance(data, dict) and data.get("type") == "service_account":
            raise SheetsError(
                "This is a service account key. Use «I have a service account key» instead."
            )
        raise SheetsError("This is not an OAuth client file. Download the JSON of a Desktop app.")
    return data


def install_oauth_client(source: Path, data_dir: Path) -> Path:
    """Скопировать проверенный файл клиента в папку данных под нужным именем."""
    check_oauth_client(source)
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / OAUTH_CLIENT_NAME
    target.write_bytes(source.read_bytes())
    return target


def find_downloaded_client(downloads: Path) -> Path | None:
    """Самый свежий скачанный файл клиента: Google называет его client_secret_….json."""
    try:
        found = [p for p in downloads.glob("client_secret*.json") if p.is_file()]
    except OSError:
        return None
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def _gspread():
    import gspread  # тяжёлый импорт: только когда таблица действительно нужна

    return gspread


def service_account_email(key_file: Path) -> str:
    if not key_file.is_file():
        raise SheetsError(f"Key file not found: {key_file}")
    try:
        return json.loads(key_file.read_text(encoding="utf-8"))["client_email"]
    except (ValueError, KeyError) as exc:
        raise SheetsError(f"{key_file.name} is not a service account key") from exc


def authorize(link: SheetLink):
    """gspread-клиент по сохранённому способу входа. Без браузера: токен уже есть."""
    gspread = _gspread()
    key = Path(link.key_file)
    if link.mode == "service":
        service_account_email(key)
        return gspread.service_account(filename=str(key))
    if not key.is_file():
        raise SheetsError("Google sign-in expired. Open Setup and sign in again.")
    from google.oauth2.credentials import Credentials

    try:
        # Права берём из самого токена: у своего входа это drive.file, у готового токена
        # может быть spreadsheets. Подменять их нельзя: Google откажет при продлении.
        creds = Credentials.from_authorized_user_file(str(key))
    except ValueError as exc:
        raise SheetsError("Google sign-in is broken. Open Setup and sign in again.") from exc
    return gspread.authorize(creds)


def sign_in(client_file: Path, token_file: Path, flow: Callable | None = None):
    """Вход через Google в браузере. Возвращает gspread-клиент, токен сохраняется в token_file.

    flow — для тестов: функция (client_config, scopes) → Credentials.
    """
    gspread = _gspread()
    if flow is None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        def flow(config: dict, scopes: list[str]):
            app_flow = InstalledAppFlow.from_client_config(config, scopes)
            return app_flow.run_local_server(
                port=0,
                open_browser=True,
                authorization_prompt_message="",
                success_message="cloDICK is connected. You can close this tab.",
            )

    try:
        config = json.loads(client_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SheetsError(f"Broken OAuth client file: {client_file}") from exc
    creds = flow(config, OAUTH_SCOPES)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return gspread.authorize(creds)


def find_or_create_sheet(gc, title: str = SHEET_TITLE) -> tuple[str, str]:
    """Таблица клодика у пользователя: найти созданную раньше или создать новую.

    С правами drive.file поиск видит только файлы клодика, так что чужие таблицы
    с тем же названием не попадутся. Возвращает id и адрес.
    """
    gspread = _gspread()
    try:
        found = gc.openall(title)
        book = found[0] if found else gc.create(title)
    except gspread.exceptions.APIError as exc:
        raise SheetsError(f"Google API error: {exc}") from exc
    return book.id, book.url


def open_by_link(gc, sheet: str) -> tuple[str, str]:
    """Открыть таблицу по адресу или id (для сервисного аккаунта). Возвращает id и адрес."""
    gspread = _gspread()
    try:
        book = gc.open_by_url(sheet) if "/" in sheet else gc.open_by_key(sheet.strip())
    except gspread.SpreadsheetNotFound as exc:
        raise SheetsError("Spreadsheet not found. Check the link.") from exc
    except gspread.NoValidUrlKeyFound as exc:
        raise SheetsError("This does not look like a Google Sheets link.") from exc
    except PermissionError as exc:
        raise SheetsError("No access. Share the sheet with the service account.") from exc
    except gspread.exceptions.APIError as exc:
        raise SheetsError(f"Google API error: {exc}") from exc
    return book.id, book.url


class GoogleSheetClient:
    """Реализация SheetClient из engine.py поверх gspread.

    Пишем как есть (RAW): таблица не превращает «2026-10-02» в дату со своим форматом,
    и то, что записали, потом читается теми же символами.
    """

    def __init__(self, gc, spreadsheet_id: str, account: str = "") -> None:
        self._gspread = _gspread()
        self.account = account
        gc.set_timeout(TIMEOUT_SECONDS)
        try:
            self._book = gc.open_by_key(spreadsheet_id)
        except self._gspread.SpreadsheetNotFound as exc:
            raise SheetsError("Spreadsheet not found. Check spreadsheet_id.") from exc
        except PermissionError as exc:
            who = account or "this account"
            raise SheetsError(f"No access. Share the sheet with {who} as an editor.") from exc
        except self._gspread.exceptions.APIError as exc:
            raise SheetsError(f"Google API error: {exc}") from exc
        self._sheets: dict = {}

    @classmethod
    def from_link(cls, link: SheetLink) -> GoogleSheetClient:
        account = service_account_email(Path(link.key_file)) if link.mode == "service" else ""
        return cls(authorize(link), link.spreadsheet_id, account)

    @classmethod
    def service_account(cls, key_file: Path, spreadsheet_id: str) -> GoogleSheetClient:
        """Вход по ключу из config.toml ([sheets])."""
        return cls.from_link(SheetLink("service", spreadsheet_id, str(key_file)))

    def _sheet(self, tab: str):
        if tab not in self._sheets:
            try:
                sheet = self._book.worksheet(tab)
            except self._gspread.WorksheetNotFound:
                sheet = self._book.add_worksheet(title=tab, rows=200, cols=12)
                sheet.freeze(rows=1)
            self._sheets[tab] = sheet
        return self._sheets[tab]

    def read(self, tab: str) -> list[list[str]]:
        return self._sheet(tab).get_all_values()

    def update_rows(self, tab: str, rows: dict[int, list[str]]) -> None:
        data = [
            {"range": f"A{n}:{column_letter(len(values))}{n}", "values": [values]}
            for n, values in rows.items()
        ]
        self._sheet(tab).batch_update(data, value_input_option="RAW")

    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        self._sheet(tab).append_rows(rows, value_input_option="RAW", table_range="A1")

    def delete_rows(self, tab: str, numbers: list[int]) -> None:
        sheet = self._sheet(tab)
        for n in sorted(numbers, reverse=True):  # с конца: номера выше не сдвигаются
            sheet.delete_rows(n)
