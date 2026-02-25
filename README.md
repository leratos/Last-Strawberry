# Last-Strawberry

OpenRouter-first Pen-and-Paper platform with a FastAPI V2 backend, bridge-compatible legacy API, and operational monitoring.

[![Backend V2 CI](https://github.com/leratos/Last-Strawberry/actions/workflows/backend_v2_ci.yml/badge.svg)](https://github.com/leratos/Last-Strawberry/actions/workflows/backend_v2_ci.yml)
[![codecov](https://codecov.io/gh/leratos/Last-Strawberry/branch/main/graph/badge.svg)](https://codecov.io/gh/leratos/Last-Strawberry)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-brightgreen.svg)
![Status](https://img.shields.io/badge/status-M4%2FM5-green.svg)

## Current State
- M4 complete: full cutover to `backend_v2` (OpenRouter runtime path).
- Legacy Google inference runtime path is decommissioned.
- `backend_server` gameplay endpoints run bridge-only to `backend_v2`.
- M5 complete: operations playbook, phase-5 ops report, and extended monitoring alerts are in place.

## Repository Overview
- `backend_v2/`: primary game backend (auth, worlds, turns, memory, metrics).
- `backend_server/`: legacy-compatible API facade used as V2 bridge.
- `apps/web_client/`: current greenfield web client (React + Vite).
- `archive/legacy_frontend/web_frontend/`: archived legacy frontend.
- `docs/`: runbooks, dashboards, roadmap, DoD documents.

## Architecture (Runtime)
1. Client calls `backend_server` legacy-compatible endpoints (`/token`, `/worlds/create`, `/command`, `/load_game_summary`).
2. `backend_server` performs bridge login to `backend_v2` and forwards gameplay requests.
3. `backend_v2` orchestrates OpenRouter models (analysis + narrative), persistence, retrieval/memory, and metrics.

## Quick Start (Local)
### 1) Start backend_v2
```powershell
uvicorn backend_v2.app.main:app --reload --port 8002 --env-file backend_v2/.env
```

### 2) Start backend_server in bridge mode
```powershell
$env:LS_V2_BRIDGE_ENABLED="true"
$env:LS_V2_BASE_URL="http://127.0.0.1:8002"
$env:LS_V2_TIMEOUT_SECONDS="90"
uvicorn backend_server.main:app --reload --port 8001
```

### 3) Run end-to-end phase-4/5 smoke
```powershell
python backend_server/scripts/smoke_phase4_release.py `
  --backend-base-url http://127.0.0.1:8001 `
  --v2-base-url http://127.0.0.1:8002 `
  --username admin `
  --password <password> `
  --bridge-timeout 90
```

Expected: JSON output ending with `"ok": true`.

## Operations (Phase 5)
- Daily/weekly operations playbook: `docs/phase5_operations_playbook.md`
- V2 ops report script: `backend_v2/scripts/ops_phase5_report.py`
- Monitoring runbook: `docs/monitoring_prometheus_v2.md`
- Alert rules: `docs/alert_rules_backend_v2.yml`
- Grafana dashboard JSON: `docs/grafana_dashboard_backend_v2.json`

Example ops report:
```powershell
python backend_v2/scripts/ops_phase5_report.py `
  --base-url http://127.0.0.1:8002 `
  --window 300s `
  --max-5xx 1.0 `
  --max-429 5.0 `
  --max-estimated-cost-per-minute 0.10 `
  --max-provider-cost-per-minute 0.10 `
  --require-prometheus-families
```

## Testing
```powershell
python -m pytest backend_v2/tests backend_server/tests -q
```

CI coverage gate for `backend_v2` is enforced in GitHub Actions + Codecov.

## Security and Secrets
- Do not commit secrets.
- Use env vars and/or keyring for API keys.
- For metrics endpoint hardening, use `LS_METRICS_API_KEY` (+ optional header override).

## Key Docs
- V2 roadmap and milestones: `docs/roadmap_v2_execution.md`
- M4 cutover DoD: `docs/m4_definition_of_done.md`
- M4 cutover runbook: `docs/phase4_cutover_runbook.md`
- Bridge setup: `docs/backend_server_v2_bridge.md`
