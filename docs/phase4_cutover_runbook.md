# Phase 4 Cutover Runbook (Canary)

## Scope
- Roll out `backend_server` traffic to `backend_v2` in controlled steps.
- Keep rollback path fast (`LS_V2_BRIDGE_CANARY_PERCENT=0`).
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
- `LS_V2_BRIDGE_CANARY_PERCENT=<0..100>`
- `LS_V2_BRIDGE_CANARY_FORCE_USER_IDS=<comma separated user_id list>`

## Rollout Plan
1. Step A (10%)
   - Set `LS_V2_BRIDGE_CANARY_PERCENT=10`.
   - Add internal QA users to `LS_V2_BRIDGE_CANARY_FORCE_USER_IDS`.
   - Observe at least 30 minutes.
2. Step B (50%)
   - Increase to `LS_V2_BRIDGE_CANARY_PERCENT=50`.
   - Observe at least 60 minutes.
3. Step C (100%)
   - Increase to `LS_V2_BRIDGE_CANARY_PERCENT=100`.
   - Keep force-user list for support/testing only.

## Release Gates (must stay green per step)
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
1. Immediate traffic stop to V2:
   - Set `LS_V2_BRIDGE_CANARY_PERCENT=0`.
2. If needed, disable bridge entirely:
   - Set `LS_V2_BRIDGE_ENABLED=false`.
3. Restart `backend_server`.
4. Re-run smoke test on legacy flow and confirm service stability.

## Post-cutover tasks
- Keep `backend_server` bridge enabled at 100% for a burn-in window.
- Archive/decommission legacy Google inference path after burn-in.
- Freeze runbook + incident notes in docs.
