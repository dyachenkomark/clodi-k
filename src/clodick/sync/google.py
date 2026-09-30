"""Доступ к Google Таблице через сервисный аккаунт. gspread грузится только здесь."""

from __future__ import annotations

import json
from pathlib import Path

# Сколько ждать ответа Google, секунды: сеть не должна подвешивать синхронизацию.
TIMEOUT_SECONDS = 20


def column_letter(index: int) -> str:
    """Номер колонки с единицы в букву: 1 → A, 27 → AA."""
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


class SheetsError(Exception):
    """Таблица недоступна. Текст уже понятен человеку."""


class GoogleSheetClient:
    """Реализация SheetClient из engine.py поверх gspread.

    Пишем как есть (RAW): таблица не превращает «2026-10-02» в дату со своим форматом,
    и то, что записали, потом читается теми же символами.
    """

    def __init__(self, key_file: Path, spreadsheet_id: str) -> None:
        import gspread  # тяжёлый импорт: только когда синхронизация включена

        self._gspread = gspread
        if not key_file.is_file():
            raise SheetsError(f"Key file not found: {key_file}")
        try:
            # Почта сервисного аккаунта: ей надо открыть доступ к таблице.
            self.account = json.loads(key_file.read_text(encoding="utf-8"))["client_email"]
        except (ValueError, KeyError) as exc:
            raise SheetsError(f"{key_file.name} is not a service account key") from exc
        try:
            client = gspread.service_account(filename=str(key_file))
            client.set_timeout(TIMEOUT_SECONDS)
            self._book = client.open_by_key(spreadsheet_id)
        except gspread.SpreadsheetNotFound as exc:
            raise SheetsError("Spreadsheet not found. Check spreadsheet_id.") from exc
        except PermissionError as exc:
            raise SheetsError(
                f"No access. Share the sheet with {self.account} as an editor."
            ) from exc
        except gspread.exceptions.APIError as exc:
            raise SheetsError(f"Google API error: {exc}") from exc
        except ValueError as exc:
            raise SheetsError(f"Key file is not a service account key: {exc}") from exc
        self._sheets: dict = {}

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
