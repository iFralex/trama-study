#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"
export PLAYWRIGHT_BROWSERS_PATH="$PROJECT_DIR/.state/browsers"
if [ ! -x .venv/bin/python ]; then
  echo "Esegui prima Setup.command."
  read -r -p "Invio per chiudere " _
  exit 1
fi
.venv/bin/python -m polimi_lectures.start
