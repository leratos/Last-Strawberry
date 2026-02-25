# Archivplan: Legacy -> Greenfield Repo-Struktur

Stand: 22. Februar 2026

## Ziel
Legacy-Bestand im selben Repo erhalten, aber den Greenfield-Track klar trennen.

## Wichtige Regel
`gitignore` ignoriert keine bereits versionierten Dateien. Archivierung bedeutet daher:
- bewusstes Verschieben (git move)
- nicht "unsichtbar machen"

## Prinzipien fuer die Archivierung
- Ein PR nur fuer Moves/Umbenennungen
- Keine Logikaenderungen im selben PR
- Laufende Greenfield-Ordner duerfen nicht mit Legacy-Pfaden kollidieren
- Dokumentation vor dem Move aktualisieren

## Vorgeschlagene Zielstruktur
- `archive/legacy_backend_server/`
- `archive/legacy_backend_v2_transition/`
- `archive/legacy_desktop_core/`
- `archive/legacy_training_tools/`
- `archive/legacy_frontend/`

## Mappings (Vorschlag)
- `backend_server/` -> `archive/legacy_backend_server/`
- `backend_v2/` -> `archive/legacy_backend_v2_transition/`
- `class_folder/` -> `archive/legacy_desktop_core/class_folder/`
- `trainer/` -> `archive/legacy_training_tools/trainer/`
- `ai_service/` -> `archive/legacy_training_tools/ai_service/`
- `cronjob/` -> `archive/legacy_training_tools/cronjob/`
- `server_tools/` -> `archive/legacy_backend_server/server_tools/`
- `web_frontend/` -> `archive/legacy_frontend/web_frontend/`
- `game_main.py` -> `archive/legacy_desktop_core/game_main.py`

## Was NICHT sofort verschoben werden sollte
- `.github/workflows/*` (bis Greenfield-CI steht)
- `docs/` (enthaelt weiterhin wertvolle Referenz und Ops-Wissen)
- Monitoring-/Runbooks, solange sie fuer den Greenfield-Betrieb als Vorlage dienen

## Empfohlene Reihenfolge
1. Greenfield-Ordnerstruktur anlegen (`apps/`, `packages/`, `infra/`)
2. Greenfield-CI Mindestworkflow gruen bekommen
3. Archiv-Move-PR fuer Legacy erstellen
4. Dokument-Links und README aktualisieren
5. Branch Protection um Greenfield-Checks erweitern

## Status (Archivierung abgeschlossen im aktuellen Scope)
Das Archivprogramm ist fuer den **aktuellen Greenfield-/Kompatibilitaets-Scope** abgeschlossen.

Erledigt:
- Wave 1 (inaktive Legacy-Pfade)
- Wave 2 (templates/trainer/analysis_dataset inkl. Referenzbereinigung + Doku-Nachlauf)

Keine weitere Archivwelle ist aktuell erforderlich, solange die unten gelisteten Komponenten aktiv genutzt werden.

## Status (Wave 1 erledigt)
Archiviert (ohne aktive Bridge-/CI-Pfade anzufassen):
- `ai_service/` -> `archive/legacy_training_tools/ai_service/`
- `cronjob/` -> `archive/legacy_training_tools/cronjob/`
- `tools/` -> `archive/legacy_training_tools/tools/`
- `lora_adapter/` -> `archive/legacy_training_tools/lora_adapter/`
- `web_frontend/` -> `archive/legacy_frontend/web_frontend/`
- `game_main.py` -> `archive/legacy_desktop_core/game_main.py`
- `test_suite_analysis.py` -> `archive/legacy_misc/test_suite_analysis.py`

Bewusst weiterhin **nicht** verschoben (aktuell aktive Runtime-/Ops-/Bridge-Komponenten):
- `backend_v2/`
- `backend_server/`
- `server_tools/`
- `class_folder/`

Bewusst weiterhin **nicht** verschoben (Kompatibilitaets-Shim, absichtlich top-level belassen):
- `templates/`

Zusatzstatus:
- `analysis_dataset.jsonl` wurde in Wave 2 Schritt 3 bereits archiviert nach `archive/legacy_misc/analysis_dataset.jsonl`.
- `trainer/` wurde in Wave 2 Schritt 2 bereits archiviert nach `archive/legacy_training_tools/trainer/`.

Wave-2-Dokumentation (historisch / Nachvollziehbarkeit):
- `docs/archive_legacy_wave2_preparation.md`

## Abschlusskriterium fuer das Thema "Archivieren"
Das Thema gilt als abgeschlossen, wenn:
- keine offenen Move-Wellen fuer inaktive Legacy-Pfade existieren
- verbleibende Top-Level-Legacy-Komponenten explizit als aktiv/notwendig dokumentiert sind
- Dokumentation und Referenzen auf archivierte Pfade nachgezogen wurden

Dieser Zustand ist mit Stand dieser Datei erreicht.
