# Greenfield Roadmap (Web-only, OpenRouter-first)

Stand: 22. Februar 2026

## Zielbild
- Reines Web-Spiel unter eigener Subdomain (z. B. `play.last-strawberry.com`)
- FastAPI-basierte Game API
- OpenRouter fuer LLM-Funktionen (Intent + Narration)
- Deterministischer Regelkern als autoritative Spielwahrheit
- Iterative Weiterentwicklung nach spielbaren Versionen

## Produktprinzipien
- Kein Weltenwechsel fuer aktive Charakterinstanzen
- Charaktervorlagen koennen in neue Welten "geforkt" werden (getrennte Entwicklung)
- Inventar-Items sind grundsaetzlich nutzbar (mind. eine Interaktion)
- LLMs unterstuetzen, aber definieren nicht allein den Spielzustand

---

## G0: Greenfield Foundation (Konzept -> Scaffold)
Zeitraum: sofort

### Deliverables
- Repo-Struktur fuer Greenfield (`apps/`, `packages/`, `infra/`)
- Gemeinsame Schemas (World bootstrap, Turn intent/resolution, State delta)
- Regelkern-Skeleton
- Web-Client-Skeleton (React + TS + Vite)
- Archivplan fuer Legacy-Bestand

### Meilenstein G0
- Greenfield-Startpaket ist im Repo vorhanden und teamfaehig dokumentiert.

---

## G1: World Bootstrap + Creation Flow
Zeitraum: nach G0

### Deliverables
- "Neue Welt erstellen" Flow mit strukturiertem World/Character-Seed
- Validator/Normalizer fuer LLM-Outputs
- Persistente Speicherung von Weltgrundlage + Charakterinstanz
- Initialer Narrator-Text (Startsituation)

### Meilenstein G1
- Nutzer kann aus Beschreibungen eine neue spielbare Welt erzeugen und Startszene erhalten.

---

## G2: Turn Pipeline MVP (Intent -> Rules -> Narration)
Zeitraum: nach G1

### Deliverables
- Intent-Analyse (strukturierte Aktionen)
- Deterministischer Regelkern fuer MVP-Aktionen:
  - Move
  - Inspect
  - Talk
  - Attack
  - UseItem
- Narration aus `TurnResolution` statt Keyword-Parsing
- Persistentes Turn-Log + StateDelta

### Meilenstein G2
- 3-5 Zuege pro Sitzung spielbar mit konsistentem Zustand.

---

## G3: UI MVP (Game Loop, Charaktersheet, Inventar)
Zeitraum: nach G2

### Deliverables
- Spielansicht mit Narrativ + Eingabe + Verlauf
- Charaktersheet (readable, stabile Felder)
- Inventar (mindestens `inspect/use/equip/consume`)
- Fehler-/Timeout-UX (401/429/502/504)

### Meilenstein G3
- Spielbarer Web-MVP fuer internen Test.

---

## G4: Persistence Expansion (NPC Memory + World Memory)
Zeitraum: nach G3

### Deliverables
- Persistente NPC-Profile, Beziehungen, Erinnerungen, Zustandsdaten
- Kontextauswahl fuer relevante NPC-Erinnerungen je Turn
- Wiedererkennung und konsistente Wiederverwendung von NPCs ueber Turns

### Meilenstein G4
- NPCs koennen langfristig konsistent erinnert und narrativ wieder eingebunden werden.

---

## G5: Internal Alpha -> Closed Beta Vorbereitung
Zeitraum: nach G4

### Deliverables
- E2E-Checks fuer Hauptspielpfad
- Monitoring/Ops Uebernahme aus V2-Betriebserfahrung
- Lasttest-Basis fuer Game Loop
- Security/Deployment-Hardening fuer Web-only Stack

### Meilenstein G5
- Beta-Kandidat mit stabiler Architektur und reproduzierbarem Betrieb.

---

## Technische Schulden / Quality Debt (aktiv dokumentiert)

- **Narration Quality Debt (reporthafte/auflistende Erzaehlweise)**
  - Aktuelle Narration ist funktional korrekt, wirkt aber teilweise wie ein Status-/Eventbericht statt wie eine zusammenhaengende Szene.
  - Bewusst waehrend Entwicklungs-/Testphase nicht voll optimiert (Token-/Zeitbudget).
  - Verbindliche Zielregeln und spaetere Architektur (`Rules -> Story Beats -> Narrator`) dokumentiert in:
    - `docs/narration_quality_debt_v1.md`

---

## Fortschritt (Micro-Stages G30-G39, Discovery/World-Interaction Ausbau)

### Abgeschlossen
- G30: Freitext-Inspect auf sichtbare Umweltziele (scene_points/container) gemappt.
- G31: `OPEN`/`SEARCH` als strukturierte Container-Aktionen mit getrennter Persistenzsemantik (`open` vs `search`).
- G32: UI-Quick-Actions fuer Container (`Oeffnen`, `Durchsuchen`) hinzugefuegt.
- G33: Preview-Narration hebt Container-/Loot-Ergebnisse klarer hervor.
- G34: Discovery-Status im UI (Badges/Counter) verbessert.
- G35: Rollenwissen fuer NPCs bis zur Interaktion maskiert.
- G36: Fraktionswissen fuer NPCs bis zur Interaktion maskiert.
- G37: `TAKE` fuer Szene-Objekte (MVP) mit persistentem `taken`-Zustand und einmaligem Loot.
- G38: Greenfield-Quickcheck deckt Discovery + Container + Scene-Object-Interaktionen mit ab.
- G39: Doku/Progress aktualisiert und Batch-Regression durchgefuehrt.

### Ergebnis nach G39
- Discovery und Sichtbarkeit sind jetzt deutlich naeher an der gewuenschten Spielregel: Spieler kann nicht allein durch Freitext neue NPCs/Objekte "erschaffen" oder alles sofort wissen.
- Umweltinteraktionen sind als eigene, testbare Aktionen modelliert (`INSPECT`, `OPEN`, `SEARCH`, `TAKE`) statt nur freier Narrativ-Text.
- Quickcheck deckt neben Kampf/Distanz jetzt auch Exploration-/Loot-Pfade ab.

## Fortschritt (Micro-Stages G40-G49, Discovery-Qualitaet & UX)

### Abgeschlossen
- G40: `INSPECT` unterscheidet `broad` vs. `focused` (Parser-Parameter `inspect_mode`), inkl. natuerlicher Formulierungen (`schaue mir X genauer an`).
- G41: Rules Engine emittiert `inspect_broad_success` fuer breites Umsehen.
- G42: Wiederholtes breites Umsehen ohne neue Funde liefert `discovery_nothing_new`.
- G43: Gezieltes, aber unsichtbares/unbekanntes `INSPECT` liefert `CLARIFY` statt Fehlklassifikation als breites Umsehen.
- G44: Phrasen wie `durchsuche die Umgebung` werden korrekt als breites `INSPECT` interpretiert.
- G45: `GameContextResponse` fuehrt strukturierte Hidden-Counts (`hidden_npc_count`, `hidden_scene_point_count`) ein.
- G46: Web-UI fuer Interaktionspunkte bietet Filter und Sortierung.
- G47: Vor Detail-Inspect werden Container-/Objekt-Aktionen sichtbar, aber deaktiviert mit klarer UX-Hinweisbeschriftung.
- G48: Discovery-aware Clarify-Messages fuer `OPEN`/`SEARCH`/`TAKE` bei unsichtbaren Zielen.
- G49: Quickcheck erweitert um Hidden-Counts vor Discovery und Wiederholungs-INSPECT mit `discovery_nothing_new`.

### Ergebnis nach G49
- Exploration fuehlt sich konsistenter an: Spieler unterscheiden klar zwischen "umsehen" (breit) und "gezielt untersuchen" (fokussiert).
- Discovery-Status ist im UI und im API-Context besser sichtbar/auswertbar.
- Fehlbedienungen bei Umweltaktionen (unsichtbare Ziele) fuehren zu klaren Hinweisen statt irrefuehrenden Ergebnissen.
