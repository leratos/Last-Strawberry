# M4 Definition Of Done (Phase 4 Cutover)

Stand: 21. Februar 2026

## Ziel
Vollstaendiger Cutover auf die OpenRouter-basierte V2-Plattform ohne aktiven Legacy-GCP-Inferenzpfad.

## Abnahmekriterien
- `backend_server` Gameplay-Endpunkte arbeiten bridge-only ueber `backend_v2`.
- Legacy-GCP-Inferenzpfad ist aus Runtime-Code und Runtime-Dependencies entfernt.
- Kosten-/Latenz-Telemetrie fuer Modellversuche ist in API + Prometheus vorhanden.
- Betriebsrunbook fuer Bridge-only Betrieb, Rollback und Release-Gates ist dokumentiert.
- FastAPI-Startup ist deprecation-sicher (`lifespan` statt `@app.on_event`).
- CI ist gruen inkl. Coverage-Checks.

## Nachweis-Artefakte
- `docs/backend_server_v2_bridge.md`
- `docs/phase4_cutover_runbook.md`
- `backend_server/scripts/smoke_v2_bridge.py`
- `backend_server/scripts/playtest_bridge_quickcheck.py`
- `backend_server/scripts/smoke_phase4_release.py`
- `backend_v2/scripts/smoke_slo.py`

## Abschluss-Checks
1. `python -m pytest backend_v2/tests backend_server/tests -q`
2. `python backend_server/scripts/smoke_phase4_release.py --backend-base-url http://127.0.0.1:8001 --v2-base-url http://127.0.0.1:8002 --username <user> --password <pass> --bridge-timeout 90`
3. Grafana/Prometheus Gates laut `docs/phase4_cutover_runbook.md` sind gruen.

## Ergebnis
M4 ist erreicht, wenn alle Abschluss-Checks bestanden sind und der Release-Smoke `"ok": true` ausgibt.
