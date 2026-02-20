# Monitoring Runbook: Prometheus Export (V2)

Stand: 19. Februar 2026

## Ziel
- `/v2/metrics/prometheus` stabil und sicher fuer Prometheus bereitstellen.
- Zwei Modi unterstuetzen:
  - Bearer-only (Standard, wenn `LS_METRICS_API_KEY` nicht gesetzt ist)
  - API-Key-Header (wenn `LS_METRICS_API_KEY` gesetzt ist)

## Konfiguration
Relevante Variablen:
- `LS_METRICS_API_KEY` (optional)
- `LS_METRICS_API_KEY_HEADER` (optional, default `X-Metrics-Key`)

Wenn `LS_METRICS_API_KEY` gesetzt ist:
- Endpoint erwartet Header `LS_METRICS_API_KEY_HEADER: <value>`
- Bearer-Token ist dann fuer diesen Endpoint nicht erforderlich

Wenn `LS_METRICS_API_KEY` nicht gesetzt ist:
- Endpoint bleibt Bearer-geschuetzt

## Smoke Checks
### 1) Bearer-Modus (kein Metrics-API-Key gesetzt)
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8002/v2/metrics/prometheus
# erwartet: 401
```

```bash
TOKEN=$(curl -s -X POST http://localhost:8002/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"username":"ops"}' | jq -r .access_token)

curl -s http://localhost:8002/v2/metrics/prometheus \
  -H "Authorization: Bearer $TOKEN" | head -n 20
```

### 2) API-Key-Modus (`LS_METRICS_API_KEY` gesetzt)
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8002/v2/metrics/prometheus
# erwartet: 401
```

```bash
curl -s http://localhost:8002/v2/metrics/prometheus \
  -H "X-Metrics-Key: <LS_METRICS_API_KEY>" | head -n 20
```

## Prometheus Scrape Beispiel
```yaml
scrape_configs:
  - job_name: last_strawberry_backend_v2
    metrics_path: /v2/metrics/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["backend-v2.internal:8002"]
    http_headers:
      X-Metrics-Key:
        values: ["${LS_METRICS_API_KEY}"]
```

Falls deine Prometheus-Version `http_headers` nicht unterstuetzt:
- Zugriff ueber einen internen Reverse Proxy absichern und Header dort injizieren.

## Betriebsregeln
- `LS_METRICS_API_KEY` als Secret verwalten, nicht im Repo speichern.
- Key rotieren (z. B. monatlich oder nach Incident).
- Zugriffe auf `/v2/metrics/prometheus` nur aus Monitoring-Netzen erlauben.
- `401`-Anstiege in `error_categories{category="auth"}` und `http_status{status="401"}` alarmieren.
- `413`-Anstiege (`error_category_total{category="security"}` bzw. `http_status_total{status="413"}`) auf Request-Floods/Fehlkonfiguration pruefen.
- `429` auf `/v2/auth/login` bzw. `audit_event_total{event="auth_login_rate_limited"}` beobachten (Brute-Force/Abuse-Indikator).

## Modell-Fallback Telemetrie
Seit Phase 3 exportiert Prometheus auch Modellrouting-Metriken:
- `ls_backend_v2_model_route_total{stage,requested_model,used_model,fallback}`
- `ls_backend_v2_model_attempt_error_total{stage,model}`

Empfohlene Alarme:
- Erhoehte `model_attempt_error_total` fuer Primarmodelle (`stage="analysis"` und/oder `stage="narrative"`).
- Sprunghaft steigender Anteil von `fallback="true"` in `model_route_total`.
