#!/usr/bin/env bash
# JobBot launcher for macOS / Linux
set -e
cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[*] First run: setting up JobBot (this only happens once)..."
    python3 -m venv .venv
    ./.venv/bin/pip install --quiet --upgrade pip
    ./.venv/bin/pip install --quiet -r requirements.txt
fi

echo "[*] Starting JobBot..."
echo "[*] Once it says 'Starting JobBot Web UI', open http://127.0.0.1:5000 in your browser."
./.venv/bin/python jobbot.py web
