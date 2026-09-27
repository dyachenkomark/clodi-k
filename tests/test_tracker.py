from datetime import date, datetime

import pytest

from clodick.core.tracker import Tracker, logical_day


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 9, 26, 3, 59), date(2026, 9, 25)),
        (datetime(2026, 9, 26, 4, 0), date(2026, 9, 26)),
        (datetime(2026, 9, 26, 23, 59), date(2026, 9, 26)),
        (datetime(2026, 1, 1, 1, 0), date(2025, 12, 31)),
    ],
)
def test_logical_day_respects_day_start_hour(moment, expected):
    assert logical_day(moment, day_start_hour=4) == expected


def test_new_day_starts_empty(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    status = tracker.status()
    assert status.day == date(2026, 9, 26)
    assert status.done_count == 0
    assert status.total == 3
    assert not status.all_done


def test_mark_done_is_idempotent(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    assert tracker.mark_done("sport") is True
    assert tracker.mark_done("sport") is False
    status = tracker.status()
    assert status.done_count == 1
    assert status.items[0].done_at == datetime(2026, 9, 26, 12)


def test_unmark(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    assert tracker.unmark("sport") is False
    tracker.mark_done("sport")
    assert tracker.unmark("sport") is True
    assert tracker.status().done_count == 0


def test_after_midnight_counts_for_previous_day(config, repo):
    clock = FakeClock(datetime(2026, 9, 27, 1, 30))
    tracker = Tracker(config, repo, clock=clock)
    tracker.mark_done("study")
    assert tracker.status(date(2026, 9, 26)).done_count == 1

    clock.now = datetime(2026, 9, 27, 9)
    assert tracker.status().done_count == 0


def test_all_done(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    for key in ("sport", "study", "language"):
        tracker.mark_done(key)
    assert tracker.status().all_done


def test_unknown_category_raises(config, repo):
    tracker = Tracker(config, repo)
    with pytest.raises(KeyError):
        tracker.mark_done("chess")


def test_one_off_task_disappears_the_day_after_it_is_done(config, repo):
    clock = FakeClock(datetime(2026, 9, 26, 12))
    tracker = Tracker(config, repo, clock=clock)
    task = tracker.add_task("  Call   Anna ")
    key = f"task:{task.id}"
    assert task.title == "Call Anna"
    status = tracker.status()
    assert status.total == 4
    assert status.items[-1].category.custom

    clock.now = datetime(2026, 9, 27, 12)
    assert key in [i.category.key for i in tracker.status().items]
    tracker.mark_done(key)
    assert tracker.status().all_done is False
    assert tracker.status().items[-1].done

    clock.now = datetime(2026, 9, 28, 12)
    assert key not in [i.category.key for i in tracker.status().items]
    with pytest.raises(KeyError):
        tracker.mark_done(key)


def test_daily_task_repeats_and_goes_before_one_off(config, repo):
    clock = FakeClock(datetime(2026, 9, 26, 12))
    tracker = Tracker(config, repo, clock=clock)
    once = tracker.add_task("Buy milk")
    daily = tracker.add_task("Stretch", daily=True)
    keys = [i.category.key for i in tracker.status().items]
    assert keys[3:] == [f"task:{daily.id}", f"task:{once.id}"]
    tracker.mark_done(f"task:{daily.id}")

    clock.now = datetime(2026, 9, 27, 12)
    item = next(i for i in tracker.status().items if i.category.key == f"task:{daily.id}")
    assert not item.done


def test_remove_task(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    task = tracker.add_task("Buy milk")
    tracker.mark_done(f"task:{task.id}")
    assert tracker.remove_task(f"task:{task.id}") is True
    assert tracker.status().total == 3
    assert tracker.remove_task("sport") is False
    assert tracker.remove_task(f"task:{task.id}") is False


def test_empty_task_title_is_rejected(config, repo):
    tracker = Tracker(config, repo, clock=FakeClock(datetime(2026, 9, 26, 12)))
    with pytest.raises(ValueError):
        tracker.add_task("   ")
