# Backend Server V2 Bridge (E2E)

This mode keeps legacy `backend_server` endpoint shapes (`/token`, `/worlds/create`, `/command`, `/load_game_summary`) but executes gameplay strictly via `backend_v2`.

## 1. Start backend_v2

```powershell
uvicorn backend_v2.app.main:app --reload --port 8002 --env-file backend_v2/.env
```

## 2. Start backend_server in bridge mode

```powershell
$env:LS_V2_BRIDGE_ENABLED="true"
$env:LS_V2_BASE_URL="http://127.0.0.1:8002"
uvicorn backend_server.main:app --reload --port 8001
```

Optional timeout tuning:

```powershell
$env:LS_V2_TIMEOUT_SECONDS="45"
```

## 3. Run smoke test (legacy API path)

```powershell
python backend_server/scripts/smoke_v2_bridge.py `
  --base-url http://127.0.0.1:8001 `
  --username <legacy_user> `
  --password <legacy_password>
```

Expected: `PASS: backend_server bridge smoke succeeded`

## Behavior

- Auth to `backend_server` remains legacy (`/token`).
- Bridge routing is mandatory for gameplay endpoints:
  - `LS_V2_BRIDGE_ENABLED=true` is required for `/worlds`, `/worlds/create`, `/command`, `/load_game_summary`.
  - If bridge mode is disabled, these endpoints return `503` with a decommission hint.
- For each protected game request, `backend_server` performs an internal `/v2/auth/login` and forwards to:
  - `GET /v2/worlds`
  - `POST /v2/worlds`
  - `POST /v2/game/turn`
  - `GET /v2/worlds/{id}/turns`
- Response shape is mapped back to legacy frontend expectations.
