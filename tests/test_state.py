from clodick.storage.db import connect
from clodick.storage.state import StateStore


def test_roundtrip(tmp_path):
    conn = connect(tmp_path / "s.db")
    state = StateStore(conn)
    assert state.get("house_pos") is None
    assert state.get("walks", True) is True
    state.set("house_pos", [10, 20])
    state.set("walks", False)
    state.set("walks", True)
    assert state.get("house_pos") == [10, 20]
    assert state.get("walks") is True
    conn.close()
