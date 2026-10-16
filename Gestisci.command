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
.venv/bin/python -c 'from polimi_lectures.config import data_root; print("Cartella dati:", data_root())'
echo "1) Login, ricerca corso e download guidato"
echo "2) Scarica lezioni raccolte"
echo "3) Prima prova: scarica una lezione"
echo "4) Mostra catalogo di tutti i corsi"
echo "5) Controlla installazione"
echo "6) Raccogli lezioni manualmente dal browser"
echo "7) Scarica materiali WeBeep"
echo "8) Trascrivi lezioni scaricate"
echo "9) Scegli o scarica il modello Whisper"
echo "10) Associa slide e materiali alle lezioni"
read -r -p "Numero dell'operazione [1]: " ACTION
ACTION="${ACTION:-1}"
case "$ACTION" in
  1|2|3|6|7|8|10) ;;
  9)
    .venv/bin/python -m polimi_lectures.cli whisper-model
    read -r -p "Invio per chiudere " _
    exit 0
    ;;
  4)
    .venv/bin/python -m polimi_lectures.cli status
    read -r -p "Invio per chiudere " _
    exit 0
    ;;
  5)
    .venv/bin/python -m polimi_lectures.cli doctor
    read -r -p "Invio per chiudere " _
    exit 0
    ;;
  *) echo "Scelta non valida."; exit 1 ;;
esac
DEFAULT_COURSE="$(.venv/bin/python -c 'from polimi_lectures.config import load_config; print(load_config().get("last_course", ""))')"
COURSE_PROMPT="Nome o codice del corso"
if [ -n "$DEFAULT_COURSE" ]; then COURSE_PROMPT="$COURSE_PROMPT [$DEFAULT_COURSE]"; fi
while true; do
  read -r -p "$COURSE_PROMPT: " COURSE_NAME
  COURSE_NAME="${COURSE_NAME#"${COURSE_NAME%%[![:space:]]*}"}"
  COURSE_NAME="${COURSE_NAME%"${COURSE_NAME##*[![:space:]]}"}"
  COURSE_NAME="${COURSE_NAME:-$DEFAULT_COURSE}"
  if [ -z "$COURSE_NAME" ] || [[ "$COURSE_NAME" =~ ^[0-9]{1,4}$ ]]; then
    echo "Scrivi il nome o il codice del corso."
  else
    break
  fi
done
echo "Corso selezionato: $COURSE_NAME"
case "$ACTION" in
  1) .venv/bin/python -m polimi_lectures.cli wizard --course "$COURSE_NAME" ;;
  2) .venv/bin/python -m polimi_lectures.cli download --course "$COURSE_NAME" ;;
  3) .venv/bin/python -m polimi_lectures.cli wizard --course "$COURSE_NAME" ;;
  4) .venv/bin/python -m polimi_lectures.cli status --course "$COURSE_NAME" ;;
  6) .venv/bin/python -m polimi_lectures.cli discover --course "$COURSE_NAME" ;;
  7) .venv/bin/python -m polimi_lectures.cli materials --course "$COURSE_NAME" ;;
  8) .venv/bin/python -m polimi_lectures.cli transcribe --course "$COURSE_NAME" ;;
  10) .venv/bin/python -m polimi_lectures.cli align --course "$COURSE_NAME" ;;
esac
read -r -p "Invio per chiudere " _
