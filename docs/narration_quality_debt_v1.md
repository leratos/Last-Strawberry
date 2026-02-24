# Narration Quality Debt (Greenfield)

Stand: 23. Februar 2026

## Zweck

Diese Datei dokumentiert eine bewusst aufgeschobene Qualitaetsbaustelle im Greenfield-Game-API-Stack:

- Die aktuelle KI-Narration ist funktional korrekt, wirkt aber oft reporthaft/auflistend.
- Die Optimierung wird bewusst spaeter vertieft, um waehrend der Entwicklungs- und Testphase OpenRouter-Tokens zu sparen.
- Das Ziel ist, die Baustelle nicht zu vergessen und spaetere Refactors vorzubereiten.

Die Regeln hier sind verbindlich fuer spaetere Narration-Optimierung.

---

## Narration Quality Debt

### Problemdefinition

Aktuelle Erzaehltexte (vor allem im `hybrid`-Modus mit OpenRouter-Narration) neigen zu:

- Aufzaehlungsstil statt Szenenfluss
- statischer Status-Bericht statt lebendiger Erzaehlung
- Wiederholung von Ort/Inventar/Status, auch wenn es nicht narrativ relevant ist
- zu direkter Uebernahme von System-Event-Reihenfolgen
- gelegentlicher Sprachmischung (DE/EN, z. B. `slightly`)

### Beispiel (reporthaft / unerwuenscht)

> Du hast dich Kael genaehert und ein Gespraech mit ihm gefuehrt. Anschliessend hast du eine Vorratskiste genauer untersucht und sie geoeffnet. Deine Beziehung zu Kael hat sich slightly verbessert. Du befindest dich immer noch auf dem Marktplatz, genauer gesagt im Brunnenplatz. Dein Inventar enthaelt einen Starter-Heiltrank.

### Warum das problematisch ist

- Schlechter Lesefluss / wenig Atmosphaere
- Spieler nimmt das System als Event-Logger wahr statt als Geschichte
- Wiederholte Statusnennung erhoeht Textlaenge ohne Mehrwert
- Immersion sinkt trotz korrekter Regelauflosung

### Status

- **Technisch korrekt**, aber **narrativ qualitativ unzureichend**
- Kein Blocker fuer Entwicklungsphase / interne Tests
- Wird fuer erste ernsthafte Playtests / Alpha-Playability relevant

---

## Zielbild (gewuenschte Narration)

### Kernziel

Narration soll:

- szenisch und zusammenhaengend wirken
- Systemereignisse korrekt abbilden (keine erfundenen Zustandsaenderungen)
- nur relevante Statusinfos nennen
- mit einer sinnvollen Anschlussfrage oder Handlungsoeffnung enden

### Zielcharakteristik (MVP)

- 3-6 Saetze pro Turn (Richtwert)
- 1 kurzer Absatz (standard)
- klare Kausalitaet (Aktion -> Reaktion -> Konsequenz)
- Fokus auf das, was sich fuer den Spieler erzaehlerisch geaendert hat

### Beispiel (zielnaeher)

> Kael hebt den Blick, als du an den Brunnenplatz herantrittst. Das kurze Gespraech verlaeuft ueberraschend ruhig, und sein Ton wirkt dir gegenueber etwas offener als zuvor. Waehrend er weiterspricht, faellt dir neben dem Brunnen eine Vorratskiste auf; du untersuchst sie genauer und bekommst sie schliesslich auf. Im Inneren liegt ein Verbandspaket zwischen altem Verpackungsmaterial. Was tust du als Naechstes?

Wichtig:

- gleiche Faktenbasis wie oben
- weniger Statusreport
- mehr Szene und Uebergang

---

## Regeln (verbindlich fuer spaetere Optimierung)

### Inhaltliche Regeln

- Narration darf **keine autoritativen Zustandsaenderungen erfinden**.
- Narration darf nur Zustandsaenderungen beschreiben, die durch Rules Engine / Persistenz belegt sind.
- Nicht jeder Delta-Wert muss im Text erscheinen.
- Nur narrativ relevante Fakten sollen genannt werden.

### Stilregeln

- Deutsch-only (keine Sprachmischung mit Englisch)
- Keine Eventlistenform / kein Abarbeiten von Eventcodes
- Keine redundante Wiederholung von Ort/Inventar/HP/Fokus in jedem Turn
- Keine Formulierungen wie:
  - "anschliessend ... danach ... danach ..." in Kettenform
  - "du befindest dich immer noch ..." ohne narrativen Zweck

### Priorisierung im Turn-Text (heuristisch)

Bei knappen Texten priorisieren:

1. direkte Aktion des Spielers
2. sichtbare Reaktion der Welt/NPCs
3. relevante Konsequenz (Fund, Beziehungsaenderung, Gefahr)
4. optional ein Statusdetail, wenn es fuer die naechste Entscheidung wichtig ist
5. Anschlussfrage / Handlungsoeffnung

### Transparenzregeln

- Wenn ein Turn nur teilweise verarbeitet wurde (`partial_multiclause_parse`), darf Narration den nicht ausgefuehrten Teil **nicht** implizit als erledigt darstellen.
- `clarify_required` bleibt System-/UX-Signal; Narration darf den offenen Punkt erwaehnen, aber nicht raten.

---

## Spaetere Architektur (geplantes Grundprinzip)

### Problem des aktuellen Ansatzes

Aktuell wird Narration zu stark aus rohen Events/State-Details gespeist. Das foerdert reporthafte Texte.

### Geplantes Grundprinzip (spaeterer Ausbau)

Nicht:

- `Rules Engine -> rohe system_events -> Narrator`

Sondern:

- `Rules Engine/Persistenz -> Story Beat Composer -> Narrator`

### Zielarchitektur (leichtgewichtig)

1. **Rules Engine / Persistenz** (autoritative Wahrheit)
   - liefert Events, Deltas, Kontext, NPC-Reaktionen

2. **Story Beat Composer** (deterministisch, lokal)
   - verdichtet rohe Events zu narrativen Bausteinen:
     - Bewegung
     - Interaktion
     - Reaktion
     - Fund/Konsequenz
     - offener Hook
   - filtert irrelevante Details
   - markiert kritische Fakten, die genannt werden muessen

3. **Narrator (LLM oder Preview-Fallback)**
   - formuliert nur die Beats als Szene
   - keine freie Regelentscheidung

### Warum dieses Prinzip wichtig ist

- bessere Erzaehlqualitaet bei gleicher Regeltreue
- weniger Prompt-Chaos
- spaeter einfacher anpassbar (Stilwechsel ohne Regelumbau)
- Token-effizienter, weil nur verdichtete Beats statt kompletter Eventlisten gesendet werden

---

## Ausloeser fuer Umsetzung (wann aktiv angehen)

Die aktive Narration-Optimierung sollte priorisiert werden, wenn mindestens einer der Punkte eintritt:

- erste laengere interne Playtests (30-60 Minuten) starten
- wiederholtes Spielerfeedback zu "berichtshaft / trocken / unverbunden"
- OpenRouter-Tokens wieder gezielt fuer Qualitaetsarbeit eingeplant sind
- Vertical Slice der ersten Welt inhaltlich steht und Systemfeatures langsamer wachsen

---

## Offene Fragen fuer spaeter

- Soll Narration je nach Weltstil/Preset unterschiedliche Erzaehlprofile nutzen (z. B. gritty, mystery, heroic)?
- Wie streng sollen Turn-Laengen begrenzt werden (harte Satz-/Zeichenlimits)?
- Welche Statusinfos muessen bei Gefahr/Kampf zwingend genannt werden?
- Wie stark sollen NPC-Reaktionsstile (freundlich/vorsichtig/aggressiv) in die Narration einfliessen?
