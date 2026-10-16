#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m polimi_lectures.studio
result=$?
if [ "$result" -ne 0 ]; then
  read -r -p "Invio per chiudere "
fi
exit "$result"
