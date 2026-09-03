#!/data/data/com.termux/files/usr/bin/bash
# JobBot launcher for Termux (Android)
set -e
cd "$(dirname "$0")"

echo "[*] Checking Python..."
if ! command -v python &> /dev/null; then
    echo "[*] Installing Python via Termux package manager..."
    pkg update -y && pkg install -y python
fi

if [ ! -d ".venv" ]; then
    echo "[*] First run: setting up JobBot (this only happens once)..."
    python -m venv .venv
    ./.venv/bin/pip install --quiet --upgrade pip
    ./.venv/bin/pip install --quiet -r requirements.txt
fi

echo "[*] Starting JobBot..."
echo "[*] Once it says 'Starting JobBot Web UI', open Chrome and go to: http://127.0.0.1:5000"
./.venv/bin/python jobbot.py web
