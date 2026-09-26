"""Точка входа. Пока это консольная команда; окно с енотом появится на этапе 1.

Примеры:
    clodick              показать статус дня
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

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clodick", description="cloDICK — задачи дня")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="показать статус дня (по умолчанию)")
    done = sub.add_parser("done", help="отметить направление выполненным")
    done.add_argument("key")
    undo = sub.add_parser("undo", help="снять отметку")
    undo.add_argument("key")
    return parser


def format_status(status: DayStatus) -> str:
    lines = [f"{status.day:%d.%m.%Y}: {status.done_count}/{status.total}"]
    for item in status.items:
        mark = "[x]" if item.done else "[ ]"
        lines.append(f"  {mark} {item.category.title} ({item.category.key})")
    if status.all_done:
        lines.append("Всё сделано, енот доволен.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(paths.log_dir())

    try:
        config = load_config(paths.config_path())
    except ConfigError as exc:
        print(f"Ошибка в настройках: {exc}", file=sys.stderr)
        return 2

    conn = connect(paths.db_path())
    try:
        tracker = Tracker(config, CompletionRepository(conn))
        try:
            if args.command == "done":
                if not tracker.mark_done(args.key, source="cli"):
                    print("Уже отмечено сегодня.")
                log.info("done %s", args.key)
            elif args.command == "undo":
                if not tracker.unmark(args.key):
                    print("Отметки не было.")
                log.info("undo %s", args.key)
        except KeyError as exc:
            print(exc.args[0], file=sys.stderr)
            return 2
        print(format_status(tracker.status()))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
