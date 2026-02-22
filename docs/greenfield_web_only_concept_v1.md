# Greenfield Web-only Konzept (OpenRouter-first)

Stand: 22. Februar 2026

## Entscheidung (Strategischer Pivot)
Last-Strawberry wird ab jetzt als **Greenfield Web-only Anwendung** geplant:
- keine Desktop-Anwendung als Produktfokus
- kein lokales LLM / kein Google-Cloud-Inferenzpfad
- OpenRouter-first (internetabhängig, daher Web als natuerlicher Client)

## Produkt-Topologie (dein Hosting-Kontext)
- `last-strawberry.com` ist die Hauptdomain fuer das Spiel / Entry Point.
- Das Spiel laeuft als getrennte Web-App auf eigener Subdomain, z. B.:
  - `play.last-strawberry.com` (Spiel-Frontend)
  - `api.last-strawberry.com` (Game API hinter Reverse Proxy)
- Vorteil: Spiel-Frontend und API sind sauber getrennt, aber unter derselben Produktdomain.

## Warum dieser Neustart sinnvoll ist (kritische Bewertung)

### Starkes Argument fuer Greenfield
- Die bisherigen Altpfade (Desktop + Legacy-Backend + fruehere Trainings-/GCP-Annahmen) tragen Architekturentscheidungen, die nicht mehr zum Zielsystem passen.
- Ihr habt bereits viel in **Ops/CI/Monitoring/Bridge** investiert. Das ist wertvoll, aber nicht automatisch ein gutes Produktfundament fuer eine moderne Web-RPG-Plattform.
- Ein vollwertiges DnD-aehnliches Erlebnis braucht ein **sauberes Domänenmodell**. Das ist schwer auf einem historisch gewachsenen JSON-/Monolith-Stapel nachzuziehen.

### Harte Wahrheit / Risiko
- "Vollwertiges DnD-Erlebnis" ist sehr groß. Das ist nicht nur UI + LLM:
  - Regelwerk / Kampf / Ressourcen / Status
  - Inventarlogik / Item-Nutzung
  - Klassen / Progression / Zauber
  - konsistente Welt- und Charakterzustände
  - UX fuer komplexe Entscheidungen
- Wenn ihr alles gleichzeitig wollt, scheitert das Projekt an Scope, nicht an Technik.

### Empfehlung
- **Greenfield ja**
- aber zuerst **DnD-like / SRD-inspiriertes MVP**, nicht sofort "vollwertig"
- klare Stufen:
  1. Story + State + Inventar nutzbar
  2. deterministische Regeln fuer Kernaktionen
  3. Ausbau Richtung taktischer Tiefe

## Produktprinzipien (von dir vorgegeben, hier formalisiert)

### P1: Kein Weltenwechsel fuer einen aktiven Charakter
- Ein `WorldCharacter` ist strikt an **eine Weltinstanz** gebunden.
- Kein direkter Transfer desselben Charakters zwischen Welten.

### P2: Charakter kann als Vorlage in andere Welten eingefuegt werden
- Das ist kein "derselbe Zustand", sondern eine **neue Instanz**.
- Gleiche Ausgangsbasis, aber getrennte Entwicklung.

Formal:
- `CharacterTemplate` (wiederverwendbare Vorlage)
- `WorldCharacter` (weltgebundene Instanz)

### P3: Inventargegenstaende sind grundsaetzlich verwendbar
- Jedes Item hat mindestens eine sinnvolle Interaktion.
- "Deko-Items" nur wenn explizit als `decorative=true` markiert.

## Zielarchitektur (Greenfield Web-only)

## Uebersicht
- **Web Client (SPA)**: Spiel-UI, Charaktersheet, Inventar, Verlauf
- **Game API (FastAPI)**: Auth, Worlds, Turns, State, Inventory, Character
- **LLM Orchestrator**: Intent-Analyse + Narration (OpenRouter)
- **Rules Engine (deterministisch)**: autoritativer Zustand, Wuerfe, Kosten, Effekte
- **Persistence**: relationale DB (empfohlen Postgres, nicht SQLite als Langfristziel)
- **Memory/RAG**: asynchroner Kontextspeicher fuer Story-/Lore-Rueckbezug
- **Observability**: Prometheus/Grafana/Logs (bereits stark, weiter nutzen)

## Kritischer Architekturpunkt (sehr wichtig)
Die LLMs duerfen **nicht** die alleinige Wahrheit fuer Spielzustand sein.

### Schlecht (brittle)
- Erzähler schreibt Text
- Assistent scannt Text/Keywords ("heilt", "greift an", ...)
- daraus wird State geaendert

Problem:
- Synonyme / Formulierungen / Halluzinationen
- schwer testbar
- inkonsistente State-Aenderungen

### Besser (empfohlen)
- LLM analysiert Spielerintention -> **strukturierte Aktion(en)** (JSON / function-call)
- **Rules Engine** wendet Regeln und State-Aenderungen deterministisch an
- Narrator-LLM formuliert Geschichte aus dem *tatsaechlichen* Ergebnis
- Optionaler Validator prueft Schema + Plausibilitaet

Das ist der Unterschied zwischen "coolem Demo-LLM" und "spielbarer RPG-Plattform".

## Domänenmodell (MVP -> erweiterbar)

### Kernobjekte
- `User`
- `World`
- `WorldLore` (Weltgrundlage, Fraktionen, Orte, Tonalitaet)
- `CharacterTemplate`
- `WorldCharacter` (Instanz eines Charakters in einer Welt)
- `CharacterState`
- `InventoryItemInstance`
- `ItemDefinition`
- `Turn`
- `TurnAction` (analysierte Intention)
- `TurnResolution`
- `StateDelta`
- `JournalEntry`

## Entwicklungsprinzip (spielbar zuerst, dann gezielt ausbauen)
Das Projekt soll nach spielbaren Versionen bewusst weiterentwickelt werden. Das ist ein Vorteil, kein Nachteil.

Empfehlung:
- zuerst ein sauberer, spielbarer Kern
- danach iterative Systemausbauten mit klaren Datenmodellen
- neue Features auf persistente Modelle stützen, nicht nur auf Prompt-Kontext

### Beispiel: NPC-Gedaechtnis (vorbereiten, spaeter ausbauen)
Zielbild:
- `NPCProfile` (Name, Rolle, Stats, Persoenlichkeit)
- `NPCRelationship` (Beziehung zu Charakter/Partei, Verlauf, Tags)
- `NPCMemoryEntry` (wichtige gemeinsame Ereignisse, Zusagen, Konflikte)
- `NPCState` (Ort, Verfuegbarkeit, Ziele)

Wichtig:
- persistente Speicherung in der DB
- kontextuelle Auswahl relevanter Erinnerungen pro Turn
- keine reine Prompt-Longlist ohne Struktur

### Wichtige Beziehungen
- `User 1..n Worlds` (oder Ownership/Permissions spaeter)
- `World 1..n WorldCharacters`
- `CharacterTemplate 1..n WorldCharacters`
- `WorldCharacter 1..1 CharacterState`
- `WorldCharacter 1..n InventoryItemInstance`
- `World 1..n Turns`

## Welt-/Charakter-Erstellung (dein Ablauf erweitert und verbessert)

## Ziel
Der Nutzer beschreibt Welt und Charakter grob, das System erzeugt eine spielbare Grundlage und speichert sie konsistent.

## Ablauf (empfohlen)

### 1) Eingabe durch Nutzer (Creation Prompt)
Nutzer gibt an:
- Weltbeschreibung (Setting, Ton, Genre)
- Charakterbeschreibung (Name/Archetyp/Motivation)
- Optional:
  - Schwierigkeit / Stil (grim, heroic, whimsical)
  - Startregion
  - Sicherheits-/Contentgrenzen

### 2) LLM "World Builder" erzeugt strukturierte Grundlage (nicht nur Text)
OpenRouter-Modell erzeugt **JSON nach Schema**, z. B.:
- Weltname
- Kurzlore
- Startort
- 3-5 relevante Fraktionen/NPCs
- Startkonflikt / Hook
- Tonalitaet / Spielstil
- Startressourcen / Starteritems
- CharacterTemplate-Vorschlag

### 3) Validator + Normalizer (deterministisch)
Backend prueft:
- Pflichtfelder vorhanden
- Längen/Typen ok
- keine leeren Schlüssel
- Inventaritems existieren als Definitionsobjekte oder werden als generische Items angelegt
- Startwerte im erlaubten Bereich

Fehlerfall:
- LLM-Output verwerfen oder gezielt nachgenerieren (nur fehlende Felder).

### 4) Persistenz (atomar)
Transaktion speichert:
- `World`
- `WorldLore`
- `CharacterTemplate`
- `WorldCharacter`
- `CharacterState`
- `InventoryItemInstance[]`
- initiale `JournalEntry`/`Turn(0)`

### 5) LLM "Narrator" erzeugt Einstiegsszene
Eingabe:
- validierte Weltgrundlage
- Startort
- Charakterstatus
- Startkonflikt

Ausgabe:
- **Anfangstext** (narrativ)
- klare situative Orientierung
- 2-4 offensichtliche Handlungsoptionen (nicht hardcoded, aber plausibel)

### 6) Initiales UI-Ergebnis
UI zeigt:
- Einstiegstext
- Charaktersheet (Startstatus)
- Inventar (benutzbar)
- Eingabe fuer ersten Zug

## Turn-Ablauf (verbesserte Version deines Vorschlags)

Dein Vorschlag ist stark, aber ich wuerde ihn strukturell anders schneiden.

### Ziel des Turn-Systems
- konsistente Spielwelt
- testbare Regeln
- gutes Narrativ
- nachvollziehbare State-Aenderungen

## Empfohlener Turn-Flow (pro Zug)

### A) Player Input
Spieler gibt Freitext ein:
- "Ich gehe zur Taverne und frage nach einem Heiler."
- "Ich greife den Banditen mit dem Dolch an."
- "Ich benutze den Heiltrank."

### B) Context Assembly (deterministisch)
Backend sammelt:
- aktueller CharacterState
- Inventar
- aktueller Ort
- relevante NPC/World-Zustaende
- letzte Turns
- Memory/RAG-Kontext (optional, kuratiert)

### C) LLM "Intent Analyst" -> strukturierte Aktionen
LLM erzeugt **Intent JSON** (Schema-validiert), z. B.:
- `MOVE`
- `TALK`
- `ATTACK`
- `USE_ITEM`
- `CAST_SPELL`
- `INSPECT`
- `SKILL_CHECK`

Wichtig:
- Mehrfachaktionen nur begrenzt (z. B. 1 Hauptaktion + 1 Interaktion)
- Unklare Eingaben werden als `CLARIFY` markiert statt halluziniert

### D) Rules Engine / Simulation Core (autoritative Wahrheit)
Deterministische Verarbeitung:
- Vorbedingungen pruefen (ist Item da? Reichweite? Ressourcen?)
- Wurfmechaniken (später D20/SRD-nah)
- Schaden/Heilung/Status
- Inventaraenderungen
- Ortswechsel
- NPC-Reaktionen (regel- oder stategetrieben)

Ergebnis:
- `TurnResolution`
- `StateDelta`
- `SystemEvents[]`

### E) LLM "Narrator" erzaehlt Ergebnis
Input ist **nicht** nur Playertext, sondern die aufgeloeste Wahrheit:
- Aktionen
- Wurfergebnisse
- StateDelta
- relevante Welt-/NPC-Kontexte

Output:
- Narrativtext
- klare Konsequenzen
- neue Situation + Optionen

### F) Optionaler "Post-Turn Extractor" (nur UI-Hilfen, nicht Wahrheit)
Falls noetig:
- Highlights fuer UI (`damage dealt`, `item consumed`, `relationship changed`)

Aber:
- State selbst kommt aus Rules Engine, nicht aus Keyword-Parsing des Narrativs.

### G) Persistenz + Event Log
Speichern:
- Turn Input
- Intent JSON
- Resolution
- StateDelta
- Narrativ
- Kosten/Latency/Providerdaten

### H) UI-Update
UI aktualisiert:
- Narrativ
- Charaktersheet (delta-markiert)
- Inventar (verbrauchte/erhaltene Items)
- Journal/Combat Log

## Warum dein "zweiter Assistant per Schlagworten" nicht ideal ist

### Vorteil (deiner Idee)
- schnell implementierbar
- low effort prototype

### Nachteil (entscheidend)
- "Heilung" kann im Text vorkommen, ohne dass wirklich geheilt wurde
- Synonyme/Flexionen/Erzählstil machen Parsing fragil
- sehr schwer zu testen und zu debuggen

### Empfehlung
- Keywords nur als **Fallback-UX-Hinweis**
- nie als autoritative State-Quelle

## Inventar-System (MVP, aber sinnvoll)

## Mindestanforderungen
Jedes Item ist mindestens:
- `inspect`-bar
- `use`-bar **oder** `equip`-bar **oder** `consume`-bar

### ItemDefinition (statisch)
- `item_def_id`
- `name`
- `category`
- `rarity`
- `description`
- `use_modes[]` (`consume`, `equip`, `activate`, `throw`, `read`, ...)
- `effect_blueprint` (regelbasierte Effekte)
- `stackable`
- `max_stack`

### InventoryItemInstance (pro Charakter/Welt)
- `inventory_item_id`
- `world_character_id`
- `item_def_id`
- `quantity`
- `durability` (optional)
- `charges` (optional)
- `equipped_slot` (optional)
- `custom_state` (z. B. "identified")

## Charaktermodell (weltgebundene Entwicklung)

### CharacterTemplate (wiederverwendbare Vorlage)
- `template_id`
- `creator_user_id`
- `base_name`
- `archetype`
- `origin`
- `default_attributes`
- `starter_preferences`

### WorldCharacter (Instanz)
- `world_character_id`
- `world_id`
- `template_id` (optional)
- `display_name`
- `level`
- `xp`
- `current_status`
- `created_at`

### CharacterState (autoritativer Zustand)
- Attribute
- Ressourcen (HP, Mana/Fokus, Ausdauer)
- Status-Effekte
- Standort
- Beziehungen/Flags (spaeter)

## "Vollwertiges DnD-Erlebnis" – realistische Bewertung

## Was realistisch kurzfristig ist (MVP / Alpha)
- Freitext-Spiel mit konsistentem Zustand
- Inventar nutzbar
- einfache Wuerfe/Checks
- Kampf light (Angriff, Verteidigung, Heilung, Verbrauchsitems)
- Charaktersheet + Journal

## Was mittelfristig ist
- Initiative / Rundenkampf
- Zaubersystem
- Klassen/Fertigkeiten mit Progression
- Gegner-KI und Encounter-Logik
- Quests, Fraktionen, Beziehungen

## Was spaet kommt (echtes "DnD-like depth")
- Regelvollstaendigkeit
- komplexe Taktik
- Balancing ueber viele Klassen/Items
- Kampagnen-/Party-Features

## Lizenz-/Markenhinweis (wichtig)
- "D&D" als Bezeichnung und konkrete Regel-/Content-Elemente koennen rechtlich relevant sein.
- Empfehlung:
  - intern "DnD-like / SRD-inspired"
  - spaeter klare Lizenzstrategie (SRD/OGL/ORC/komplett eigenes Regelset)

## Empfohlene Greenfield-Struktur im Repo (ohne sofort alles umzubauen)

### Aktiv (neu)
- `apps/web_client/`
- `apps/game_api/`
- `packages/shared_schemas/`
- `packages/rules_engine/`
- `packages/ui_components/` (optional spaeter)
- `infra/` (deploy/runbooks/templates)

### Legacy (archiviert, aber versioniert)
- `archive/legacy_backend_server/`
- `archive/legacy_desktop_core/`
- `archive/legacy_training_tools/`

## Archivstrategie (kritisch/pragmatisch)
**Wichtig:** `gitignore` wirkt nicht auf bereits versionierte Dateien.

Das heisst:
- Wenn wir Altcode im Repo archivieren, bleibt er bewusst versioniert.
- `gitignore` ist nur fuer neue lokale Artefakte sinnvoll.

Empfehlung:
1. Erst **Archiv-Mapping** definieren (welcher Ordner wohin).
2. Dann in einem eigenen PR verschieben (nur Moves, keine Logikaenderungen).
3. `gitignore` nur ergaenzen fuer lokale Archiv-Artefakte:
   - `archive_work/`
   - `archive_exports/`
   - `archive_tmp/`

## Phase-0 Greenfield (neuer Startpunkt) – konkrete Reihenfolge

### G0.1 Scope + Regeln fixieren
- Weltgebundene Charakterinstanzen
- Inventar immer nutzbar
- MVP-Aktionssatz
- "Nicht jetzt"-Liste (harte Scope-Grenzen)

### G0.2 Domainmodell + Schemas
- JSON-Schemas / Pydantic-Modelle fuer:
  - World bootstrap
  - Turn intent
  - Turn resolution
  - State delta
  - Character state
  - Inventory item

### G0.3 Rules Engine Kern
- deterministische Aktionen:
  - `MOVE`
  - `INSPECT`
  - `USE_ITEM`
  - `ATTACK`
  - `TALK`

### G0.4 Web UI MVP
- Login
- Welt erstellen
- Spielansicht
- Charaktersheet
- Inventar
- Journal

### G0.5 E2E + Ops Mindeststandard
- bestehende Monitoring-/CI-Erfahrungen uebernehmen
- Smoke fuer World Creation + 3 Turns + Reload

## Konkrete Bewertung deiner Idee (Kurzfazit)

### Sehr gut
- Web-only statt Desktop (passt zur OpenRouter-Abhaengigkeit)
- Weltgebundene Charakterentwicklung
- wiederverwendbare Charakterbasis mit divergenter Entwicklung
- Inventar-Items als nutzbare Spielobjekte

### Muss verbessert werden (und wurde oben korrigiert)
- "Narrator -> Keyword-Parser -> State" ist zu fragil als Kernmechanik

### Gesamtbewertung
- **Produktidee:** stark
- **Architektur-Richtung (Greenfield Web-only):** sehr stark
- **Umsetzungsrisiko:** hoch, aber kontrollierbar bei hartem MVP-Scope
- **Empfehlung:** sofort auf Greenfield umstellen, Legacy einfrieren/archivieren

## Naechste Entscheidungen (von dir)
1. Bevorzugter Frontend-Stack fuer Greenfield:
   - React/Next.js
   - Vue/Nuxt
   - anderes
2. Regelziel fuer MVP:
   - narrative RPG + leichte Regeln
   - D20/SRD-light von Anfang an
3. Single-Character oder Party-Support im MVP?
4. Echtzeit/Streaming-Text oder nur Turn-basiert kompletter Response?
5. Sollen wir das Greenfield-Projekt im bestehenden Repo als `apps/*` starten?
