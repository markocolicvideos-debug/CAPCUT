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

# 2) venv mit Python 3.10+ anlegen.
#    Der Server nutzt 3.10er-Syntax (z.B. 'str | None'), 3.9 reicht NICHT.
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  command -v "$cand" >/dev/null 2>&1 || continue
  v=$("$cand" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null) || continue
  if [ "${v:-0}" -ge 310 ] 2>/dev/null; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "FEHLER: Kein Python 3.10+ gefunden."
  echo "  Installiere eines, z.B. mit Homebrew:  brew install python@3.11"
  exit 1
fi
echo "==> Nutze $PY ($("$PY" --version 2>&1))"

# Vorhandene venv mit zu alter Python-Version verwerfen und neu aufbauen.
if [ -d ".venv" ]; then
  vv=$(.venv/bin/python -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
  if [ "${vv:-0}" -lt 310 ]; then
    echo "==> Vorhandene .venv ist zu alt (Python <3.10) – wird neu aufgebaut."
    rm -rf .venv
  fi
fi
if [ ! -d ".venv" ]; then
  echo "==> Lege venv an (.venv) mit $PY"
  "$PY" -m venv .venv
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
