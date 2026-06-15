#!/usr/bin/env python3
"""Baut aus einem Ordner mit zeitgestempelten Bildern einen CapCut-Entwurf.

Dateiname = Zeitstempel (HH-MM-SS, fuehrende Nullen egal). Jedes Bild laeuft
lueckenlos bis zu seinem eigenen Zeitstempel:
    00-00-02.png -> 0..2 s
    00-00-05.png -> 2..5 s
    00-00-08.png -> 5..8 s

Verwendet die lokale CapCutAPI (https://github.com/sun-guannan/CapCutAPI):
    POST /create_draft {width, height}            -> draft_id
    POST /add_image    {image_url, draft_id, ...}  je Bild
    POST /save_draft   {draft_id, draft_folder}    schreibt dfd_*-Ordner

Nur Standardbibliothek noetig (urllib) – laeuft auch ausserhalb des venv.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Konfiguration (per Umgebungsvariable ueberschreibbar)
# --------------------------------------------------------------------------
# Adresse des CapCutAPI-Servers (capcut_server.py).
BASE_URL = os.environ.get("BASE_URL", "http://localhost:9001")

# Lokaler Ordner mit den Bildern. Reihenfolge der Aufloesung:
#   1. erstes CLI-Argument   2. Umgebungsvariable IMAGE_DIR   3. ./images
IMAGE_DIR = os.environ.get("IMAGE_DIR", "./images")

# Basis-URL, unter der derselbe Ordner per HTTP erreichbar ist
# (typisch: im Bilderordner `python3 -m http.server 8000`). Mit / am Ende.
IMAGE_BASE = os.environ.get("IMAGE_BASE", "http://localhost:8000/")

# Projekt-Aufloesung.
WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))

# CapCut-Projektordner (macOS-Standard). <user> wird ueber das Home aufgeloest.
DRAFT_FOLDER = os.environ.get(
    "DRAFT_FOLDER",
    os.path.expanduser(
        "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
    ),
)

# Erlaubte Bildendungen.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Netzwerk-Timeout pro Request (Sekunden).
HTTP_TIMEOUT = 120


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
def parse_timestamp(filename):
    """Liest den Zeitstempel (Sekunden, float) aus dem Dateinamen.

    Nimmt alle Zahlengruppen im Namen (ohne Endung) und interpretiert die
    letzten drei rechtsbuendig als H, M, S. So funktionieren '00-00-02',
    '2', '1-30' (= 1 min 30 s) und '01-02-03' gleichermassen.
    Gibt None zurueck, wenn keine Zahl gefunden wird.
    """
    stem = os.path.splitext(filename)[0]
    groups = re.findall(r"\d+", stem)
    if not groups:
        return None
    nums = [int(g) for g in groups][-3:]      # nur die letzten drei zaehlen
    nums = [0] * (3 - len(nums)) + nums        # rechtsbuendig zu [H, M, S]
    hours, minutes, seconds = nums
    return hours * 3600 + minutes * 60 + seconds


def collect_images(image_dir):
    """Liefert sortierte Liste (timestamp, filename) der gueltigen Bilder."""
    if not os.path.isdir(image_dir):
        sys.exit(f"FEHLER: IMAGE_DIR existiert nicht: {image_dir}")

    items = []
    skipped = []
    for name in os.listdir(image_dir):
        if os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
            continue
        ts = parse_timestamp(name)
        if ts is None:
            skipped.append(name)
            continue
        items.append((ts, name))

    if skipped:
        print("Hinweis: ohne erkennbaren Zeitstempel uebersprungen: "
              + ", ".join(sorted(skipped)))

    items.sort(key=lambda x: (x[0], x[1]))
    return items


def build_segments(items):
    """Baut lueckenlose Segmente. start = Ende des Vorgaengers, end = ts.

    Segmente mit Dauer <= 0 werden uebersprungen.
    Rueckgabe: Liste von dicts {filename, start, end, duration}.
    """
    segments = []
    prev_end = 0.0
    for ts, name in items:
        start = prev_end
        end = float(ts)
        prev_end = end
        if end - start <= 0:
            print(f"Hinweis: {name} uebersprungen (Dauer <= 0: "
                  f"{start:.3f} -> {end:.3f})")
            continue
        segments.append({
            "filename": name,
            "start": start,
            "end": end,
            "duration": end - start,
        })
    return segments


def image_url_for(filename):
    """IMAGE_BASE + URL-kodierter Dateiname."""
    base = IMAGE_BASE if IMAGE_BASE.endswith("/") else IMAGE_BASE + "/"
    return base + urllib.parse.quote(filename)


def post(path, body):
    """POST JSON an BASE_URL+path, gib geparste JSON-Antwort zurueck."""
    url = BASE_URL.rstrip("/") + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except ValueError:
            sys.exit(f"FEHLER {path}: HTTP {exc.code}: {raw[:500]}")
    except urllib.error.URLError as exc:
        sys.exit(f"FEHLER {path}: Server nicht erreichbar ({BASE_URL}): "
                 f"{exc.reason}\nLaeuft 'python capcut_server.py'?")
    try:
        return json.loads(raw)
    except ValueError:
        sys.exit(f"FEHLER {path}: keine JSON-Antwort: {raw[:500]}")


def find_draft_id(payload):
    """Sucht 'draft_id' rekursiv irgendwo in der Antwort (output/result/...)."""
    found = []

    def walk(obj):
        if isinstance(obj, dict):
            for key, val in obj.items():
                if key == "draft_id" and isinstance(val, str) and val:
                    found.append(val)
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return found[0] if found else None


def check_response(path, payload):
    """Prueft das success/error-Feld und bricht bei Fehler ab."""
    if isinstance(payload, dict) and payload.get("success") is False:
        err = payload.get("error") or payload.get("output") or payload
        sys.exit(f"FEHLER {path}: Server meldet Fehler: {err}")
    return payload


# --------------------------------------------------------------------------
# Hauptablauf
# --------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    dry_run = "--dry-run" in flags or "-n" in flags
    assume_yes = "--yes" in flags or "-y" in flags

    image_dir = args[0] if args else IMAGE_DIR
    image_dir = os.path.abspath(os.path.expanduser(image_dir))

    print("Konfiguration:")
    print(f"  BASE_URL     = {BASE_URL}")
    print(f"  IMAGE_DIR    = {image_dir}")
    print(f"  IMAGE_BASE   = {IMAGE_BASE}")
    print(f"  WIDTH x HEIGHT = {WIDTH} x {HEIGHT}")
    print(f"  DRAFT_FOLDER = {DRAFT_FOLDER}")
    print()

    items = collect_images(image_dir)
    if not items:
        sys.exit(f"FEHLER: keine Bilder ({', '.join(IMAGE_EXTS)}) in {image_dir}")

    segments = build_segments(items)
    if not segments:
        sys.exit("FEHLER: keine gueltigen Segmente (alle Dauern <= 0).")

    # Geplanten Ablauf zur Kontrolle ausgeben.
    print("Geplanter Ablauf:")
    print(f"  {'Datei':<30} {'Start':>8} {'Ende':>8} {'Dauer':>8}")
    for seg in segments:
        print(f"  {seg['filename']:<30} {seg['start']:>8.2f} "
              f"{seg['end']:>8.2f} {seg['duration']:>8.2f}")
    total = segments[-1]["end"]
    print(f"  -> {len(segments)} Segmente, Gesamtlaenge {total:.2f}s")
    print()

    if dry_run:
        print("--dry-run: nichts gebaut.")
        return

    if not assume_yes and sys.stdin.isatty():
        answer = input("Entwurf jetzt bauen? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "j", "ja"):
            print("Abgebrochen.")
            return

    # 1) Draft anlegen.
    print("create_draft ...")
    resp = check_response("/create_draft", post("/create_draft", {
        "width": WIDTH, "height": HEIGHT,
    }))
    draft_id = find_draft_id(resp)
    if not draft_id:
        sys.exit(f"FEHLER: keine draft_id in Antwort: {json.dumps(resp)[:500]}")
    print(f"  draft_id = {draft_id}")

    # 2) Bilder hinzufuegen.
    for seg in segments:
        url = image_url_for(seg["filename"])
        print(f"add_image  {seg['filename']}  "
              f"{seg['start']:.2f}->{seg['end']:.2f}s")
        check_response("/add_image", post("/add_image", {
            "image_url": url,
            "draft_id": draft_id,
            "start": seg["start"],
            "end": seg["end"],
            "width": WIDTH,
            "height": HEIGHT,
        }))

    # 3) Speichern -> erzeugt dfd_*-Ordner.
    print("save_draft ...")
    resp = check_response("/save_draft", post("/save_draft", {
        "draft_id": draft_id,
        "draft_folder": DRAFT_FOLDER,
    }))
    print(f"  Antwort: {json.dumps(resp)[:500]}")

    print()
    print("Fertig.")
    print(f"  draft_id = {draft_id}")
    print(f"  Ziel-Ordner: {DRAFT_FOLDER}")
    print("Erscheint der Entwurf nicht in CapCut: den erzeugten dfd_*-Ordner")
    print("nach DRAFT_FOLDER kopieren und CapCut neu starten.")


if __name__ == "__main__":
    main()
