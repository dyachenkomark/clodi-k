import textwrap

import pytest

from clodick.characters import (
    DEFAULT_CHARACTER,
    REQUIRED_ANIMATIONS,
    CharacterError,
    builtin_dir,
    discover,
    load_character,
)
from clodick.desktop.themes import THEMES

FRAME = "'''\nKK\nKK\nKK\n'''"
HEAD = 'size = [2, 3]\n[palette]\nK = "#112233"\n'


def write_pack(folder, body):
    folder.mkdir(parents=True)
    (folder / "character.toml").write_text(textwrap.dedent(body), encoding="utf-8")
    return folder


def minimal_pack(folder, char_id="blob", extra=""):
    animations = "\n".join(
        f"[animations.{name}]\nframes = [{FRAME}]" for name in REQUIRED_ANIMATIONS
    )
    body = f'id = "{char_id}"\nname = "Капля"\nsize = [2, 3]\n{extra}\n[palette]\nK = "#112233"\n'
    return write_pack(folder, body + animations)


def test_builtin_raccoon_is_valid():
    raccoon = load_character(builtin_dir() / DEFAULT_CHARACTER)
    assert raccoon.name == "Raccoon"
    assert (raccoon.width, raccoon.height) == (22, 18)
    for name in REQUIRED_ANIMATIONS:
        assert raccoon.animations[name].frame_count >= 1


def test_raccoon_has_variant_for_every_non_classic_theme():
    raccoon = load_character(builtin_dir() / DEFAULT_CHARACTER)
    assert set(raccoon.variants) == set(THEMES) - {"classic"}
    assert raccoon.palette_for("claude")["G"] != raccoon.palette_for("classic")["G"]


def test_minimal_pack_loads(tmp_path):
    blob = load_character(minimal_pack(tmp_path / "blob"))
    assert blob.id == "blob"
    assert blob.palette["."] is None
    assert blob.animations["walk"].frames[0] == ("KK", "KK", "KK")


def test_user_pack_is_discovered_next_to_builtin(tmp_path):
    minimal_pack(tmp_path / "blob")
    found = discover([builtin_dir(), tmp_path])
    assert {"raccoon", "blob"} <= found.keys()


def test_broken_pack_is_skipped(tmp_path):
    write_pack(tmp_path / "broken", 'id = "broken"\nsize = [2, 2]\n')
    assert "broken" not in discover([tmp_path])


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('size = [2, 3]\n[palette]\nK = "#112233"\n', "не хватает анимаций"),
        ('size = "big"\n', "size"),
        ('id = "Кот"\nsize = [2, 3]\n', "id"),
        ('size = [2, 3]\n[palette]\nK = "red"\n', "#rrggbb"),
        (
            HEAD + '[animations.sit]\nframes = ["KKK\\nKK\\nKK"]\n',
            "символов",
        ),
        (
            HEAD + '[animations.sit]\nframes = ["KX\\nKK\\nKK"]\n',
            "нет в palette",
        ),
        ('size = [2, 3]\n[palette]\nK = "#112233"\n[variants.night]\nQ = "#000000"\n', "Q"),
        ('size = [2, 3]\n[animations.sit]\nsheet = "nope.png"\ncount = 2\n', "nope.png"),
    ],
)
def test_invalid_packs_explain_the_problem(tmp_path, body, message):
    folder = write_pack(tmp_path / "bad", body)
    with pytest.raises(CharacterError, match=message):
        load_character(folder)
