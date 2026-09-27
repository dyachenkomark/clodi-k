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
    }


def character_toml() -> str:
    lines = [
        "# Персонаж cloDICK. Сгенерирован tools/raccoon_art.py — правьте генератор, не этот файл.",
        'id = "raccoon"',
        'name = "Raccoon"',
        'author = "cloDICK"',
        'description = "A grey masked raccoon who lives on your screen like on a floor."',
        f"size = [{W}, {H}]",
        "# Белое пузо: тут пишется загрузка RAM.",
        "belly = [10, 13, 8, 4]",
        "",
        "[palette]",
        *(f'{k} = "{v}"' for k, v in PALETTE.items()),
    ]
    for theme, colors in VARIANTS.items():
        lines += ["", f"[variants.{theme}]", *(f'{k} = "{v}"' for k, v in colors.items())]
    for name, (comment, frames) in animations().items():
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
