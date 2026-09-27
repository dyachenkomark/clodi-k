"""Поведение персонажа: сидит, спит, машет, гуляет, возится. Без Qt, чтобы легко тестировать.

Экран для персонажа — пол, на который смотрят сверху под углом. Координаты x, y — левый
верхний угол кадра персонажа на экране, в логических пикселях.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    SIT = "sit"
    SLEEP = "sleep"
    WAVE = "wave"
    WALK = "walk"
    # Необязательные позы: есть не у каждого персонажа.
    WASH = "wash"
    STRETCH = "stretch"
    EAT = "eat"


# Чем персонаж может заняться сам, пока сидит.
FIDGETS = (Mode.WASH, Mode.STRETCH)

# Куда смотрит на ходу.
RIGHT, LEFT, UP, DOWN = "right", "left", "up", "down"


@dataclass(frozen=True)
class Area:
    """Где может стоять левый верхний угол кадра персонажа."""

    left: float
    top: float
    right: float
    bottom: float

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, self.left), self.right), min(max(y, self.top), self.bottom)


# Сколько секунд длится каждое занятие: (минимум, максимум).
SIT_AT_HOME = (15.0, 45.0)
SIT_OUTSIDE = (4.0, 10.0)
SLEEP = (45.0, 120.0)
WALK_CHANCE = 0.4
SLEEP_CHANCE = 0.15
# Ночью персонаж сонный: чаще спит, реже гуляет.
NIGHT_WALK_CHANCE = 0.1
NIGHT_SLEEP_CHANCE = 0.6
# Во сколько раз быстрее обычного шага он отбегает от курсора.
RUSH = 4.0
# Шанс повозиться (потереть лапки, потянуться) и сколько это длится.
FIDGET_CHANCE = 0.3
FIDGET = (2.5, 4.0)


class Brain:
    def __init__(
        self,
        home: tuple[float, float],
        area: Area,
        *,
        speed: float,
        walks: bool = True,
        roam: float = 500.0,
        rng: random.Random | None = None,
        fidgets: tuple[Mode, ...] = (),
    ) -> None:
        self.home = home
        self.area = area
        self.speed = speed
        self.walks = walks
        # Как далеко от своего места он уходит гулять, в логических пикселях.
        self.roam = roam
        self.rng = rng or random.Random()
        self.fidgets = fidgets
        self.x, self.y = home
        self.mode = Mode.SIT
        self.facing = DOWN
        # Последнее направление по горизонтали: 1 — вправо, -1 — влево.
        self.side = 1
        self._outside = False
        self._target: tuple[float, float] | None = None
        self._rush = False
        self.sleepy = False
        self._timer = self._pick(SIT_AT_HOME)

    @property
    def at_home(self) -> bool:
        return not self._outside

    @property
    def is_active(self) -> bool:
        """Нужны ли частые обновления: персонаж двигается или машет."""
        return self.mode in (Mode.WALK, Mode.WAVE)

    def place(self, x: float, y: float) -> None:
        """Персонажа перетащили мышью: где отпустили, там теперь его место."""
        self.home = (x, y)
        self.x, self.y = x, y
        self._outside = False
        self._target = None
        self._sit()

    def set_area(self, area: Area) -> None:
        """Сменился экран или размер персонажа. Место и позиция остаются в его пределах."""
        self.area = area
        self.home = area.clamp(*self.home)
        if self.at_home:
            self.x, self.y = self.home
        else:
            self.x, self.y = area.clamp(self.x, self.y)
            if self.mode is Mode.WALK:
                self._walk_to(*self.home)

    def set_walks(self, walks: bool) -> None:
        self.walks = walks
        if not walks and self._outside and self.mode is not Mode.WAVE:
            self._walk_to(*self.home)

    def wave(self, seconds: float = 5.0) -> None:
        """Привлечь внимание: остановиться и помахать."""
        self.mode = Mode.WAVE
        self._timer = seconds

    def dodge(self, x: float, y: float) -> bool:
        """Отбежать от курсора в точку x, y. Потом он посидит там и вернётся на место.

        Возвращает False, если бежать некуда: точка за краем экрана совпала с текущей.
        """
        x, y = self.area.clamp(x, y)
        if (x, y) == (self.x, self.y):
            return False
        self._outside = True
        self._walk_to(x, y)
        self._rush = True
        return True

    def act(self, mode: Mode, seconds: float) -> None:
        """Заняться чем-то на месте: поесть, потянуться. Прогулку не прерывает."""
        if self.mode is Mode.WALK:
            return
        self.mode = mode
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
        if self._outside and self.mode in (Mode.SIT, Mode.WAVE):
            self._walk_to(*self.home)
        elif self.mode is Mode.SIT:
            self._decide()
        else:
            self._sit()

    def _decide(self) -> None:
        roll = self.rng.random()
        walk, sleep = (
            (NIGHT_WALK_CHANCE, NIGHT_SLEEP_CHANCE) if self.sleepy else (WALK_CHANCE, SLEEP_CHANCE)
        )
        if self.walks and roll < walk:
            target = self._pick_walk_target()
            if target is not None:
                self._outside = True
                self._walk_to(*target)
                return
        if roll < walk + sleep:
            self.mode = Mode.SLEEP
            self._timer = self._pick(SLEEP)
            return
        if self.fidgets and roll < walk + sleep + FIDGET_CHANCE:
            self.mode = self.rng.choice(self.fidgets)
            self._timer = self._pick(FIDGET)
            return
        self._sit()

    def _pick_walk_target(self) -> tuple[float, float] | None:
        """Случайная точка в пределах roam от дома, не ближе трёх секунд ходьбы."""
        min_distance = self.speed * 3
        if self.roam < min_distance:
            return None
        hx, hy = self.home
        for _ in range(12):
            angle = self.rng.uniform(0, 2 * math.pi)
            distance = self.rng.uniform(min_distance, self.roam)
            x, y = self.area.clamp(hx + distance * math.cos(angle), hy + distance * math.sin(angle))
            if math.dist((x, y), self.home) >= min_distance:
                return x, y
        return None

    def _walk_to(self, x: float, y: float) -> None:
        self.mode = Mode.WALK
        self._target = (x, y)
        self._rush = False
        dx, dy = x - self.x, y - self.y
        if dx:
            self.side = 1 if dx > 0 else -1
        if abs(dx) >= abs(dy):
            if dx:
                self.facing = RIGHT if dx > 0 else LEFT
        else:
            self.facing = DOWN if dy > 0 else UP

    def _step(self, dt: float) -> None:
        assert self._target is not None
        tx, ty = self._target
        distance = math.dist((self.x, self.y), (tx, ty))
        step = self.speed * dt * (RUSH if self._rush else 1.0)
        if distance <= step:
            self.x, self.y = tx, ty
            self._arrive()
        else:
            self.x += (tx - self.x) * step / distance
            self.y += (ty - self.y) * step / distance

    def _arrive(self) -> None:
        self._target = None
        self._rush = False
        if (self.x, self.y) == self.home:
            self._outside = False
            self.facing = DOWN
            self._sit()
        else:
            self.mode = Mode.SIT
            self._timer = self._pick(SIT_OUTSIDE)

    def _sit(self) -> None:
        self.mode = Mode.SIT
        self._timer = self._pick(SIT_OUTSIDE if self._outside else SIT_AT_HOME)

    def _pick(self, span: tuple[float, float]) -> float:
        return self.rng.uniform(*span)
