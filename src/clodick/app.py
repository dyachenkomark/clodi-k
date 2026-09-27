"""Точка входа.

clodick              запустить персонажа на рабочем столе
clodick status       статус дня в консоли
clodick done sport   отметить спорт
clodick undo sport   снять отметку
"""

from __future__ import annotations

import argparse
import logging
import sys

from clodick import __version__, paths
from clodick.config import ConfigError, load_config
from clodick.core.models import DayStatus
from clodick.core.tracker import Tracker
from clodick.logging_setup import setup_logging
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.storage.state import StateStore

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clodick", description="cloDICK — daily tasks")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="show today's status")
    done = sub.add_parser("done", help="mark an item done")
    done.add_argument("key")
    undo = sub.add_parser("undo", help="unmark an item")
    undo.add_argument("key")
    return parser


def format_status(status: DayStatus) -> str:
    lines = [f"{status.day:%d.%m.%Y}: {status.done_count}/{status.total}"]
    for item in status.items:
        mark = "[x]" if item.done else "[ ]"
        lines.append(f"  {mark} {item.category.title} ({item.category.key})")
    if status.all_done:
        lines.append("All done!")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(paths.log_dir())

    try:
        config = load_config(paths.config_path())
    except ConfigError as exc:
        _error(f"Ошибка в настройках: {exc}")
        return 2

    conn = connect(paths.db_path())
    try:
        tracker = Tracker(config, CompletionRepository(conn))
        if args.command is None:
            from clodick.desktop.main import run  # Qt грузим, только если нужно окно

            return run(config, tracker, StateStore(conn))
        return _run_cli(args, tracker)
    finally:
        conn.close()


def _run_cli(args: argparse.Namespace, tracker: Tracker) -> int:
    try:
        if args.command == "done":
            if not tracker.mark_done(args.key, source="cli"):
                print("Already marked today.")
            log.info("done %s", args.key)
        elif args.command == "undo":
            if not tracker.unmark(args.key):
                print("It was not marked.")
            log.info("undo %s", args.key)
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
        return 2
    print(format_status(tracker.status()))
    return 0


def _error(message: str) -> None:
    """Пишет ошибку в консоль, если она есть, и всегда в лог."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    log.error(message)


def gui_main() -> int:
    """Запуск без консольного окна на Windows."""
    return main([])


if __name__ == "__main__":
    raise SystemExit(main())
