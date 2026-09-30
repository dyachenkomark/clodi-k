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
    sync = make_sync(config)
    desktop = DesktopApp(app, config, tracker, state, ram_reader=ram_percent, sync=sync)
    desktop.start()
    if sync is not None:
        sync.start()
    log.info("окно запущено")
    try:
        return app.exec()
    finally:
        lock.unlock()


def make_sync(config: Config):
    """Фоновая синхронизация с Google Таблицей, если она настроена."""
    if not config.sheets.enabled:
        return None
    from clodick.sync.google import GoogleSheetClient
    from clodick.sync.worker import SheetSync

    key_file = paths.data_dir() / config.sheets.key_file
    return SheetSync(
        paths.db_path(),
        lambda: GoogleSheetClient(key_file, config.sheets.spreadsheet_id),
        period=config.sheets.sync_seconds,
    )


def _log_exception(exc_type, exc, tb) -> None:
    log.critical("необработанная ошибка", exc_info=(exc_type, exc, tb))
