"""История по дням: что отмечено, какие заметки, сколько фокусов. Выгрузка в CSV и JSON.

CSV — для таблицы: одна строка на пункт или заметку. JSON — для LLM: вложенная структура
по дням. Без Qt, чтобы переиспользовать в боте.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from clodick.config import Config
from clodick.storage.repository import CompletionRepository

CSV_COLUMNS = ["day", "item_key", "item_title", "done", "done_at", "note", "note_at"]


def history(repo: CompletionRepository, config: Config, first: date, last: date) -> list[dict]:
    """Дни с first по last: направления из настроек каждый день, свои задачи — если по ним
    что-то было в этот день."""
    done = {(d, key): at for d, key, at in repo.completions_between(first, last)}
    notes: dict[tuple[date, str], list] = {}
    # Название пункта: из настроек, из задач, а для удалённых задач — из самих записей.
    titles = repo.completion_titles()
    titles |= {task.key: task.title for task in repo.tasks()}
    titles |= {cat.key: cat.title for cat in config.categories}
    for note in repo.notes_between(first, last):
        notes.setdefault((note.day, note.key), []).append(note)
        titles.setdefault(note.key, note.title)
    focus: dict[date, list[int]] = {}
    for day, _key, minutes in repo.focus_between(first, last):
        focus.setdefault(day, []).append(minutes)

    days = []
    day = first
    while day <= last:
        keys = [cat.key for cat in config.categories]
        extra = {k for d, k in (*done, *notes) if d == day and k not in keys}
        keys += sorted(extra)
        items = []
        for key in keys:
            at = done.get((day, key))
            items.append(
                {
                    "key": key,
                    "title": titles.get(key, key),
                    "done": at is not None,
                    "done_at": at.isoformat() if at else None,
                    "notes": [
                        {"text": n.text, "at": n.created_at.isoformat()}
                        for n in notes.get((day, key), [])
                    ],
                }
            )
        sessions = focus.get(day, [])
        days.append(
            {
                "day": day.isoformat(),
                "items": items,
                "focus": {"sessions": len(sessions), "minutes": sum(sessions)},
            }
        )
        day += timedelta(days=1)
    return days


def csv_rows(days: list[dict]) -> list[dict]:
    rows = []
    for day in days:
        for item in day["items"]:
            base = {
                "day": day["day"],
                "item_key": item["key"],
                "item_title": item["title"],
                "done": "yes" if item["done"] else "no",
                "done_at": item["done_at"] or "",
            }
            if not item["notes"]:
                rows.append({**base, "note": "", "note_at": ""})
            for note in item["notes"]:
                rows.append({**base, "note": note["text"], "note_at": note["at"]})
    return rows


def export(path: Path, repo: CompletionRepository, config: Config, first: date, last: date) -> int:
    """Пишет историю в path: .csv или .json по расширению. Возвращает число дней."""
    days = history(repo, config, first, last)
    if path.suffix.lower() == ".json":
        payload = {"from": first.isoformat(), "to": last.isoformat(), "days": days}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif path.suffix.lower() == ".csv":
        # utf-8-sig: Excel и Google Таблицы сразу видят кириллицу.
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(csv_rows(days))
    else:
        raise ValueError("Export file must end with .csv or .json")
    return len(days)
