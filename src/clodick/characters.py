"""Персонажи: енот и все, кого добавят потом.

Персонаж — папка с файлом character.toml и, при желании, PNG-листами кадров.
Встроенные лежат в clodick/assets/characters, свои — в папке данных, подпапка characters.
Формат описан в docs/CHARACTERS.md. Модуль без Qt: его используют и настройки, и сервер.
"""

from __future__ import annotations

import logging
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED_ANIMATIONS = ("sit", "sleep", "wave", "walk")
DEFAULT_CHARACTER = "raccoon"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID = re.compile(r"^[a-z0-9_-]{1,32}$")


class CharacterError(ValueError):
    """Пакет персонажа собран неправильно."""


@dataclass(frozen=True)
class Animation:
    """Кадры одной анимации: текстовые карты или PNG-лист с кадрами в ряд."""

    frames: tuple[tuple[str, ...], ...] = ()
    sheet: Path | None = None
    count: int = 0

    @property
    def frame_count(self) -> int:
        return self.count if self.sheet else len(self.frames)


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    width: int
    height: int
    animations: dict[str, Animation]
    palette: dict[str, str | None] = field(default_factory=dict)
    variants: dict[str, dict[str, str | None]] = field(default_factory=dict)
    author: str = ""
    description: str = ""
    path: Path | None = None
    # Где пузо в кадрах sit, sleep и wave: x, y, ширина, высота в пикселях арта.
    # Там пишется загрузка RAM. Нет пуза — нет надписи.
    belly: tuple[int, int, int, int] | None = None

    def palette_for(self, theme: str) -> dict[str, str | None]:
        """Палитра с учётом варианта под тему, если он есть."""
        return {**self.palette, **self.variants.get(theme, {})}


def builtin_dir() -> Path:
    return Path(__file__).parent / "assets" / "characters"


def load_character(folder: Path) -> Character:
    path = folder / "character.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CharacterError(f"{folder}: нет файла character.toml") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CharacterError(f"{path}: {exc}") from exc

    where = f"персонаж {folder.name}"
    char_id = raw.get("id", folder.name)
    if not isinstance(char_id, str) or not _ID.match(char_id):
        raise CharacterError(f"{where}: id — латиница в нижнем регистре, цифры, _ и -")
    size = raw.get("size")
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) for v in size)):
        raise CharacterError(f"{where}: size должен быть [ширина, высота]")
    width, height = size
    if not (1 <= width <= 128 and 1 <= height <= 128):
        raise CharacterError(f"{where}: размер кадра от 1 до 128 пикселей")

    palette = {".": None, **_parse_palette(raw.get("palette", {}), f"{where}, palette")}
    variants = {
        theme: _parse_palette(colors, f"{where}, variants.{theme}")
        for theme, colors in raw.get("variants", {}).items()
    }
    for theme, colors in variants.items():
        extra = colors.keys() - palette.keys()
        if extra:
            raise CharacterError(
                f"{where}, variants.{theme}: символы {sorted(extra)} не описаны в palette"
            )

    animations = {}
    for name, spec in raw.get("animations", {}).items():
        animations[name] = _parse_animation(
            spec, folder, width, height, palette, f"{where}, {name}"
        )
    missing = [name for name in REQUIRED_ANIMATIONS if name not in animations]
    if missing:
        raise CharacterError(f"{where}: не хватает анимаций {missing}")

    belly = raw.get("belly")
    if belly is not None:
        ok = isinstance(belly, list) and len(belly) == 4 and all(isinstance(v, int) for v in belly)
        if not ok or not (
            belly[0] >= 0
            and belly[1] >= 0
            and belly[2] > 0
            and belly[3] > 0
            and belly[0] + belly[2] <= width
            and belly[1] + belly[3] <= height
        ):
            raise CharacterError(f"{where}: belly — [x, y, ширина, высота] внутри кадра")
        belly = tuple(belly)

    return Character(
        id=char_id,
        name=str(raw.get("name", char_id)),
        width=width,
        height=height,
        animations=animations,
        palette=palette,
        variants=variants,
        author=str(raw.get("author", "")),
        description=str(raw.get("description", "")),
        path=folder,
        belly=belly,
    )


def discover(folders: Iterable[Path]) -> dict[str, Character]:
    """Все персонажи из папок. Более поздняя папка перекрывает одноимённых из ранней.

    Сломанный пакет пропускается с записью в лог, чтобы не ронять приложение.
    """
    found: dict[str, Character] = {}
    for base in folders:
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if (p / "character.toml").is_file()):
            try:
                character = load_character(folder)
            except CharacterError as exc:
                log.warning("пропускаю персонажа: %s", exc)
                continue
            found[character.id] = character
    return found


def _parse_palette(raw: object, where: str) -> dict[str, str | None]:
    if not isinstance(raw, dict):
        raise CharacterError(f"{where}: ожидается таблица символ = цвет")
    palette: dict[str, str | None] = {}
    for char, color in raw.items():
        if len(char) != 1 or char == ".":
            raise CharacterError(f"{where}: ключ {char!r} должен быть одним символом, не точкой")
        if color == "":
            palette[char] = None
        elif isinstance(color, str) and _HEX.match(color):
            palette[char] = color.lower()
        else:
            raise CharacterError(f"{where}: цвет {char} = {color!r}, нужен #rrggbb или пусто")
    return palette


def _parse_animation(
    spec: object,
    folder: Path,
    width: int,
    height: int,
    palette: dict[str, str | None],
    where: str,
) -> Animation:
    if not isinstance(spec, dict):
        raise CharacterError(f"{where}: ожидается таблица с frames или sheet")
    if "sheet" in spec:
        sheet = folder / str(spec["sheet"])
        count = spec.get("count")
        if not sheet.is_file():
            raise CharacterError(f"{where}: нет файла {sheet.name}")
        if not isinstance(count, int) or count < 1:
            raise CharacterError(f"{where}: для sheet нужен count — число кадров в ряд")
        return Animation(sheet=sheet, count=count)

    frames_raw = spec.get("frames")
    if not isinstance(frames_raw, list) or not frames_raw:
        raise CharacterError(f"{where}: нужен непустой список frames")
    frames = []
    for index, text in enumerate(frames_raw):
        rows = tuple(line for line in str(text).strip("\n").splitlines())
        label = f"{where}, кадр {index + 1}"
        if len(rows) != height:
            raise CharacterError(f"{label}: {len(rows)} строк, а высота {height}")
        for number, row in enumerate(rows, start=1):
            if len(row) != width:
                raise CharacterError(
                    f"{label}, строка {number}: {len(row)} символов, нужно {width}"
                )
            unknown = set(row) - palette.keys()
            if unknown:
                raise CharacterError(f"{label}, строка {number}: нет в palette {sorted(unknown)}")
        frames.append(rows)
    return Animation(frames=tuple(frames))
