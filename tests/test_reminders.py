from datetime import date, datetime, time

from clodick.core.models import Category, CategoryStatus, DayStatus
from clodick.core.reminders import ReminderClock, parse_times, reminder_text


def test_parse_times_sorted_unique():
    assert parse_times(["20:00", "09:30", "20:00"]) == (time(9, 30), time(20, 0))


def test_fires_once_when_time_passes():
    clock = ReminderClock([time(10, 0)], datetime(2026, 9, 26, 9, 59))
    assert clock.check(datetime(2026, 9, 26, 9, 59, 30)) is False
    assert clock.check(datetime(2026, 9, 26, 10, 0, 10)) is True
    assert clock.check(datetime(2026, 9, 26, 10, 0, 40)) is False


def test_start_after_reminder_does_not_fire():
    clock = ReminderClock([time(10, 0)], datetime(2026, 9, 26, 12, 0))
    assert clock.check(datetime(2026, 9, 26, 12, 1)) is False


def test_sleep_over_several_reminders_fires_once():
    clock = ReminderClock([time(10, 0), time(15, 0)], datetime(2026, 9, 26, 9, 0))
    assert clock.check(datetime(2026, 9, 26, 16, 0)) is True
    assert clock.check(datetime(2026, 9, 26, 16, 1)) is False


def test_crosses_midnight():
    clock = ReminderClock([time(0, 30)], datetime(2026, 9, 26, 23, 50))
    assert clock.check(datetime(2026, 9, 27, 0, 31)) is True


def test_clock_going_back_does_not_refire():
    clock = ReminderClock([time(10, 0)], datetime(2026, 9, 26, 9, 0))
    assert clock.check(datetime(2026, 9, 26, 10, 1)) is True
    assert clock.check(datetime(2026, 9, 26, 9, 30)) is False
    assert clock.check(datetime(2026, 9, 26, 10, 2)) is False


def _status(done):
    items = tuple(
        CategoryStatus(Category(key, title), key in done)
        for key, title in [("sport", "Sport"), ("language", "Call Anna")]
    )
    return DayStatus(date(2026, 9, 26), items)


def test_reminder_text_lists_pending():
    assert reminder_text(_status({"sport"})) == "Hey! Still to do: Call Anna."
    assert reminder_text(_status({"sport", "language"})) is None
