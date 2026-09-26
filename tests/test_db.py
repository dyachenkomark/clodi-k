from clodick.storage.db import MIGRATIONS, connect


def test_migrations_apply_once(tmp_path):
    path = tmp_path / "x.db"
    conn = connect(path)
    conn.close()
    conn = connect(path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert version == len(MIGRATIONS)
