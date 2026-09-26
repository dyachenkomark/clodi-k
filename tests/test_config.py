import pytest

from clodick.config import DEFAULT_CONFIG, ConfigError, load_config, parse_config


def test_first_run_writes_default_config(tmp_path):
    path = tmp_path / "config.toml"
    config = load_config(path)
    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG
    assert [c.key for c in config.categories] == ["sport", "study", "language"]
    assert config.day_start_hour == 4
    assert config.daily_goal_minutes == 15
    assert config.reminders == ("10:00", "15:00", "20:00")
    assert config.category("language").url is None


def test_broken_toml_raises_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("day_start_hour = ", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize(
    "raw",
    [
        {"categories": []},
        {"categories": [{"key": "a"}]},
        {"categories": [{"key": "a", "title": "A"}, {"key": "a", "title": "B"}]},
        {"day_start_hour": 24, "categories": [{"key": "a", "title": "A"}]},
        {"daily_goal_minutes": 0, "categories": [{"key": "a", "title": "A"}]},
        {"reminders": ["25:00"], "categories": [{"key": "a", "title": "A"}]},
        {"reminders": ["9"], "categories": [{"key": "a", "title": "A"}]},
    ],
)
def test_invalid_config(raw):
    with pytest.raises(ConfigError):
        parse_config(raw)
