# Inbetriebnahme-Anleitung (Operator Guide)

Stand: 28. Februar 2026

Diese Anleitung ist fuer Personen, die das System lokal oder in einer frischen Umgebung erstmals in Betrieb nehmen.

## 1. Zielbild

Empfohlener Produktpfad fuer Spielbetrieb:

- API: `apps/game_api` auf Port `8010`
- Web-Client: `apps/web_client` auf Port `3001`
- LLM-Modus:
  - `preview` fuer kostenfreie, deterministische Entwicklung
  - `hybrid` fuer OpenRouter-Narration/Bootstrap (optional)

Legacy-Pfade (`backend_v2`, `backend_server`) sind weiterhin vorhanden, aber fuer den Greenfield-Spielpfad nicht erforderlich.

## 2. Voraussetzungen

- Windows 10/11 mit PowerShell (oder Linux/macOS mit analoger Shell-Anpassung)
- Python `3.12+`
- Node.js `20+` und `npm`
- Git
- Optional fuer Hybrid:
  - OpenRouter API Key (`OPENROUTER_API_KEY`)

## 3. Erstes Setup (einmalig)

Im Repo-Root ausfuehren:

```powershell
cd C:\Dev\last-strawberry\Last-Strawberry
python -m venv .venv-v2
.\.venv-v2\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend_v2/requirements.txt
pip install -r backend_server/requirements.txt
npm --prefix apps/web_client ci
```

Hinweis:
- `requirements.txt` im Repo-Root ist Legacy/Training-lastig und **nicht** fuer den Greenfield-Start gedacht.

## 4. Laufzeit-Umgebung setzen

Im selben Terminal (oder in jedem API-Terminal) setzen:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\packages\shared_schemas;$PWD\packages\rules_engine"
```

Standard-DB fuer Greenfield:
- `apps/game_api/data/greenfield_game.db`

Optional eigener DB-Pfad:

```powershell
$env:LS_GREENFIELD_DB_PATH = "apps/game_api/data/greenfield_game.db"
```

## 5. Startreihenfolge

### Terminal 1: Game API starten

```powershell
cd C:\Dev\last-strawberry\Last-Strawberry
.\.venv-v2\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD;$PWD\packages\shared_schemas;$PWD\packages\rules_engine"
python -m uvicorn apps.game_api.app.main:app --reload --host 127.0.0.1 --port 8010
```

### Terminal 2: Web-Client starten

```powershell
cd C:\Dev\last-strawberry\Last-Strawberry
npm --prefix apps/web_client run dev -- --host 127.0.0.1 --port 3001
```

Dann im Browser:
- `http://127.0.0.1:3001`

## 6. Funktionscheck (Health + Quick Flow)

### 6.1 API Health

```powershell
curl.exe http://127.0.0.1:8010/health
```

Erwartet: JSON mit `status` und Laufzeitinformationen.

### 6.2 Bootstrap-Preview (PowerShell-sicher, ohne Quote-Probleme)

```powershell
$body = @{
  user_id = "local-operator"
  world_description = "Duestere Hafenstadt mit okkulten Konflikten."
  character_description = "Neuer Ermittler mit Blick fuer Details."
} | ConvertTo-Json

Invoke-RestMethod `
  -Method POST `
  -Uri "http://127.0.0.1:8010/v1/worlds/bootstrap/preview" `
  -ContentType "application/json" `
  -Body $body
```

### 6.3 Turn-Loop Quickcheck

```powershell
cd C:\Dev\last-strawberry\Last-Strawberry
.\.venv-v2\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD;$PWD\packages\shared_schemas;$PWD\packages\rules_engine"
python apps/game_api/scripts/check_greenfield_turn_loop.py --base-url http://127.0.0.1:8010
```

Erwartet: `PASS: greenfield turn-loop quickcheck succeeded`.

## 7. LLM-Modi (preview vs hybrid)

### Preview (Default)

Keine API-Kosten, ideal fuer Entwicklung:

```powershell
$env:LS_GREENFIELD_LLM_MODE = "preview"
```

### Hybrid (OpenRouter aktiv)

```powershell
$env:LS_GREENFIELD_LLM_MODE = "hybrid"
$env:LS_GREENFIELD_LLM_FALLBACK_TO_PREVIEW = "true"
$env:OPENROUTER_API_KEY = "<dein_key>"
```

Optional:

```powershell
$env:LS_GREENFIELD_HYBRID_INTENT_LLM_FOR_COMPLEX_INPUTS = "true"
```

Empfehlung:
- fuer Entwicklungsphasen: `preview`
- fuer Narrations-/Bootstrap-Qualitaetstest: `hybrid` mit begrenztem Testfenster

## 8. Stop / Neustart

- API beenden: `Ctrl + C` im Uvicorn-Terminal
- Web beenden: `Ctrl + C` im Vite-Terminal
- Neustart in gleicher Reihenfolge wie in Abschnitt 5

## 9. Hauefige Fehler und Loesungen

### `ModuleNotFoundError: ls_shared_schemas`

`PYTHONPATH` fehlt.

Loesung:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\packages\shared_schemas;$PWD\packages\rules_engine"
```

### Web erreichbar laut Vite, Browser zeigt trotzdem nichts

Host-Binding explizit setzen:

```powershell
npm --prefix apps/web_client run dev -- --host 127.0.0.1 --port 3001
```

### JSON-Fehler bei `curl` in PowerShell

PowerShell escaped `curl`-JSON haeufig unguenstig. Nutze stattdessen `Invoke-RestMethod` mit `ConvertTo-Json` (siehe Abschnitt 6.2).

### Port belegt (`8010` oder `3001`)

- freien Port waehlen (`--port ...`)
- fuer Web-Client API-URL anpassen:

```powershell
$env:VITE_GAME_API_BASE_URL = "http://127.0.0.1:8011"
```

### Datenbank fuer Test resetten

Datei loeschen:
- `apps/game_api/data/greenfield_game.db`

Beim naechsten API-Start wird die SQLite-Struktur wieder angelegt.

## 10. Optional: Legacy-Bridge Pfad (nur wenn benoetigt)

Falls ein alter Client ueber den Bridge-Stack getestet werden soll:

- `backend_v2` starten (`8002`)
- `backend_server` im Bridge-Modus starten (`8001`)

Details:
- `README.md` (Root, Abschnitt Quick Start)
- `docs/backend_server_v2_bridge.md`

