"""Синхронизация локального кэша с листами Google Таблицы. Без сети и без Google: клиент — снаружи.

Таблица — главная копия данных. Для каждой строки сравниваются три версии:
локальная, из таблицы и «какой строка была в таблице в прошлый раз» (sync_state).
По ним видно, кто что поменял:

- поменяли только в клодике — уходит в таблицу;
- поменяли только в таблице — приходит в клодик;
- поменяли разные поля одной строки — берутся обе правки;
- поменяли одно и то же поле — побеждает таблица;
- строку удалили в таблице — удаляется и в клодике;
- строку дописали в таблицу руками без id — она получает id и подхватывается.

Строки ищутся по id, а не по номеру, поэтому сортировка и свои колонки ничего не ломают.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

log = logging.getLogger(__name__)

Row = dict[str, str]


class SheetClient(Protocol):
    def read(self, tab: str) -> list[list[str]]:
        """Все значения листа, первая строка — заголовки. Листа нет — создаётся пустой."""

    def update_rows(self, tab: str, rows: dict[int, list[str]]) -> None:
        """Перезаписать строки целиком. Ключ — номер строки листа, с единицы."""

    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        """Дописать строки в конец."""

    def delete_rows(self, tab: str, numbers: list[int]) -> None:
        """Удалить строки по номерам."""


class Table(Protocol):
    """Одна таблица кэша и её лист."""

    tab: str
    columns: tuple[str, ...]

    def local_rows(self) -> dict[str, Row]: ...

    def apply(self, row_id: str, row: Row | None) -> None:
        """Записать строку в кэш. None — удалить."""

    def normalize(self, row: Row, now: datetime) -> Row | None:
        """Привести строку из листа к каноническому виду: даты, статусы, id.
        None — строка пустая или негодная, её надо пропустить."""


@dataclass
class Report:
    pulled: int = 0  # строк изменено в кэше
    pushed: int = 0  # строк изменено в таблице

    def __add__(self, other: Report) -> Report:
        return Report(self.pulled + other.pulled, self.pushed + other.pushed)


class SyncState:
    """Какими строки были в таблице при прошлой синхронизации."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def rows(self, tab: str) -> dict[str, Row]:
        with self._lock:
            found = self._conn.execute(
                "SELECT id, row FROM sync_state WHERE tab = ?", (tab,)
            ).fetchall()
        return {row_id: json.loads(row) for row_id, row in found}

    def replace(self, tab: str, rows: dict[str, Row]) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM sync_state WHERE tab = ?", (tab,))
            self._conn.executemany(
                "INSERT INTO sync_state (tab, id, row) VALUES (?, ?, ?)",
                [(tab, rid, json.dumps(row, ensure_ascii=False)) for rid, row in rows.items()],
            )


def merge(local: Row | None, remote: Row | None, base: Row | None, columns) -> Row | None:
    """Итоговая строка по трём версиям. None — строки быть не должно."""
    if base is None:
        # Общей истории нет. Есть с обеих сторон — таблица главнее.
        return remote if remote is not None else local
    if remote is None:
        return None  # удалили в таблице
    if local is None:
        # Удалили в клодике. Если строку в таблице с тех пор правили, она остаётся.
        return None if remote == base else remote
    return {
        c: local[c] if local[c] != base.get(c, "") and remote[c] == base.get(c, "") else remote[c]
        for c in columns
    }


def sync_table(table: Table, client: SheetClient, state: SyncState, now: datetime) -> Report:
    values = client.read(table.tab)
    header = [h.strip() for h in values[0]] if values else []
    missing = [c for c in table.columns if c not in header]
    header_changed = bool(missing)
    header = header + missing
    col = {name: header.index(name) for name in table.columns}

    remote: dict[str, Row] = {}
    raw: dict[str, Row] = {}
    number: dict[str, int] = {}
    cells_of: dict[str, list[str]] = {}
    for n, cells in enumerate(values[1:], start=2):
        row = {c: (cells[col[c]].strip() if col[c] < len(cells) else "") for c in table.columns}
        normal = table.normalize(dict(row), now)
        if normal is None:
            continue
        rid = normal["id"]
        if rid in remote:
            log.warning("лист %s: id %s встречается дважды, строка %s пропущена", table.tab, rid, n)
            continue
        remote[rid], raw[rid], number[rid], cells_of[rid] = normal, row, n, cells

    local = table.local_rows()
    base = state.rows(table.tab)
    report = Report()
    new_base: dict[str, Row] = {}
    updates: dict[int, list[str]] = {}
    appends: list[list[str]] = []
    deletes: list[int] = []

    def cells(row: Row, old: list[str]) -> list[str]:
        """Строка листа: наши колонки из row, чужие колонки пользователя — как были."""
        out = [old[i] if i < len(old) else "" for i in range(len(header))]
        for c in table.columns:
            out[col[c]] = row[c]
        return out

    for rid in sorted(set(local) | set(remote) | set(base)):
        mine, theirs = local.get(rid), remote.get(rid)
        merged = merge(mine, theirs, base.get(rid), table.columns)
        if merged != mine:
            table.apply(rid, merged)
            report.pulled += 1
        if merged is None:
            if theirs is not None:
                deletes.append(number[rid])
            continue
        new_base[rid] = merged
        if theirs is None:
            appends.append(cells(merged, []))
        elif merged != raw[rid]:
            updates[number[rid]] = cells(merged, cells_of[rid])

    if header_changed:
        updates[1] = header
    if updates:
        client.update_rows(table.tab, updates)
    if appends:
        client.append_rows(table.tab, appends)
    if deletes:
        client.delete_rows(table.tab, deletes)
    report.pushed = len(updates) - header_changed + len(appends) + len(deletes)
    state.replace(table.tab, new_base)
    return report
