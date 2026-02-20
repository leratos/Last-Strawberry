# Playtest Quickcheck (Bridge Mode)

Goal: run a short reproducible Pen&Paper E2E test via legacy API paths while gameplay is executed by `backend_v2`.

## Prerequisites

1. `backend_v2` is running on `http://127.0.0.1:8002`
2. `backend_server` is running on `http://127.0.0.1:8001` with bridge mode:

```powershell
$env:LS_V2_BRIDGE_ENABLED="true"
$env:LS_V2_BASE_URL="http://127.0.0.1:8002"
uvicorn backend_server.main:app --reload --port 8001
```

## Run quickcheck

```powershell
python backend_server/scripts/playtest_bridge_quickcheck.py `
  --base-url http://127.0.0.1:8001 `
  --username admin `
  --password Strawberry!2026
```

Expected output starts with:

```text
PASS: playtest bridge quickcheck succeeded
```

## What is validated

- Happy path:
  - login (`POST /token`)
  - world create (`POST /worlds/create`)
  - multiple turns (`POST /command`)
  - summary (`GET /load_game_summary`)
- Failure path:
  - invalid bearer token -> `401`
  - invalid `world_id` on `/command` -> non-2xx

## Manual follow-up (UI)

After script pass:

1. Open UI and login with same user.
2. Create one world manually.
3. Play 2-3 turns and verify:
   - each command returns narrative text
   - reload world works
   - summary is not empty.
