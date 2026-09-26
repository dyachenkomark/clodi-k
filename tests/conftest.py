import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from clodick.config import parse_config
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLODICK_HOME", str(tmp_path / "home"))


@pytest.fixture
def config():
    return parse_config(
        {
            "day_start_hour": 4,
            "reminders": ["10:00", "20:00"],
            "categories": [
                {"key": "sport", "title": "Спорт"},
                {"key": "study", "title": "Учёба"},
                {"key": "language", "title": "Язык", "url": "https://example.com"},
            ],
        }
    )


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "test.db")
    yield CompletionRepository(conn)
    conn.close()
