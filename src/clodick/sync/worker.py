"""Фоновая синхронизация с таблицей: свой поток и своё соединение с кэшем.

Сеть не трогает поток интерфейса. Интерфейс узнаёт о новостях через pop_changed().
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.sync.engine import SheetClient
from clodick.sync.tables import sync_all

log = logging.getLogger(__name__)

# После правки ждём немного: несколько галочек подряд уйдут одним заходом.
DEBOUNCE_SECONDS = 2.0


class SheetSync:
    def __init__(
        self,
        db_path: Path,
        client_factory: Callable[[], SheetClient],
        period: float = 60.0,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._db_path = db_path
        self._factory = client_factory
        self._period = period
        self._clock = clock
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._changed = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_ok: datetime | None = None
        self.error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="sheet-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def request(self) -> None:
        """Что-то поменялось локально: синхронизироваться в ближайшие секунды."""
        self._wake.set()

    def pop_changed(self) -> bool:
        """Пришли ли из таблицы изменения с прошлого вопроса."""
        changed = self._changed.is_set()
        self._changed.clear()
        return changed

    @property
    def status(self) -> str:
        if self.error:
            return f"Sheet: {self.error}"
        if self.last_ok:
            return f"Sheet synced {self.last_ok:%H:%M}"
        return "Sheet: connecting"

    def _run(self) -> None:
        conn = connect(self._db_path)
        repo = CompletionRepository(conn)
        client: SheetClient | None = None
        try:
            while not self._stop.is_set():
                try:
                    client = client or self._factory()
                    report = sync_all(repo, client, self._clock())
                    if report.pulled:
                        self._changed.set()
                    if report.pulled or report.pushed:
                        log.info("таблица: пришло %s, ушло %s", report.pulled, report.pushed)
                    self.last_ok, self.error = self._clock(), None
                except Exception as exc:  # сеть, лимиты, права: попробуем в следующий раз
                    if str(exc) != self.error:
                        log.warning("таблица недоступна: %s", exc)
                    self.error = str(exc)[:120]
                    client = None
                if self._wake.wait(self._period) and not self._stop.is_set():
                    self._stop.wait(DEBOUNCE_SECONDS)
                self._wake.clear()
        finally:
            conn.close()
