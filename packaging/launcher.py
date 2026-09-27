"""Точка входа для сборки в exe: запускает персонажа без консольного окна."""

from clodick.app import gui_main

if __name__ == "__main__":
    raise SystemExit(gui_main())
