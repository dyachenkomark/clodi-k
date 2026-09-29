"""Рисует енота в виде сверху под углом и пишет пакет персонажа.

    uv run python tools/raccoon_art.py src/clodick/assets/characters/raccoon/character.toml

Енот собирается из фигур: тело, голова, уши, лапы, полосатый хвост. Каждый слой
получает контур и кладётся поверх предыдущих, дальние части рисуются первыми.
Экран для енота — пол, поэтому он стоит на четырёх лапах, а хвост лежит на полу.
"""

from __future__ import annotations

import sys
from pathlib import Path

W, H = 28, 20

PALETTE = {
    "K": "#26262e",  # контур
    "G": "#8b909b",  # серая шерсть
    "g": "#5d626d",  # тёмная шерсть, дальние лапы
    "W": "#ecebef",  # белая шерсть
    "M": "#16161b",  # полоски хвоста
    "m": "#3f424b",  # маска вокруг глаз
    "E": "#ffffff",  # блик в глазу
    "P": "#d98c9c",  # розовое в ушах
    "Z": "#9fc3ff",  # буквы сна
    "C": "#d9a066",  # печенька
    "c": "#6b4226",  # шоколадная крошка
}

VARIANTS = {
    "claude": {
        "K": "#2a2926",
        "G": "#a39e91",
        "g": "#78736a",
        "W": "#faf9f5",
        "M": "#141413",
        "m": "#57534b",
        "P": "#d97757",
        "Z": "#d97757",
    },
    "claude_orange": {
        "K": "#141413",
        "G": "#d97757",
        "g": "#b85c3e",
        "W": "#faf9f5",
        "M": "#141413",
        "m": "#6e3524",
        "P": "#faf9f5",
        "Z": "#d97757",
    },
    "claude_night": {
        "K": "#0f0f0e",
        "G": "#8f8a80",
        "g": "#625e57",
        "W": "#f0eee6",
        "M": "#0f0f0e",
        "m": "#3a3834",
        "P": "#d97757",
        "Z": "#f3c98b",
    },
}


class Layer:
    """Слой пикселей. Контур добавляется вокруг всего слоя при наложении."""

    def __init__(self, raw: bool = False) -> None:
        self.px: dict[tuple[int, int], str] = {}
        # raw — пиксели уже с контуром (шаблон), обводить не нужно.
        self.raw = raw

    def set(self, x: int, y: int, ch: str) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.px[(x, y)] = ch

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, ch: str, only=False) -> None:
        """Заливка эллипса. only=True красит только уже занятые пиксели слоя."""
        for y in range(H):
            for x in range(W):
                inside = ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1
                if inside and (not only or (x, y) in self.px):
                    self.set(x, y, ch)

    def rect(self, x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, ch)

    def outlined(self) -> dict[tuple[int, int], str]:
        out = dict(self.px)
        for x, y in self.px:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n not in self.px and 0 <= n[0] < W and 0 <= n[1] < H:
                    out.setdefault(n, "K")
        return out


def compose(*layers: Layer) -> list[str]:
    grid = [["."] * W for _ in range(H)]
    for layer in layers:
        for (x, y), ch in (layer.px if layer.raw else layer.outlined()).items():
            grid[y][x] = ch
    return ["".join(row) for row in grid]


def striped_tail(points, radii, rings=3) -> Layer:
    """Пушистый хвост по точкам от основания к кончику: серый с чёрными кольцами.

    Между точками вставляются промежуточные, кольцо — каждый rings-й шаг, кончик чёрный.
    """
    dense = []
    for (x0, y0), (x1, y1), r0, r1 in zip(points, points[1:], radii, radii[1:], strict=False):
        for k in range(3):
            t = k / 3
            dense.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r0 + (r1 - r0) * t))
    dense.append((*points[-1], radii[-1]))
    tail = Layer()
    for i, (x, y, r) in enumerate(dense):
        ring = i % rings == rings - 1 or i == len(dense) - 1
        tail.ellipse(x, y, r, r, "M" if ring else "G")
    return tail


# ---------------- морда анфас ----------------


def stamp(rows: list[str], ox: int, oy: int) -> Layer:
    """Шаблон с контуром в слой: точка — прозрачно."""
    layer = Layer(raw=True)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                layer.set(ox + x, oy + y, ch)
    return layer


# Голова анфас 16×13. Острые уши с белой каймой, маска-«очки» с серой полоской
# на лбу, белые щёки в стороны, крупные блестящие глаза, нос и улыбка.
FRONT_HEAD = [
    ".KK..........KK.",
    "KWGK........KGWK",
    "KWPGK......KGPWK",
    "KWPGGKKKKKKGGPWK",
    ".KGGGGGGGGGGGGK.",
    "KGWWGGGggGGGWWGK",
    "KmmmmmmmGGmmmmmK",
    "KmmmmmmmGGmmmmmK",
    "KWmmmWWKKWWmmmWK",
    "KWWmWWWWWWWWmWWK",
    ".KWWWWKWWKWWWWK.",
    "..KWWWWKKWWWWK..",
    "...KKKWWWWKKK...",
]
# Где глаза: левый верхний пиксель каждого глаза 2×2 (строка 6).
EYES = (3, 11)


def front_face(*, eyes="open", look=0, mouth=None) -> list[str]:
    rows = [list(r) for r in FRONT_HEAD]
    for left in EYES:
        if eyes == "closed":
            # Довольная дуга ∩ на маске.
            rows[7][left - 1] = rows[6][left] = rows[6][left + 1] = rows[7][left + 2] = "K"
        else:
            x = left + look
            rows[6][x], rows[6][x + 1] = "E", "K"
            rows[7][x], rows[7][x + 1] = "K", "K"
    if mouth == "yawn":
        rows[10][7] = rows[10][8] = "M"
        rows[11][7] = rows[11][8] = "P"
    elif mouth == "open":
        rows[10][7] = rows[10][8] = "M"
        rows[11][7] = rows[11][8] = "W"
    return ["".join(r) for r in rows]


# Голова сбоку, смотрит вправо, 13×10.
SIDE_HEAD = [
    "..KK.........",
    ".KWPK........",
    ".KWGGKKKK....",
    "KGGGGGGGGK...",
    "KGGGWWWGGGK..",
    "KGmmmEKmmmK..",
    "KGGmmKKmWWWKK",
    "KGWWWWWWWWWKK",
    ".KWPWWWKWWK..",
    "..KKKKKKKKK..",
]

# Голова со спины 16×11: уши, затылок, края маски по бокам.
BACK_HEAD = [
    ".KK..........KK.",
    "KWGK........KGWK",
    "KWGGK......KGGWK",
    "KWGGGKKKKKKGGGWK",
    ".KGGGGGGGGGGGGK.",
    "KGGGGGGggGGGGGGK",
    "KmGGGGGggGGGGGmK",
    "KmmGGGGggGGGGmmK",
    ".KWGGGGGGGGGGWK.",
    "..KKGGGGGGGGKK..",
    "....KKKKKKKK....",
]

# Голова спящего клубком, смотрит влево-вниз, 11×9. Глаза закрыты, улыбается.
SLEEP_HEAD = [
    ".KK....KK..",
    "KWPK..KPWK.",
    "KGGGKKGGGGK",
    "KGWWGgGWWGK",
    "KmKmmGmmKmK",
    "KmmKmGmKmmK",
    "KPWWWKWWWPK",
    ".KWWKWKWWK.",
    "..KKWWWKK..",
]


# ---------------- сидит анфас ----------------


def sit(
    *, eyes="open", look=0, mouth=None, paws="down", paw_phase=0, cookie=None, arms_up=False
) -> list[str]:
    cx = 14.0
    tail = striped_tail(
        [(18.5, 15.6), (21.5, 16.9), (24.0, 17.0), (25.6, 15.8)], [2.2, 2.2, 1.9, 1.1]
    )
    hind = Layer()
    hind.ellipse(9.2, 17.3, 2.6, 1.5, "g")
    hind.ellipse(18.8, 17.3, 2.6, 1.5, "g")
    body = Layer()
    body.ellipse(cx, 14.2, 5.6, 4.9, "G")
    body.ellipse(cx, 15.2, 3.9, 2.9, "W", only=True)
    front = Layer()
    if paws == "down":
        front.ellipse(11.8, 18.0, 1.5, 1.1, "G")
        front.ellipse(16.2, 18.0, 1.5, 1.1, "G")
    elif paws == "wash":
        dx = (0.6, -0.6)[paw_phase % 2]
        front.ellipse(12.9 + dx, 14.2, 1.5, 1.3, "G")
        front.ellipse(15.1 - dx, 14.2, 1.5, 1.3, "G")
    elif paws == "wave":
        front.ellipse(16.2, 18.0, 1.5, 1.1, "G")
        front.ellipse(6.4, 9.0 - paw_phase, 1.5, 1.5, "G")
        front.rect(7, 10 - paw_phase, 8, 13, "G")
    if arms_up:
        front.ellipse(6.6, 5.5, 1.5, 1.5, "G")
        front.rect(7, 6, 8, 12, "G")
        front.ellipse(21.4, 5.5, 1.5, 1.5, "G")
        front.rect(19, 6, 20, 12, "G")
    snack = Layer()
    if cookie:
        snack.ellipse(cx, 14.2, 2.6, 1.8, "C")
        snack.set(13, 14, "c")
        snack.set(15, 15, "c")
        if cookie == "bitten":
            for x, y in ((15, 13), (16, 13), (16, 14)):
                snack.px.pop((x, y), None)
        front.ellipse(11.2, 14.4, 1.3, 1.3, "G")
        front.ellipse(16.8, 14.4, 1.3, 1.3, "G")
    head = stamp(front_face(eyes=eyes, look=look, mouth=mouth), 6, 0)
    return compose(tail, hind, body, head, snack, front)


# ---------------- спит клубком ----------------


def sleep(frame: int) -> list[str]:
    breathe = 0.3 * frame
    body = Layer()
    body.ellipse(14.5, 12.6, 7.4 + breathe, 5.9 + breathe, "G")
    head = stamp(SLEEP_HEAD, 3, 7)
    tail = striped_tail(
        [(21.0, 15.0), (18.6, 16.9), (15.6, 17.6), (12.6, 17.4), (10.0, 16.3)],
        [2.3, 2.3, 2.2, 2.0, 1.2],
    )
    zs = Layer()
    z = [(0, 0), (1, 0), (2, 0), (3, 0), (2, 1), (1, 2), (0, 3), (1, 3), (2, 3), (3, 3)]
    ox, oy = ((20, 3), (23, 0))[frame]
    letters = [(ox + x, oy + y) for x, y in z]
    for x, y in letters:
        zs.set(x, y, "Z")
    grid = compose(body, head, tail)
    rows = [list(r) for r in grid]
    for (x, y), ch in zs.px.items():
        rows[y][x] = ch
    return ["".join(r) for r in rows]


# ---------------- идёт вбок (вправо) ----------------


def walk_side(phase: int) -> list[str]:
    swing = (1, 0, -1, 0)[phase]
    bob = (0, 1, 0, 1)[phase] * 0  # тело не прыгает, шаг видно по лапам
    far = Layer()
    for x in (8 - swing, 17 + swing):
        far.rect(x, 14 + bob, x + 1, 18, "g")
    tail = striped_tail([(6.4, 11.6), (4.0, 10.6), (2.0, 8.9)], [2.4, 2.2, 1.1])
    body = Layer()
    body.ellipse(12.8, 12.2 + bob, 7.6, 3.9, "G")
    for x in range(6, 20):
        if (x, 15 + bob) in body.px:
            body.set(x, 15 + bob, "W")
    near = Layer()
    for x in (7 + swing, 16 - swing):
        near.rect(x, 14 + bob, x + 1, 18, "G")
        near.set(x, 18, "g")
        near.set(x + 1, 18, "g")
    head = stamp(SIDE_HEAD, 15, 2)
    return compose(far, tail, body, near, head)


# ---------------- идёт к зрителю ----------------


def walk_down(phase: int) -> list[str]:
    lift = (1, 0, -1, 0)[phase]
    tail = striped_tail([(16.5, 6.5), (18.0, 4.2), (19.6, 2.6)], [2.1, 1.9, 1.1])
    body = Layer()
    body.ellipse(14.0, 11.6, 6.4, 5.2, "G")
    legs = Layer()
    for x, up in ((10, lift > 0), (16, lift < 0)):
        legs.rect(x, 13, x + 1, 17 if up else 18, "G")
        legs.rect(x, 17 if up else 18, x + 1, 17 if up else 18, "g")
    head = stamp(front_face(), 6, 2)
    return compose(tail, body, legs, head)


# ---------------- идёт от зрителя ----------------


def walk_up(phase: int) -> list[str]:
    lift = (1, 0, -1, 0)[phase]
    head = stamp(BACK_HEAD, 6, 0)
    body = Layer()
    body.ellipse(14.0, 11.4, 6.2, 5.0, "G")
    body.ellipse(14.0, 10.6, 1.0, 3.6, "g", only=True)
    legs = Layer()
    for x, up in ((9, lift > 0), (17, lift < 0)):
        legs.rect(x, 14, x + 1, 16 if up else 17, "g")
    tail = striped_tail([(14.0, 14.4), (14.3, 16.0), (15.0, 17.6)], [2.6, 2.4, 1.3])
    return compose(head, legs, body, tail)


# ---------------- по диагонали ----------------


def walk_down_right(phase: int) -> list[str]:
    """Идёт вниз-вправо: морда к зрителю, тело по диагонали, хвост сзади слева вверху."""
    swing = (1, 0, -1, 0)[phase]
    tail = striped_tail([(9.0, 9.2), (6.6, 7.2), (4.4, 5.4)], [2.3, 2.1, 1.1])
    far = Layer()
    for x in (12 - swing, 19 + swing):
        far.rect(x, 13, x + 1, 16, "g")
    body = Layer()
    body.ellipse(13.8, 11.8, 6.2, 4.3, "G")
    near = Layer()
    for x in (8 + swing, 15 - swing):
        near.rect(x, 14, x + 1, 18, "G")
        near.rect(x, 18, x + 1, 18, "g")
    head = stamp(front_face(), 11, 2)
    return compose(tail, far, body, near, head)


def walk_up_right(phase: int) -> list[str]:
    """Идёт вверх-вправо: затылок справа вверху, хвост к зрителю слева внизу."""
    swing = (1, 0, -1, 0)[phase]
    head = stamp(BACK_HEAD, 11, 0)
    far = Layer()
    for x in (18 - swing, 21 + swing):
        far.rect(x, 11, x + 1, 14, "g")
    body = Layer()
    body.ellipse(14.0, 11.2, 6.4, 4.4, "G")
    body.ellipse(14.4, 10.6, 3.6, 1.0, "g", only=True)
    near = Layer()
    for x in (8 + swing, 12 - swing):
        near.rect(x, 14, x + 1, 18, "G")
        near.rect(x, 18, x + 1, 18, "g")
    tail = striped_tail([(9.6, 14.0), (7.2, 15.8), (5.0, 17.2)], [2.4, 2.2, 1.2])
    return compose(head, far, body, near, tail)


# ---------------- действия ----------------


def limb(layer: Layer, x0: float, y0: float, x1: float, y1: float, ch: str = "G") -> None:
    """Лапа отрезком толщиной два пикселя, на конце подушечка."""
    steps = max(1, round(max(abs(x1 - x0), abs(y1 - y0)) * 2))
    for i in range(steps + 1):
        t = i / steps
        layer.ellipse(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 1.0, 1.0, ch)
    layer.ellipse(x1, y1, 1.4, 1.4, ch)


def raw(points: list[tuple[int, int]], ch: str) -> Layer:
    """Пиксели без контура: ноты, брызги, пар, земля."""
    layer = Layer(raw=True)
    for x, y in points:
        layer.set(x, y, ch)
    return layer


def shift(frame: list[str], dx: int = 0, dy: int = 0) -> list[str]:
    """Сдвиг всего кадра: наклоны в танце, подпрыгивание."""
    out = [["."] * W for _ in range(H)]
    for y, row in enumerate(frame):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= x + dx < W and 0 <= y + dy < H:
                out[y + dy][x + dx] = ch
    return ["".join(r) for r in out]


def rotate_ccw(rows: list[str]) -> list[str]:
    width = len(rows[0])
    return ["".join(row[width - 1 - i] for row in rows) for i in range(width)]


SIT_TAIL = ([(18.5, 15.6), (21.5, 16.9), (24.0, 17.0), (25.6, 15.8)], [2.2, 2.2, 1.9, 1.1])
WAG_TAIL = ([(18.5, 15.4), (21.2, 14.4), (23.2, 12.6), (24.2, 10.6)], [2.2, 2.2, 1.9, 1.1])


def seated(
    *,
    eyes="open",
    look=0,
    mouth=None,
    head_dx=0,
    head_dy=0,
    tail=SIT_TAIL,
    paws_down=(True, True),
    back=(),
    front=(),
) -> list[str]:
    """Сидит анфас: хвост на полу, задние лапы, тело, голова, затем предметы и лапы спереди."""
    tail_layer = striped_tail(*tail)
    hind = Layer()
    hind.ellipse(9.2, 17.3, 2.6, 1.5, "g")
    hind.ellipse(18.8, 17.3, 2.6, 1.5, "g")
    body = Layer()
    body.ellipse(14.0, 14.2, 5.6, 4.9, "G")
    body.ellipse(14.0, 15.2, 3.9, 2.9, "W", only=True)
    feet = Layer()
    for x, down in zip((11.8, 16.2), paws_down, strict=True):
        if down:
            feet.ellipse(x, 18.0, 1.5, 1.1, "G")
    head = stamp(front_face(eyes=eyes, look=look, mouth=mouth), 6 + head_dx, head_dy)
    return compose(*back, tail_layer, hind, body, feet, head, *front)


def arms(*segments: tuple[float, float, float, float]) -> Layer:
    layer = Layer()
    for x0, y0, x1, y1 in segments:
        limb(layer, x0, y0, x1, y1)
    return layer


def note(x: int, y: int) -> list[tuple[int, int]]:
    """Нотка ♪: флажок, палочка, головка."""
    return [(x + 1, y), (x, y), (x, y + 1), (x, y + 2), (x - 1, y + 2), (x - 1, y + 3), (x, y + 3)]


def scratch(frame: int) -> list[str]:
    leg = Layer()
    limb(leg, 8.5, 16.0, 5.6, 6.2 + frame, "g")
    return seated(eyes="closed", head_dx=1, paws_down=(False, True), front=(leg,))


def roll(frame: int) -> list[str]:
    wiggle = (1, -1)[frame]
    tail = striped_tail([(21.5, 15.2), (24.0, 16.0), (26.2, 15.0)], [2.2, 2.0, 1.1])
    body = Layer()
    body.ellipse(15.0, 14.6, 7.2, 3.8, "G")
    body.ellipse(15.0, 13.8, 5.0, 2.2, "W", only=True)
    legs = Layer()
    for x, dx in ((11.0, wiggle), (14.0, -wiggle), (17.5, wiggle), (20.5, -wiggle)):
        limb(legs, x, 12.5, x + dx, 6.8, "G")
    head = stamp(rotate_ccw(front_face(eyes="closed", mouth="open")), 0, 4)
    return compose(tail, body, legs, head)


def dance(frame: int) -> list[str]:
    up = arms((9.0, 12.5, 3.5, 7.5), (19.0, 12.5, 24.5, 7.5))
    chest = arms((10.5, 13.5, 12.0, 14.0), (17.5, 13.5, 16.0, 14.0))
    if frame == 3:
        return seated(eyes="closed", mouth="open", front=(chest,))
    body = seated(eyes="closed", mouth="open", front=(up,))
    return shift(body, dx=(-1, 0, 1)[frame], dy=-1 if frame == 1 else 0)


def peek(frame: int) -> list[str]:
    paws = Layer()
    limb(paws, 9.0, 13.5, 9.8, 7.4)
    paws.ellipse(9.8, 7.0, 2.0, 1.8, "G")
    if frame == 0:
        limb(paws, 19.0, 13.5, 18.2, 7.4)
        paws.ellipse(18.2, 7.0, 2.0, 1.8, "G")
    else:
        limb(paws, 19.0, 13.5, 17.5, 14.5)
    return seated(eyes="open", look=1 if frame else 0, front=(paws,))


def sneeze(frame: int) -> list[str]:
    if frame == 0:
        return seated(eyes="closed")
    if frame == 1:
        spray = raw([(10, 12), (12, 13), (15, 13), (17, 12), (9, 14), (18, 14)], "Z")
        return seated(eyes="closed", mouth="open", head_dy=1, front=(spray,))
    return seated()


def side_pose(*, head_dy=0, legs=(0, 0), extra=()) -> list[str]:
    """Стоит боком, смотрит вправо: для копания и обнюхивания."""
    far = Layer()
    for x in (8, 17):
        far.rect(x, 14, x + 1, 18, "g")
    tail = striped_tail([(6.4, 11.6), (4.0, 10.6), (2.0, 8.9)], [2.4, 2.2, 1.1])
    body = Layer()
    body.ellipse(12.8, 12.2, 7.6, 3.9, "G")
    for x in range(6, 20):
        if (x, 15) in body.px:
            body.set(x, 15, "W")
    near = Layer()
    for x, dx in zip((7, 16), legs, strict=True):
        near.rect(x + dx, 14, x + dx + 1, 18, "G")
        near.rect(x + dx, 18, x + dx + 1, 18, "g")
    head = stamp(SIDE_HEAD, 15, 2 + head_dy)
    return compose(far, tail, body, near, head, *extra)


def dig(frame: int) -> list[str]:
    dirt = [(4, 14), (2, 12), (5, 11), (3, 15)] if frame else [(3, 13), (1, 10), (6, 12), (4, 16)]
    return side_pose(head_dy=3, legs=(0, 2 if frame else -1), extra=(raw(dirt, "c"),))


def sniff(frame: int) -> list[str]:
    return side_pose(head_dy=4 + frame, legs=(0, 0))


def play(frame: int) -> list[str]:
    ball_at = ((23.5, 16.8), (24.5, 12.5), (23.5, 9.5), (21.5, 13.0))[frame]
    ball = Layer()
    ball.ellipse(*ball_at, 1.5, 1.5, "P")
    front = [ball]
    if frame == 3:
        front.insert(0, arms((18.0, 13.5, 20.0, 13.0)))
    return seated(look=1, paws_down=(True, frame != 3), front=tuple(front))


def read(frame: int) -> list[str]:
    book = Layer()
    book.rect(11, 13, 16, 16, "C")
    book.rect(13, 13, 14, 16, "c")
    paws = arms((10.0, 13.0, 10.8, 15.0), (18.0, 13.0, 17.2, 15.0))
    return seated(look=(-1, 1)[frame], front=(book, paws))


def sip(frame: int) -> list[str]:
    lift = 2 if frame else 0
    lift = 3 if frame else 0
    mug = Layer()
    mug.rect(12, 12 - lift, 16, 16 - lift, "P")
    mug.rect(13, 12 - lift, 15, 12 - lift, "c")
    mug.set(11, 13 - lift, "P")
    mug.set(11, 14 - lift, "P")
    steam = raw([(13, 10), (14, 9), (13, 8), (15, 7)], "g") if not frame else Layer()
    paw = arms((19.0, 14.0, 17.4, 14.2 - lift))
    return seated(eyes="closed" if frame else "open", front=(mug, paw, steam))


def clap(frame: int) -> list[str]:
    if frame:
        paws = arms((10.5, 13.5, 13.4, 12.6), (17.5, 13.5, 14.6, 12.6))
    else:
        paws = arms((10.5, 13.5, 10.8, 12.4), (17.5, 13.5, 17.2, 12.4))
    return seated(eyes="closed", mouth="open", front=(paws,))


def doze(frame: int) -> list[str]:
    return seated(eyes="closed", head_dy=frame)


def sing(frame: int) -> list[str]:
    notes = note(22, 2) + note(25, 6) if frame else note(21, 5) + note(24, 1)
    return seated(eyes="closed", mouth="open", front=(raw(notes, "Z"),))


def flex(frame: int) -> list[str]:
    bent = arms(
        (9.5, 12.5, 5.5, 10.5),
        (5.5, 10.5, 6.5, 6.5 - frame),
        (18.5, 12.5, 22.5, 10.5),
        (22.5, 10.5, 21.5, 6.5 - frame),
    )
    sparkle = raw([(3, 5), (25, 5), (2, 8), (26, 8)] if frame else [(4, 3), (24, 3)], "Z")
    return seated(front=(bent, sparkle))


def tailwag(frame: int) -> list[str]:
    return seated(tail=(SIT_TAIL, WAG_TAIL)[frame])


def trash(frame: int) -> list[str]:
    can = Layer()
    can.rect(20, 11, 25, 18, "g")
    can.rect(19, 10, 26, 10, "m")
    for x in (22, 24):
        for y in range(12, 18):
            can.set(x, y, "m")
    if frame == 0:
        reach = arms((17.0, 13.0, 20.5, 10.0))
        figure = seated(look=1, paws_down=(True, False), front=(reach,))
    elif frame == 1:
        reach = arms((17.0, 13.0, 21.5, 11.0))
        figure = seated(eyes="closed", paws_down=(True, False), front=(reach,))
    else:
        paper = Layer()
        paper.rect(3, 2, 6, 4, "W")
        lines = raw([(4, 3), (5, 3)], "g")
        figure = seated(mouth="open", front=(arms((9.5, 12.5, 5.5, 5.5)), paper, lines))
    frame_rows = shift(figure, dx=-3)
    return compose_on(frame_rows, can)


def compose_on(frame: list[str], *layers: Layer) -> list[str]:
    """Положить слои поверх готового кадра."""
    grid = [list(r) for r in frame]
    for layer in layers:
        for (x, y), ch in (layer.px if layer.raw else layer.outlined()).items():
            grid[y][x] = ch
    return ["".join(r) for r in grid]


def hiccup(frame: int) -> list[str]:
    face = {"eyes": "closed", "mouth": "open"} if frame else {}
    return shift(seated(**face), dy=-frame)


# ---------------- лазает по правому краю ----------------


def climb_body(phase: int) -> tuple[Layer, Layer, Layer, Layer]:
    """Тело вертикально, пузом к правому краю кадра (к «стволу»), хвост свисает вниз."""
    reach = (0, 2)[phase % 2]
    far = Layer()
    limb(far, 20.5, 8.5, 26.0, 7.0 + reach, "g")
    limb(far, 20.5, 15.0, 26.0, 16.5 - reach, "g")
    tail = striped_tail(
        [(17.6, 16.4), (15.0, 17.2), (12.4, 17.4), (10.2, 16.6)], [2.2, 2.1, 1.9, 1.1]
    )
    body = Layer()
    body.ellipse(19.5, 12.0, 3.8, 6.2, "G")
    body.ellipse(21.4, 12.4, 1.6, 4.6, "W", only=True)
    near = Layer()
    limb(near, 21.0, 9.0, 26.0, 5.0 + 2 - reach, "G")
    limb(near, 21.0, 15.5, 26.0, 18.0 - 2 + reach, "G")
    return far, tail, body, near


def climb(phase: int) -> list[str]:
    far, tail, body, near = climb_body(phase)
    head = stamp(SIDE_HEAD, 14, 0)
    return compose(far, tail, body, head, near)


def climb_hang(frame: int) -> list[str]:
    """Висит наверху и оглядывается на зрителя."""
    far, tail, body, near = climb_body(0)
    head = stamp(front_face(look=-1 if frame else 0), 9, 0)
    return compose(far, tail, body, head, near)


def animations() -> dict[str, tuple[str, list[list[str]]]]:
    return {
        "sit": ("Сидит на полу анфас. Второй кадр — моргание.", [sit(), sit(eyes="closed")]),
        "sleep": ("Спит клубком, хвост вокруг.", [sleep(0), sleep(1)]),
        "wave": ("Машет лапой.", [sit(paws="wave", paw_phase=0), sit(paws="wave", paw_phase=1)]),
        "walk": (
            "Идёт вправо на четырёх лапах. Влево кадры отражаются.",
            [walk_side(p) for p in range(4)],
        ),
        "walk_down": ("Идёт к зрителю, вниз по экрану.", [walk_down(p) for p in range(4)]),
        "walk_down_right": (
            "Идёт вниз-вправо по диагонали. Вниз-влево кадры отражаются.",
            [walk_down_right(p) for p in range(4)],
        ),
        "walk_up_right": (
            "Идёт вверх-вправо по диагонали. Вверх-влево кадры отражаются.",
            [walk_up_right(p) for p in range(4)],
        ),
        "walk_up": ("Идёт от зрителя, вверх по экрану.", [walk_up(p) for p in range(4)]),
        "wash": ("Трёт лапки.", [sit(paws="wash", paw_phase=0), sit(paws="wash", paw_phase=1)]),
        "stretch": (
            "Зевает и потягивается.",
            [sit(eyes="closed", mouth="yawn"), sit(eyes="closed", mouth="yawn", arms_up=True)],
        ),
        "eat": (
            "Грызёт печеньку.",
            [
                sit(eyes="closed", paws="none", cookie="full"),
                sit(eyes="closed", paws="none", cookie="bitten"),
            ],
        ),
        "look": ("Косится на курсор: влево, вправо.", [sit(look=-1), sit(look=1)]),
        "scratch": ("Чешет ухо задней лапой.", [scratch(0), scratch(1)]),
        "roll": ("Валяется на спине лапами вверх.", [roll(0), roll(1)]),
        "dance": ("Танцует.", [dance(i) for i in range(4)]),
        "peek": ("Ку-ку: закрыл глаза лапами и подглядывает.", [peek(0), peek(1)]),
        "sneeze": ("Чихает.", [sneeze(0), sneeze(0), sneeze(1), sneeze(2)]),
        "dig": ("Копает ямку, летит земля.", [dig(0), dig(1)]),
        "sniff": ("Нюхает пол.", [sniff(0), sniff(1)]),
        "play": ("Играет с мячиком.", [play(i) for i in range(4)]),
        "read": ("Читает книжку.", [read(0), read(1)]),
        "sip": ("Пьёт какао.", [sip(0), sip(0), sip(1)]),
        "clap": ("Хлопает в ладоши.", [clap(0), clap(1)]),
        "doze": ("Клюёт носом сидя.", [doze(0), doze(1)]),
        "sing": ("Поёт, летят нотки.", [sing(0), sing(1)]),
        "flex": ("Показывает мускулы.", [flex(0), flex(1)]),
        "tailwag": ("Виляет хвостом.", [tailwag(0), tailwag(1)]),
        "trash": ("Роется в мусорке и находит бумажку.", [trash(0), trash(1), trash(2)]),
        "hiccup": ("Икает.", [hiccup(0), hiccup(0), hiccup(1)]),
        "climb": ("Лезет по правому краю экрана, как по дереву.", [climb(0), climb(1)]),
        "climb_hang": ("Висит наверху и оглядывается.", [climb_hang(0), climb_hang(1)]),
    }


def character_toml(
    *,
    char_id: str = "raccoon",
    name: str = "Raccoon",
    description: str = "A grey masked raccoon who lives on your screen like on a floor.",
    generator: str = "tools/raccoon_art.py",
    palette: dict | None = None,
    variants: dict | None = None,
    edit=None,
) -> str:
    """Пакет персонажа. Другие персонажи (мышка, пингвин) передают свои имя, цвета и
    генератор. edit(animations) может заменить или убрать анимации."""
    palette = PALETTE if palette is None else palette
    variants = VARIANTS if variants is None else variants
    lines = [
        f"# Персонаж cloDICK. Сгенерирован {generator} — правьте генератор, не этот файл.",
        f'id = "{char_id}"',
        f'name = "{name}"',
        'author = "cloDICK"',
        f'description = "{description}"',
        f"size = [{W}, {H}]",
        "# Светлое пузо: тут пишется загрузка RAM.",
        "belly = [10, 13, 8, 4]",
        "",
        "[palette]",
        *(f'{k} = "{v}"' for k, v in palette.items()),
    ]
    for theme, colors in variants.items():
        lines += ["", f"[variants.{theme}]", *(f'{k} = "{v}"' for k, v in colors.items())]
    anims = animations()
    if edit is not None:
        anims = edit(anims)
    for name, (comment, frames) in anims.items():
        for frame in frames:
            assert len(frame) == H and all(len(r) == W for r in frame), name
        body = ",\n".join("'''\n" + "\n".join(f) + "\n'''" for f in frames)
        lines += ["", f"# {comment}", f"[animations.{name}]", f"frames = [\n{body},\n]"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("character.toml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(character_toml(), encoding="utf-8")
    print(out)
