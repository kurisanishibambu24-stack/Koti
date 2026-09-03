@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed. Get it from https://www.python.org/downloads/ and run this again.
    echo IMPORTANT: during install, tick the box that says "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [*] First run: setting up JobBot ^(this only happens once^)...
    python -m venv .venv
    ".venv\Scripts\pip.exe" install --quiet --upgrade pip
    ".venv\Scripts\pip.exe" install --quiet -r requirements.txt
)

echo [*] Starting JobBot...
echo [*] Once it says "Starting JobBot Web UI", open http://127.0.0.1:5000 in your browser.
".venv\Scripts\python.exe" jobbot.py web
pause
