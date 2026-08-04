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
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Konfiguration (per Umgebungsvariable ueberschreibbar)
# --------------------------------------------------------------------------
# Adresse des CapCutAPI-Servers (capcut_server.py).
BASE_URL = os.environ.get("BASE_URL", "http://localhost:9001")

# >>> HIER den Ordner mit deinen Bildern/Videos eintragen. <<<
# Dann reicht spaeter:  bash run.sh   (ohne Pfad dahinter)
# Beispiel:
#   MEDIA_ORDNER = "/Users/markocolic/Desktop/Elevenlabs/Bilder"
# Tipp: Alternativ die Datei "ordner.txt" neben diesem Skript anlegen und den
# Pfad da hineinschreiben - die ueberlebt jedes Update dieses Skripts.
MEDIA_ORDNER = ""


def _ordner_aus_textdatei():
    """Liest den Medien-Ordner aus 'ordner.txt' neben diesem Skript.

    Erste nicht-leere Zeile, die nicht mit '#' beginnt. Fehlt die Datei,
    wird "" zurueckgegeben.
    """
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "ordner.txt")
    try:
        with open(pfad, encoding="utf-8") as fh:
            for zeile in fh:
                zeile = zeile.strip().strip('"').strip("'")
                if zeile and not zeile.startswith("#"):
                    return os.path.expanduser(zeile)
    except OSError:
        pass
    return ""


# Lokaler Ordner mit den Medien. Reihenfolge der Aufloesung:
#   1. erstes CLI-Argument   2. Umgebungsvariable IMAGE_DIR
#   3. MEDIA_ORDNER (oben)   4. Datei ordner.txt   5. ./images
IMAGE_DIR = (os.environ.get("IMAGE_DIR") or MEDIA_ORDNER
             or _ordner_aus_textdatei() or "./images")

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

# Verzeichnis, in dem der CapCutAPI-Server die dfd_*-Ordner anlegt
# (= Arbeitsverzeichnis des Servers, normal die geklonte ./VectCutAPI).
# Wird gebraucht, um den fertigen Entwurf automatisch nach DRAFT_FOLDER zu
# kopieren. Nicht gefunden -> Kopieren wird uebersprungen (mit Hinweis).
SERVER_DIR = os.environ.get(
    "SERVER_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "VectCutAPI"),
)

# Erlaubte Bildendungen.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Erlaubte Videoendungen. Die Laenge von MP4/MOV liest das Skript selbst
# (Standardbibliothek); fuer andere Formate wird ffprobe versucht.
VIDEO_EXTS = (".mp4", ".mov", ".m4v")
MEDIA_EXTS = IMAGE_EXTS + VIDEO_EXTS

# Wie Videos auf ihren Zeit-Slot gebracht werden:
#   "speed" - ganzes Video, exakt eingepasst (schneller/langsamer). Default.
#   "trim"  - Anfang bis zum Zeitstempel, Rest abgeschnitten (Speed 1.0).
#   "auto"  - trimmen wenn Video laeng genug, sonst per Speed einpassen.
VIDEO_FIT = os.environ.get("VIDEO_FIT", "speed").lower()

# Gemeinsame Spur fuer Bilder UND Videos (lueckenlose, einreihige Timeline).
TRACK_NAME = os.environ.get("TRACK_NAME", "main")

# Netzwerk-Timeout pro Request (Sekunden).
HTTP_TIMEOUT = 120


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
def parse_timestamp(filename):
    """Liest den Zeitstempel (Sekunden, float) aus dem Dateinamen.

    Eine fuehrende Nummerierung wird per '_' abgetrennt und ignoriert; der
    Zeitstempel ist der letzte '_'-Abschnitt. Unterstuetzte Formate:
      HH-MM-SS       z.B. 001_00-00-04      -> 4.0 s
      HH-MM-SS-mmm   z.B. 001_00-00-04-880  -> 4.880 s  (mmm = Millisekunden)
    Kuerzere Formen ('2', '1-30') werden rechtsbuendig als H-M-S gedeutet.
    Gibt None zurueck, wenn keine Zahl gefunden wird.
    """
    stem = os.path.splitext(filename)[0]
    time_part = stem.rsplit("_", 1)[-1]
    groups = [int(g) for g in re.findall(r"\d+", time_part)]
    if not groups:
        return None
    millis = 0.0
    if len(groups) >= 4:
        # H-M-S-mmm: letzte Gruppe sind Millisekunden
        millis = groups[-1] / 1000.0
        hours, minutes, seconds = groups[-4], groups[-3], groups[-2]
    else:
        hms = [0] * (3 - len(groups)) + groups   # rechtsbuendig zu [H, M, S]
        hours, minutes, seconds = hms[-3], hms[-2], hms[-1]
    return round(hours * 3600 + minutes * 60 + seconds + millis, 3)


def is_video(filename):
    return os.path.splitext(filename)[1].lower() in VIDEO_EXTS


def mp4_duration(path):
    """Liest die Dauer (Sekunden) aus der mvhd-Box eines MP4/MOV.

    Nur Standardbibliothek, kein ffmpeg. Springt durch die Box-Struktur
    (liest nicht die ganze Datei ein) und findet moov -> mvhd.
    Gibt None zurueck, wenn nichts gefunden wird.
    """
    import struct
    total = os.path.getsize(path)
    with open(path, "rb") as f:
        def find(parent_end, name):
            while f.tell() + 8 <= parent_end:
                pos = f.tell()
                head = f.read(8)
                if len(head) < 8:
                    return None
                box_size = struct.unpack(">I", head[:4])[0]
                box_type = head[4:8]
                hdr = 8
                if box_size == 1:                       # 64-bit largesize
                    box_size = struct.unpack(">Q", f.read(8))[0]
                    hdr = 16
                elif box_size == 0:                     # bis Ende
                    box_size = parent_end - pos
                if box_type == name:
                    return pos, pos + hdr, pos + box_size
                if box_size <= 0:
                    return None
                f.seek(pos + box_size)
            return None

        f.seek(0)
        moov = find(total, b"moov")
        if not moov:
            return None
        f.seek(moov[1])
        mvhd = find(moov[2], b"mvhd")
        if not mvhd:
            return None
        version = f.read(1)[0]
        if version == 1:
            f.seek(mvhd[1] + 20)
            timescale = struct.unpack(">I", f.read(4))[0]
            duration = struct.unpack(">Q", f.read(8))[0]
        else:
            f.seek(mvhd[1] + 12)
            timescale = struct.unpack(">I", f.read(4))[0]
            duration = struct.unpack(">I", f.read(4))[0]
        return duration / timescale if timescale else None


def _mp4_list_boxes(f, start, end):
    """Listet (typ, body_start, box_end) der MP4-Boxen zwischen start..end."""
    import struct
    out = []
    f.seek(start)
    while f.tell() + 8 <= end:
        pos = f.tell()
        head = f.read(8)
        if len(head) < 8:
            break
        size = struct.unpack(">I", head[:4])[0]
        typ = head[4:8]
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size <= 0:
            break
        out.append((typ, pos + hdr, pos + size))
        f.seek(pos + size)
    return out


def mp4_resolution(path):
    """Liest (Breite, Hoehe) aus der tkhd-Box des Video-Tracks. Nur Stdlib.

    Breite/Hoehe stehen als 16.16-Festkomma in den letzten 8 Bytes der tkhd.
    Genommen wird der erste Track mit Dimensionen != 0 (= der Video-Track).
    Gibt (w, h) oder None zurueck.
    """
    import struct
    total = os.path.getsize(path)
    with open(path, "rb") as f:
        top = _mp4_list_boxes(f, 0, total)
        moov = next((b for b in top if b[0] == b"moov"), None)
        if not moov:
            return None
        for typ, body, end in _mp4_list_boxes(f, moov[1], moov[2]):
            if typ != b"trak":
                continue
            for t2, b2, e2 in _mp4_list_boxes(f, body, end):
                if t2 != b"tkhd":
                    continue
                f.seek(e2 - 8)
                w = struct.unpack(">I", f.read(4))[0] >> 16
                h = struct.unpack(">I", f.read(4))[0] >> 16
                if w and h:
                    return int(w), int(h)
    return None


def ffprobe_duration(path):
    """Fallback fuer Nicht-MP4-Formate, falls ffmpeg/ffprobe vorhanden ist."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=30,
        )
        val = out.stdout.strip()
        return float(val) if val else None
    except Exception:
        return None


def video_duration(path):
    """Dauer (Sekunden) eines Videos: erst eingebauter MP4-Leser, dann ffprobe."""
    if os.path.splitext(path)[1].lower() in (".mp4", ".mov", ".m4v"):
        try:
            dur = mp4_duration(path)
            if dur and dur > 0:
                return dur
        except Exception:
            pass
    return ffprobe_duration(path)


def video_segment_params(src_len, target_dur, mode):
    """Liefert (source_start, source_end, speed) fuer ein Video.

    speed: ganzes Video exakt in den Slot (schneller/langsamer).
    trim:  Anfang bis target_dur, Speed 1.0 (nur wenn Video lang genug).
    auto:  trim wenn moeglich, sonst speed.

    Speed wird NICHT gerundet: so ergibt source_duration/speed exakt die
    Slot-Dauer, und der Server rundet erst beim us-Wert (mikrosekundengenau).
    """
    if mode in ("trim", "auto") and src_len >= target_dur:
        return 0.0, target_dur, 1.0
    speed = src_len / target_dur            # auch Fallback wenn Video zu kurz
    return 0.0, src_len, speed


def collect_media(image_dir):
    """Liefert sortierte Liste (timestamp, filename) gueltiger Bilder/Videos."""
    if not os.path.isdir(image_dir):
        sys.exit(f"FEHLER: IMAGE_DIR existiert nicht: {image_dir}")

    items = []
    skipped = []
    for name in os.listdir(image_dir):
        if os.path.splitext(name)[1].lower() not in MEDIA_EXTS:
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


def patch_video_dimensions(draft_id, segments):
    """Schreibt die echten Video-Aufloesungen in das erzeugte draft_info.json.

    Ohne ffmpeg kennt der Server die Aufloesung nicht und setzt 1920x1080.
    Wir korrigieren das anhand der lokal gemessenen Werte (Abgleich per URL).
    Rueckgabe: Anzahl korrigierter Video-Materialien.
    """
    by_url = {}
    for seg in segments:
        if seg.get("is_video") and seg.get("vid_res"):
            by_url[image_url_for(seg["filename"])] = seg["vid_res"]
    if not by_url:
        return 0
    info_path = os.path.join(SERVER_DIR, draft_id, "draft_info.json")
    if not os.path.isfile(info_path):
        return 0
    try:
        with open(info_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return 0
    fixed = 0
    for mat in data.get("materials", {}).get("videos", []):
        if mat.get("type") != "video":
            continue
        res = by_url.get(mat.get("remote_url"))
        if res:
            mat["width"], mat["height"] = int(res[0]), int(res[1])
            fixed += 1
    if fixed:
        try:
            with open(info_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except OSError:
            return 0
    return fixed


def install_draft(draft_id):
    """Kopiert den fertigen dfd_-Ordner von SERVER_DIR nach DRAFT_FOLDER.

    save_draft schreibt den Ordner ins Arbeitsverzeichnis des Servers (nicht
    automatisch nach DRAFT_FOLDER). Da save_draft synchron ist, ist der Ordner
    hier bereits vollstaendig. Rueckgabe: Zielpfad bei Erfolg, sonst None.
    """
    src = os.path.join(SERVER_DIR, draft_id)
    if not os.path.isdir(src):
        print(f"Hinweis: Entwurfsordner nicht in SERVER_DIR gefunden:\n  {src}")
        print("  -> Der Server lief evtl. in einem anderen Verzeichnis.")
        print(f"  -> Suche den Ordner '{draft_id}' im Arbeitsverzeichnis deines")
        print(f"     Servers und kopiere ihn manuell nach:\n     {DRAFT_FOLDER}")
        return None
    dst = os.path.join(DRAFT_FOLDER, draft_id)
    if os.path.abspath(src) == os.path.abspath(dst):
        return dst  # liegt bereits am Ziel
    try:
        os.makedirs(DRAFT_FOLDER, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return dst
    except OSError as exc:
        print(f"Hinweis: automatisches Kopieren fehlgeschlagen: {exc}")
        print(f"  Bitte manuell kopieren:\n    cp -R '{src}' '{DRAFT_FOLDER}/'")
        return None


# --------------------------------------------------------------------------
# Hauptablauf
# --------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    dry_run = "--dry-run" in flags or "-n" in flags
    assume_yes = "--yes" in flags or "-y" in flags
    no_install = "--no-install" in flags

    image_dir = args[0] if args else IMAGE_DIR
    image_dir = os.path.abspath(os.path.expanduser(image_dir))

    print("Konfiguration:")
    print(f"  BASE_URL     = {BASE_URL}")
    print(f"  IMAGE_DIR    = {image_dir}")
    print(f"  IMAGE_BASE   = {IMAGE_BASE}")
    print(f"  WIDTH x HEIGHT = {WIDTH} x {HEIGHT}")
    print(f"  DRAFT_FOLDER = {DRAFT_FOLDER}")
    print()

    items = collect_media(image_dir)
    if not items:
        sys.exit(f"FEHLER: keine Medien ({', '.join(MEDIA_EXTS)}) in {image_dir}")

    segments = build_segments(items)
    if not segments:
        sys.exit("FEHLER: keine gueltigen Segmente (alle Dauern <= 0).")

    # Medien-Infos ermitteln (fuer Videos: Laenge messen, Speed berechnen).
    for seg in segments:
        seg["is_video"] = is_video(seg["filename"])
        if not seg["is_video"]:
            continue
        path = os.path.join(image_dir, seg["filename"])
        length = video_duration(path)
        if not length or length <= 0:
            sys.exit(
                f"FEHLER: Videolaenge nicht lesbar: {seg['filename']}\n"
                "  Der eingebaute Leser unterstuetzt MP4/MOV. Fuer andere\n"
                "  Formate ffmpeg installieren:  brew install ffmpeg")
        seg["src_len"] = length
        try:
            seg["vid_res"] = mp4_resolution(path)
        except Exception:
            seg["vid_res"] = None
        s_start, s_end, speed = video_segment_params(
            length, seg["duration"], VIDEO_FIT)
        seg["src_start"], seg["src_end"], seg["speed"] = s_start, s_end, speed
        if not 0.1 <= speed <= 100:
            print(f"  WARNUNG: {seg['filename']} braucht {speed:.3f}x "
                  "(ausserhalb 0.1-100x) - CapCut kann das evtl. nicht.")

    # Geplanten Ablauf zur Kontrolle ausgeben.
    print(f"Geplanter Ablauf (Video-Modus: {VIDEO_FIT}):")
    print(f"  {'Datei':<26} {'Typ':<6} {'Start':>8} {'Ende':>8} "
          f"{'Dauer':>8}  Hinweis")
    for seg in segments:
        if seg["is_video"]:
            typ = "Video"
            res = seg.get("vid_res")
            res_txt = f", {res[0]}x{res[1]}" if res else ""
            if abs(seg["speed"] - 1.0) < 1e-6:
                hint = f"1.000x (Quelle {seg['src_len']:.3f}s{res_txt})"
            else:
                verb = "schneller" if seg["speed"] > 1 else "langsamer"
                hint = (f"{seg['speed']:.3f}x {verb} "
                        f"(Quelle {seg['src_len']:.3f}s{res_txt})")
        else:
            typ = "Bild"
            hint = ""
        print(f"  {seg['filename']:<26} {typ:<6} {seg['start']:>8.3f} "
              f"{seg['end']:>8.3f} {seg['duration']:>8.3f}  {hint}")
    total = segments[-1]["end"]
    print(f"  -> {len(segments)} Segmente, Gesamtlaenge {total:.3f}s")
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

    # 2) Bilder/Videos hinzufuegen (alles auf einer Spur, lueckenlos).
    for seg in segments:
        url = image_url_for(seg["filename"])
        if seg["is_video"]:
            print(f"add_video  {seg['filename']}  "
                  f"{seg['start']:.3f}->{seg['end']:.3f}s  {seg['speed']:.3f}x")
            check_response("/add_video", post("/add_video", {
                "video_url": url,
                "draft_id": draft_id,
                "target_start": seg["start"],
                "start": seg["src_start"],
                "end": seg["src_end"],
                "speed": seg["speed"],
                "duration": seg["src_len"],
                "track_name": TRACK_NAME,
                "width": WIDTH,
                "height": HEIGHT,
            }))
        else:
            print(f"add_image  {seg['filename']}  "
                  f"{seg['start']:.3f}->{seg['end']:.3f}s")
            check_response("/add_image", post("/add_image", {
                "image_url": url,
                "draft_id": draft_id,
                "start": seg["start"],
                "end": seg["end"],
                "track_name": TRACK_NAME,
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

    # 3b) Echte Video-Aufloesungen ins JSON schreiben (Server kann sie ohne
    #     ffmpeg nicht lesen und nutzt sonst 1920x1080).
    fixed = patch_video_dimensions(draft_id, segments)
    if fixed:
        print(f"  Aufloesung gesetzt fuer {fixed} Video(s).")

    # 4) Entwurf nach DRAFT_FOLDER kopieren (ausser --no-install).
    print()
    if no_install:
        print("Fertig (ohne Installation, --no-install).")
        print(f"  draft_id = {draft_id}")
        print(f"  Erzeugter Ordner: {os.path.join(SERVER_DIR, draft_id)}")
        print(f"  Manuell nach {DRAFT_FOLDER} kopieren und CapCut neu starten.")
        return

    installed = install_draft(draft_id)
    print()
    print("Fertig.")
    print(f"  draft_id = {draft_id}")
    if installed:
        print(f"  Entwurf installiert: {installed}")
        print("  -> CapCut zuerst beenden, dann neu starten. Der Entwurf")
        print("     erscheint dann in der Projektliste.")
    else:
        print("  Entwurf NICHT automatisch installiert (Hinweis oben beachten).")


if __name__ == "__main__":
    main()
