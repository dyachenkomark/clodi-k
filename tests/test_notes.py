import csv
import json
from datetime import date, datetime

import pytest

from clodick.core import history
from clodick.core.tracker import Tracker


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_notes_attach_to_today_items(config, repo):
    clock = Clock(datetime(2026, 9, 28, 19, 0))
    tracker = Tracker(config, repo, clock=clock)
    tracker.mark_done("sport")
    tracker.add_note("sport", "  5 km, 28 min ")
    tracker.add_note("sport", "knee ok")
    sport = tracker.status().items[0]
    assert [n.text for n in sport.notes] == ["5 km, 28 min", "knee ok"]
    assert sport.notes[0].title == "Sport"

    clock.now = datetime(2026, 9, 29, 12, 0)
    assert tracker.status().items[0].notes == ()


def test_note_validation_and_delete(config, repo):
    tracker = Tracker(config, repo, clock=Clock(datetime(2026, 9, 28, 12)))
    with pytest.raises(KeyError):
        tracker.add_note("chess", "e4")
    with pytest.raises(ValueError):
        tracker.add_note("sport", "   ")
    note = tracker.add_note("study", "chapter 3")
    assert tracker.delete_note(note.id)
    assert not tracker.delete_note(note.id)
    assert tracker.status().items[1].notes == ()


def test_note_keeps_title_after_task_is_deleted(config, repo, tmp_path):
    clock = Clock(datetime(2026, 9, 28, 12))
    tracker = Tracker(config, repo, clock=clock)
    task = tracker.add_task("Call Anna")
    key = f"task:{task.id}"
    tracker.mark_done(key)
    tracker.add_note(key, "agreed on Friday")
    tracker.remove_task(key)
    days = history.history(repo, config, date(2026, 9, 28), date(2026, 9, 28))
    titles = {i["key"]: i["title"] for i in days[0]["items"]}
    assert titles[key] == "Call Anna"


def test_export_csv_and_json(config, repo, tmp_path):
    clock = Clock(datetime(2026, 9, 27, 10))
    tracker = Tracker(config, repo, clock=clock)
    tracker.mark_done("sport")
    tracker.add_note("sport", "бег 5 км")
    tracker.add_focus("sport", datetime(2026, 9, 27, 9), 25)
    clock.now = datetime(2026, 9, 28, 10)
    tracker.add_note("language", "20 new words")

    out = tmp_path / "h.csv"
    assert history.export(out, repo, config, date(2026, 9, 27), date(2026, 9, 28)) == 2
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert len(rows) == 6  # три направления × два дня, заметок по одной
    sport = rows[0]
    assert (sport["day"], sport["item_title"], sport["done"], sport["note"]) == (
        "2026-09-27",
        "Sport",
        "yes",
        "бег 5 км",
    )
    assert rows[5]["note"] == "20 new words"
    assert rows[5]["done"] == "no"

    out = tmp_path / "h.json"
    history.export(out, repo, config, date(2026, 9, 27), date(2026, 9, 28))
    data = json.loads(out.read_text(encoding="utf-8"))
    first = data["days"][0]
    assert first["focus"] == {"sessions": 1, "minutes": 25}
    assert first["items"][0]["notes"][0]["text"] == "бег 5 км"

    with pytest.raises(ValueError):
        history.export(tmp_path / "h.txt", repo, config, date(2026, 9, 27), date(2026, 9, 28))
