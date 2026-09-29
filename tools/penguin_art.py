"""Рисует третьего персонажа — пингвина — и пишет его пакет.

    uv run python tools/penguin_art.py src/clodick/assets/characters/penguin/character.toml

Пингвин берёт позы енота из raccoon_art.py и подменяет головы, хвост и цвета. Вместо
ходьбы он катается на пузе: кадры walk — скольжение, а walk_down, walk_up и диагонали
убраны, поэтому в любую сторону он скользит, показанный сбоку. Позы, которые пингвину
не идут (лазание, копание и обнюхивание на четырёх лапах, чесание уха лапой,
виляние коротким хвостиком), тоже убраны.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import raccoon_art as art

# У пингвина G — чёрная спина, W — белое пузо, g — оранжевые лапки.
PALETTE = {
    "K": "#1c1f27",  # контур
    "G": "#343a48",  # спина, голова, ласты
    "g": "#f39a3a",  # лапки
    "W": "#f4f5f7",  # пузо и мордочка
    "M": "#1c1f27",  # рот
    "m": "#9aa0ad",  # брызги, крышка мусорки
    "E": "#ffffff",  # блик в глазу
    "P": "#f39a3a",  # клюв
    "Z": "#7fb3ff",  # буквы сна, ноты
    "C": "#d9a066",  # печенька, книжка
    "c": "#6b4226",  # крошки, какао
}

VARIANTS = {
    "claude": {"K": "#1f1e1d", "G": "#3d3d3a", "Z": "#d97757", "g": "#e58a52", "P": "#e58a52"},
    "claude_orange": {"K": "#141413", "Z": "#d97757"},
    "claude_night": {"K": "#0f0f0e", "G": "#4a4843", "Z": "#f3c98b", "W": "#e8e6df"},
}

# Голова анфас 16×13: круглая тёмная, белая мордочка, глаза с бликом, оранжевый клюв.
FRONT_HEAD = [
    "................",
    "................",
    ".....KKKKKK.....",
    "...KKGGGGGGKK...",
    "..KGGGGGGGGGGK..",
    ".KGGGWWGGWWGGGK.",
    ".KGGWWWWWWWWGGK.",
    ".KGWWEKWWEKWWGK.",
    ".KGWWKKWWKKWWGK.",
    ".KGWWWWPPWWWWGK.",
    "..KGWWPPPPWWGK..",
    "...KGWWWWWWGK...",
    "....KKKKKKKK....",
]
EYES = (5, 9)


def front_face(*, eyes="open", look=0, mouth=None) -> list[str]:
    rows = [list(r) for r in FRONT_HEAD]
    for left in EYES:
        for y in (7, 8):
            rows[y][left] = rows[y][left + 1] = "W"
        if eyes == "closed":
            # Довольная дуга ∩ шириной четыре пикселя.
            rows[7][left] = rows[7][left + 1] = "K"
            rows[8][left - 1] = rows[8][left + 2] = "K"
        else:
            x = left + look
            rows[7][x], rows[7][x + 1] = "E", "K"
            rows[8][x], rows[8][x + 1] = "K", "K"
    if mouth in ("yawn", "open"):
        rows[10][7] = rows[10][8] = "M"
    return ["".join(r) for r in rows]


# Голова сбоку, смотрит вправо, 13×10: клюв вперёд.
SIDE_HEAD = [
    "....KKKKK....",
    "..KKGGGGGKK..",
    ".KGGGGGGGGGK.",
    "KGGGGGGWWWGK.",
    "KGGGGGWWEKWK.",
    "KGGGGGWWKKWKK",
    "KGGGGGWWWWPPK",
    ".KGGGGWWWWKK.",
    "..KGGGWWWWK..",
    "...KKKKKKK...",
]

# Голова со спины 16×10: круглый тёмный затылок.
BACK_HEAD = [
    "................",
    "................",
    ".....KKKKKK.....",
    "...KKGGGGGGKK...",
    "..KGGGGGGGGGGK..",
    ".KGGGGGGGGGGGGK.",
    ".KGGGGGGGGGGGGK.",
    ".KGGGGGGGGGGGGK.",
    "..KGGGGGGGGGGK..",
    "...KKGGGGGGKK...",
]

# Голова спящего, 11×9: глаза закрыты, клюв.
SLEEP_HEAD = [
    "..KKKKKK...",
    ".KGGGGGGK..",
    "KGGWWWWGGK.",
    "KGWKWWKWGGK",
    "KGWWWWWWGK.",
    "KGWWPPWWGK.",
    ".KGWPPWWK..",
    "..KGWWWK...",
    "...KKKK....",
]


def stub_tail(points, radii, rings=3) -> art.Layer:
    """Короткий тёмный хвостик у основания, где у енота начинается пушистый хвост."""
    tail = art.Layer()
    x, y = points[0]
    tail.ellipse(x, y, 1.6, 1.3, "G")
    return tail


def slide(phase: int) -> list[str]:
    """Катится на пузе вправо: лежит, ласты прижаты, лапки сзади, за ним брызги."""
    feet = art.Layer()
    kick = (0, 1, 0)[phase]
    feet.ellipse(2.6, 15.2 - kick, 1.6, 0.9, "g")
    feet.ellipse(3.2, 16.8 + kick, 1.6, 0.9, "g")
    body = art.Layer()
    body.ellipse(13.0, 14.6, 9.2, 3.3, "G")
    for x, y in list(body.px):
        if y >= 15:
            body.set(x, y, "W")
    flipper = art.Layer()
    flipper.ellipse(10.5 - kick * 0.5, 12.2, 3.4, 1.0, "G")
    head = art.stamp(SIDE_HEAD, 15, 7)
    spray_rows = (
        [(0, 13), (1, 17), (0, 18)],
        [(1, 14), (0, 16), (2, 18)],
        [(0, 12), (2, 15), (1, 18)],
    )[phase]
    spray = art.raw(spray_rows, "m")
    return art.compose(feet, body, flipper, head, spray)


def edit(animations: dict) -> dict:
    """Ходьба — это скольжение на пузе. Лишние для пингвина позы убраны."""
    drop = {
        "walk_down",
        "walk_up",
        "walk_down_right",
        "walk_up_right",
        "climb",
        "climb_hang",
        "dig",
        "sniff",
        "scratch",
        "tailwag",
    }
    out = {name: value for name, value in animations.items() if name not in drop}
    out["walk"] = (
        "Катится на пузе вправо. Влево кадры отражаются, в другие стороны тоже скользит боком.",
        [slide(p) for p in range(3)],
    )
    return out


def install() -> None:
    art.front_face = front_face
    art.SIDE_HEAD = SIDE_HEAD
    art.BACK_HEAD = BACK_HEAD
    art.SLEEP_HEAD = SLEEP_HEAD
    art.striped_tail = stub_tail


def character_toml() -> str:
    install()
    return art.character_toml(
        char_id="penguin",
        name="Penguin",
        description="A little penguin who slides around on its belly.",
        generator="tools/penguin_art.py",
        palette=PALETTE,
        variants=VARIANTS,
        edit=edit,
    )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("character.toml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(character_toml(), encoding="utf-8")
    print(out)
