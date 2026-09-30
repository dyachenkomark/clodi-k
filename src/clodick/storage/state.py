"""Небольшое хранилище ключ-значение для состояния интерфейса."""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

# Правка задач снаружи (MCP-сервер для Claude): {"at": момент, "text": что сделано}.
# Енот следит за этим ключом, обновляет чек-лист и отправляет правку в таблицу.
EXTERNAL_CHANGE = "external_change"


class StateStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
