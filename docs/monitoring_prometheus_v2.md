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

## Alert Rules einbinden
Starter-Regeln liegen in `docs/alert_rules_backend_v2.yml`.

In `prometheus.yml`:
```yaml
rule_files:
  - /etc/prometheus/rules/alert_rules_backend_v2.yml
```

Datei nach `/etc/prometheus/rules/alert_rules_backend_v2.yml` kopieren und Prometheus neu laden.

Konkrete Schritte (Linux):
```bash
sudo install -D -m 0644 docs/alert_rules_backend_v2.yml /etc/prometheus/rules/alert_rules_backend_v2.yml
promtool check rules /etc/prometheus/rules/alert_rules_backend_v2.yml
curl -X POST http://localhost:9090/-/reload
```

## Betriebsregeln
- `LS_METRICS_API_KEY` als Secret verwalten, nicht im Repo speichern.
- Key rotieren (z. B. monatlich oder nach Incident).
- Zugriffe auf `/v2/metrics/prometheus` nur aus Monitoring-Netzen erlauben.
- `401`-Anstiege in `error_categories{category="auth"}` und `http_status{status="401"}` alarmieren.
- `413`-Anstiege (`error_category_total{category="security"}` bzw. `http_status_total{status="413"}`) auf Request-Floods/Fehlkonfiguration pruefen.
- `429` auf `/v2/auth/login` bzw. `audit_event_total{event="auth_login_rate_limited"}` beobachten (Brute-Force/Abuse-Indikator).
- `429` auf `/v2/game/turn` mit `audit_event_total{event="rate_limit_ip_exceeded"}` als Signal fuer IP-basierten Abuse beobachten.
- `504` auf `/v2/game/turn` beobachten (Turn-Timeout-Guard via `LS_TURN_TIMEOUT_SECONDS`, default `60`); bei Anstieg Modell-Latenz/Fallback-Kette pruefen.
- `audit_event_total{event="turn_timeout"}` als Timeout-Fruehwarnsignal verwenden (ergaenzt `http_status_total{status="504"}`).

## Modell-Fallback Telemetrie
Seit Phase 3 exportiert Prometheus auch Modellrouting-Metriken:
- `ls_backend_v2_model_route_total{stage,requested_model,used_model,fallback}`
- `ls_backend_v2_model_attempt_error_total{stage,model}`

Empfohlene Alarme:
- Erhoehte `model_attempt_error_total` fuer Primarmodelle (`stage="analysis"` und/oder `stage="narrative"`).
- Sprunghaft steigender Anteil von `fallback="true"` in `model_route_total`.

## SLO-Snapshot im Retrieval-Endpoint
`GET /v2/metrics/retrieval` liefert in `windowed_rates` pro Zeitfenster jetzt auch:
- `errors_5xx_percent`
- `rate_limit_429_percent`

Damit kann ein schneller API-SLO-Check ohne PromQL erfolgen (z. B. `errors_5xx_percent < 1.0` fuer Beta-Ziel).

## SLO-Status Endpoint
`GET /v2/metrics/slo` liefert einen kompakten Pass/Fail-Status fuer ein Zeitfenster.
Defaultwerte kommen aus:
- `LS_SLO_WINDOW` (default `300s`)
- `LS_SLO_MAX_5XX_PERCENT` (default `1.0`)
- `LS_SLO_MAX_429_PERCENT` (default `5.0`)

Beispiel:
```bash
curl -s http://localhost:8002/v2/metrics/slo \
  -H "Authorization: Bearer $TOKEN"
```

Mit eigenen Schwellwerten:
```bash
curl -s "http://localhost:8002/v2/metrics/slo?window=60s&max_5xx_percent=1.0&max_429_percent=5.0" \
  -H "Authorization: Bearer $TOKEN"
```

### Smoke per Script (automatisiert)
```bash
python backend_v2/scripts/smoke_slo.py --base-url http://localhost:8002
```

Mit harten Grenzwerten und Exit-Code bei Breach:
```bash
python backend_v2/scripts/smoke_slo.py \
  --base-url http://localhost:8002 \
  --window 60s \
  --max-5xx 1.0 \
  --max-429 5.0 \
  --require-ok
```

### Monitoring-Stack Smoke (Backend + Prometheus)
```bash
python backend_v2/scripts/smoke_monitoring_stack.py \
  --backend-url http://localhost:8002 \
  --prometheus-url http://localhost:9090 \
  --expected-job last_strawberry_backend_v2 \
  --metrics-key dev-metrics-key
```

Optional inkl. Grafana Dashboard API-Pruefung:
```bash
python backend_v2/scripts/smoke_monitoring_stack.py \
  --backend-url http://localhost:8002 \
  --prometheus-url http://localhost:9090 \
  --expected-job last_strawberry_backend_v2 \
  --metrics-key dev-metrics-key \
  --grafana-url http://localhost:3000 \
  --grafana-api-token <token>
```

## Monitoring-Events gezielt erzeugen (lokal)
PowerShell-Helfer zum Erzeugen von Events fuer Dashboard/Alerts:
- `auth_failed` (401)
- `provider`-Fehler
- `turn_timeout`
- Modell-Fallback-Routen

Script:
```powershell
powershell -ExecutionPolicy Bypass -File backend_v2/scripts/generate_monitoring_events.ps1 -BaseUrl http://localhost:8002
```

Hinweise:
- Das Script sichert `backend_v2/.env`, aendert fuer einzelne Szenarien temporaer Werte und stellt am Ende den Originalzustand wieder her.
- Fuer Konfigurationswechsel fordert das Script einen manuellen Backend-Restart an.

## Grafana Dashboard
Import-Datei: `docs/grafana_dashboard_backend_v2.json`

Import in Grafana:
1. Dashboards -> New -> Import
2. JSON-Datei hochladen
3. Prometheus-Datasource auswaehlen
4. Speichern
