# Beitrag zu Last-Strawberry: KI-gesteuertes Text-Abenteuer

Vielen Dank für dein Interesse an Last-Strawberry!  
Wir freuen uns über jede Art von Unterstützung – sei es durch Bugreports, Feature-Ideen, Dokumentation oder Code!

## Wie du beitragen kannst

### 1. Fehlermeldungen/Bugreports
- Prüfe, ob der Fehler schon im [Issues-Bereich](https://github.com/DeinName/Last-Strawberry/issues) gemeldet wurde.
- Erstelle ein neues Issue, falls nicht. Gib dabei möglichst viele Details an:
  - Beschreibung des Problems
  - Schritte zum Reproduzieren
  - Erwartetes und aktuelles Verhalten
  - Screenshots oder Logs (falls vorhanden)

### 2. Feature-Vorschläge
- Öffne ein Issue mit dem Label `feature request`.
- Beschreibe die Funktion so konkret wie möglich. Wie könnte sie das Projekt verbessern?

### 3. Code-Beiträge (Pull Requests)
- Forke das Repository und arbeite in einem eigenen Branch (`feature/<dein_feature>` oder `fix/<dein_fix>`).
- Schreibe sauberen, gut kommentierten Code.
- Halte dich an die [PEP8-Standards](https://pep8.org/) (Python) und die im Projekt vorgegebene Struktur.
- Führe möglichst vor dem PR die Testsuite lokal aus (`pytest`, falls eingerichtet).
- Rebase/merge regelmäßig mit dem aktuellen `main`.
- Schreibe im PR eine kurze Beschreibung der Änderung.
- Beziehe dich auf das zugehörige Issue (`Fixes #123`).

### 4. Dokumentation
- Verbesserungen und Ergänzungen der Dokumentation sind immer willkommen!
- Rechtschreibkorrekturen, neue Tutorials, bessere Readmes? Einfach PR eröffnen.

## Code of Conduct
Wir wünschen uns einen respektvollen, offenen und hilfsbereiten Umgangston.  
Bitte beachte unseren [Code of Conduct](./CODE_OF_CONDUCT.md).

## Lokale Entwicklung

**Abhängigkeiten:**
- Python 3.10+
- Siehe `requirements.txt`
- Für Cloud-Funktionen: Zugangsdaten separat anfragen

**Schnellstart:**
```bash
git clone https://github.com/DeinName/Last-Strawberry.git
cd Last-Strawberry
python -m venv .venv
pip install -r requirements.txt
# Starte dann das Backend z. B. mit
uvicorn backend_server.main:app --reload --port 8001
```
## Kontakt & Fragen
- Bei Fragen einfach Issue öffnen oder direkt über [Signz-Vision.de](https://signz-vision.de) melden.
- Für Alpha-Zugang: Melde dich per Nachricht auf GitHub oder des Forum von Signz-Vision

