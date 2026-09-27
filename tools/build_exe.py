"""Собирает cloDICK в папку с exe через PyInstaller.

    uv run --with pyinstaller python tools/build_exe.py

Результат: dist/cloDICK/cloDICK.exe на Windows (на Linux — dist/cloDICK/cloDICK).
Собирать нужно на той же ОС, для которой сборка: PyInstaller не умеет кросс-компиляцию.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    icon = BUILD / "cloDICK.ico"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py"), str(icon)], check=True)
    assets = ROOT / "src" / "clodick" / "assets"
    PyInstaller.__main__.run(
        [
            str(ROOT / "packaging" / "launcher.py"),
            "--name=cloDICK",
            "--windowed",
            "--onedir",
            "--noconfirm",
            "--clean",
            f"--icon={icon}",
            f"--paths={ROOT / 'src'}",
            f"--add-data={assets}{os.pathsep}clodick/assets",
            "--exclude-module=tkinter",
            "--exclude-module=unittest",
            "--exclude-module=pydoc",
            f"--distpath={ROOT / 'dist'}",
            f"--workpath={BUILD / 'pyinstaller'}",
            f"--specpath={BUILD}",
        ]
    )


if __name__ == "__main__":
    main()
