# Archiv-Welle 2 Vorbereitung (trainer / templates / analysis_dataset)

Stand: 25. Februar 2026

## Ziel
Die naechste Archiv-Welle soll folgende Legacy-Pfade verschieben:

- `trainer/`
- `templates/`
- `analysis_dataset.jsonl`

Wichtig: **nur zusammen mit Referenzbereinigung**, damit aktive Pfade (`backend_server`, `class_folder`, `server_tools`) nicht brechen.

## Warum Wave 2 nicht als reiner Move-PR geht
Diese Pfade sind noch indirekt/aktiv referenziert:

- `backend_server/main.py`
  - Dateipfade auf `trainer/train_analyst.py`, `trainer/train_narrative.py`
- `class_folder/core/hf_fine_tuner.py`
  - Dateipfad auf `analysis_dataset.jsonl`
- `class_folder/*`, `trainer/*`, `server_tools/*`
  - Python-Imports auf `templates.regeln`

Damit ist Wave 2 **kein** reiner `git mv`-PR, sondern ein koordinierter Migrations-PR (oder mehrere kleine PRs).

## Bereits erledigte Vorbereitung (in G660-G699)
1. `backend_server/main.py`
   - Trainer-Script-Pfade nutzen jetzt Fallback-Resolver:
     - zuerst `trainer/...`
     - spaeter kompatibel mit `archive/legacy_training_tools/trainer/...`
2. `class_folder/core/hf_fine_tuner.py`
   - Analyse-Dataset wird jetzt an beiden Orten gesucht:
     - `analysis_dataset.jsonl`
     - `archive/legacy_misc/analysis_dataset.jsonl`

Damit sind zwei harte Dateipfad-Abhaengigkeiten bereits migrationsfest.

## Offene Referenzbereinigung fuer Wave 2

### A) `templates/` (kritisch)
Aktive Imports:
- `class_folder/game_logic/base_game_manager.py`
- `class_folder/game_logic/game_manager.py`
- `class_folder/game_logic/game_manager_online.py`
- `class_folder/ui/setup_dialogs.py`
- `server_tools/generate_analysis_data_from_db.py`
- `trainer/generate_interactive_training_data.py`
- `trainer/training_ui_server.py`

### Empfohlene Strategie (kompatibel)
1. `git mv templates archive/legacy_desktop_core/templates`
2. Top-Level-Compat-Shim beibehalten:
   - neues `templates/__init__.py`
   - neues `templates/regeln.py` (re-export aus `archive.legacy_desktop_core.templates.regeln`)
3. `archive/`, `archive/legacy_desktop_core/`, `archive/legacy_desktop_core/templates/` als Python-Packages absichern (`__init__.py`)
4. Spaeter (optional): Imports in Legacy-Modulen direkt auf Archivpfad umstellen und Shim entfernen

Diese Strategie vermeidet einen Big-Bang-Importbruch.

### B) `trainer/`
Geplanter Zielpfad:
- `archive/legacy_training_tools/trainer/`

Dank Fallback in `backend_server/main.py` ist der direkte Runtime-Bruch bereits reduziert.

Trotzdem vor Move pruefen:
- Manuelle Admin-/Trainingspfade in `backend_server`
- Doku-Verweise (nicht blocker, aber nachziehen)

### C) `analysis_dataset.jsonl`
Geplanter Zielpfad:
- `archive/legacy_misc/analysis_dataset.jsonl`

`class_folder/core/hf_fine_tuner.py` ist bereits kompatibel vorbereitet (Fallback-Suche).

## Empfohlene Ausfuehrungsreihenfolge fuer Wave 2
1. `templates/`-Shim-PR (inkl. Archiv-Move + `__init__.py`-Pakete)
2. `trainer/`-Move-PR (Pfadreferenzen sind vorbereitet)
3. `analysis_dataset.jsonl`-Move-PR
4. Doku-Nachlauf-PR (restliche historische Pfade in README/docs bereinigen)

## Abbruchkriterien / Risiken
- Wenn `backend_server`-Admin-Training im laufenden Betrieb aktiv genutzt wird, `trainer/`-Move nur nach kurzem Smoke-Test.
- `templates/`-Move ohne Shim fuehrt sehr wahrscheinlich zu Importfehlern in Legacy-Pfaden.
- `analysis_dataset.jsonl`-Move ist relativ sicher, aber nur wenn Fine-Tuning-Pfade den Fallback behalten.

## Minimaler Smoke-Test nach Wave 2 (empfohlen)
1. `python -m uvicorn backend_server.main:app --reload --port 8001` (Importcheck)
2. Optionaler Trainingspfad-Check (nur Path-Aufloesung, kein Training starten)
3. `python -m pytest backend_server/tests -q` (soweit lauffaehig im aktuellen Env)
