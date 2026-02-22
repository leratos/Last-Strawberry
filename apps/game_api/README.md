# Greenfield Game API (Scaffold)

Zweck:
- FastAPI-basierte Greenfield-Game-API fuer das Web-Spiel
- getrennt vom Legacy-`backend_server`/`backend_v2` Pfad

## Geplanter Flow
1. World Bootstrap (Welt + Charakter aus Nutzerbeschreibung)
2. Turn Intent Analyse (LLM)
3. Turn Resolution (Rules Engine)
4. Turn Narration (LLM)
5. Persistenz + State Delta + Journal

## Start (Scaffold, lokal)
Python-Pfad fuer lokale Paketimporte setzen (PowerShell):

```powershell
$env:PYTHONPATH = \"$PWD;$PWD\\packages\\shared_schemas;$PWD\\packages\\rules_engine\"
python -m uvicorn apps.game_api.app.main:app --reload --port 8010
```

## Hinweis
Aktuell ist dies ein Start-Skeleton mit Health-Endpoint und Preview-Routen.
