#!/usr/bin/env bash
# Startet CapCutAPI-Server (9001) + HTTP-Server fuer Bilder (8000) im
# Hintergrund und fuehrt danach build_capcut_draft.py aus.
#
# Nutzung:   ./run.sh [BILDERORDNER]
# Beispiel:  ./run.sh ~/Desktop/meine_bilder
#
# Voraussetzung: einmalig ./setup.sh ausgefuehrt (legt VectCutAPI/.venv an).
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

# Ordner: 1. Argument, 2. Umgebungsvariable, 3. MEDIA_ORDNER aus dem Skript.
IMAGE_DIR="${1:-${IMAGE_DIR:-}}"
if [ -z "$IMAGE_DIR" ]; then
  IMAGE_DIR="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import build_capcut_draft as b; print(b.IMAGE_DIR)' "$ROOT" 2>/dev/null || true)"
fi

RESOLVED="$(cd "${IMAGE_DIR:-.}" 2>/dev/null && pwd || true)"
if [ -z "$IMAGE_DIR" ] || [ -z "$RESOLVED" ] || [ ! -d "$RESOLVED" ]; then
  echo "FEHLER: Medien-Ordner nicht gefunden${IMAGE_DIR:+: $IMAGE_DIR}"
  echo
  echo "Zwei Moeglichkeiten:"
  echo "  1) Ordner direkt uebergeben:"
  echo "       bash run.sh \"/Users/$(whoami)/Desktop/MeinOrdner\""
  echo "     (Tipp: 'bash run.sh ' tippen und den Ordner aus dem Finder"
  echo "      ins Terminal ziehen - der Pfad wird eingefuegt.)"
  echo "  2) Ordner einmalig oben in build_capcut_draft.py eintragen:"
  echo "       MEDIA_ORDNER = \"/Pfad/zu/deinem/Ordner\""
  exit 1
fi
IMAGE_DIR="$RESOLVED"
echo "==> Medien-Ordner: $IMAGE_DIR"

API_PORT="${API_PORT:-9001}"
HTTP_PORT="${HTTP_PORT:-8000}"
export BASE_URL="${BASE_URL:-http://localhost:${API_PORT}}"
export IMAGE_BASE="${IMAGE_BASE:-http://localhost:${HTTP_PORT}/}"
export IMAGE_DIR

PIDS=()
cleanup() {
  echo
  echo "==> Stoppe Hintergrund-Server (${PIDS[*]:-keine})"
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

wait_for_port() {  # $1=port $2=name
  for _ in $(seq 1 30); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
      exec 3>&- 3<&- ; echo "    $2 (Port $1) ist bereit."; return 0
    fi
    sleep 0.5
  done
  echo "FEHLER: $2 (Port $1) wurde nicht bereit."; return 1
}

# (a) CapCutAPI-Server starten.
if [ ! -d "$ROOT/VectCutAPI/.venv" ]; then
  echo "FEHLER: VectCutAPI/.venv fehlt. Bitte zuerst ./setup.sh ausfuehren."
  exit 1
fi
echo "==> Starte CapCutAPI-Server auf Port ${API_PORT}"
(
  cd "$ROOT/VectCutAPI"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec python capcut_server.py
) > "$ROOT/server.log" 2>&1 &
PIDS+=($!)

# (b) HTTP-Server im Bilderordner starten.
echo "==> Starte HTTP-Server fuer Bilder auf Port ${HTTP_PORT} ($IMAGE_DIR)"
(
  cd "$IMAGE_DIR"
  exec python3 -m http.server "$HTTP_PORT"
) > "$ROOT/http.log" 2>&1 &
PIDS+=($!)

wait_for_port "$API_PORT" "CapCutAPI-Server"
wait_for_port "$HTTP_PORT" "Bild-HTTP-Server"

# (c) Build ausfuehren.
echo "==> Baue Entwurf"
python3 "$ROOT/build_capcut_draft.py" "$IMAGE_DIR" "${@:2}"

echo "==> Build beendet. Server werden gestoppt (Logs: server.log / http.log)."
