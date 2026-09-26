from clodick.app import main


def test_cli_flow(capsys):
    assert main(["status"]) == 0
    assert "0/3" in capsys.readouterr().out

    assert main(["done", "sport"]) == 0
    out = capsys.readouterr().out
    assert "1/3" in out
    assert "[x] Спорт" in out

    assert main(["done", "sport"]) == 0
    assert "Уже отмечено" in capsys.readouterr().out

    assert main(["undo", "sport"]) == 0
    assert "0/3" in capsys.readouterr().out


def test_cli_unknown_category(capsys):
    assert main(["done", "chess"]) == 2
    assert "Неизвестное направление" in capsys.readouterr().err
