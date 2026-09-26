"""Пиксель-арт домика в виде текстовой карты.

Каждый символ — один пиксель, цвет берётся из PALETTE. Точка — прозрачный пиксель.
Персонажи живут отдельно, в пакетах: см. clodick/characters.py и docs/CHARACTERS.md.
"""

from __future__ import annotations

PALETTE: dict[str, str | None] = {
    ".": None,
    "K": "#26262e",  # контур
    "R": "#b5523b",  # крыша
    "r": "#7d3526",  # тень крыши
    "B": "#c9955c",  # доски стен
    "b": "#8c6239",  # щели между досками
    "D": "#3b2a1f",  # дверь
    "Y": "#f2d16b",  # окно и ручка двери
    "S": "#6f7580",  # труба
    "L": "#6fae4a",  # трава
    "l": "#4e8a33",  # тёмная трава
}

# Двор справа от домика: отсюда начинается место персонажа (в пикселях арта).
YARD_X = 36
# Строка, где начинается трава: персонаж стоит на ней лапами.
GROUND_ROW = 29

# Домик слева, справа двор с травой — там живёт персонаж.
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
