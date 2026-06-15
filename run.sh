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

IMAGE_DIR="${1:-${IMAGE_DIR:-./images}}"
IMAGE_DIR="$(cd "$IMAGE_DIR" 2>/dev/null && pwd || true)"
if [ -z "$IMAGE_DIR" ] || [ ! -d "$IMAGE_DIR" ]; then
  echo "FEHLER: Bilderordner nicht gefunden. Aufruf: ./run.sh <BILDERORDNER>"
  exit 1
fi

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
