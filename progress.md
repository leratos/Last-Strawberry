Original prompt: Weiter mit G4 (Context Assembly + NPC Memory Retrieval + Web-Anbindung Start)
- G4 gestartet: Backend Context Assembly + NPC Memory Retrieval zuerst, danach Web-Anbindung.
- Hinweis: develop-web-game Skill nur teilweise angewandt; Playwright-Loop wird verschoben bis echte interaktive Game-Loop/Deterministic Hooks vorhanden sind.
- G4 Backend: /v1/worlds/{world_id}/context mit Retrieval-Sortierung fuer NPC-Memory implementiert.
- G4 Frontend: Bootstrap + Turn-Loop + Context-Rendering an game_api angebunden (MVP).
- G5: Intent-Parser auf Wortgrenzen umgestellt; false positive schaue -> haue behoben und getestet.
- G5: Turn-Verlauf zeigt jetzt Event-Severity + Message; Welt-ID kann direkt geladen werden.
- G5: MariaDB-Kompatibilitaetscheck-Script fuer Migrations-SQL als Basis hinzugefuegt.
