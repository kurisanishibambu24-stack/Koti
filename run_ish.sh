#!/bin/sh
# JobBot launcher for iSH (iPhone/iPad)
set -e
cd "$(dirname "$0")"

echo "[*] Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "[*] Installing Python via apk (this can take a few minutes on iSH)..."
    apk update && apk add python3 py3-pip
fi

if [ ! -d ".venv" ]; then
    echo "[*] First run: setting up JobBot (this only happens once)..."
    python3 -m venv .venv
    ./.venv/bin/pip install --quiet --upgrade pip
    ./.venv/bin/pip install --quiet -r requirements.txt
fi

echo "[*] Starting JobBot..."
echo "[*] Once it says 'Starting JobBot Web UI', open Safari and go to: http://127.0.0.1:5000"
./.venv/bin/python jobbot.py web
