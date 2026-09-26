import re

import pytest

from clodick.config import ConfigError, parse_config
from clodick.desktop.art import PALETTE
from clodick.desktop.themes import THEMES, Theme

HEX = re.compile(r"^#[0-9a-f]{6}$")


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_theme_colors_are_valid(theme: Theme):
    assert theme.palette.keys() == PALETTE.keys()
    for char, color in theme.art.items():
        assert char in PALETTE, f"{theme.key}: лишний символ {char!r}"
        assert color is None or HEX.match(color), f"{theme.key}: {char}={color}"
    for name in ("panel_bg", "text", "accent", "bubble_bg", "sign_bg", "sign_text"):
        assert HEX.match(getattr(theme, name)), f"{theme.key}.{name}"


def test_config_accepts_known_theme():
    config = parse_config(
        {"categories": [{"key": "a", "title": "A"}], "desktop": {"theme": "claude"}}
    )
    assert config.desktop.theme == "claude"


def test_config_rejects_unknown_theme():
    with pytest.raises(ConfigError, match="неизвестная тема"):
        parse_config({"categories": [{"key": "a", "title": "A"}], "desktop": {"theme": "x"}})
