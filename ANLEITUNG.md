# CapCut-Entwurf aus Bildern – Anleitung zum Wiederverwenden

Aus einem Ordner voller zeitgestempelter Bilder automatisch einen bearbeitbaren
CapCut-Entwurf bauen. Jedes Bild läuft lückenlos bis zu seinem eigenen
Zeitstempel (z.B. `00-00-05` = bis Sekunde 5).

> Es gibt auch eine Word-Version dieser Anleitung (`CapCut_Anleitung.docx`).

## So baust du einen neuen Entwurf (2 Befehle)

Alles ist bereits installiert. Für ein neues Projekt nur noch das:

1. **Bilder bereitlegen** – ein Ordner mit nach Zeitstempel benannten Bildern,
   z.B. `001_00-00-01.jpg`. Die führende Nummer (`001_`) ist optional.
2. **CapCut beenden** (falls offen): `Cmd + Q`
3. **Terminal öffnen:** `Cmd + Leertaste` → „Terminal" → Enter
4. **Diese zwei Zeilen** (einzeln, Enter nach jeder):
   ```bash
   cd ~/Downloads/capcut-tool
   bash run.sh "/Users/markocolic/Downloads/nano-banana"
   ```
   💡 Tipp: Statt den Pfad zu tippen, nur `bash run.sh ` (mit Leerzeichen)
   schreiben und den Bilderordner aus dem Finder ins Terminal ziehen.
5. **Warten**, bis unten steht:
   ```
   Fertig.
     Entwurf installiert: /Users/markocolic/Movies/CapCut/.../dfd_...
   ```
   ⚠️ Bei „Terminal möchte auf den Ordner ‚Movies' zugreifen" → **„OK"**.
6. **CapCut öffnen** → neues Projekt steht oben in der Liste. 🎬

Für jedes weitere Projekt einfach Schritt 1–6 wiederholen – egal in welchem
neuen Terminal-Fenster.

## Ordner einmalig festlegen (dann kein Pfad mehr nötig)

Wenn du immer denselben Ordner nutzt, trag ihn einmal ein:

```bash
echo "/Users/markocolic/Desktop/Elevenlabs/Bilder" > ~/Downloads/capcut-tool/ordner.txt
```

Danach genügt zum Bauen:

```bash
bash ~/Downloads/capcut-tool/run.sh
```

Zum Wechseln einfach denselben `echo`-Befehl mit einem anderen Pfad ausführen –
oder wie gewohnt einen Ordner direkt übergeben (der hat immer Vorrang). Beim
Start zeigt das Skript an, welchen Ordner es nimmt: `==> Medien-Ordner: …`

## Wichtig zu wissen

- Du musst in CapCut **kein** Projekt vorher anlegen – das Skript erstellt es.
- Jeder Lauf erzeugt ein **neues** Projekt; alte bleiben erhalten.
- Die Installation (Python 3.11, Server, Pakete) ist schon erledigt und bleibt
  bestehen. **Setup musst du nicht wieder machen.**
- Deine Bilddateien werden nie verändert, umbenannt oder verschoben.

## Dateinamen-Format

Zeitstempel als `HH-MM-SS` **oder** `HH-MM-SS-mmm` (mit Millisekunden, für mehr
Genauigkeit). Die führende Nummerierung wird ignoriert:

- `001_00-00-01.jpg` → Sekunde 1.000
- `001_00-00-04-880.jpg` → Sekunde 4.880 (`880` = Millisekunden)
- `005_00-00-19-060.jpg` → Sekunde 19.060
- `013_00-01-00.jpg` → 1:00 Minute (60 s)

Beide Formate funktionieren – auch gemischt im selben Ordner.

## Bilder und Videos

Es gehen Bilder (`.png .jpg .jpeg .webp`) **und** Videos (`.mp4 .mov .m4v`) –
auch gemischt im selben Ordner, alles lückenlos auf einer Spur.

Videos werden standardmäßig **exakt auf ihren Zeit-Slot eingepasst**: ist das
Video länger als der Slot, wird es schneller gemacht; ist es kürzer, langsamer
– so passt es immer genau und der ganze Inhalt bleibt erhalten. (Die Videolänge
liest das Skript selbst, ohne Zusatzprogramm.)

Andere Modi über eine Umgebungsvariable vor dem Befehl:

```bash
VIDEO_FIT=trim bash run.sh "/Pfad/zu/deinen/Medien"   # statt Speed: abschneiden
```

## Wenn mal etwas nicht klappt

**„Server nicht erreichbar" / „Port 9001 nicht bereit":** Grund anzeigen mit
```bash
cat ~/Downloads/capcut-tool/server.log
```

**Neues Projekt erscheint nicht in CapCut:** CapCut komplett beenden (`Cmd + Q`)
und neu starten.

**Python-/Umgebungsfehler (z.B. nach macOS-Update):** Umgebung neu aufbauen –
diese eine Zeile komplett einfügen:
```bash
cd ~/Downloads/capcut-tool/VectCutAPI && rm -rf .venv && "$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate && echo "VENV FERTIG"
```

## Wichtige Orte

| Was | Pfad |
|-----|------|
| Das Tool (Skripte) | `~/Downloads/capcut-tool` |
| Server-Protokoll (bei Fehlern) | `~/Downloads/capcut-tool/server.log` |
| CapCut-Entwürfe | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` |
| Beispiel-Bilderordner | `~/Downloads/nano-banana` |
