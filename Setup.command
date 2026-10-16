#!/bin/bash
set -euo pipefail
umask 077
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"
python3 -m polimi_lectures.configure
export PLAYWRIGHT_BROWSERS_PATH="$PROJECT_DIR/.state/browsers"
export PIP_CACHE_DIR="$PROJECT_DIR/.state/pip-cache"
mkdir -p .state
chmod 700 .state
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m playwright install chromium
.venv/bin/python -m polimi_lectures.cli doctor
echo "Setup completato. Apri Avvia.command."
if [ -t 0 ]; then read -r -p "Invio per chiudere " _; fi
