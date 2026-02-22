# UI- und Spielfluss-Blueprint (V2)

Stand: 22. Februar 2026

## Zweck
Dieses Dokument definiert vor der Closed Beta den minimalen, aber konsistenten UI- und Spielfluss fuer Last-Strawberry auf V2.

Ziel:
- klare Screen-Struktur
- klare Zustandsuebergaenge
- klare API-Vertraege
- sichtbare Gaps (vor allem Inventar/Charaktersheet)

## Kritische Feststellung (ohne Schoenfaerben)
Aktuell ist der technische V2-Backend-Flow funktionsfaehig, aber die Produktoberflaeche ist noch kein sauber definiertes Spielsystem.

Was bereits gut ist:
- Login / Weltliste / Turn-Loop / Verlauf (Basisfluss) sind vorhanden.
- Bridge und V2 sind technisch spielbar.
- Monitoring/CI/Ops sind fuer den Reifegrad stark.

Was vor Closed Beta noch fehlt oder unscharf ist:
- Charaktersheet als konsistente Ansicht mit stabilen Feldern.
- Inventar-UX und Datenvertrag.
- sichtbare Turn-Nebenwirkungen (State-Delta, Events, Wuerfel, Statusaenderungen).
- UI-Fehlerzustaende fuer Timeout/Provider-Failure/Rate-Limits.

Wenn das vor Beta nicht definiert ist, wird Feedback diffus ("fuehlt sich komisch an") statt umsetzbar.

## Produktziel fuer den ersten Beta-Loop
Ein Testspieler soll in unter 2 Minuten:
1. einloggen
2. eine Welt erstellen oder oeffnen
3. 3-5 Zuege spielen
4. Charakterstatus / Inventar / Verlauf verstehen
5. ohne Hilfe weitermachen koennen

## Core Loop (MVP)
1. Login
2. Weltliste laden
3. Welt erstellen oder bestehende Welt oeffnen
4. Spielansicht laden
5. Spieler gibt Befehl ein
6. Turn wird verarbeitet
7. UI zeigt:
   - Narrativ
   - Systemereignisse / Kommandos (kompakt)
   - relevante State-Aenderungen
8. Spieler entscheidet naechsten Zug

## Primare Screens (Phase-10 Pflichtumfang)

### 1) Login
Zweck:
- Zugang herstellen

Pflichtfelder:
- Benutzername
- Passwort

Pflichtzustaende:
- idle
- submitting
- success (redirect)
- invalid credentials (401)
- server unavailable / timeout

API:
- `POST /token` (legacy backend auth fuer aktuelles Frontend/Bridge)
- Optional spaeter: direkter V2-Login fuer V2-only UI-Variante (`POST /v2/auth/login`)

### 2) Weltliste / Lobby
Zweck:
- Welten anzeigen
- neue Welt erstellen

Elemente:
- Liste bestehender Welten (Name, letztes Update optional, Kurzstatus optional)
- CTA "Neue Welt"
- CTA "Fortsetzen"

Pflichtzustaende:
- loading
- empty state (keine Welten)
- error state

API:
- `GET /worlds` (bridge-kompatibel)
- `POST /worlds/create`

### 3) Welterstellung
Zweck:
- schnelle Erzeugung eines spielbaren Einstiegs

Pflichtfelder (MVP):
- Weltname
- Charaktername
- Kurz-Backstory
- Attribute (vereinfachtes Schema)
- Template/Genre (falls vorhanden)

Pflichtzustaende:
- validation error
- creating
- success -> direkt in Spielansicht

API:
- `POST /worlds/create`

### 4) Spielansicht (Hauptscreen)
Zweck:
- eigentlicher Turn-Loop

Layoutbereiche (MVP):
- Narrativ-Panel (groesser Bereich)
- Eingabezeile / Turn-Form
- Verlauf/Log (letzte Eintraege)
- Seitenpanel oder Tabs fuer:
  - Charaktersheet
  - Inventar
  - Welt-/Session-Infos

Pflichtaktionen:
- Turn absenden
- Verlauf nachladen
- Tabs wechseln

Pflichtzustaende:
- turn pending
- timeout (504)
- provider error (502)
- rate limited (429)
- unauthorized/session expired (401)
- partial success (Narrativ da, State unklar)

APIs:
- `POST /command` (bridge)
- `GET /load_game_summary`
- Optional direkt V2:
  - `POST /v2/game/turn`
  - `GET /v2/worlds/{world_id}/turns`

### 5) Charaktersheet (MVP-Ansicht)
Zweck:
- Spieler versteht aktuellen Zustand

Pflichtbereiche:
- Identitaet: Name, Welt, ggf. Rolle/Klasse
- Kernattribute (z. B. Staerke, Geschick, Intelligenz, Charisma)
- Ressourcen (z. B. HP, Ausdauer, Mana/Fokus, falls vorhanden)
- Status-Effekte (Buffs/Debuffs)
- Ort / Situation (aktueller Kontext)

Wichtig:
- Werte muessen aus einem stabilen Datenvertrag kommen.
- Freitext-only ist fuer Beta zu fragil.

Aktueller Gap:
- V2 liefert bereits `extracted_commands`, aber kein klares `character_state`-Objekt fuer die UI.

Empfohlener Zielvertrag (neu/zu ergaenzen):
- `character_state` im Turn-Response oder separater Endpoint:
  - `player_id`
  - `name`
  - `attributes`
  - `resources`
  - `status_effects`
  - `location`
  - `updated_at`

### 6) Inventar (MVP-Ansicht)
Zweck:
- Gegenstaende sichtbar, benutzbar, nachvollziehbar

MVP-Regeln (einfach halten):
- Liste von Items
- Menge/Stack (`quantity`)
- Kategorie (`consumable`, `weapon`, `quest`, ...)
- kurze Beschreibung
- optional `equipped` Flag

Nicht zwingend fuer MVP:
- Gewicht
- Grid-Slots
- komplexe Container

Aktueller Gap:
- Kein klarer V2-Datenvertrag fuer Inventarzustand im UI sichtbar.

Empfohlener Zielvertrag:
- `inventory` als Liste im Player-State:
  - `item_id`
  - `name`
  - `quantity`
  - `category`
  - `description`
  - `equipped`

### 7) Verlauf / Journal / Log
Zweck:
- Kontext halten
- Nachvollziehbarkeit fuer Spieler und Debugging

Darstellung (MVP):
- chronologische Liste
- Eintragstypen visuell getrennt:
  - Spieleraktion
  - Narrativ
  - Systemevent (optional)
  - Fehlerhinweis

API:
- `GET /load_game_summary` (legacy/bridge)
- spaeter feinere Historie ueber V2-Turnliste

## Zustandsmodell (UI State Machine, vereinfacht)

### Session State
- `unauthenticated`
- `authenticating`
- `authenticated`
- `session_expired`
- `auth_error`

### World State
- `worlds_loading`
- `worlds_ready`
- `world_creating`
- `world_opening`
- `world_error`

### Turn State
- `idle`
- `submitting`
- `success`
- `rate_limited`
- `timeout`
- `provider_error`
- `validation_error`
- `unknown_error`

Wichtig:
- UI darf bei Fehlern nicht nur Toast anzeigen, sondern muss naechste Aktion anbieten:
  - Retry
  - Eingabe behalten
  - Zur Lobby
  - Neu anmelden

## Fehler-UX (Pflicht vor Beta)

### 401 / Session abgelaufen
- Nachricht: "Sitzung abgelaufen. Bitte erneut anmelden."
- Aktion:
  - Zur Login-Seite
  - ungesendeten Eingabetext lokal behalten

### 429 / Rate Limit
- Nachricht mit Restzeit-Hinweis (falls bekannt)
- Eingabe bleibt erhalten
- Retry nach kurzer Wartezeit

### 502 / Provider Fehler
- Nachricht: "KI-Dienst aktuell nicht erreichbar."
- Retry-Button
- Verlauf bleibt sichtbar

### 504 / Timeout
- Nachricht: "Zugverarbeitung dauert zu lange."
- Optionen:
  - Erneut senden
  - Eingabe anpassen
  - Status aktualisieren / Verlauf laden

## API-Mapping (Ist vs. Ziel)

### Ist (nutzbar)
- Auth (legacy): `POST /token`
- Weltenliste: `GET /worlds`
- Welterstellung: `POST /worlds/create`
- Turn: `POST /command`
- Verlauf/Kompaktzusammenfassung: `GET /load_game_summary`

### Bereits in V2 vorhanden (direkte Nutzung spaeter/parallel)
- `POST /v2/auth/login`
- `GET /v2/worlds`
- `POST /v2/worlds`
- `POST /v2/game/turn`
- `GET /v2/worlds/{world_id}/turns`

### Fehlend / zu schaerfen fuer gute UI (vor oder waehrend Phase 11)
- expliziter Character-State-Response fuer UI
- expliziter Inventory-State-Response fuer UI
- strukturierte Turn-Deltas:
  - Attribute veraendert?
  - Item erhalten/verbraucht?
  - Ortswechsel?
  - Statuseffekt hinzugefuegt/entfernt?

## Empfohlene Datenvertraege (V2-nahe Zielstruktur)

### TurnResponse (UI-relevant erweitert)
- `narrative`
- `extracted_commands`
- `models`
- `provider`
- `created_at`
- `ui_state` (neu, optionaler Block):
  - `character_state`
  - `inventory`
  - `system_events`
  - `turn_summary`

### CharacterState (neu)
- `player_id: int`
- `name: str`
- `attributes: dict[str, int|float]`
- `resources: dict[str, int|float]`
- `status_effects: list[dict]`
- `location: str`
- `updated_at: str`

### InventoryItem (neu)
- `item_id: str`
- `name: str`
- `quantity: int`
- `category: str`
- `description: str`
- `equipped: bool`

## Umsetzungsreihenfolge fuer Phase 11 (empfohlen)
1. Fehler-UX fuer bestehenden Flow (401/429/502/504)
2. Spielansicht aufraeumen (Narrativ + Eingabe + Verlauf)
3. Charaktersheet (zuerst read-only, ggf. Mock/Placeholder-Daten)
4. Inventar (zuerst read-only, einfache Liste)
5. Strukturierte Turn-Deltas / State-Updates aus Backend nachziehen
6. E2E-Tests fuer kompletten UI-Loop

## Definition of Done fuer "Beta-faehiger Spielfluss"
- Nutzer kann ohne Entwicklerhilfe 3-5 Turns spielen.
- UI zeigt klar:
  - was passiert ist (Narrativ)
  - was sich geaendert hat (State/Inventar/Ort)
  - was als naechstes moeglich ist
- Fehlerzustaende sind benutzbar (kein Dead End).
- E2E-Smoke testet den Hauptfluss.

## Offene Entscheidungen (gezielt frueh klaeren)
1. Inventar-Komplexitaet im MVP:
   - nur Liste oder bereits Equip/Use-Interaktionen?
2. Charaktersheet-Quellen:
   - aus Legacy-Bridge aggregieren oder V2-API erweitern?
3. Turn-Kommandos in UI:
   - fuer Spieler sichtbar (Debug/Transparenz) oder nur intern?
4. Mobile-first oder Desktop-first fuer Beta?
5. Ein-Welt-Fokus oder Multi-Welt-Wechsel im aktiven Spiel?
