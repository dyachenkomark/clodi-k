"""Запуск персонажа на рабочем столе."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from clodick import paths
from clodick.config import Config
from clodick.core.tracker import Tracker
from clodick.desktop.controller import DesktopApp
from clodick.storage.state import StateStore
from clodick.system.ram import ram_percent

log = logging.getLogger(__name__)


def run(config: Config, tracker: Tracker, state: StateStore) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("cloDICK")
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(paths.data_dir() / "clodick.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(
            None, "cloDICK", "cloDICK is already running. Look for it in the tray."
        )
        return 1

    sys.excepthook = _log_exception
    sync_factory = make_sync_factory(config)
    link = current_link(config, state)
    sync = sync_factory(link) if link is not None else None
    desktop = DesktopApp(
        app, config, tracker, state, ram_reader=ram_percent, sync=sync, sync_factory=sync_factory
    )
    desktop.start()
    if sync is not None:
        sync.start()
    log.info("окно запущено")
    try:
        return app.exec()
    finally:
        lock.unlock()


def current_link(config: Config, state: StateStore):
    """Как ходить в таблицу: подключённая в мастере, иначе заданная в config.toml."""
    from clodick.sync.google import SheetLink

    link = SheetLink.from_dict(state.get("sheet_link"))
    if link is not None:
        return link
    if config.sheets.enabled:
        key_file = paths.data_dir() / config.sheets.key_file
        return SheetLink("service", config.sheets.spreadsheet_id, str(key_file))
    return None


def make_sync_factory(config: Config):
    """link → фоновая синхронизация с этой таблицей."""

    def factory(link):
        from clodick.sync.google import GoogleSheetClient
        from clodick.sync.worker import SheetSync

        return SheetSync(
            paths.db_path(),
            lambda: GoogleSheetClient.from_link(link),
            period=config.sheets.sync_seconds,
        )

    return factory


def _log_exception(exc_type, exc, tb) -> None:
    log.critical("необработанная ошибка", exc_info=(exc_type, exc, tb))
