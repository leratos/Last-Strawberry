# Archiv-PR Move Manifest (reiner Archiv-PR)

Stand: 22. Februar 2026

## Zweck
Dieses Manifest dient als Grundlage fuer einen **reinen Archiv-PR**:
- nur `git mv`
- keine Logikaenderungen
- keine CI-/Testlogik in demselben PR

## Statushinweis (historisch)
Dieses Manifest ist inzwischen eine **historische Referenz**.

Der urspruengliche Gesamt-Move wurde bewusst in mehrere Waves aufgeteilt. Wave 1 und Wave 2 sind abgeschlossen; die verbleibenden Top-Level-Komponenten werden aktuell aus Kompatibilitaetsgruenden nicht verschoben.

## Branch-Empfehlung
- `chore/archive-legacy-v1`

## Vorbedingungen
1. Greenfield-Scaffold ist in `main` gemerged.
2. Greenfield-CI-Checks existieren oder Legacy-Checks bleiben vorerst aktiv.
3. Links in Doku/README sind vorbereitet.

## Geplante Moves (nur Vorschlag, exakt so im PR ausfuehren)
```powershell
git mv backend_server archive/legacy_backend_server
git mv backend_v2 archive/legacy_backend_v2_transition
git mv class_folder archive/legacy_desktop_core/class_folder
git mv game_main.py archive/legacy_desktop_core/game_main.py
git mv trainer archive/legacy_training_tools/trainer
git mv ai_service archive/legacy_training_tools/ai_service
git mv cronjob archive/legacy_training_tools/cronjob
git mv web_frontend archive/legacy_frontend/web_frontend
```

## Spezielle Faelle (separat pruefen)
- `server_tools/`
  - haengt historisch an `backend_server`, wird aber ggf. noch in Tests/Tools referenziert
  - Empfehlung: in erstem Archiv-PR noch **nicht** verschieben, sondern in PR #2
- `.github/workflows/*`
  - nicht mit Archiv-PR verschieben
- `docs/*`
  - nicht mit Archiv-PR verschieben

## PR-Checkliste (reiner Archiv-PR)
- [ ] Nur Moves/Umbenennungen im Diff
- [ ] Keine inhaltlichen Codeaenderungen
- [ ] CI-Fehler nur wegen Pfadreferenzen identifiziert und notiert (nicht im selben PR "nebenbei" fixen)
- [ ] Folge-PR fuer Pfadfixes/CI-Anpassungen vorbereitet

## Folge-PRs nach Archiv-PR
1. CI-/Workflow-Pfade auf Greenfield umstellen
2. Legacy-Dokumentation auf neue Archivpfade aktualisieren
3. `server_tools/` und weitere Restordner geordnet archivieren

## Update: Wave 1 bereits archiviert (teilweise)
Bereits nach `archive/` verschoben:
- `ai_service/`
- `cronjob/`
- `tools/`
- `lora_adapter/`
- `web_frontend/`
- `game_main.py`
- `test_suite_analysis.py`

Bewusst weiter top-level belassen (aktiver Betrieb / Kompatibilitaet):
- `backend_v2/`
- `backend_server/`
- `server_tools/`
- `class_folder/`
- `templates/`

Bereits in Wave 2 archiviert:
- `trainer/` -> `archive/legacy_training_tools/trainer/`
- `analysis_dataset.jsonl` -> `archive/legacy_misc/analysis_dataset.jsonl`

Wave-2-Referenzdoku (historisch, abgeschlossen):
- `docs/archive_legacy_wave2_preparation.md`
