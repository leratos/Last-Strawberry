# Last-Strawberry V2 Roadmap (OpenRouter + Codecov)

Stand: 18. Februar 2026

## Zielbild
- V2 als OpenRouter-first Plattform stabil ausrollen.
- Legacy-Inferenzpfad (Google Cloud) schrittweise ablösen.
- Qualität durch CI + Coverage-Gates erzwingen.

## Leit-KPIs
- API-Fehlerrate (`5xx`): < 1.0% (Beta), < 0.3% (Prod)
- p95 Turn-Latenz: < 6s (Beta), < 4s (Prod-Ziel)
- Kosten pro Turn: transparent messen, monatliche Budgetgrenze definieren
- Testabdeckung backend_v2: stufenweise erhöhen (siehe Codecov-Gates)

---

## Phase 0: Planung und Baseline
Zeitraum: 19.02.2026 - 25.02.2026

### Deliverables
- Architekturentscheidungen finalisieren (Provider-Abstraktion, Datenmodell, Auth-Strategie).
- Scope-Freeze für V2-MVP.
- Codecov im Projekt aktiv einbinden (Repository verbinden, erste Baseline-Pipeline).

### Meilenstein M0 (25.02.2026)
- `docs/restart_v2_openrouter.md` als verbindliche Grundlage bestätigt.
- CI läuft für `backend_v2` mit Test-Job grün.
- Erste Coverage an Codecov gemeldet (nur Reporting, noch keine harten Gates).

---

## Phase 1: Fundament und Qualitätsgates
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
- Persistenz für Welten/Spieler/Events (zuerst SQLite oder direkt Postgres).
- Auth (JWT, stateless) + Ownership-Prüfungen.
- `/v2/game/turn` mit stabiler Analyse/Narrative-Kette und Modellkonfiguration.
- Basis-Observability (strukturierte Logs + Korrelations-ID).

### Codecov-Gates (ab M2)
- Projekt-Coverage: >= 55%
- Patch-Coverage: >= 75%
- Kritische Module (`providers`, `services`) mit gezielten Unit-Tests.

### Meilenstein M2 (31.03.2026)
- End-to-End spielbar auf V2 (Auth -> World -> Turn -> Persistenz).
- Keine Legacy-Abhängigkeit im primären V2-Flow.

---

## Phase 3: Migration und Härten
Zeitraum: 01.04.2026 - 21.04.2026

### Deliverables
- Frontend schrittweise auf `/v2`-Endpoints umstellen (oder kompatible Adapterroute bereitstellen).
- Fallback-/Routing-Strategie für OpenRouter-Modelle:
  - Analyse: stabil/deterministisch
  - Narrative: quality-first + fallback (schneller/günstiger)
- Last-/Fehlertests für parallele Turns.
- Security-Hardening (Secrets, Logging-Sanitization, Rate-Limits).

### Codecov-Gates (ab M3)
- Projekt-Coverage: >= 62%
- Patch-Coverage: >= 80%
- Diff-Coverage für sicherheitskritische Dateien verpflichtend.

### Meilenstein M3 (21.04.2026)
- V2 Beta-Ready.
- Migration von Testnutzern auf V2 möglich.

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
- Vollständiger Cutover auf OpenRouter-basierte V2-Plattform.
- Legacy-Inferenzpfad außer Betrieb.

---

## Codecov Setup-Checklist (konkret)
1. Repo unter `https://app.codecov.io/gh/leratos/...` verbinden.
2. GitHub Action ergänzen:
   - Tests ausführen
   - `coverage.xml` erzeugen
   - Upload zu Codecov
3. `codecov.yml` hinzufügen:
   - Statuschecks (`project`, `patch`)
   - Pfadfokus zunächst `backend_v2/**`
4. Branch Protection:
   - Codecov-Checks als Required Status Checks.
5. Monatliches Gate-Raising nur bei stabiler grüner CI.

## Risiken und Gegenmaßnahmen
- Risiko: Modellverhalten instabil bei Providerwechsel.
  - Gegenmaßnahme: Golden test cases + fallback chain.
- Risiko: Coverage steigt nur formal, nicht in kritischen Flows.
  - Gegenmaßnahme: Modul-spezifische Mindesttests für Orchestrator/Provider/Auth.
- Risiko: Migration blockiert Frontend.
  - Gegenmaßnahme: Übergangsadapter und schrittweises Routing.
