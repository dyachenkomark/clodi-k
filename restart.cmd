@echo off
rem Update cloDICK and restart the raccoon. Double-click or run: restart.cmd
cd /d "%~dp0"
taskkill /im clodick-gui.exe /f >nul 2>&1
git pull --ff-only
uv sync
start "" ".venv\Scripts\clodick-gui.exe"
