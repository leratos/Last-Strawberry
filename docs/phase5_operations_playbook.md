# Phase 5 Operations Playbook

Stand: 21. Februar 2026

## Ziel
Stabiler Betrieb nach M4-Cutover mit wiederholbaren Checks fuer Verfuegbarkeit, SLO, Kosten und Alerting.

## Daily Routine
1. Health check:
   - `GET /health` (backend_server)
   - `GET /v2/health` (backend_v2)
2. Ops report:
   - `python backend_v2/scripts/ops_phase5_report.py --base-url http://127.0.0.1:8002 --require-prometheus-families`
3. Bridge smoke:
   - `python backend_server/scripts/smoke_phase4_release.py --backend-base-url http://127.0.0.1:8001 --v2-base-url http://127.0.0.1:8002 --username <user> --password <pass> --bridge-timeout 90`
4. Grafana/Prometheus:
   - Verify all critical panels and alert states are green.

## Weekly Routine
1. Review cost trend:
   - `ls_backend_v2_estimated_cost_usd_per_minute{window="60s"}`
   - `ls_backend_v2_provider_reported_cost_usd_per_minute{window="60s"}`
2. Review latency trend:
   - `ls_backend_v2_model_latency_ms_p95`
   - `ls_backend_v2_model_latency_ms_p99`
3. Review fallback/error trend:
   - `ls_backend_v2_model_route_total{fallback="true"}`
   - `ls_backend_v2_model_attempt_error_total`
4. Rotate metrics key if used (`LS_METRICS_API_KEY`).

## Alert Response Priorities
1. `LastStrawberryV2TargetDown` (critical)
2. `LastStrawberryV2High5xxPercent` / `LastStrawberryV2High429Percent`
3. `LastStrawberryV2ProviderErrorsSpike`
4. `LastStrawberryV2AnalysisLatencyBudgetSpike` / `LastStrawberryV2NarrativeLatencyBudgetSpike`
5. `LastStrawberryV2EstimatedCostRateHigh`

## Incident Notes Template
- Incident start/end (UTC)
- Affected endpoints
- SLO impact (5xx%, 429%)
- Root cause
- Mitigation/rollback used
- Follow-up action items
