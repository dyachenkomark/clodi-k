from clodick.app import main


def test_cli_flow(capsys):
    assert main(["status"]) == 0
    assert "0/3" in capsys.readouterr().out

    assert main(["done", "sport"]) == 0
    out = capsys.readouterr().out
    assert "1/3" in out
    assert "[x] Sport" in out

    assert main(["done", "sport"]) == 0
    assert "Already marked" in capsys.readouterr().out

    assert main(["undo", "sport"]) == 0
    assert "0/3" in capsys.readouterr().out


def test_cli_unknown_category(capsys):
    assert main(["done", "chess"]) == 2
    assert "Unknown item" in capsys.readouterr().err


def test_cli_notes_and_export(capsys, tmp_path):
    assert main(["done", "sport"]) == 0
    assert main(["note", "sport", "5", "km"]) == 0
    out = capsys.readouterr().out
    assert "- 5 km" in out

    assert main(["notes"]) == 0
    assert "Sport: 5 km" in capsys.readouterr().out

    path = tmp_path / "history.csv"
    assert main(["export", str(path)]) == 0
    assert "Exported 1 days" in capsys.readouterr().out
    assert "5 km" in path.read_text(encoding="utf-8-sig")

    assert main(["note", "chess", "e4"]) == 2
