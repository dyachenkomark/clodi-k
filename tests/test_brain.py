import math
import random

import pytest

from clodick.desktop.brain import DOWN, LEFT, RIGHT, SIT_AT_HOME, UP, Area, Brain, Mode

AREA = Area(0, 0, 1000, 800)


class ScriptedRng(random.Random):
    """random() отдаёт заранее заданные значения, остальное — обычный генератор."""

    def __init__(self, rolls):
        super().__init__(1)
        self._rolls = list(rolls)

    def random(self):
        return self._rolls.pop(0) if self._rolls else 0.99

    def uniform(self, a, b):
        return a + (b - a) * super().random()


def make_brain(rolls=(), walks=True, home=(500.0, 400.0), roam=300.0, area=AREA):
    return Brain(home, area, speed=40.0, walks=walks, roam=roam, rng=ScriptedRng(rolls))


def run(brain, seconds, step=0.1):
    for _ in range(int(seconds / step)):
        brain.tick(step)


def run_until(brain, predicate, max_seconds=600, step=0.1):
    for _ in range(int(max_seconds / step)):
        if predicate(brain):
            return
        brain.tick(step)
    raise AssertionError("не дождались")


def walking(brain):
    return brain.mode is Mode.WALK


def test_starts_sitting_at_home():
    brain = make_brain()
    assert brain.mode is Mode.SIT
    assert brain.at_home
    assert (brain.x, brain.y) == (500, 400)


def test_walk_out_within_roam_and_come_back():
    brain = make_brain(rolls=[0.1])
    run_until(brain, walking, SIT_AT_HOME[1] + 1)
    assert not brain.at_home
    target = brain._target
    assert math.dist(target, (500, 400)) <= 300 + 1e-6

    run(brain, 60)
    assert brain.at_home
    assert (brain.x, brain.y) == (500, 400)
    assert brain.mode in (Mode.SIT, Mode.SLEEP)
    assert brain.facing == DOWN


def test_walks_in_both_axes():
    ys = set()
    for seed in range(20):
        brain = Brain((500.0, 400.0), AREA, speed=40.0, roam=300.0, rng=random.Random(seed))
        for _ in range(3000):
            brain.tick(0.1)
            ys.add(round(brain.y))
    assert len(ys) > 50


@pytest.mark.parametrize(
    ("target", "facing"),
    [((600, 400), RIGHT), ((400, 400), LEFT), ((500, 200), UP), ((510, 600), DOWN)],
)
def test_facing_follows_main_direction(target, facing):
    brain = make_brain()
    brain._walk_to(*target)
    assert brain.facing == facing


def test_side_remembers_last_horizontal_direction():
    brain = make_brain()
    brain._walk_to(400, 400)
    brain._walk_to(400 - 1, 100)
    assert brain.facing == UP
    assert brain.side == -1


def test_no_walks_when_disabled():
    brain = make_brain(rolls=[0.1] * 10, walks=False)
    run(brain, 600, step=1.0)
    assert brain.at_home


def test_falls_asleep_and_wakes():
    brain = make_brain(rolls=[0.5])
    run_until(brain, lambda b: b.mode is Mode.SLEEP, SIT_AT_HOME[1] + 1)
    brain.wake()
    assert brain.mode is Mode.SIT


def test_wave_then_returns_home():
    brain = make_brain(rolls=[0.1])
    run_until(brain, walking, SIT_AT_HOME[1] + 1)
    run(brain, 1)
    brain.wave(2)
    pos = (brain.x, brain.y)
    run(brain, 1)
    assert brain.mode is Mode.WAVE
    assert (brain.x, brain.y) == pos
    run(brain, 60)
    assert brain.at_home


def test_smaller_area_pulls_home_inside():
    brain = make_brain(home=(900.0, 700.0))
    brain.set_area(Area(0, 0, 500, 500))
    assert brain.home == (500, 500)
    assert (brain.x, brain.y) == (500, 500)


def test_disabling_walks_sends_raccoon_home():
    brain = make_brain(rolls=[0.1])
    run_until(brain, walking, SIT_AT_HOME[1] + 1)
    brain.set_walks(False)
    run(brain, 60)
    assert brain.at_home


@pytest.mark.parametrize("home", [(0.0, 0.0), (1000.0, 800.0)])
def test_walk_stays_in_area(home):
    brain = Brain(home, AREA, speed=40.0, roam=2000.0, rng=random.Random(7))
    for _ in range(20000):
        brain.tick(0.1)
        assert 0 <= brain.x <= 1000
        assert 0 <= brain.y <= 800


def test_no_room_to_walk():
    brain = make_brain(rolls=[0.1] * 10, roam=50.0)
    run(brain, 600, step=1.0)
    assert brain.at_home


def test_place_makes_new_home_and_stops_walk():
    brain = make_brain()
    brain._outside = True
    brain._walk_to(100.0, 100.0)
    brain.place(300.0, 200.0)
    assert (brain.x, brain.y) == brain.home == (300.0, 200.0)
    assert brain.at_home
    assert brain.mode is Mode.SIT
    run(brain, 1)
    assert (brain.x, brain.y) == (300.0, 200.0)


def test_dodge_runs_fast_then_goes_home():
    brain = make_brain()
    assert brain.dodge(600.0, 400.0)
    assert brain.mode is Mode.WALK
    brain.tick(0.5)
    assert brain.x > 500 + 40 * 0.5 * 2  # быстрее обычного шага
    run(brain, 1)
    assert (brain.x, brain.y) == (600.0, 400.0)
    assert not brain.at_home
    run(brain, 30)
    assert brain.at_home


def test_dodge_is_clamped_to_screen():
    brain = make_brain(home=(990.0, 400.0))
    brain.dodge(2000.0, 400.0)
    run(brain, 5)
    assert brain.x == 1000.0
    assert not make_brain(home=(1000.0, 400.0)).dodge(2000.0, 400.0)


def test_sleepy_brain_sleeps_more():
    awake = make_brain(rolls=[0.6])
    awake._decide()
    assert awake.mode is Mode.SIT

    sleepy = make_brain(rolls=[0.6])
    sleepy.sleepy = True
    sleepy._decide()
    assert sleepy.mode is Mode.SLEEP


def test_fidgets_only_when_available():
    plain = make_brain(rolls=[0.7])
    plain._decide()
    assert plain.mode is Mode.SIT

    busy = make_brain(rolls=[0.7])
    busy.fidgets = (Mode.WASH,)
    busy._decide()
    assert busy.mode is Mode.WASH
    run(busy, 5)
    assert busy.mode is Mode.SIT


def test_act_does_not_interrupt_walk():
    brain = make_brain()
    brain._walk_to(100.0, 100.0)
    brain.act(Mode.EAT, 3.0)
    assert brain.mode is Mode.WALK
