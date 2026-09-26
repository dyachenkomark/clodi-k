"""Темы оформления: цвета домика, чек-листа, пузыря и таблички.

Тема выбирается в config.toml: [desktop] theme = "classic".
Модуль без Qt, чтобы настройки могли проверять название темы.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clodick.desktop.art import PALETTE

SERIF = "Georgia, 'DejaVu Serif', 'Times New Roman', serif"
SANS = "'Segoe UI', 'DejaVu Sans', sans-serif"


@dataclass(frozen=True)
class Theme:
    key: str
    title: str
    # Цвета домика поверх базовой палитры из art.py. Цвета персонажа — в его пакете.
    art: dict[str, str | None] = field(default_factory=dict)
    # Чек-лист.
    panel_bg: str = "#2b2d35"
    panel_border: str = "#16161b"
    text: str = "#ecebef"
    muted: str = "#8b909b"
    accent: str = "#6fae4a"
    progress: str = "#f2d16b"
    box_bg: str = "#1f2026"
    title_font: str = SANS
    body_font: str = SANS
    radius: int = 10
    # Пузырь.
    bubble_bg: str = "#fbfaf6"
    bubble_border: str = "#26262e"
    bubble_text: str = "#26262e"
    # Табличка RAM на домике.
    sign_bg: str = "#3b2a1f"
    sign_border: str = "#26262e"
    sign_text: str = "#f2d16b"

    @property
    def palette(self) -> dict[str, str | None]:
        return {**PALETTE, **self.art}


# Палитра в духе Claude: кремовая бумага, терракота, тёплые чернила.
INK = "#141413"
INK_SOFT = "#3d3d3a"
CREAM = "#faf9f5"
PAPER = "#f0eee6"
PAPER_DARK = "#e3dfd3"
STONE = "#b0aea5"
TERRACOTTA = "#d97757"
TERRACOTTA_DARK = "#b85c3e"
NIGHT = "#262624"
NIGHT_DEEP = "#1f1e1d"

THEMES: dict[str, Theme] = {
    theme.key: theme
    for theme in (
        Theme(key="classic", title="Классика"),
        Theme(
            key="claude",
            title="Терракота",
            art={
                "K": "#2a2926",
                "R": TERRACOTTA,
                "r": TERRACOTTA_DARK,
                "B": PAPER,
                "b": PAPER_DARK,
                "D": INK_SOFT,
                "Y": "#f3c98b",
                "S": STONE,
                "L": "#a7ae86",
                "l": "#8c9470",
            },
            panel_bg=CREAM,
            panel_border=PAPER_DARK,
            text=INK,
            muted="#87867f",
            accent=TERRACOTTA,
            progress=TERRACOTTA,
            box_bg=CREAM,
            title_font=SERIF,
            body_font=SERIF,
            radius=14,
            bubble_bg=CREAM,
            bubble_border=INK_SOFT,
            bubble_text=INK,
            sign_bg=CREAM,
            sign_border=INK_SOFT,
            sign_text=TERRACOTTA_DARK,
        ),
        Theme(
            key="claude_orange",
            title="Рыжий енот",
            art={
                "K": INK,
                "R": INK_SOFT,
                "r": INK,
                "B": PAPER,
                "b": PAPER_DARK,
                "D": TERRACOTTA,
                "Y": CREAM,
                "S": INK_SOFT,
                "L": PAPER_DARK,
                "l": STONE,
            },
            panel_bg=PAPER,
            panel_border=STONE,
            text=INK,
            muted="#87867f",
            accent=INK,
            progress=TERRACOTTA_DARK,
            box_bg=CREAM,
            title_font=SERIF,
            body_font=SANS,
            radius=6,
            bubble_bg=TERRACOTTA,
            bubble_border=INK,
            bubble_text=CREAM,
            sign_bg=INK,
            sign_border=INK,
            sign_text=CREAM,
        ),
        Theme(
            key="claude_night",
            title="Ночь",
            art={
                "K": "#0f0f0e",
                "R": "#8a4a35",
                "r": "#5e3224",
                "B": "#4a4642",
                "b": "#3a3733",
                "D": "#0f0f0e",
                "Y": "#f3c98b",
                "S": "#5a5650",
                "L": "#56603f",
                "l": "#434b30",
            },
            panel_bg=NIGHT,
            panel_border="#3a3935",
            text=PAPER,
            muted="#8f8d85",
            accent=TERRACOTTA,
            progress=TERRACOTTA,
            box_bg=NIGHT_DEEP,
            title_font=SERIF,
            body_font=SERIF,
            radius=14,
            bubble_bg=NIGHT,
            bubble_border=TERRACOTTA,
            bubble_text=PAPER,
            sign_bg=NIGHT_DEEP,
            sign_border="#0f0f0e",
            sign_text="#f3c98b",
        ),
    )
}

DEFAULT_THEME = "claude"
