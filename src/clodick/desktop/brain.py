"""Поведение персонажа: сидит, спит, машет, гуляет, чем-то занят. Без Qt, чтобы легко тестировать.

Экран для персонажа — пол, на который смотрят сверху под углом. Координаты x, y — левый
верхний угол кадра персонажа на экране, в логических пикселях.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

from clodick.desktop.actions import Action


class Mode(Enum):
    SIT = "sit"
    SLEEP = "sleep"
    WAVE = "wave"
    WALK = "walk"
    # Занят действием из actions.py: какое — в Brain.action.
    ACT = "act"
    # Лазает по правому краю экрана: вверх, висит, вниз.
    CLIMB = "climb"


# Куда смотрит на ходу: восемь направлений через 45°. Экран: y растёт вниз.
RIGHT, LEFT, UP, DOWN = "right", "left", "up", "down"
DOWN_RIGHT, DOWN_LEFT, UP_RIGHT, UP_LEFT = "down_right", "down_left", "up_right", "up_left"
DIRECTIONS = (RIGHT, DOWN_RIGHT, DOWN, DOWN_LEFT, LEFT, UP_LEFT, UP, UP_RIGHT)

# Настроение: обычное, спокойное (фокус, ночь) и игривое (перерыв).
NORMAL, CALM, LIVELY = "normal", "calm", "lively"


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
SIT_AT_HOME = (10.0, 30.0)
SIT_OUTSIDE = (4.0, 10.0)
SLEEP = (30.0, 90.0)
WALK_CHANCE = 0.3
SLEEP_CHANCE = 0.1
# Шанс заняться чем-нибудь из actions.py.
ACTION_CHANCE = 0.5
# Ночью персонаж сонный: чаще спит, реже гуляет.
NIGHT_WALK_CHANCE = 0.1
NIGHT_SLEEP_CHANCE = 0.5
# Во сколько раз быстрее обычного шага он отбегает от курсора и носится.
RUSH = 4.0
# Кружится за хвостом: поворот каждые SPIN_STEP секунд.
SPIN_STEP = 0.12
# Носится зигзагом: сколько точек и как далеко от места.
ZOOMIES_POINTS = 4
ZOOMIES_RADIUS = 160.0
# Лазание по правому краю: скорость относительно шага, на какую долю пути до верха
# экрана залезает, сколько висит наверху.
CLIMB_SPEED = 1.0
CLIMB_HEIGHT = (0.35, 0.75)
HANG = (3.0, 6.0)
# Убегает по двойному клику: во сколько раз дальше своей ширины.
FLEE_DISTANCE = 4.0


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
        actions: dict[str, Action] | None = None,
    ) -> None:
        self.home = home
        self.area = area
        self.speed = speed
        self.walks = walks
        # Как далеко от своего места он уходит гулять, в логических пикселях.
        self.roam = roam
        self.rng = rng or random.Random()
        # Какие действия доступны этому персонажу.
        self.actions = actions or {}
        self.mood = NORMAL
        self.x, self.y = home
        self.mode = Mode.SIT
        self.action: str | None = None
        self.facing = DOWN
        # Последнее направление по горизонтали: 1 — вправо, -1 — влево.
        self.side = 1
        self._outside = False
        self._target: tuple[float, float] | None = None
        self._route: list[tuple[float, float]] = []
        self._rush = False
        self._spin = 0.0
        # Лазание: to_edge (идёт к краю), up, hang, down или None.
        self.climb_phase: str | None = None
        self._ground_y = 0.0
        self.sleepy = False
        # Какое действие он начал сам с прошлого pop_started(): чтобы сказать реплику.
        self._started: str | None = None
        self._timer = self._pick(SIT_AT_HOME)

    @property
    def at_home(self) -> bool:
        return not self._outside

    @property
    def is_active(self) -> bool:
        """Нужны ли частые обновления: персонаж двигается, машет или кружится."""
        moving_up_or_down = self.mode is Mode.CLIMB and self.climb_phase != "hang"
        return self.mode in (Mode.WALK, Mode.WAVE) or self.action == "spin" or moving_up_or_down

    def pop_started(self) -> str | None:
        started, self._started = self._started, None
        return started

    def place(self, x: float, y: float) -> None:
        """Персонажа перетащили мышью: где отпустили, там теперь его место."""
        self.home = (x, y)
        self.x, self.y = x, y
        self._outside = False
        self._target = None
        self._route = []
        self.climb_phase = None
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
                self._route = []
                self._walk_to(*self.home)

    def set_walks(self, walks: bool) -> None:
        self.walks = walks
        if walks or not self._outside or self.mode is Mode.WAVE:
            return
        if self.mode is Mode.CLIMB:
            self._climb_down()
            return
        self._route = []
        self.climb_phase = None
        self._walk_to(*self.home)

    def wave(self, seconds: float = 5.0) -> None:
        """Привлечь внимание: остановиться и помахать. На краю экрана не машет — держится."""
        if self.mode is Mode.CLIMB:
            return
        self._set_mode(Mode.WAVE)
        self._timer = seconds

    def dodge(self, x: float, y: float) -> bool:
        """Отбежать от курсора в точку x, y. Потом он посидит там и вернётся на место.

        Возвращает False, если бежать некуда: точка за краем экрана совпала с текущей.
        """
        x, y = self.area.clamp(x, y)
        if (x, y) == (self.x, self.y):
            return False
        self._outside = True
        self._route = []
        self._walk_to(x, y)
        self._rush = True
        return True

    def approach(self, x: float, y: float, stop: float) -> bool:
        """Подойти посмотреть на точку, остановившись в stop пикселях от неё."""
        if self.mode not in (Mode.SIT, Mode.ACT) or not self.walks:
            return False
        distance = math.dist((self.x, self.y), (x, y))
        if distance <= stop + self.speed:
            return False
        k = (distance - stop) / distance
        tx, ty = self.area.clamp(self.x + (x - self.x) * k, self.y + (y - self.y) * k)
        if math.dist((tx, ty), self.home) > self.roam:
            return False
        self._outside = True
        self._walk_to(tx, ty)
        return True

    def flee(self, from_x: float, from_y: float, width: float) -> bool:
        """Убежать подальше от точки, например от двойного клика. Потом вернётся на место."""
        if self.mode is Mode.CLIMB:
            return False
        cx, cy = self.x + width / 2, self.y + width / 2
        dx, dy = cx - from_x, cy - from_y
        length = math.hypot(dx, dy) or 1.0
        if length < 1.5:
            dx, dy, length = self.rng.choice((-1.0, 1.0)), 0.0, 1.0
        distance = width * FLEE_DISTANCE
        dx, dy = dx / length * distance, dy / length * distance
        return self.dodge(self.x + dx, self.y + dy) or self.dodge(self.x - dx, self.y - dy)

    def climb(self) -> bool:
        """Пойти к правому краю экрана и полезть по нему вверх, как по дереву."""
        if not self.walks or self.mode is Mode.CLIMB:
            return False
        edge = self.area.right
        if abs(edge - self.x) > self.roam * 2 or self.y - self.area.top < self.speed * 3:
            return False
        self._outside = True
        self._route = []
        self.climb_phase = "to_edge"
        if self.x == edge:
            self._arrive()
        else:
            self._walk_to(edge, self.y)
        return True

    def act(self, name: str, seconds: float) -> None:
        """Заняться действием на месте: поесть, похлопать. Прогулку не прерывает."""
        if self.mode in (Mode.WALK, Mode.CLIMB):
            return
        self._set_mode(Mode.ACT, name)
        self._timer = seconds

    def wake(self) -> None:
        if self.mode is Mode.SLEEP:
            self._sit()

    def tick(self, dt: float) -> None:
        if self.mode is Mode.WALK:
            self._step(dt)
            return
        if self.mode is Mode.CLIMB:
            self._climb_tick(dt)
            return
        if self.action == "spin":
            self._spin += dt
            while self._spin >= SPIN_STEP:
                self._spin -= SPIN_STEP
                i = DIRECTIONS.index(self.facing)
                self.facing = DIRECTIONS[(i + 1) % len(DIRECTIONS)]
        self._timer -= dt
        if self._timer > 0:
            return
        if self._outside and self.mode in (Mode.SIT, Mode.WAVE, Mode.ACT):
            self._walk_to(*self.home)
        elif self.mode is Mode.SIT:
            self._decide()
        else:
            self._sit()

    # --- решения ---

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
            self._set_mode(Mode.SLEEP)
            self._timer = self._pick(SLEEP)
            return
        if roll < walk + sleep + ACTION_CHANCE:
            name = self._pick_action()
            if name is not None:
                self._start(name)
                return
        self._sit()

    def _pick_action(self) -> str | None:
        """Случайное действие с учётом настроения: спокойное, обычное или игривое."""
        mood = CALM if self.sleepy else self.mood
        weights = {}
        for name, action in self.actions.items():
            weight = action.weight
            if mood == CALM and not action.calm:
                weight = 0
            elif mood == LIVELY and action.lively:
                weight *= 3
            if action.kind in ("zoomies", "climb") and not self.walks:
                weight = 0
            if weight > 0:
                weights[name] = weight
        if not weights:
            return None
        roll = self.rng.random() * sum(weights.values())
        for name, weight in weights.items():
            roll -= weight
            if roll < 0:
                return name
        return name

    def _start(self, name: str) -> None:
        action = self.actions[name]
        self._started = name
        if action.kind == "climb":
            if not self.climb():
                self._started = None
                self._sit()
            return
        if action.kind == "zoomies":
            self._route = [self._zoomies_point() for _ in range(ZOOMIES_POINTS)]
            self._outside = True
            x, y = self._route.pop(0)
            self._walk_to(x, y)
            self._rush = True
            return
        self._set_mode(Mode.ACT, name)
        self._spin = 0.0
        self._timer = self._pick(action.seconds)

    def _zoomies_point(self) -> tuple[float, float]:
        hx, hy = self.home
        angle = self.rng.uniform(0, 2 * math.pi)
        distance = self.rng.uniform(ZOOMIES_RADIUS / 3, ZOOMIES_RADIUS)
        return self.area.clamp(hx + distance * math.cos(angle), hy + distance * math.sin(angle))

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

    # --- движение ---

    def _walk_to(self, x: float, y: float) -> None:
        self._set_mode(Mode.WALK)
        self._target = (x, y)
        self._rush = False
        dx, dy = x - self.x, y - self.y
        if dx:
            self.side = 1 if dx > 0 else -1
        if dx or dy:
            # Ближайшее из восьми направлений: 30° и 60° — диагональ, 15° — вбок.
            angle = math.degrees(math.atan2(dy, dx)) % 360
            self.facing = DIRECTIONS[round(angle / 45) % 8]

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
        if self.climb_phase == "to_edge":
            # У края: полез вверх на случайную высоту.
            self._ground_y = self.y
            share = self.rng.uniform(*CLIMB_HEIGHT)
            top = self.y - (self.y - self.area.top) * share
            self._set_mode(Mode.CLIMB)
            self.climb_phase = "up"
            self.facing = UP
            self._target = (self.x, top)
            return
        if self._route:
            x, y = self._route.pop(0)
            self._walk_to(x, y)
            self._rush = True
            return
        self._rush = False
        if (self.x, self.y) == self.home:
            self._outside = False
            self.facing = DOWN
            self._sit()
        else:
            self._set_mode(Mode.SIT)
            self._timer = self._pick(SIT_OUTSIDE)

    def _climb_tick(self, dt: float) -> None:
        if self.climb_phase == "hang":
            self._timer -= dt
            if self._timer <= 0:
                self._climb_down()
            return
        assert self._target is not None
        ty = self._target[1]
        step = self.speed * CLIMB_SPEED * dt
        if abs(ty - self.y) <= step:
            self.y = ty
            if self.climb_phase == "up":
                self.climb_phase = "hang"
                self._timer = self._pick(HANG)
            else:
                # Слез: посидит внизу и пойдёт домой.
                self.climb_phase = None
                self._target = None
                self.facing = DOWN
                self._set_mode(Mode.SIT)
                self._timer = self._pick(SIT_OUTSIDE)
        else:
            self.y += step if ty > self.y else -step

    def _climb_down(self) -> None:
        self.climb_phase = "down"
        self.facing = DOWN
        self._target = (self.x, self._ground_y)

    def _sit(self) -> None:
        self._set_mode(Mode.SIT)
        self._timer = self._pick(SIT_OUTSIDE if self._outside else SIT_AT_HOME)

    def _set_mode(self, mode: Mode, action: str | None = None) -> None:
        if self.action == "spin" and action != "spin":
            self.facing = DOWN
        self.mode = mode
        self.action = action

    def _pick(self, span: tuple[float, float]) -> float:
        return self.rng.uniform(*span)
