"""Поведение персонажа: сидит, спит, машет, гуляет. Без Qt, чтобы легко тестировать.

Координата x — левый край окна персонажа на экране, в логических пикселях.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    SIT = "sit"
    SLEEP = "sleep"
    WAVE = "wave"
    WALK = "walk"


@dataclass(frozen=True)
class Bounds:
    """Допустимые значения x для персонажа."""

    left: float
    right: float


# Сколько секунд длится каждое занятие: (минимум, максимум).
SIT_AT_HOME = (60.0, 150.0)
SIT_OUTSIDE = (4.0, 10.0)
SLEEP = (60.0, 180.0)
WALK_CHANCE = 0.35
SLEEP_CHANCE = 0.2


class Brain:
    def __init__(
        self,
        home_x: float,
        bounds: Bounds,
        *,
        speed: float,
        walks: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self.home_x = home_x
        self.bounds = bounds
        self.speed = speed
        self.walks = walks
        self.rng = rng or random.Random()
        self.x = home_x
        self.mode = Mode.SIT
        self.facing = 1
        self._outside = False
        self._target: float | None = None
        self._timer = self._pick(SIT_AT_HOME)

    @property
    def at_home(self) -> bool:
        return not self._outside

    @property
    def is_active(self) -> bool:
        """Нужны ли частые обновления: персонаж двигается или машет."""
        return self.mode in (Mode.WALK, Mode.WAVE)

    def place(self, x: float) -> None:
        """Персонажа перетащили мышью: где отпустили, там теперь его место."""
        self.home_x = self.x = x
        self._outside = False
        self._target = None
        self._sit()

    def set_home(self, home_x: float, bounds: Bounds) -> None:
        """Сменилось место или границы. Если персонаж на месте, он остаётся там."""
        self.home_x = home_x
        self.bounds = bounds
        if self.at_home:
            self.x = home_x
        else:
            self.x = min(max(self.x, bounds.left), bounds.right)
            if self.mode is Mode.WALK:
                self._walk_to(home_x)

    def set_walks(self, walks: bool) -> None:
        self.walks = walks
        if not walks and self._outside and self.mode is not Mode.WAVE:
            self._walk_to(self.home_x)

    def wave(self, seconds: float = 5.0) -> None:
        """Привлечь внимание: остановиться и помахать."""
        self.mode = Mode.WAVE
        self._timer = seconds

    def wake(self) -> None:
        if self.mode is Mode.SLEEP:
            self._sit()

    def tick(self, dt: float) -> None:
        if self.mode is Mode.WALK:
            self._step(dt)
            return
        self._timer -= dt
        if self._timer > 0:
            return
        if (self.mode is Mode.WAVE and self._outside) or (self.mode is Mode.SIT and self._outside):
            self._walk_to(self.home_x)
        elif self.mode is Mode.SIT:
            self._decide()
        else:
            self._sit()

    def _decide(self) -> None:
        roll = self.rng.random()
        if self.walks and roll < WALK_CHANCE:
            target = self._pick_walk_target()
            if target is not None:
                self._outside = True
                self._walk_to(target)
                return
        if roll < WALK_CHANCE + SLEEP_CHANCE:
            self.mode = Mode.SLEEP
            self._timer = self._pick(SLEEP)
            return
        self._sit()

    def _pick_walk_target(self) -> float | None:
        min_distance = self.speed * 3
        candidates = []
        if self.home_x - self.bounds.left >= min_distance:
            candidates.append((self.bounds.left, self.home_x - min_distance))
        if self.bounds.right - self.home_x >= min_distance:
            candidates.append((self.home_x + min_distance, self.bounds.right))
        if not candidates:
            return None
        low, high = self.rng.choice(candidates)
        return self.rng.uniform(low, high)

    def _walk_to(self, target: float) -> None:
        self.mode = Mode.WALK
        self._target = target
        if target != self.x:
            self.facing = 1 if target > self.x else -1

    def _step(self, dt: float) -> None:
        assert self._target is not None
        distance = self._target - self.x
        step = self.speed * dt
        if abs(distance) <= step:
            self.x = self._target
            self._arrive()
        else:
            self.x += step if distance > 0 else -step

    def _arrive(self) -> None:
        self._target = None
        if self.x == self.home_x:
            self._outside = False
            self._sit()
        else:
            self.mode = Mode.SIT
            self._timer = self._pick(SIT_OUTSIDE)

    def _sit(self) -> None:
        self.mode = Mode.SIT
        self._timer = self._pick(SIT_OUTSIDE if self._outside else SIT_AT_HOME)

    def _pick(self, span: tuple[float, float]) -> float:
        return self.rng.uniform(*span)
