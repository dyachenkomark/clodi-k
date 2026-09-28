"""Точка входа.

clodick              запустить персонажа на рабочем столе
clodick status       статус дня в консоли
clodick done sport   отметить спорт
clodick undo sport   снять отметку
clodick note sport "5 км за 28 минут"   заметка к пункту: результат, комментарий
clodick notes --days 7                  заметки за последние дни
clodick export history.csv              выгрузить историю: .csv для таблицы, .json для LLM
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from clodick import __version__, paths
from clodick.config import ConfigError, load_config
from clodick.core import history
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
    note = sub.add_parser("note", help="add a note or result to today's item")
    note.add_argument("key")
    note.add_argument("text", nargs="+")
    notes = sub.add_parser("notes", help="show notes of the last days")
    notes.add_argument("--days", type=int, default=7)
    export = sub.add_parser("export", help="export history to .csv or .json")
    export.add_argument("path", type=Path)
    export.add_argument("--from", dest="first", type=date.fromisoformat, default=None)
    export.add_argument("--to", dest="last", type=date.fromisoformat, default=None)
    return parser


def format_status(status: DayStatus) -> str:
    lines = [f"{status.day:%d.%m.%Y}: {status.done_count}/{status.total}"]
    for item in status.items:
        mark = "[x]" if item.done else "[ ]"
        lines.append(f"  {mark} {item.category.title} ({item.category.key})")
        for note in item.notes:
            lines.append(f"        - {note.text}")
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
        repo = CompletionRepository(conn)
        tracker = Tracker(config, repo)
        if args.command is None:
            from clodick.desktop.main import run  # Qt грузим, только если нужно окно

            return run(config, tracker, StateStore(conn))
        if args.command == "notes":
            return _print_notes(repo, tracker.today(), args.days)
        if args.command == "export":
            return _export(args, repo, config, tracker.today())
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
        elif args.command == "note":
            tracker.add_note(args.key, " ".join(args.text), source="cli")
            log.info("note %s", args.key)
    except (KeyError, ValueError) as exc:
        print(exc.args[0], file=sys.stderr)
        return 2
    print(format_status(tracker.status()))
    return 0


def _print_notes(repo: CompletionRepository, today: date, days: int) -> int:
    notes = repo.notes_between(today - timedelta(days=max(1, days) - 1), today)
    if not notes:
        print("No notes yet.")
    for note in notes:
        print(f"{note.day:%d.%m} {note.title}: {note.text}")
    return 0


def _export(args: argparse.Namespace, repo: CompletionRepository, config, today: date) -> int:
    first = args.first or repo.first_day() or today
    last = args.last or today
    try:
        count = history.export(args.path, repo, config, first, last)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"Exported {count} days to {args.path}")
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
