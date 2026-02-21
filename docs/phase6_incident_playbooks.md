# Phase 6 Incident Playbooks

Stand: 21. Februar 2026

## Ziel
Schnelle, wiederholbare Behandlung der haeufigsten Produktionsstoerungen im V2/OpenRouter-Stack.

## 1) Turn Timeout Spike (`504` auf `/v2/game/turn`)

### Signals
- `http_status_total{status="504"}`
- `audit_event_total{event="turn_timeout"}`
- Alert: `LastStrawberryV2TurnTimeoutSpike`

### Triage
1. `GET /v2/health` pruefen.
2. `GET /v2/metrics/retrieval` auf `windowed_rates` pruefen.
3. Prometheus:
   - `ls_backend_v2_model_latency_ms_p95{stage="analysis"}`
   - `ls_backend_v2_model_latency_ms_p95{stage="narrative"}`
4. Logs auf Provider-/Netzwerkfehler pruefen.

### Mitigation
1. `LS_TURN_TIMEOUT_SECONDS` temporaer erhoehen (z. B. `60 -> 90`).
2. Langsames Modell auf schnelleres Fallback umstellen:
   - `LS_ANALYSIS_FALLBACK_MODELS`
   - `LS_NARRATIVE_FALLBACK_MODELS`
3. Bei Lastspitzen Rate-Limits straffen.

### Recovery Check
- `python backend_v2/scripts/smoke_slo.py --base-url http://127.0.0.1:8002 --require-ok`
- `python backend_server/scripts/smoke_phase4_release.py --backend-base-url http://127.0.0.1:8001 --v2-base-url http://127.0.0.1:8002 --username <user> --password <pass> --bridge-timeout 90`

## 2) Metrics/Auth Fehler (`401` auf `/v2/metrics/prometheus`)

### Signals
- `http_status_total{status="401"}`
- `error_category_total{category="auth"}`
- Ops Report: `prometheus_families.ok=false` + `status_code=401`

### Triage
1. Pruefen, ob `LS_METRICS_API_KEY` gesetzt ist.
2. Headername pruefen:
   - `LS_METRICS_API_KEY_HEADER`
3. Test:
   - `curl -i -H "X-Metrics-Key: <key>" http://127.0.0.1:8002/v2/metrics/prometheus`

### Mitigation
1. Key/Header in Prometheus scrape config korrigieren.
2. Bei Key-Rotation Prometheus neu laden.
3. Schluessel in Secret-Store statt Klartextdatei pflegen.

### Recovery Check
- `python backend_v2/scripts/ops_phase5_report.py --base-url http://127.0.0.1:8002 --require-prometheus-families`

## 3) Bridge Provider Failure (`502` via `backend_server`)

### Signals
- `POST /command` oder `/worlds/create` liefert `502`.
- Body enthaelt `V2 bridge error` oder `All analysis models failed`.
- Alert: `LastStrawberryV2ProviderErrorsSpike`

### Triage
1. `GET /health` auf backend_server:
   - `v2_bridge_status.enabled=true`
   - `v2_bridge_status.status=ok`
2. `GET /v2/health` auf backend_v2.
3. OpenRouter Key / Base URL pruefen:
   - `LS_OPENROUTER_API_KEY`
   - `LS_OPENROUTER_BASE_URL`
4. Fallback-Konfiguration pruefen:
   - `LS_ANALYSIS_FALLBACK_MODELS`
   - `LS_NARRATIVE_FALLBACK_MODELS`

### Mitigation
1. Gueltigen API-Key setzen/rotieren.
2. Fallback-Modelle aktivieren oder anpassen.
3. Falls nur einzelnes Modell betroffen: Primarmodell austauschen.

### Recovery Check
- `python backend_server/scripts/smoke_v2_bridge.py --base-url http://127.0.0.1:8001 --username <user> --password <pass> --timeout 90`
- `python backend_server/scripts/playtest_bridge_quickcheck.py --base-url http://127.0.0.1:8001 --username <user> --password <pass> --timeout 90`

## Incident-Abschluss
1. Timeline + Root Cause dokumentieren.
2. Dauerhafte Gegenmassnahme erfassen (Config, Code, Alert-Tuning).
3. Falls notwendig, Schwellen in `LS_OPS_*` anpassen und in PR dokumentieren.
