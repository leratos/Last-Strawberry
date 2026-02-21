# Phase 4 Cutover Runbook (Bridge-Only)

## Scope
- Operate `backend_server` gameplay strictly via `backend_v2`.
- Legacy Google inference path stays decommissioned.
- Use existing Grafana/Prometheus SLO signals as release gates.

## Prerequisites
- `backend_v2` healthy on target URL (`/v2/health` and `/v2/metrics/prometheus`).
- `backend_server` bridge mode available (`LS_V2_BRIDGE_ENABLED=true`).
- Smoke scripts green:
  - `python backend_server/scripts/smoke_v2_bridge.py ...`
  - `python backend_server/scripts/playtest_bridge_quickcheck.py ...`

## Environment Controls
- `LS_V2_BRIDGE_ENABLED=true`
- `LS_V2_BASE_URL=http://127.0.0.1:8002` (adjust per environment)
- `LS_V2_TIMEOUT_SECONDS=45`

## Release Gates (must stay green)
- `5xx` percent within SLO (`/v2/metrics/slo`).
- `429` percent within SLO (`/v2/metrics/slo`).
- No sustained `turn_timeout` spike.
- No sustained provider error spike.
- No sustained stage budget spike:
  - `audit_event_total{event="analysis_latency_budget_exceeded"}`
  - `audit_event_total{event="narrative_latency_budget_exceeded"}`
- p95/p99 model latency stable for active models:
  - `ls_backend_v2_model_latency_ms_p95{stage,model}`
  - `ls_backend_v2_model_latency_ms_p99{stage,model}`
- Estimated cost trend stable:
- `ls_backend_v2_estimated_cost_usd_per_minute{window="60s"}`
- Manual quickcheck still passes.

## Rollback
1. Keep bridge enabled (`LS_V2_BRIDGE_ENABLED=true`) and restart `backend_server`.
2. If `backend_v2` is unhealthy, rollback by deploying the previous backend release artifact.
3. Re-run:
   - `python backend_server/scripts/smoke_v2_bridge.py ...`
   - `python backend_server/scripts/playtest_bridge_quickcheck.py ...`

## Post-cutover tasks
- Keep `backend_server` bridge enabled and monitor SLOs for burn-in window.
- Keep legacy Google inference path archived and out of runtime dependencies.
- Freeze runbook + incident notes in docs.
