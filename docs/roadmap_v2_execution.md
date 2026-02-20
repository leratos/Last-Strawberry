# Last-Strawberry V2 Roadmap (OpenRouter + Codecov)

Stand: 19. Februar 2026

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
