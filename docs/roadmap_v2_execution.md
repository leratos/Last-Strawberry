# Last-Strawberry V2 Roadmap (OpenRouter + Codecov)

Stand: 21. Februar 2026

## Strategischer Hinweis (22.02.2026)
- Ab diesem Punkt wird ein **Greenfield Web-only Neustart** als bevorzugter Produktpfad bewertet.
- Die bisherigen Phasen 7-12 bleiben als Referenz fuer Betriebs-/Produktreife erhalten, werden aber fuer den Greenfield-Track neu zugeschnitten.
- Das Spiel soll auf `last-strawberry.com` laufen (Frontend/API getrennt ueber Subdomains moeglich).
- Grundlage fuer den Neustart:
  - `docs/greenfield_web_only_concept_v1.md`
  - `docs/ui_gameflow_blueprint_v2.md` (UI-/Spielflusslogik bleibt als Input wertvoll)
  - `docs/greenfield_roadmap_web_v1.md`

## Zielbild
- V2 als OpenRouter-first Plattform stabil ausrollen.
- Legacy-Inferenzpfad (Google Cloud) schrittweise abloesen.
- Qualitaet durch CI + Coverage-Gates erzwingen.
- RAG/Memory statt regelmaessigem Modell-Retraining im Runtime-Pfad.

## Leit-KPIs
- API-Fehlerrate (`5xx`): < 1.0% (Beta), < 0.3% (Prod)
- p95 Turn-Latenz: < 6s (Beta), < 4s (Prod-Ziel)
- Kosten pro Turn: transparent messen, monatliche Budgetgrenze definieren
- Testabdeckung backend_v2: stufenweise erhoehen (siehe Codecov-Gates)

---

## Phase 0: Planung und Baseline
Zeitraum: 19.02.2026 - 25.02.2026

### Deliverables
- Architekturentscheidungen finalisieren (Provider-Abstraktion, Datenmodell, Auth-Strategie).
- Scope-Freeze fuer V2-MVP.
- Codecov im Projekt aktiv einbinden (Repository verbinden, erste Baseline-Pipeline).

### Meilenstein M0 (25.02.2026)
- `docs/restart_v2_openrouter.md` als verbindliche Grundlage bestaetigt.
- CI laeuft fuer `backend_v2` mit Test-Job gruen.
- Erste Coverage an Codecov gemeldet (nur Reporting, noch keine harten Gates).

---

## Phase 1: Fundament und Qualitaetsgates
Zeitraum: 26.02.2026 - 10.03.2026

### Deliverables
- Stabile v2-Konfiguration inkl. Keyring/Env-Fallback.
- Orchestrator robust gegen Provider-Fehler.
- CI-Workflow mit Coverage-Upload (`coverage.xml`) auf Codecov.
- `codecov.yml` mit initialen Statuschecks.

### Codecov-Gates (ab M1)
- Projekt-Coverage (backend_v2): >= 45%
- Patch-Coverage: >= 70%
- PR darf bei Gate-Verletzung nicht gemerged werden.

### Meilenstein M1 (10.03.2026)
- Reproduzierbarer Build + Tests lokal und in CI.
- Verbindliche Coverage-Gates aktiv.
- Verbindliche Abnahmekriterien in `docs/m1_definition_of_done.md`.

---

## Phase 2: V2 Gameplay Vertical Slice
Zeitraum: 11.03.2026 - 31.03.2026

### Deliverables
- Persistenz fuer Welten/Spieler/Events (zuerst SQLite oder direkt Postgres).
- Auth (JWT, stateless) + Ownership-Pruefungen.
- RAG/Memory statt regelmaessigem Retraining (`docs/rag_memory_v2_architecture.md`).
- `/v2/game/turn` mit stabiler Analyse/Narrative-Kette und modellgetriebener Memory-Einbindung.
- Basis-Observability (strukturierte Logs + Korrelations-ID).

### Codecov-Gates (ab M2)
- Projekt-Coverage: >= 55%
- Patch-Coverage: >= 75%
- Kritische Module (`providers`, `services`) mit gezielten Unit-Tests.

### Meilenstein M2 (31.03.2026)
- End-to-End spielbar auf V2 (Auth -> World -> Turn -> Persistenz).
- Persistenter Memory-Ansatz definiert und in Runtime-Plan verankert (kein Training im Online-Pfad).
- Keine Legacy-Abhaengigkeit im primaeren V2-Flow.

---

## Phase 3: Migration und Haerten
Zeitraum: 01.04.2026 - 21.04.2026

### Deliverables
- Frontend schrittweise auf `/v2`-Endpoints umstellen (oder kompatible Adapterroute bereitstellen).
- Fallback-/Routing-Strategie fuer OpenRouter-Modelle:
  - Analyse: stabil/deterministisch
  - Narrative: quality-first + fallback (schneller/guenstiger)
- Last-/Fehlertests fuer parallele Turns.
- Security-Hardening (Secrets, Logging-Sanitization, Rate-Limits).
- Hybrid Retrieval fuer Memory (lexical + vector).

### Codecov-Gates (ab M3)
- Projekt-Coverage: >= 62%
- Patch-Coverage: >= 80%
- Diff-Coverage fuer sicherheitskritische Dateien verpflichtend.

### Meilenstein M3 (21.04.2026)
- V2 Beta-Ready.
- Migration von Testnutzern auf V2 moeglich.

### Fortschritt (20.02.2026, vorgezogen umgesetzt)
- Parallel-Turn Last-/Fehlertests als automatisierte API-Tests hinzugefuegt (`backend_v2/tests/test_parallel_turns.py`):
  - Burst mit aktivem Limiter (`200` + `429` gemischt, inkl. Metrik-Validierung)
  - Burst mit simuliertem Provider-Ausfall (`502`, inkl. Error-Metrik-Validierung)
- Lokales Lasttest-CLI fuer manuelle Bursts hinzugefuegt (`backend_v2/scripts/run_parallel_turn_load.py`).
- Security-Hardening erweitert:
  - Request-Body-Limit in Middleware (`LS_MAX_REQUEST_BODY_BYTES`, `413` bei Ueberschreitung)
  - Striktere Eingabegrenzen fuer `TurnRequest` (z. B. `player_command` max. 2000 Zeichen)
  - Login-Rate-Limit fuer `/v2/auth/login` inkl. Audit-Event (`auth_login_rate_limited`)
  - Zusaetzliches IP-basiertes Turn-Rate-Limit (`rate_limit_ip_exceeded`) fuer `/v2/game/turn`
- Turn-Timeout-Guard fuer `/v2/game/turn` umgesetzt (`LS_TURN_TIMEOUT_SECONDS`, default `60`, `504` bei Ueberschreitung) inkl. API-/Config-Tests.
- Retrieval-Monitoring erweitert: `windowed_rates` liefert jetzt auch prozentuale API-Fehlerraten (`errors_5xx_percent`, `rate_limit_429_percent`) fuer schnellere SLO-Bewertung.
- Turn-Timeouts werden als dediziertes Audit-Event erfasst (`turn_timeout`) fuer frueheres Alerting vor groesseren 504-Wellen.
- Betriebs-Monitoring erweitert um `/v2/metrics/slo` (window-basierte Pass/Fail-Auswertung mit konfigurierbaren 5xx/429-Schwellen im Request).
- SLO-Defaults zentral in Runtime-Config verankert (`LS_SLO_WINDOW`, `LS_SLO_MAX_5XX_PERCENT`, `LS_SLO_MAX_429_PERCENT`) und ueber API-Query weiterhin uebersteuerbar.
- Prometheus-Alert-Starterset hinzugefuegt (`docs/alert_rules_backend_v2.yml`) fuer SLO-, Timeout-, Provider- und Auth-Fehler-Signale.
- Monitoring-Operationalisierung erweitert: automatisierter SLO-Smoke (`backend_v2/scripts/smoke_slo.py`) und importierbares Grafana-Dashboard (`docs/grafana_dashboard_backend_v2.json`).
- Lokales Monitoring-Testen erweitert: PowerShell-Generator fuer gezielte Event-Simulation (`backend_v2/scripts/generate_monitoring_events.ps1`).
- Monitoring-Betrieb weiter gehaertet: End-to-End Stack-Smoke (`backend_v2/scripts/smoke_monitoring_stack.py`) fuer Backend/Prometheus (optional Grafana API).
- Frontend-MVP auf `/v2`-API angebunden (historischer Legacy-Pfad `web_frontend`, inzwischen archiviert unter `archive/legacy_frontend/web_frontend`): Login (`/v2/auth/login`), Weltenliste/Erstellung (`GET/POST /v2/worlds`), Turn-Loop (`/v2/game/turn`) und Verlaufsladen (`/v2/worlds/{world_id}/turns`); Legacy-UI-Aktionen ohne V2-Backend (Profil/Admin/Export/Korrektur) werden im MVP ausgeblendet.
- E2E-Bruecke fuer Legacy-Backend vorbereitet: `backend_server` kann Legacy-Endpunkte im Bridge-Modus (`LS_V2_BRIDGE_ENABLED=true`) auf `backend_v2` routen, inkl. Smoke-Script (`backend_server/scripts/smoke_v2_bridge.py`) und Runbook (`docs/backend_server_v2_bridge.md`).
- Reproduzierbarer Playtest-Quickcheck fuer Bridge-Flow hinzugefuegt (`backend_server/scripts/playtest_bridge_quickcheck.py`, `docs/playtest_bridge_quickcheck.md`) mit Happy Path + Failure Path.

---

## Phase 4: Produktiv-Cutover
Zeitraum: 22.04.2026 - 13.05.2026

### Deliverables
- Canary-Rollout (z. B. 10% -> 50% -> 100%).
- Kosten- und Latenz-Tuning pro Modellklasse (z. B. 70B vs. Mid-tier).
- Legacy-GCP-Inferenzpfad deaktivieren und archivieren.
- Betriebsrunbook (Incident-Flow, Rollback, SLOs).

### Codecov-Gates (ab M4)
- Projekt-Coverage: >= 70%
- Patch-Coverage: >= 85%

### Meilenstein M4 (13.05.2026)
- Vollstaendiger Cutover auf OpenRouter-basierte V2-Plattform.
- Legacy-Inferenzpfad ausser Betrieb.

### Fortschritt (21.02.2026, Phase 4A gestartet)
- Canary-Mechanik im `backend_server` als user-sticky Routing umgesetzt:
  - `LS_V2_BRIDGE_CANARY_PERCENT` (0..100) fuer schrittweisen Traffic-Shift.
  - `LS_V2_BRIDGE_CANARY_FORCE_USER_IDS` fuer interne Pilot-/QA-User.
- Bridge-Runbook erweitert (`docs/backend_server_v2_bridge.md`) und separates Cutover-Runbook hinzugefuegt (`docs/phase4_cutover_runbook.md`).
- Phase 4B gestartet: Kosten-/Latenz-Telemetrie je Modellroute in `backend_v2` erweitert
  - neue Metriken fuer Stage+Modell (`model_attempt_total`, `model_latency_ms_{avg,p95,p99,max}`, `model_tokens_total`, `model_cost_usd_total`)
  - Kostenrate je Fenster (`estimated_cost_usd_per_minute`, `provider_reported_cost_usd_per_minute`)
  - Budget-Audit-Events fuer Stage-Latenz (`analysis_latency_budget_exceeded`, `narrative_latency_budget_exceeded`)
- Phase 4C gestartet: Legacy-GCP-Inferenzpfad im `backend_server` deaktiviert/archiviert
  - Gameplay-Endpunkte laufen bridge-only ueber `backend_v2`; ohne `LS_V2_BRIDGE_ENABLED=true` liefern sie `503`
  - Google-Auth/GCP-Inferenzcode entfernt; `backend_server/requirements.txt` ohne `google-auth`/`certifi`
  - Cutover-Runbook auf Bridge-only-Betrieb und artefaktbasierten Rollback aktualisiert
- Phase 4D gestartet: Runtime-Hardening im `backend_server`
  - FastAPI-Startup von `@app.on_event("startup")` auf `lifespan` migriert (deprecation-sicher)
  - Backend-Tests auf no-op Lifespan umgestellt, damit sie ohne DB-Startup-Seiteneffekte stabil bleiben
- Phase 4E abgeschlossen: Finale Cutover-Abnahme
  - gebuendelter Release-Smoke hinzugefuegt (`backend_server/scripts/smoke_phase4_release.py`)
  - M4-Abnahmekriterien formalisiert (`docs/m4_definition_of_done.md`)
  - Runbook um finalen Validation-Command erweitert (`docs/phase4_cutover_runbook.md`)

### Meilensteinstatus
- M4 erreicht am 21.02.2026:
  - V2/OpenRouter ist primaerer und aktiver Runtime-Pfad.
  - Legacy-GCP-Inferenzpfad ist aus Runtime deaktiviert/archiviert.
  - Betriebs- und Abnahmecheckliste fuer den Cutover ist dokumentiert und automatisierbar.

---

## Phase 5: Betriebsstabilitaet und Kostenkontrolle
Zeitraum: 21.02.2026 - 07.03.2026

### Deliverables
- README auf aktuellen OpenRouter/V2-Stand konsolidieren (inkl. Codecov-Tag).
- Post-cutover Ops-Playbook mit Daily/Weekly-Routinen.
- Wiederholbarer Ops-Report fuer Health + SLO + Kostenraten.
- Erweiterte Prometheus-Alert-Starterregeln fuer Latenzbudget- und Kosten-Spikes.

### Meilenstein M5
- Operative Daily-Checks sind skriptbar und dokumentiert.
- Alert-Regeln decken Verfuegbarkeit, Fehler, Latenzbudget und Kostenrate ab.
- Projekt-Doku reflektiert den realen Produktivpfad (V2/OpenRouter, bridge-only).

### Fortschritt (21.02.2026)
- Neuer Ops-Report fuer V2 hinzugefuegt: `backend_v2/scripts/ops_phase5_report.py`
  - Prueft `v2/health`, `v2/metrics/slo`, Kostenrate und optional zentrale Prometheus-Metric-Familien.
- Monitoring-Runbook erweitert um Phase-5-Ops-Report (`docs/monitoring_prometheus_v2.md`).
- Alert-Starterregeln erweitert (`docs/alert_rules_backend_v2.yml`):
  - `LastStrawberryV2AnalysisLatencyBudgetSpike`
  - `LastStrawberryV2NarrativeLatencyBudgetSpike`
  - `LastStrawberryV2EstimatedCostRateHigh`
- Betriebsplaybook hinzugefuegt: `docs/phase5_operations_playbook.md`.

### Meilensteinstatus
- M5 erreicht am 21.02.2026:
  - Phase-5-Ops-Checks sind implementiert und dokumentiert.
  - Alerting deckt jetzt auch Latenzbudget- und Kosten-Spitzen ab.
  - Doku-Basis ist auf den aktiven V2-Betrieb vereinheitlicht.

---

## Phase 6: Release-Automation und Incident-Playbooks
Zeitraum: 21.02.2026 - 28.02.2026

### Deliverables
- Automatisierter CI-Gate fuer Release-/Ops-Abnahme:
  - `smoke_phase4_release.py`
  - `ops_phase5_report.py --require-prometheus-families`
- Zentrale Ops-Schwellen als Env-Defaults fuer Skripte (`LS_OPS_*`).
- Konkrete Incident-Playbooks fuer die Top-Fehlerbilder (`504`, `401`, `502`).

### Meilenstein M6
- Reproduzierbarer Release/Ops-Gate in GitHub Actions.
- Schwellenwerte fuer SLO/Kosten nicht mehr nur als CLI-Konvention, sondern zentral als Env-Defaults.
- Incident-Response fuer haeufige Stoerungen als Schritt-fuer-Schritt-Runbook dokumentiert.

### Fortschritt (21.02.2026)
- Neuer Workflow: `.github/workflows/phase6_release_ops_gate.yml`
  - startet lokalen Mock-OpenRouter (`backend_v2/scripts/mock_openrouter_server.py`)
  - startet `backend_v2` + `backend_server`
  - fuehrt `smoke_phase4_release.py` und `ops_phase5_report.py` als Gate aus
- Ops-/SLO-Skripte lesen zentrale Env-Defaults:
  - `backend_v2/scripts/ops_phase5_report.py`
  - `backend_v2/scripts/smoke_slo.py`
- Incident-Runbook hinzugefuegt:
  - `docs/phase6_incident_playbooks.md`

### Meilensteinstatus
- M6 erreicht am 21.02.2026:
  - Release/Ops-Gate ist CI-automatisiert und reproduzierbar.
  - Ops-Schwellen sind zentralisierbar ueber `LS_OPS_*`.
  - Incident-Playbooks fuer `504`/`401`/`502` sind dokumentiert.

---

## Phase 7: Deployment-Readiness (Server/Staging)
Zeitraum: 22.02.2026 - 07.03.2026

### Deliverables
- Server-Betrieb fuer `backend_v2` + `backend_server` reproduzierbar dokumentieren (Plesk/Linux).
- Service-Start/Restart-Strategie (z. B. systemd oder Plesk-Tasking) inkl. Logging-Pfade.
- Reverse-Proxy-/TLS-/Header-Konzept fuer Frontend + beide Backends.
- Backup/Restore-Runbook fuer Datenbanken und `.env`-Secrets.
- Deployment- und Rollback-Dry-Run (ohne Produktiv-Cutover erzwingen).

### Meilenstein M7
- Vollstaendiger Server-Dry-Run ist dokumentiert und wiederholbar.
- Rollback auf funktionierende Version ist in < 15 Minuten durchfuehrbar.
- Monitoring (Prometheus/Grafana) bleibt nach Restart/Deploy stabil.

---

## Phase 8: Performance und Lasttests
Zeitraum: 08.03.2026 - 21.03.2026

### Deliverables
- Lastprofile definieren (single-user, parallel turns, burst, abuse-nahe Szenarien).
- Reproduzierbare Lasttests fuer Bridge-Flow und direkten V2-Flow.
- Bottleneck-Analyse (Provider, DB/SQLite, Locking, Netzwerk, Timeouts).
- Tuning-Empfehlungen fuer Timeouts, Rate-Limits, Fallback-Ketten und Modellwahl.

### Meilenstein M8
- Belastbare Betriebsgrenzen dokumentiert (z. B. parallele Turns, Timeout-Wahrscheinlichkeit).
- Konkrete Tuning-Defaults fuer Beta-Betrieb festgelegt.
- Lasttest-Resultate als Vergleichsbasis fuer spaetere Releases archiviert.

---

## Phase 9: Security Hardening (Pre-Beta)
Zeitraum: 22.03.2026 - 04.04.2026

### Deliverables
- Secret-Handling und Deployment-Configs haerten (keine Klartext-Leaks in Logs/Repo).
- Auth/JWT/CORS/CSP Review fuer `backend_server` + `backend_v2`.
- Abuse-Schutz und Audit-Logging auf reale Angriffspfade pruefen.
- Security-Checkliste fuer Release-Freigabe.
- Optional: Bedrohungsmodell (`Threat Model`) fuer V2 + Bridge + Monitoring.

### Meilenstein M9
- Kritische Security-Luecken geschlossen oder bewusst mit Risiko dokumentiert.
- Release-Checkliste enthaelt verbindliche Security-Gates.
- Log-Sanitization/Secret-Schutz gegenpruefbar.

---

## Phase 10: UI- und Spielfluss-Definition (Pre-Beta Product Design)
Zeitraum: 05.04.2026 - 18.04.2026

### Deliverables
- Core-Loop definieren (Login -> Welt -> Turn -> State-Update -> Weiterer Turn).
- UI-Blueprint fuer zentrale Screens:
  - Weltliste / Welterstellung
  - Spielansicht (Narrativ + Eingabe + Systemevents)
  - Charaktersheet
  - Inventar
  - Verlauf / Journal / Log
- Daten- und Zustandsmodell definieren:
  - Welche Felder zeigt die UI?
  - Welche Felder kommen aus welcher API?
  - Loading-/Error-/Timeout-/Reconnect-Zustaende
- API-Gap-Liste (was im V2-Backend fuer Inventar/Charaktersheet noch fehlt)
- Umsetzungsreihenfolge fuer Frontend-MVP (must/should/could)

### Meilenstein M10
- UI/Spielfluss ist schriftlich definiert und fuer Umsetzung freigegeben.
- Charaktersheet/Inventar-Datenvertraege sind festgelegt.
- Closed-Beta-Feedback kann sich auf Spiel und Qualitaet konzentrieren (nicht auf fehlende Grundstruktur).

### Referenz
- UI/Gameflow-Blueprint: `docs/ui_gameflow_blueprint_v2.md`

---

## Phase 11: Frontend-MVP Umsetzung und E2E-Playtest
Zeitraum: 19.04.2026 - 09.05.2026

### Deliverables
- UI gemaess Phase-10-Blueprint umsetzen (mindestens Core-Loop + Basisansichten).
- Fehler-/Timeout-UX sichtbar und benutzbar machen.
- E2E-Tests fuer Hauptfluss:
  - Login
  - Welt erstellen/oeffnen
  - Mehrere Turns
  - Verlauf neu laden
- Quickcheck fuer UI-Flow (lokal + CI)

### Meilenstein M11
- "Kurzer Pen&Paper-Teststart" ist ueber UI reproduzierbar.
- E2E-Smoke deckt Hauptfluss automatisiert ab.
- Beta-kritische UX-Fehler (Blocker) sind behoben oder dokumentiert.

---

## Phase 12: Closed Beta und Feedback-Loop
Zeitraum: 10.05.2026 - 31.05.2026

### Deliverables
- Closed-Beta-Rollout an kleine Nutzergruppe (kontrolliert).
- Feedback-Kanal + Auswertung (Bug/UX/Content/Balance getrennt).
- Produktmetriken und Betriebsmetriken gemeinsam betrachten.
- Priorisierte Post-Beta-Liste fuer Phase 13+.

### Meilenstein M12
- Closed Beta laeuft mit echtem Nutzerfeedback.
- Kritische Betriebs-/UX-Themen sind identifiziert und priorisiert.
- Entscheidungsvorlage fuer Open Beta / weitere Produktisierung liegt vor.

---

## Codecov Setup-Checklist (konkret)
1. Repo unter `https://app.codecov.io/gh/leratos/...` verbinden.
2. GitHub Action ergaenzen:
   - Tests ausfuehren
   - `coverage.xml` erzeugen
   - Upload zu Codecov
3. `codecov.yml` hinzufuegen:
   - Statuschecks (`project`, `patch`)
   - Pfadfokus zunaechst `backend_v2/**`
4. Branch Protection:
   - Codecov-Checks als Required Status Checks.
5. Monatliches Gate-Raising nur bei stabiler gruener CI.

## Risiken und Gegenmassnahmen
- Risiko: Modellverhalten instabil bei Providerwechsel.
  - Gegenmassnahme: Golden test cases + fallback chain.
- Risiko: Coverage steigt nur formal, nicht in kritischen Flows.
  - Gegenmassnahme: Modul-spezifische Mindesttests fuer Orchestrator/Provider/Auth.
- Risiko: Migration blockiert Frontend.
  - Gegenmassnahme: Uebergangsadapter und schrittweises Routing.
- Risiko: Memory Drift oder Halluzinations-Verstaerkung.
  - Gegenmassnahme: Quellengebundene Memory-Writes + regelbasierte Validierung.
