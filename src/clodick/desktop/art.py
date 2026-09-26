"""Пиксель-арт енота и домика в виде текстовых карт.

Каждый символ — один пиксель, цвет берётся из PALETTE. Точка — прозрачный пиксель.
Все кадры енота одного размера, чтобы окно не прыгало при смене анимации.
Чтобы заменить графику на нарисованную вручную, достаточно поменять этот файл.
"""

from __future__ import annotations

PALETTE: dict[str, str | None] = {
    ".": None,
    "K": "#26262e",  # контур
    "G": "#8b909b",  # серая шерсть
    "g": "#5d626d",  # тёмная шерсть, лапы
    "W": "#ecebef",  # белая шерсть
    "M": "#16161b",  # маска и полоски хвоста
    "E": "#ffffff",  # блик в глазу
    "P": "#d98c9c",  # розовое в ушах
    "Z": "#9fc3ff",  # буквы сна
    # домик
    "R": "#b5523b",  # крыша
    "r": "#7d3526",  # тень крыши
    "B": "#c9955c",  # доски стен
    "b": "#8c6239",  # щели между досками
    "D": "#3b2a1f",  # дверь-нора
    "Y": "#f2d16b",  # окно
    "S": "#6f7580",  # труба
    "L": "#6fae4a",  # трава
    "l": "#4e8a33",  # тёмная трава
}

_SIT = [
    "....KK........KK......",
    "...KPgK......KgPK.....",
    "...KPGGKKKKKKGGPK.....",
    "..KGGGGGGGGGGGGGGK....",
    "..KGWWWGGGGGGWWWGK....",
    "..KMMMMMMGGMMMMMMK....",
    "..KMMEKMMGGMMEKMMK....",
    "..KWMMMMWGGWMMMMWK....",
    "...KWWWWWKKWWWWWK.....",
    "....KWWWWWWWWWWK..KK..",
    "...KGGGGGGGGGGGGKKMMK.",
    "...KGGWWWWWWWWGGKKGGK.",
    "...KGGWWWWWWWWGGKKMMK.",
    "...KGGWWWWWWWWGGKKGGK.",
    "...KGGGWWWWWWGGGKKMMK.",
    "...KGggGGGGGGggGKKGGK.",
    "...KggggGGGGggggK.KK..",
    "....KKKKKKKKKKKKK.....",
]


def _with_rows(base: list[str], changes: dict[int, str]) -> list[str]:
    rows = list(base)
    for index, row in changes.items():
        rows[index] = row
    return rows


_SIT_BLINK = _with_rows(_SIT, {6: "..KMMMMMMGGMMMMMMK...."})

_SLEEP_A = _with_rows(
    _SIT,
    {
        0: "....KK........KK..ZZZZ",
        1: "...KPgK......KgPK...Z.",
        2: "...KPGGKKKKKKGGPK..Z..",
        3: "..KGGGGGGGGGGGGGGK.ZZZ",
        6: "..KMWWMMMGGMMMWWMK....",
    },
)
_SLEEP_B = _with_rows(
    _SIT,
    {
        2: "...KPGGKKKKKKGGPK.ZZ..",
        3: "..KGGGGGGGGGGGGGGK..Z.",
        4: "..KGWWWGGGGGGWWWGK.ZZ.",
        6: "..KMWWMMMGGMMMWWMK....",
    },
)

# Машет левой лапой: лапа поднята (A) и опущена ниже (B).
_WAVE_A = _with_rows(
    _SIT,
    {
        2: "KK.KPGGKKKKKKGGPK.....",
        3: "KgKGGGGGGGGGGGGGGK....",
        4: "KGKGWWWGGGGGGWWWGK....",
        5: "KGKMMMMMMGGMMMMMMK....",
        6: "KGKMMEKMMGGMMEKMMK....",
        7: "KGKWMMMMWGGWMMMMWK....",
        8: "KGGKWWWWWKKWWWWWK.....",
        9: ".KGGKWWWWWWWWWWK..KK..",
        10: "..KGGGGGGGGGGGGGKKMMK.",
    },
)
_WAVE_B = _with_rows(
    _SIT,
    {
        6: "KKKMMEKMMGGMMEKMMK....",
        7: "KgKWMMMMWGGWMMMMWK....",
        8: "KgGKWWWWWKKWWWWWK.....",
        9: ".KGGKWWWWWWWWWWK..KK..",
        10: "..KKGGGGGGGGGGGGKKMMK.",
    },
)

# Вид сбоку, морда вправо. Для движения влево кадр отражается.
_WALK_A = [
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "..............KK..KK..",
    ".............KPgKKgPK.",
    ".KK..........KGGGGGGK.",
    "KMMK........KGGGWWGGK.",
    "KGGK.......KGGMMMMMMMK",
    ".KMMK......KGMMEKMWWWK",
    "..KGGK...KKKGGMMWWWWKK",
    "...KMMKKKGGGKWWWWWWK..",
    "....KGGGGGGGGGKKKKK...",
    "....KGGGWWWWWWGGK.....",
    "....KGgKGGGGGgKGK.....",
    "....KggK.KKKKggKK.....",
    ".....KK.......KK......",
]
_WALK_B = _with_rows(
    _WALK_A,
    {
        15: "....KGGGGgKgGGGGK.....",
        16: ".....KggKKggKKKK......",
        17: "......KK..KK..........",
    },
)

RACCOON: dict[str, list[list[str]]] = {
    "sit": [_SIT, _SIT_BLINK],
    "sleep": [_SLEEP_A, _SLEEP_B],
    "wave": [_WAVE_A, _WAVE_B],
    "walk": [_WALK_A, _WALK_B],
}

# Домик слева, справа двор с травой — там сидит енот.
HOUSE = [
    "...........................KKKK.............................",
    ".................KKKK......KSSK.............................",
    ".................KRRK......KSSK.............................",
    "...............KRRRRRRK....KSSK.............................",
    ".............KRRRRRRRRRRK..KSSK.............................",
    "...........KRRRRRRRRRRRRRRKKSSK.............................",
    ".........KRRRRRRRRRRRRRRRRRRKSK.............................",
    ".......KRRRRRRRRRRRRRRRRRRRRRRK.............................",
    ".....KRRRRRRRRRRRRRRRRRRRRRRRRRRK...........................",
    "...KRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.........................",
    ".KRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK.......................",
    "KRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRK......................",
    "rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr......................",
    "...KBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBK.........................",
    "...KbbbbbbbbbbbbbbbbbbbbbKKKKKKKbbK.........................",
    "...KBBBBBBBBBBBBBBBBBBBBBKYYKYYKBBK.........................",
    "...KBBBBBBBBBBBBBBBBBBBBBKYYKYYKBBK.........................",
    "...KbbbbbbbbbbbbbbbbbbbbbKKKKKKKbbK.........................",
    "...KBBBBBBBBBBBBBBBBBBBBBKYYKYYKBBK.........................",
    "...KBBBBBBBBBBKKKKKKKBBBBKYYKYYKBBK.........................",
    "...KbbbbbbbbbKDDDDDDDKbbbKKKKKKKbbK.........................",
    "...KBBBBBBBBKDDDDDDDDDKBBBBBBBBBBBK.........................",
    "...KBBBBBBBBKDDDDDDDDDKBBBBBBBBBBBK.........................",
    "...KbbbbbbbbKDDDDDDDDDKbbbbbbbbbbbK.........................",
    "...KBBBBBBBBKDDDDDDDYDKBBBBBBBBBBBK.........................",
    "...KBBBBBBBBKDDDDDDDDDKBBBBBBBBBBBK.........................",
    "...KbbbbbbbbKDDDDDDDDDKbbbbbbbbbbbK.........................",
    "...KBBBBBBBBKDDDDDDDDDKBBBBBBBBBBBK.........................",
    "...KBBBBBBBBKDDDDDDDDDKBBBBBBBBBBBK.........................",
    "LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL",
    "lLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLLlLL",
]
