"""Рисует второго персонажа — мышку — и пишет её пакет.

    uv run python tools/mouse_art.py src/clodick/assets/characters/mouse/character.toml

Мышка переиспользует все позы енота из raccoon_art.py: подменяются голова (анфас, сбоку,
со спины, во сне), хвост и цвета. Стиль: серая, огромные круглые розовые уши, большие
белые глаза-пуговицы с маленькими зрачками, вытянутая мордочка, розовый нос и тонкий
розовый хвост.
"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import raccoon_art as art

PALETTE = {
    "K": "#2b2f3a",  # контур
    "G": "#9a9ba3",  # серая шерсть
    "g": "#74757e",  # тёмная шерсть, дальние лапы
    "W": "#c9cad0",  # светлое пузо и мордочка
    "M": "#2b2f3a",  # тёмное: рот
    "m": "#5e5f68",  # крышка мусорки
    "E": "#ffffff",  # белки глаз
    "P": "#f2a39b",  # уши, нос, хвост
    "Z": "#9fc3ff",  # буквы сна, ноты
    "C": "#d9a066",  # печенька, книжка
    "c": "#6b4226",  # крошки, какао
}

VARIANTS = {
    "claude": {"K": "#2a2926", "Z": "#d97757", "P": "#eea08f"},
    "claude_orange": {"K": "#141413", "Z": "#d97757"},
    "claude_night": {"K": "#0f0f0e", "Z": "#f3c98b", "W": "#b9b8b2"},
}

# Голова анфас 16×13: большие круглые уши, глаза-пуговицы, мордочка вниз, розовый нос.
FRONT_HEAD = [
    ".KKKK......KKKK.",
    "KPPPPK....KPPPPK",
    "KPPPPPK..KPPPPPK",
    "KPPPPPKKKKPPPPPK",
    "KGPPPGGGGGGPPPGK",
    "KGGEEEGGGGEEEGGK",
    "KGEEKKEGGEKKEEGK",
    "KGEEKKEGGEKKEEGK",
    "KGGEEEGWWGEEEGGK",
    ".KGGGWWWWWWGGGK.",
    "..KGGWWPPWWGGK..",
    "...KGWKWWKWGK...",
    "....KKKKKKKK....",
]
# Зрачки 2×2: левый глаз столбцы 4–5, правый 10–11 (скошены к носу), строки 6–7.
PUPILS = (4, 10)


def front_face(*, eyes="open", look=0, mouth=None) -> list[str]:
    rows = [list(r) for r in FRONT_HEAD]
    if eyes == "closed":
        for y in (5, 6, 7, 8):
            for x in (*range(2, 7), *range(9, 14)):
                rows[y][x] = "G"
        # Довольные дуги ∩.
        for a, b in ((2, 6), (9, 13)):
            rows[7][a] = rows[7][b] = "K"
            for x in range(a + 1, b):
                rows[6][x] = "K"
    elif look:
        for base in PUPILS:
            for y in (6, 7):
                rows[y][base] = rows[y][base + 1] = "E"
                rows[y][base + look] = rows[y][base + look + 1] = "K"
    if mouth in ("yawn", "open"):
        rows[11][7] = rows[11][8] = "M"
    return ["".join(r) for r in rows]


# Голова сбоку, смотрит вправо, 13×10: ухо, глаз-пуговица, длинная мордочка, нос на конце.
SIDE_HEAD = [
    "..KKK........",
    ".KPPPK.......",
    "KPPPPPK......",
    "KPPPPGKKKK...",
    ".KKGGGGGGGK..",
    "..KGGGEEEGGK.",
    "..KGGEEKEGGGK",
    "..KGGGEEEWWWK",
    "...KGGGWWWWPK",
    "....KKKKKKKK.",
]

# Голова со спины 16×11: затылок и уши сзади.
BACK_HEAD = [
    ".KKKK......KKKK.",
    "KGGGGK....KGGGGK",
    "KGGGGGK..KGGGGGK",
    "KGGGGGKKKKGGGGGK",
    "KGGGGGGGGGGGGGGK",
    ".KGGGGGGGGGGGGK.",
    ".KGGGGGGGGGGGGK.",
    "..KGGGGGGGGGGK..",
    "...KKGGGGGGKK...",
    ".....KKKKKK.....",
]

# Голова спящей, 11×9: уши, закрытые глаза, розовый нос.
SLEEP_HEAD = [
    ".KK...KK...",
    "KPPK.KPPK..",
    "KPPGKGPPGK.",
    "KGGGGGGGGGK",
    "KGKKGGGKKGK",
    "KGGGGGGGGGK",
    ".KGGWWWWGK.",
    "..KGWWWPK..",
    "...KKKKK...",
]


def pink_tail(points, radii, rings=3) -> art.Layer:
    """Тонкий розовый хвост по тем же точкам, где у енота пушистый полосатый."""
    tail = art.Layer()
    for (x0, y0), (x1, y1) in pairwise(points):
        steps = max(1, round(max(abs(x1 - x0), abs(y1 - y0)) * 2))
        for i in range(steps + 1):
            t = i / steps
            tail.ellipse(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 0.6, 0.6, "P")
    return tail


def install() -> None:
    """Подменить у генератора енота всё, что отличает мышку."""
    art.front_face = front_face
    art.SIDE_HEAD = SIDE_HEAD
    art.BACK_HEAD = BACK_HEAD
    art.SLEEP_HEAD = SLEEP_HEAD
    art.striped_tail = pink_tail


def character_toml() -> str:
    install()
    return art.character_toml(
        char_id="mouse",
        name="Mouse",
        description="A grey mouse with huge pink ears and button eyes.",
        generator="tools/mouse_art.py",
        palette=PALETTE,
        variants=VARIANTS,
    )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("character.toml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(character_toml(), encoding="utf-8")
    print(out)
