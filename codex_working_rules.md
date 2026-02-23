# Codex Working Rules

Stand: 23. Februar 2026

## Zweck

Diese Datei definiert projektweite Arbeitsregeln fuer Codex, damit Entscheidungen, Codequalitaet und Spiellogik ueber laengere Iterationen konsistent bleiben.

## Start jeder Arbeitsphase

- Lies `progress.md` vor Beginn jeder Arbeitsphase mit Code-, Doku- oder Testaenderungen.
- Lies mindestens:
  - `Original prompt`
  - die letzten relevanten Eintraege
  - offene TODOs/Hinweise

## Progress-Dokumentation

- Lege vor der Umsetzung einen kurzen Draft-Eintrag in `progress.md` an, wenn du Code, Tests oder Doku aenderst.
- Reine Rueckfragen / Konzeptfragen ohne Aenderung muessen keinen Draft-Eintrag erzeugen.
- Dokumentiere nach jedem groesseren Arbeitsblock:
  - was umgesetzt wurde
  - was getestet wurde
  - offene Punkte / Risiken

## Git-Workflow

- Erstelle fuer jeden vereinbarten Arbeitsblock (Phase) einen neuen Branch.
- Branch-Namensschema:
  - `gxx-gyy-kurzbeschreibung` (z. B. `g40-g49-discovery-refinement`)
  - oder `gxx-hotfix-kurzbeschreibung` fuer gezielte Fixes
- Branch-Namen:
  - nur lowercase
  - ASCII (keine Umlaute/Sonderzeichen)
  - Worte mit Bindestrichen trennen
- Committe am Ende jeder Phase alle zugehoerigen Aenderungen (mindestens ein sauberer End-Commit).
- Bei groesseren Bloecken sind Zwischen-Commits erlaubt, wenn sie logisch getrennt sind.

## Qualitaetsregeln

- Weise aktiv auf folgende Punkte hin, wenn sie relevant sind:
  - fehlende Tests
  - Sicherheitsrisiken
  - Logikluecken
  - technische Schulden
- Nenne dabei nach Moeglichkeit:
  - Schweregrad / Auswirkung
  - konkrete Verbesserung
  - pragmatische Priorisierung

## Unklarheiten / Annahmen

- Wenn etwas unklar **und entscheidungsrelevant** ist: frage nach.
- Wenn etwas unklar, aber nicht blockierend ist:
  - triff eine plausible Annahme
  - benenne die Annahme explizit
  - dokumentiere sie kurz (Antwort oder `progress.md`)

## Sprachweise

- logisch
- kritisch
- analytisch

## Guardrails (Spielsystem)

- Der Spieler erzeugt keine Weltfakten, NPCs oder Objekte durch Freitext.
- Neue NPCs/Objekte erscheinen nur durch:
  - bestehenden Weltzustand
  - Narrator-/Systemeinfuehrung
  - Discovery (`INSPECT` / Umsehen / Untersuchen)
  - explizite Systemaktionen (z. B. Beschwoerung)
- LLM/Narration darf den Spielzustand nicht autoritativ festlegen.
- Die Rules Engine / Persistenz ist die autoritative Quelle fuer Zustandsaenderungen.
- Bei unklarer Zielreferenz gilt:
  - `clarify_required` statt impliziter Neuerstellung von NPCs/Objekten

## Test- und Build-Regel

- Nach jeder Phase:
  - relevante Teiltests ausfuehren (zielgerichtet)
  - danach mindestens ein zusammenfassender Regressionstest (sofern praktikabel)
- Frontend-Aenderungen:
  - `npm.cmd --prefix apps/web_client run build`
- Backend-/Regel-Aenderungen:
  - passende `pytest`-Teilbereiche und bei groesseren Bloecken gesamter Regressionstest

## Scope-Regel

- Bevorzuge kleine, testbare Schritte.
- Vermeide stille semantische Aenderungen ueber mehrere Systeme hinweg ohne Tests.
- Wenn ein Problem eigentlich ein Designproblem ist (nicht nur Parser/UI), benenne das klar.
