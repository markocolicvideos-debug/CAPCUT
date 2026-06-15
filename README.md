# CAPCUT – Entwurf aus zeitgestempelten Bildern bauen

Aus einem Ordner mit Bildern, deren **Dateiname der Zeitstempel** ist
(`HH-MM-SS`, z.B. `00-00-02.png` = Sekunde 2), wird automatisch ein
bearbeitbarer CapCut-Entwurf erzeugt. Jedes Bild laeuft **lueckenlos** bis zu
seinem eigenen Zeitstempel:

| Datei          | Start | Ende |
|----------------|-------|------|
| `00-00-02.png` | 0 s   | 2 s  |
| `00-00-05.png` | 2 s   | 5 s  |
| `00-00-08.png` | 5 s   | 8 s  |

Grundlage ist das Open-Source-Tool
[CapCutAPI](https://github.com/sun-guannan/CapCutAPI), das lokal einen Server
startet und CapCut-Draft-Dateien erzeugt (Zeiten in Sekunden als Floats).

## Voraussetzungen (macOS)

```bash
python3 --version    # 3.10 oder hoeher
ffmpeg -version
git --version
```

Fehlendes per Homebrew installieren:

```bash
brew install python ffmpeg git
```

## Schritt 1 – einmaliges Setup

Klont CapCutAPI nach `./VectCutAPI`, legt ein venv an, installiert
`requirements.txt` und kopiert `config.json.example` → `config.json`:

```bash
./setup.sh
```

## Schritt 2 – Startreihenfolge

Drei Prozesse, in dieser Reihenfolge:

```bash
# (a) CapCutAPI-Server (Terminal 1)
cd VectCutAPI && source .venv/bin/activate && python capcut_server.py   # Port 9001

# (b) HTTP-Server im Bilderordner (Terminal 2) – liefert die Bilder per URL aus
cd /pfad/zu/deinen/bildern && python3 -m http.server 8000

# (c) Build (Terminal 3)
python3 build_capcut_draft.py /pfad/zu/deinen/bildern
```

Warum (b)? CapCutAPI laedt Bilder ueber eine **URL** (`image_url`). Der lokale
HTTP-Server macht den Bilderordner unter `http://localhost:8000/` erreichbar,
ohne deine Dateien anzufassen.

### Bequemer: run.sh

`run.sh` startet (a) und (b) im Hintergrund, wartet bis beide Ports bereit
sind, fuehrt den Build aus und stoppt die Server danach wieder:

```bash
./run.sh /pfad/zu/deinen/bildern
```

Logs der Hintergrund-Server: `server.log`, `http.log`.

## Konfiguration

Oben in `build_capcut_draft.py` bzw. per Umgebungsvariable:

| Variable       | Default                                                              |
|----------------|---------------------------------------------------------------------|
| `BASE_URL`     | `http://localhost:9001`                                             |
| `IMAGE_DIR`    | 1. CLI-Argument, sonst `./images`                                  |
| `IMAGE_BASE`   | `http://localhost:8000/`                                            |
| `WIDTH`/`HEIGHT` | `1920` / `1080`                                                  |
| `DRAFT_FOLDER` | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` (macOS)     |

Vorschau ohne zu bauen:

```bash
python3 build_capcut_draft.py /pfad/zu/bildern --dry-run
```

## Schritt 3 – Entwurf in CapCut oeffnen

`save_draft` erzeugt einen Ordner, der mit `dfd_` beginnt. Erscheint der
Entwurf **nicht automatisch** in CapCut:

1. Den erzeugten `dfd_*`-Ordner nach `DRAFT_FOLDER` kopieren
   (`~/Movies/CapCut/User Data/Projects/com.lveditor.draft`).
2. CapCut neu starten.

## Zeitstempel-Format

Aus dem Dateinamen werden alle Zahlengruppen gelesen und die letzten drei
rechtsbuendig als `H-M-S` interpretiert (fuehrende Nullen egal):
`00-00-02` → 2 s, `1-30` → 90 s, `01-02-03` → 3723 s. Bilder mit Dauer ≤ 0
(z.B. doppelter Zeitstempel) werden uebersprungen. **Deine Bilddateien werden
nie umbenannt oder verschoben.**
