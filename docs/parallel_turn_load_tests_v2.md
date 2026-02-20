# Parallel Turn Load Tests (V2)

Stand: 20. Februar 2026

## Ziel
- Parallelitaet fuer `/v2/game/turn` unter Last pruefen.
- Verhalten bei Rate-Limit (`429`) und Provider-Fehlern (`502`) sichtbar machen.
- Schnell lokal testbar ohne externe Lasttest-Plattform.

## Lokal ausfuehren
Beispiel (40 Requests, 10 parallel):

```bash
python backend_v2/scripts/run_parallel_turn_load.py \
  --base-url http://localhost:8002 \
  --requests 40 \
  --concurrency 10
```

Optional strict mode (schlaegt fehl, sobald `429` auftritt):

```bash
python backend_v2/scripts/run_parallel_turn_load.py \
  --base-url http://localhost:8002 \
  --requests 40 \
  --concurrency 10 \
  --fail-on-429
```

## Exit Codes
- `0`: Lauf ohne `5xx` (und ohne `429`, wenn `--fail-on-429` gesetzt ist).
- `2`: Mindestens ein `5xx` aufgetreten.
- `3`: `--fail-on-429` aktiv und mindestens ein `429` aufgetreten.

## Auswertung
- `status_counts`: Verteilung `2xx/4xx/5xx`.
- `latency_ms.p95`: Hauptsignal fuer User-Experience.
- `sample_failures`: Erste Fehler-Responses zur schnellen Diagnose.

## Erwartung in Phase 3
- Burst-Test darf bei aktivem Limiter bewusst `429` enthalten.
- `502` sollten nur bei expliziten Provider-Stoerungen auftreten.
- Metriken im Backend pruefen:
  - `ls_backend_v2_http_status_total{status="429"}`
  - `ls_backend_v2_error_category_total{category="provider"}`
  - `ls_backend_v2_requests_per_minute{window="60s"}`
