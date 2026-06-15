#!/usr/bin/env bash
# Schritt 2: CapCutAPI klonen, venv anlegen, Abhaengigkeiten + config.json.
# Idempotent: vorhandenes ./VectCutAPI / venv werden wiederverwendet.
set -euo pipefail

cd "$(dirname "$0")"
REPO_DIR="VectCutAPI"
REPO_URL="https://github.com/sun-guannan/CapCutAPI.git"

# 1) Klonen (oder vorhandenen Klon aktualisieren).
if [ -d "$REPO_DIR/.git" ]; then
  echo "==> $REPO_DIR existiert bereits – ueberspringe Klonen."
else
  echo "==> Klone $REPO_URL nach ./$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

# 2) venv anlegen.
if [ ! -d ".venv" ]; then
  echo "==> Lege venv an (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) Abhaengigkeiten installieren (nur ins venv, nicht systemweit).
python -m pip install --upgrade pip
if [ -f requirements.txt ]; then
  echo "==> Installiere requirements.txt"
  python -m pip install -r requirements.txt
else
  echo "WARN: keine requirements.txt gefunden."
fi

# 4) config.json aus Beispiel anlegen (vorhandene nicht ueberschreiben).
if [ -f config.json ]; then
  echo "==> config.json existiert bereits – unveraendert."
elif [ -f config.json.example ]; then
  echo "==> Kopiere config.json.example -> config.json"
  cp config.json.example config.json
else
  echo "WARN: weder config.json noch config.json.example gefunden."
fi

echo
echo "Setup fertig. Server-Start:  cd $REPO_DIR && source .venv/bin/activate && python capcut_server.py"
