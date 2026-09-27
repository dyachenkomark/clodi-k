from datetime import datetime, timedelta

from clodick.core.pomodoro import Event, Phase, Pomodoro, PomodoroConfig

T0 = datetime(2026, 9, 27, 10, 0)


def test_focus_then_short_break_then_idle():
    p = Pomodoro(PomodoroConfig(focus=25, short_break=5))
    p.start_focus(T0, "sport")
    assert p.phase is Phase.FOCUS
    assert p.minutes_left(T0 + timedelta(minutes=0, seconds=30)) == 25
    assert p.check(T0 + timedelta(minutes=24)) is None
    assert p.check(T0 + timedelta(minutes=25)) is Event.FOCUS_DONE
    assert p.phase is Phase.BREAK
    assert p.break_minutes == 5
    assert p.check(T0 + timedelta(minutes=30)) is Event.BREAK_DONE
    assert p.phase is Phase.IDLE
    assert p.key is None


def test_every_fourth_break_is_long():
    p = Pomodoro(PomodoroConfig(focus=1, short_break=1, long_break=15, rounds=4))
    now = T0
    lengths = []
    for _ in range(4):
        p.start_focus(now)
        now += timedelta(minutes=1)
        p.check(now)
        lengths.append(p.break_minutes)
        now += timedelta(minutes=p.break_minutes)
        p.check(now)
    assert lengths == [1, 1, 1, 15]


def test_stop_cancels_without_counting():
    p = Pomodoro(PomodoroConfig())
    p.start_focus(T0, "study")
    p.stop()
    assert not p.active
    assert p.check(T0 + timedelta(hours=1)) is None
    assert p.streak == 0


def test_survives_restart():
    p = Pomodoro(PomodoroConfig())
    p.start_focus(T0, "task:3")
    again = Pomodoro.from_dict(PomodoroConfig(), p.to_dict())
    assert again.phase is Phase.FOCUS
    assert again.key == "task:3"
    assert again.ends == p.ends


def test_broken_saved_state_is_ignored():
    assert Pomodoro.from_dict(PomodoroConfig(), {"phase": "nonsense"}).phase is Phase.IDLE
    assert Pomodoro.from_dict(PomodoroConfig(), {"phase": "focus"}).phase is Phase.IDLE
    assert Pomodoro.from_dict(PomodoroConfig(), None).phase is Phase.IDLE
