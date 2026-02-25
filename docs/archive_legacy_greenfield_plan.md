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

## Status (Wave 1 erledigt)
Archiviert (ohne aktive Bridge-/CI-Pfade anzufassen):
- `ai_service/` -> `archive/legacy_training_tools/ai_service/`
- `cronjob/` -> `archive/legacy_training_tools/cronjob/`
- `tools/` -> `archive/legacy_training_tools/tools/`
- `lora_adapter/` -> `archive/legacy_training_tools/lora_adapter/`
- `web_frontend/` -> `archive/legacy_frontend/web_frontend/`
- `game_main.py` -> `archive/legacy_desktop_core/game_main.py`
- `test_suite_analysis.py` -> `archive/legacy_misc/test_suite_analysis.py`

Bewusst vorerst **nicht** verschoben (aktuell noch in Workflows/Bridge referenziert):
- `backend_v2/`
- `backend_server/`
- `server_tools/`
- `class_folder/`

Bewusst vorerst **nicht** verschoben (indirekte Legacy-Abhaengigkeiten):
- `trainer/`
- `templates/`
- `analysis_dataset.jsonl`
