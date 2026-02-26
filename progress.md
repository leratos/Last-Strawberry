Original prompt: Weiter mit G4 (Context Assembly + NPC Memory Retrieval + Web-Anbindung Start)
- G4 gestartet: Backend Context Assembly + NPC Memory Retrieval zuerst, danach Web-Anbindung.
- Hinweis: develop-web-game Skill nur teilweise angewandt; Playwright-Loop wird verschoben bis echte interaktive Game-Loop/Deterministic Hooks vorhanden sind.
- G4 Backend: /v1/worlds/{world_id}/context mit Retrieval-Sortierung fuer NPC-Memory implementiert.
- G4 Frontend: Bootstrap + Turn-Loop + Context-Rendering an game_api angebunden (MVP).
- G5: Intent-Parser auf Wortgrenzen umgestellt; false positive schaue -> haue behoben und getestet.
- G5: Turn-Verlauf zeigt jetzt Event-Severity + Message; Welt-ID kann direkt geladen werden.
- G5: MariaDB-Kompatibilitaetscheck-Script fuer Migrations-SQL als Basis hinzugefuegt.
- G6: run_turn nutzt jetzt Context-Assembly intern und kann Context vor/nach Turn im Response liefern.
- G6: NPC-Memory-Dedupe fuer identische Summaries (same NPC/WorldCharacter) hinzugefuegt.
- G6: Web-Client nutzt context_after_turn direkt (weniger Roundtrip) und zeigt Analyse-Kontext-Hinweise.
- G7: LLM-Runtime-Schicht (preview/openrouter) eingefuehrt; OpenRouter-Pfad mit Preview-Fallback vorbereitet.
- G7: run_turn/analyze/narrate nutzen LLM-Runtime; Health zeigt aktive Provider/Fallback-Konfiguration.
- G7: Intent-Analyzer bekommt bekannte NPC/Locations aus Context; Targets werden dadurch besser normalisiert.
- G8: OpenRouter-JSON-Hardening eingebaut (Codefence-Parsing, JSON-Objekt-Extraktion aus Prosa, Repair-Retry).
- G8: OpenRouter-Requests setzen provider.require_parameters=true; verhindert Provider-Routing ohne JSON-Parameter-Support.
- G8: Default-Modellpaar angepasst (Intent=Qwen 80B, Narration=Llama 70B) und per ENV steuerbar.
- G8: Tests erweitert fuer fenced JSON, Repair-Retry und Narration-Fallback bei invalidem OpenRouter-Output.
- G9: GameContext liefert jetzt target_catalog (NPC/Item/Location-Referenzen mit stabilen IDs) fuer UI und LLM-Analyse.
- G9: Preview-Intent-Analyzer mapped bekannte NPC/Locations auf IDs (target_ref / destination_id) und behaelt Anzeigenamen in parameters.
- G9: Rules + Persistence verarbeiten NPC-IDs fuer Beziehung/NPC-Memory updates, ohne bestehende Namenspfade zu brechen.
- G9: Web-UI zeigt Referenz-IDs fuer Inventar/NPCs und Referenz-Zaehlung/-Liste im Context an.
- G10: `TurnRunRequest` unterstuetzt `actions_override` fuer strukturierte, ID-basierte UI-Turns (Freitext bleibt parallel erhalten).
- G10: `run_turn` ueberspringt Analyzer komplett bei `actions_override` (weniger Kosten/Fehlerquellen).
- G10: Web-MVP hat jetzt einen klickbaren Struktur-Aktions-Composer (Move/Talk/Attack/Use Item) auf Basis des `target_catalog`.
- G10: OpenRouter-Intent-Normalisierung mapped namenbasierte LLM-Outputs auf bekannte target IDs (NPC/Location/Item), falls vorhanden.
- G11: Web-MVP hat jetzt eine Multi-Action-Queue fuer strukturierte Aktionen (mehrere `actions_override` in einem Turn).
- G11: Quick Actions in Panels (NPC Talk / Location Move / Item Use) triggern strukturierte ID-basierte Aktionen direkt oder legen sie in die Queue.
- G11: OpenRouter-Intent bevorzugt `response_format=json_schema` fuer Intent (Fallback auf `json_object` bleibt aktiv).
- G11: Route-Test fuer Multi-Action-Override-Queue und Runtime-Test fuer `json_schema`-Call abgesichert.
- G12: Zonenmodell eingefuehrt (CharacterState.scene_zone_*, NPCProfile.scene_zone_* / location_name) mit Distanzband im target_catalog.
- G12: Rules Engine `TALK` auto-approacht bei `far` (Zone-Wechsel + Event `auto_approach_for_talk`) statt stiller Fehlinterpretation.
- G12: Preview-Analyzer erkennt zusaetzlich `bewege mich zu ...` und fuellt Ziel-Metadaten (Zone/Distanz) fuer TALK/ATTACK/MOVE.
- G12: UI zeigt Spieler-Zone + NPC Ort/Zone/Distanz und hat Quick Action `Gehe+Rede` (TALK mit Auto-Approach).
- G13: Distanzmodell verfeinert: `same location + other zone` wird nun `near` statt `far`; target_catalog berechnet Distanzband konsistenter aus Ort+Zone.
- G13: Rules Engine `ATTACK` respektiert Distanz-Metadaten (Auto-Move/Auto-Approach bei `near|far` mit Zielposition, Warnung `attack_out_of_range` ohne Positionsdaten).
- G13: Preview-Analyzer ueberspringt falschen Orts-MOVE bei Formulierungen wie `bewege mich zu Mira und frage ...` (bekannter NPC + TALK -> TALK Auto-Approach).
- G13: Web-MVP Queue-UX verbessert (Eintrag hoch/runter/entfernen).
- G13: Neues lokales API-Script `apps/game_api/scripts/check_greenfield_turn_loop.py` fuer schnellen Turn-Loop-Sanity-Check (TALK via `actions_override`).
- G14: `ATTACK` unterstuetzt jetzt `attack_mode` (`melee`/`ranged`) mit unterschiedlichem Distanzverhalten; Nahkampf auto-approacht, Fernkampf greift ohne Annahern an.
- G14: Rules Engine vermeidet redundantes `auto_approach_for_attack`, wenn der Spieler bereits in der Zielzone steht.
- G14: Preview-Analyzer erkennt Fernkampf-Verben (`schiesse`, `feuere`, `werfe`) und setzt `parameters.attack_mode = ranged`.
- G14: Web-MVP Queue-Makros via LocalStorage (speichern/laden/loeschen) sowie Attack-Mode-Auswahl im Struktur-Composer.
- G14: Quickcheck-Script erweitert auf Queue-Turn (`TALK + ATTACK`), Standing-Pruefung und Distanz-Validierung (`adjacent` nach Turn).
- G15: Neuer Action-Typ `RETREAT` (zonenbasierter Rueckzug/Abstand gewinnen) in Shared Schemas, Parser, Rules Engine und Web-UI (Quick Action + Composer).
- G15: Freitext erkennt jetzt `entferne mich von ...` / `gehe weg von ...` als `RETREAT` statt `clarify_required`.
- G15: Rules Engine setzt bei `RETREAT` die Spieler-Zone auf Rueckzugszone und macht Distanzwechsel `adjacent -> near` im Zonenmodell sichtbar.
- G15: Quickcheck-Script erweitert um RETREAT-Turn und prueft `retreat_success` sowie Distanz `near` nach Rueckzug.
- G16: Gestuftes Retreat umgesetzt: `adjacent -> near -> far`, bei `far` bleibt `retreat_not_needed`.
- G16: Context-Distanzregeln verstehen jetzt explizite Spieler-Distanzzonen (`zone-distance-near`, `zone-distance-far`) und geben fuer NPCs in gleicher Location entsprechend `near`/`far` zurueck.
- G16: API-Route-Test erweitert auf zwei aufeinanderfolgende RETREATs (zweiter Rueckzug fuehrt zu `far`).
- G16: Quickcheck-Script prueft jetzt nach zweitem RETREAT explizit `distance_after_retreat_second == far`.
- G17: Neuer Action-Typ `APPROACH` als symmetrische Gegenaktion zu `RETREAT` (Parser, Rules, UI, Override-/LLM-Ref-Normalisierung).
- G17: `APPROACH` ist gestuft: `far -> near -> adjacent`, `adjacent` liefert `approach_not_needed`.
- G17: Web-UI hat Quick Action `Annaehern` bei NPCs; Distanzaktionen sind kontextsensitiv (z. B. `Annaehern` aus bei `adjacent`).
- G17: Quickcheck-Script erweitert auf zwei APPROACHs nach `far` und prueft `distance_after_approach_second == adjacent`.
- G17.1: Parser-Hotfix fuer umgangssprachliche Annaeherungs-Phrasen (`naeher/n�her mich ...`) inkl. Unicode-NFC-Normalisierung und Regressionstests.
- G18: Web-UI zeigt klarere Distanzhinweise im NPC-Panel und im Struktur-Composer (adjacent/near/far/unreachable mit Handlungs-Hinweis).
- G18: `APPROACH`/`RETREAT` werden im UI kontextsensitiv deaktiviert (z. B. `Annaehern` bei `adjacent`, `Abstand` bei `far/unreachable`) statt unn�tige `*_not_needed` Turns zu erzeugen.
- G19: Parser erweitert fuer weitere Distanzphrasen (`halte Abstand zu ...`, `halte mich von ... fern`, `trete einen Schritt naeher an ...`).
- G19: Erste optionale NPC-Reaktions-Events auf Distanzaktionen (standing-basiert via `target_standing` in `APPROACH`/`RETREAT`-Actions).
- G19: Distanz-Quick-Buttons zeigen sichtbare Statuslabels (`Annaehern (direkt dran)`, `Abstand (max)`) statt nur disabled.
- G20: NPC-Reaktionslogik unterscheidet jetzt `vorsichtig/aggressiv/freundlich` (standing-basiert, optional role-gestuetzt via `target_role`).
- G20: Preview-Parser gibt `target_role` aus `known_npc_refs` an Actions weiter (TALK/ATTACK/APPROACH/RETREAT).
- G20: Turn-Verlauf zeigt Event-Gruppenbadges (Bewegung/Reaktion/Kampf/Dialog/System) fuer bessere Lesbarkeit.
- G21: Rollenfokus erweitert/abgesichert fuer Heiler/Krieger/Tank mit rollenspezifischen Reaktionsmeldungen bei Distanzaktionen.
- G21: `target_catalog.npcs` traegt jetzt optional `role`; Struktur-Composer uebernimmt Rolleninfos fuer Distanz-/Talk-/Attack-Actions.
- G21: NPC-Panel zeigt Badges fuer Distanz und abgeleiteten Reaktionsstil (`freundlich/vorsichtig/aggressiv`).
- G22: Rollenspezifische Reaktionsmeldungen erweitert fuer Haendler, Magier und Beschwoerer (deutsch + englische Alias-Rollen).
- G22: Preview-Narration hebt Reaktions-Events explizit mit `Reaktion:` hervor statt sie nur implizit in den ersten Eventtexten zu verstecken.
- G22: Narration-Preview-Test hinzugefuegt (`apps/game_api/tests/test_narration_preview.py`).
- G23: IP-sicheres Urban-Occult-Preset (Binder/Champion) eingefuehrt; Bootstrap-Preview kann daraus Startwelt/NPCs/Faktionen erzeugen.
- G23: Rollen-Inferenz fuer freie NPCs erweitert (u.a. Beschwoerer/Magier/Haendler), sodass NPC-Memory seltener `unknown` bleibt.
- G24/G25: Rollen-Anreden werden auf vorhandene NPCs gemappt (`der Beschwoerer` -> Kael bei Eindeutigkeit); bei Mehrdeutigkeit jetzt `clarify_required` statt neuer Fake-NPC.
- G25: Deskriptive/generische Zielreferenzen (`zweiter Beschwoerer`, generisches `npc`) erzeugen keine `npc-auto-*`-Muell-NPCs mehr.
- G26: Discovery-System fuer NPC-Sichtbarkeit pro Welt+Charakter eingefuehrt (`npc_discoveries`). Verborgene NPCs tauchen erst nach `INSPECT`/`schau mich um` im Context/Targeting auf.
- G26: Dev/Test-NPC-Spawn kann jetzt `revealed_to_player=false` setzen, um Discovery lokal zu testen.
- G26: Parser erkennt Kurzform `schau` als `INSPECT`; unerkannte NPC-Namen liefern vor Reveal `clarify_required`.
- G27: Discovery auf sichtbare Interaktionspunkte (Scene Points / POIs) erweitert (`scene_point_discoveries`) mit Reveal durch `INSPECT` im aktuellen Ort.
- G27: Context/Target-Catalog liefert jetzt `scene_points`; UI zeigt sichtbare Interaktionspunkte + `Inspect`-Quick-Action.
- G30-G39: Discovery-/Umweltinteraktionen ausgebaut (`OPEN`, `SEARCH`, `TAKE`), UI-Quick-Actions/Badges verbessert, Quickcheck erweitert, Rollen/Fraktionen bis Interaktion verborgen.
- G40: Parser markiert `INSPECT` jetzt als `broad`/`focused` (`inspect_mode`) und erkennt Formulierungen wie `schaue mir X genauer an`.
- G41: Rules Engine unterscheidet `inspect_broad_success` von fokussierter Untersuchung (`inspect_focus_success`).
- G42: Wiederholtes breites Umsehen ohne neue Funde erzeugt `discovery_nothing_new`.
- G43: Gezielte, aber unsichtbare/unbekannte Untersuchung (`ich untersuche ...`) liefert `CLARIFY` statt faelschlich breitem Inspect.
- G44: `durchsuche die Umgebung` wird als breiter `INSPECT` interpretiert (nicht als Container-SEARCH ohne Ziel).
- G45: `/context` liefert strukturierte Hidden-Counts (`hidden_npc_count`, `hidden_scene_point_count`) fuer UI/Tools.
- G46: UI fuer Interaktionspunkte hat Filter/Sortierung (Alle/Unklar/Container/Objekte/Punkte; Name/Detail/Zone).
- G47: Container-/Objekt-Aktionen werden im UI vor Detail-Inspect sichtbar, aber deaktiviert mit klaren Hinweisen (`... erst Inspect`).
- G48: `OPEN`/`SEARCH`/`TAKE` geben discovery-aware Clarify-Messages (`schau dich zuerst um`) bei unsichtbaren Zielen.
- G49: Quickcheck prueft Hidden-Counts vor Discovery und `discovery_nothing_new` bei wiederholtem broad Inspect.
- G27: Rules Engine akzeptiert `INSPECT` auf `scene_point`-Targets (`inspect_focus_success`) statt Item-Fehler.
- G27: Retrieval-Notes unterscheiden jetzt unbekannte Praesenzen (NPCs) und unerkundete Interaktionspunkte am Ort.
- TODO (naechster Schritt): G28 Discovery fuer Objekte/Container/NPC-Rollenwissen verfeinern (z.B. Name sichtbar, Rolle erst nach genauerem Untersuchen/Gespraech).
- G29: Scene-Point-Discovery hat jetzt `detail_level` + `discovery_state` (broad `schau` zeigt Namen, fokussiertes `Inspect` hebt Details an).
- G29: Container unter den Umweltzielen haben persistente Zustandslogik (geoeffnet/durchsucht) und koennen einmalig deterministischen Loot vergeben.
- G29: UI zeigt bei Umweltzielen Details nur nach fokussiertem Inspect; Containerstatus wird sichtbar (z.B. geoeffnet/durchsucht).
- G30: Freitext-`INSPECT` kann sichtbare Umweltziele gezielt aufloesen (z. B. `Ich untersuche die Vorratskiste`) statt nur broad inspect.
- G30: `run_turn`/Preview-Analyse geben sichtbare `scene_points` an Analyzer/LLM-Runtime weiter; Route- und Parser-Tests sichern focused inspect per Freitext.
- G31: Neue strukturierte Aktionen `OPEN` und `SEARCH` eingefuehrt (Schema, Parser, Rules, Persistenz, UI-Override-Normalisierung).
- G31: Container-Semantik getrennt: `OPEN` oeffnet ohne Loot, `SEARCH` durchsucht/lootet; Route-Test deckt Sequenz `open -> search` ab.
- G32: UI-Quick-Actions fuer Container erweitert (`Oeffnen`, `Durchsuchen`) mit Status-Disable bei bereits geoeffnetem Container.
- G33: Preview-Narration hebt Container-/Loot-Ergebnisse expliziter hervor (`Fund:` / `Behaeltnis:`), statt sie nur implizit im Eventtext zu mischen.
- G34: Discovery-UI fuer Interaktionspunkte verbessert (Counter `sichtbar/detail verifiziert`, Discovery-Badges pro Punkt).
- G35: NPC-Rollenwissen wird im Context maskiert (`unknown`) bis echte Interaktion/Memory vorliegt; blo�es Entdecken reicht nicht mehr fuer Rollenerkennung.
- G36: Fraktionswissen folgt demselben Prinzip wie Rollenwissen (erst nach Interaktion sichtbar); UI zeigt Fraktion nur wenn bekannt.
- G37: Neuer Action-Typ `TAKE` fuer `scene_object`-Ziele (Freitext + strukturierte Aktion), inklusive persistenter Objektzustand `taken` und einmaligem Loot-MVP.
- G37: UI-Quick-Action `Nehmen` bei detailverifizierten Szene-Objekten, mit Statusanzeige `verfuegbar/mitgenommen`.
- G38: Greenfield-Quickcheck erweitert um Discovery (`schau mich um`), Container `OPEN/SEARCH` und `TAKE` auf Szene-Objekte.
- G39: Dokumentation/Progress auf G30-G39 aktualisiert; Abschluss-Regressionslauf (Repo-Tests + Frontend-Build) als Batch-Check.

- G50-G59 Draft (gestartet): Fokus auf Clarify-UX/Kandidatenaufloesung, Discovery-Finetuning und Interaktionsfluss fuer Umweltziele; Umsetzung in kleinen Schritten mit Teiltests + Build + Regressionstest.
- G50-G59 abgeschlossen: Clarify-UX und Discovery-Hinweise strukturiert erweitert (Parser -> Rules -> API -> UI).
- G50: `TurnSystemEvent` hat jetzt `metadata`; G54: `GameContextResponse` liefert `discovery_counts` (hidden NPCs/Scene-Points).
- G51/G52: CLARIFY-Events uebernehmen strukturierte Hinweise aus Action-Parametern (`reason`, `suggested_action`, `candidates_json`); Parser erzeugt Kandidaten fuer mehrdeutige Rollen-Anreden und unbekannte/verborgene Talk-Ziele.
- G53/G55: Web-UI rendert `clarify_required` mit klickbaren Kandidaten-Buttons und `Umsehen`-Shortcut; Story-Panel zeigt strukturierte Discovery-Zaehler + Quick-Umsehen.
- G56/G57: Szenenpunkt-Referenzaufloesung ist jetzt mehrdeutigkeitsbewusst (mehrere Kisten/Objekte -> `clarify_required` mit Kandidaten statt erster Zufallstreffer). Analyzer bekommt Scene-Point-Aliasse aus dem Context.
- G58: Tests erweitert fuer Clarify-Metadaten und mehrdeutige Scene-Targets (Parser/Rules/Routes).
- G59: Greenfield-Quickcheck prueft jetzt `discovery_counts.hidden_scene_point_count` vor Discovery und `discovery_nothing_new` beim zweiten broad inspect.
- G50-G59 Tests/Builds: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q`, `pytest packages/rules_engine/tests/test_rules_engine.py -q`, `pytest apps/game_api/tests/test_preview_routes.py -q`, `pytest apps/game_api/tests/test_greenfield_turn_loop_check.py -q`, `pytest apps/game_api/tests -q`, `npm.cmd --prefix apps/web_client run build`, final Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 289 passed.
- Offener Punkt (technische Schuld): `candidates_json` wird aktuell als JSON-String in CLARIFY-Parametern/Events transportiert; spaeter auf echtes strukturiertes `metadata.candidates[]` im Schema anheben.

- G60-G69 Draft (gestartet): Fokus auf strukturierte Clarify-Payloads (Schema/Events/UI) und deskriptive Zielaufloesung (ordinale Referenzen wie 'zweiter Beschwoerer' / 'zweite Kiste').
- G60-G69 abgeschlossen: `clarify_required` traegt jetzt zusaetzlich strukturierte Payloads im Event-Schema (`event.clarify`) mit Kandidatenliste; bestehendes `metadata`/`candidates_json` bleibt als Rueckwaertskompatibilitaet erhalten.
- G60/G61: Shared Schema (`TurnSystemEvent`) erweitert um `ClarifyPayload` / `ClarifyCandidate`; Rules Engine baut strukturierte Clarify-Details aus CLARIFY-Action-Parametern (inkl. Kandidaten-Parsing aus `candidates_json`).
- G62/G63: Web-UI liest Clarify-Kandidaten bevorzugt aus `event.clarify.candidates` und faellt auf `metadata.candidates_json` zurueck; Frontend-API-Typen erweitert.
- G64/G65: Parser kann ordinale Rollen- und Szenenreferenzen aufloesen (`zweiter Beschwoerer`, `zweite Kiste`) bei sichtbaren Kandidaten; deterministische Sortierung nach Name fuer stabile Auswahl.
- G66: Ordinale Referenzen ausserhalb des sichtbaren Kandidatenbereichs fallen auf `clarify_required` zurueck (z. B. `zweiter Beschwoerer`, wenn nur ein Beschwoerer sichtbar ist) statt still auf den einzigen Treffer zu mappen.
- G67: `/context`-Discovery-Counts erweitert um `visible_scene_point_count` und `detail_verified_scene_point_count` fuer UI/Tooling.
- G68: Route-Test fuer ordinale Rollen-Anrede an Runtime-Sichtbarkeitsregeln angepasst (G35 maskiert Rollen bis Interaktion; Test primt daher zuerst Interaktion mit den Kandidaten).
- G69: Abschluss-Regressionslauf und Frontend-Build erfolgreich.
- G60-G69 Tests/Builds: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q` (26 passed), `pytest apps/game_api/tests/test_preview_routes.py -q` (30 passed), `pytest packages/rules_engine/tests/test_rules_engine.py -q` (19 passed), `pytest apps/game_api/tests -q` (74 passed), `npm.cmd --prefix apps/web_client run build`, final Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 292 passed.
- Offener Punkt (technische Schuld): CLARIFY-Kandidaten werden weiterhin doppelt transportiert (`event.clarify.candidates` + `metadata.candidates_json`); nach UI-Migration kann das String-Feld entfernt werden.

- G70-G79 Draft (gestartet): Fokus auf Clarify-Kandidaten-UX (Gruppierung/Status), bessere R�ckfrageaufl�sung im UI und Discovery-/Zielaufl�sung-Finetuning mit Teiltests + Build + Regressionstest.
- G70-G79 abgeschlossen: Clarify-Kandidaten tragen jetzt mehr Kontextdaten (Rolle/Fraktion/Ort-Zone/Distanz) von Parser -> Rules -> Event-Schema -> UI; die Rueckfrage-Buttons koennen dadurch sinnvollere Tooltips/Infos zeigen.
- G70/G71: `ClarifyCandidate` im Shared Schema erweitert (`faction`, `location_name`, `scene_zone_name`, `distance_band_to_player`); Rules Engine uebernimmt diese Felder in `event.clarify.candidates`.
- G72/G73: Parser encodiert erweiterte Kandidateninfos fuer NPC- und Scene-Target-CLARIFYs (`_npc_visible_candidates`, Rollen-Anreden, Scene-Targets).
- G74: Web-UI rendert `clarify_required` jetzt gruppiert nach Kandidatentyp (NPCs/Container/Objekte/Interaktionspunkte) statt flacher Button-Liste.
- G75: Clarify-UI zeigt zusaetzliche Kontextinfos/Tooltips pro Kandidat (Rolle, Typ, Ort/Zone, Distanz, Fraktion wenn bekannt).
- G76: `buildClarifyCandidateAction()` uebernimmt jetzt Kandidaten-Metadaten (`target_role`, Distanz/Ort) in strukturierte Quick-Actions.
- G77: Parser kann jetzt auch `letzte/letzter ...`-Referenzen auf sichtbare Kandidaten aufloesen (NPC-Rollenanreden und Szenenziele wie `letzte Kiste`).
- G78: Szenenziel-Normalisierung entfernt nun auch `letzte*`-Ordinalwoerter vor dem Matching; vermeidet falsches `unknown_open_target` bei `letzte Kiste`.
- G79: Route-/Parsertests fuer `letzte ...`-Referenzen und strukturierte Clarify-Payloads erweitert; Frontend-CSS fuer Clarify-Gruppenlayout hinzugefuegt.
- G70-G79 Tests/Builds: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q` (28 passed), `pytest apps/game_api/tests/test_preview_routes.py -q` (30 passed), `pytest packages/rules_engine/tests/test_rules_engine.py -q` (19 passed), `pytest apps/game_api/tests -q` (76 passed), `npm.cmd --prefix apps/web_client run build`, final Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 294 passed.
- Annahme (dokumentiert): In G24-Mehrdeutigkeits-Route-Tests kann der Clarify-Reason je nach G35-Rollenmaskierung `ambiguous_npc_role_title` oder `unknown_or_ambiguous_npc_talk_target` sein; beide sind fachlich korrekt, solange kein Fake-NPC entsteht.

- G80-G89 Draft (gestartet): Fokus auf dediziertes Clarify-Panel im UI, bessere Kandidatenwiederverwendung/Suggested-Actions und kleine Discovery-/Resolver-Verfeinerungen mit Teiltests + Build + Regressionstest.
- G80-G89 abgeschlossen: Dediziertes Clarify-Panel im UI eingefuehrt (Rueckfrage aktiv), inklusive Kandidaten-Gruppierung, Kontextinfos und Quick-Resolution (`Ausfuehren` / `In Struktur-Aktion`) fuer relevante Ziele.
- G80/G81: Clarify-Kandidaten-Schema und Event-Mapping erweitert (Fraktion, Ort, Zone, Distanz) von Parser -> Rules -> `event.clarify.candidates`; UI/API-Typen lesen diese Felder strukturiert.
- G82/G83: Frontend rendert ein separates Clarify-Panel mit Reason/Suggested-Action-Badges, `Umsehen`-Shortcut bei `inspect_broad` und gruppierten Kandidatenlisten (NPCs/Container/Objekte/Interaktionspunkte).
- G84: Clarify-Kandidaten koennen in den Struktur-Composer uebernommen werden (derzeit TALK) inkl. Ziel-Metadaten (`target_role`, Ort/Zone/Distanz).
- G85/G86: Resolver erweitert um `der/die andere ...` fuer Rollen- und Szenenziele; Szenenziel-Normalisierung entfernt jetzt auch `andere*`-Woerter vor dem Matching.
- G87: Baseline-Regression in Context-Build/Main behoben (`hidden_*` nicht mehr als Top-Level-Felder auf `GameContextResponse`, nur noch ueber `discovery_counts`).
- G88: Route-Tests auf neue `discovery_counts`-Payloadform migriert (G26-Assertions fuer Hidden-NPC/Scene-Point-Counts).
- G89: Abschluss-Regressionslauf und Frontend-Build erfolgreich.
- G80-G89 Tests/Builds: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q` (36 passed), `pytest apps/game_api/tests/test_preview_routes.py -q` (31 passed), `pytest apps/game_api/tests -q` (85 passed), `npm.cmd --prefix apps/web_client run build`, final Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 304 passed.
- Offener Punkt (technische Schuld): CLARIFY-Kandidaten werden weiterhin doppelt transportiert (`event.clarify.candidates` + `metadata.candidates_json`); nach UI-Migration String-Feld entfernen.
- G90-G99 Draft (gestartet): Groesserer KI-Aktivierungsschritt (OpenRouter dort nutzen, wo es stabil Mehrwert bringt) mit deterministischem Regelkern als Autoritaet. Fokus: LLM-gestuetzter World-Bootstrap/Narration, Intent optional/hybrid mit robustem Fallback, plus Tests fuer Fallback-/Konfigurationspfade.
- G90-G99 abgeschlossen: Kontrollierte KI-Aktivierung (OpenRouter dort, wo sinnvoll) eingefuehrt, ohne den deterministischen Regelkern zu lockern.
- G90: Neuer `hybrid`-LLM-Modus in `LlmRuntime`/Settings. Policy: `bootstrap` + `narration` via OpenRouter, `intent` weiter Preview (robust) mit bestehendem Fallback-Konzept.
- G91: `LlmRuntimeStatus`/`/health` erweitert um `bootstrap_provider` und `openrouter_bootstrap_model` (sichtbar fuer Ops/Debugging).
- G92/G93: LLM-gestuetztes World-Bootstrap-Enrichment eingefuehrt (`enrich_world_bootstrap_preview`) mit OpenRouter-JSON-Schema und sicherem Merge nur auf Text-/Listenfelder (World-Name, Hook, Fraktionen, Threads, Initial-Narrativ, Orientierung).
- G94: `main.py` verdrahtet Bootstrap-Preview und World-Create auf `_build_bootstrap_result_with_llm()` (Preview-Basis + optionales LLM-Enrichment).
- G95: Fallback-Verhalten fuer Bootstrap analog zu Narration/Intent (bei Fehlern oder fehlendem Key -> Preview, sofern Fallback aktiv).
- G96/G97: Runtime-Tests fuer Hybrid-Status, Bootstrap-Fallback und Bootstrap-OpenRouter-Merge hinzugefuegt (`apps/game_api/tests/test_llm_runtime.py`).
- G98: Route-Health-Test erweitert (Bootstrap-/Intent-/Narration-Provider-Felder vorhanden).
- G99: Abschluss-Regressionslauf und Frontend-Build erfolgreich.
- G90-G99 Tests/Builds: `pytest apps/game_api/tests/test_llm_runtime.py -q` (10 passed), `pytest apps/game_api/tests/test_preview_routes.py -q` (31 passed), `npm.cmd --prefix apps/web_client run build`, final Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 307 passed.
- Empfehlung (Betrieb): Fuer erste echte KI-Nutzung `LS_GREENFIELD_LLM_MODE=hybrid` + `LS_GREENFIELD_LLM_FALLBACK_TO_PREVIEW=true`, damit Intent stabil bleibt und Bootstrap/Narration bereits KI-Mehrwert liefern.

- G100-G109 abgeschlossen: Preview-Analyzer verarbeitet Mehrfachsatz-Eingaben mit Sequenzmarkern (`dann`/`danach`/`anschliessend`) jetzt als Teilabschnitte und aggregiert mehrere Aktionen pro TurnIntent.
- G100/G101: Clause-Splitting eingefuehrt (`_split_preview_action_clauses`) und Single-Clause-Analyse in internen Helper ausgelagert (`_analyze_player_input_preview_single_clause`).
- G102: Mehrteilige Eingaben mit teilweise unverstandenen Teilabschnitten fuehren jetzt zu zusaetzlichem `CLARIFY`-Warnhinweis (`reason=partial_multiclause_parse`) statt stillem Teilverlust.
- G103: Warnhinweis enthaelt `suggested_action=use_structured_queue` als klaren UX-Hinweis fuer komplexe Eingaben.
- G104/G105: Parser-Tests fuer Mehrfachsatz (`... dann untersuche ...`) und Partial-Parse-Warnung hinzugefuegt.
- G106: Route-Integrationstest hinzugefuegt: `run_turn` fuehrt bei `... rede ..., dann untersuche ...` sowohl `talk_success` als auch `inspect_focus_success` im selben Turn aus.
- G107-G109: Abschluss-Regression erfolgreich; bestehende Deterministik/Rules bleiben unveraendert, nur Intent-Vorverarbeitung verbessert.
- G100-G109 Tests: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q` (38 passed), `pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g100_run_turn_multiclause_dann_executes_talk_and_inspect -q` (1 passed), `pytest apps/game_api/tests -q` (91 passed), finale Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 310 passed.
- Hinweis: Splitter ist aktuell bewusst konservativ (explizite Sequenzmarker); `und`-Ketten ohne Marker bleiben ein separater Ausbau-Schritt (um Fehlsplits bei z.B. `rede ... und frage ...` zu vermeiden).

- G110-G149 Draft (gestartet): Groesserer Ausbau fuer spielbare Sessions: (1) Mehrfachsatz-Intent weiter verbessern (selektives und-Splitting + weniger Teilverlust) und (2) KI-Transparenz per Provider/Fallback-Trace in API/UI, damit Hybrid/OpenRouter-Laufzeit nachvollziehbar bleibt.


- G110-G149 abgeschlossen: Fokusblock auf (A) selektives Mehrfachsatz-Parsing mit sicherem und-Splitting und (B) Provider-/Fallback-Transparenz pro Turn im API-Response + UI.
- G110-G119: TurnRunResponse um provider_trace erweitert (intent/
arration mit provider_policy, provider_used, model, allback_used, allback_reason).
- G120-G129: LlmRuntime um nalyze_intent_with_trace() und 
arrate_with_trace() erweitert; bestehende Methoden bleiben kompatible Wrapper. 
un_turn nutzt jetzt Traces und markiert UI-Overrides explizit als ui_structured_override.
- G130-G139: Web-UI zeigt Provider-Trace im Story-Panel (intent: preview, 
arration: openrouter, inkl. Fallback-Hinweis) und setzt/cleart Trace beim Weltwechsel/Bootstrap konsistent.
- G140-G149: Preview-Analyzer erweitert um konservatives und-Splitting fuer sichere Aktionswechsel (z.B. 
ede ... und untersuche ...), ohne Talk-Ketten wie 
ede ... und frage ... aggressiv zu splitten. Mehrteilige Verluste bleiben weiter via partial_multiclause_parse sichtbar.
- Neue/angepasste Tests: Runtime-Trace-Unit-Tests (	est_llm_runtime.py), Route-Trace-Response-Assertion (	est_preview_routes.py G2-Flow), Route-Test fuer 
ede ... und untersuche ..., Parser-Tests fuer safe-und-Split + No-Split-Talk-Chain.
- G110-G149 Tests/Builds: pytest apps/game_api/tests/test_intent_analysis_preview.py -q (40 passed), pytest apps/game_api/tests/test_llm_runtime.py -q (11 passed), gezielte Route-Tests fuer G2/G110 (2 passed), 
pm.cmd --prefix apps/web_client run build, finale Regression pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q -> 314 passed.
- Technische Schuld (weiter offen): Clarify-Kandidaten werden weiterhin doppelt transportiert (event.clarify.candidates + metadata.candidates_json); nach kompletter UI-Migration Legacy-String entfernen. Provider-Trace existiert derzeit pro Turn, Bootstrap-Provider-Trace nur indirekt ueber /health sichtbar.


- G150-G199 Draft (gestartet): (1) Selektiver Intent-LLM-Einsatz nur bei komplexen Mehrfachsaetzen im Hybrid-Modus (Feature-Flag + Tracing), (2) Bootstrap-Provider-Trace pro /v1/worlds/bootstrap/preview und /v1/worlds/bootstrap sichtbar machen (API + UI/Debug).

- G150-G199 abgeschlossen: (1) Selektiver Intent-LLM-Einsatz im Hybrid-Modus fuer komplexe Inputs (Feature-Flag), (2) Bootstrap-Provider-Trace pro Preview/Create im API-Response + UI sichtbar gemacht.
- G150-G159: Settings erweitert um LS_GREENFIELD_HYBRID_INTENT_LLM_FOR_COMPLEX_INPUTS (hybrid_intent_llm_for_complex_inputs, default false) und /health um Flag-Status erweitert.
- G160-G169: LlmRuntime erweitert: enrich_world_bootstrap_preview_with_trace() (Bootstrap + Trace) und selektive Intent-Provider-Policy im Hybrid-Modus (openrouter nur bei komplexen Inputs; sonst preview). Komplexitaetsheuristik: Sequenzmarker (dann/danach/anschliessend), Semikolon oder mehrere Aktionsverben mit und.
- G170-G179: main.py verdrahtet Bootstrap-Trace in /v1/worlds/bootstrap/preview und /v1/worlds/bootstrap (optionales Feld ootstrap_trace), 
un_turn bleibt mit provider_trace aus G110-G149 kompatibel.
- G180-G189: Shared-Schemas erweitert (WorldBootstrapResult.bootstrap_trace, WorldSessionResponse.bootstrap_trace, Reuse LlmCapabilityTrace), Frontend-API-Typen angepasst.
- G190-G199: Web-UI zeigt Bootstrap-Trace im Story-Panel nach Welterstellung und beherrscht Provider-Trace + Bootstrap-Trace gleichzeitig. Bootstrap-Trace wird bei Weltwechsel/Neustart zurueckgesetzt.
- Tests erweitert: Runtime-Unit-Tests fuer Hybrid-Complex-Intent-Flag (komplex -> OpenRouter, einfach -> Preview), Route-Tests fuer ootstrap_trace in Preview/Create und Health-Flag sowie bestehende Provider-Trace-Assertions im Turn-Flow.
- G150-G199 Tests/Builds: pytest apps/game_api/tests/test_llm_runtime.py -q (13 passed), gezielte Route-Tests fuer Health/Bootstrap/Create/G2 (4 passed), 
pm.cmd --prefix apps/web_client run build, finale Regression pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q -> 316 passed.
- Hinweis/Tradeoff: Selektiver Intent-LLM im Hybrid-Modus ist bewusst nur per Feature-Flag aktiv (default aus), damit Kosten/Fehlinterpretationsrisiko kontrolliert bleiben. provider_trace/ootstrap_trace macht den tatsaechlich genutzten Provider sichtbar.


- G200-G249 Draft (gestartet): Pronomen-/Referenzaufloesung in Mehrfachsatzketten (z.B. 'untersuche die Kiste, dann oeffne sie') plus Folgeverbesserungen fuer natuerliche Turn-Sequenzen. Fokus auf deterministische Preview-Intent-Analyse, Tests und stabile Fallbacks.

- G200-G249 abgeschlossen (Teilfokus mit hohem Nutzwert): Pronomen-/Referenzaufloesung in Mehrfachsatzketten im deterministischen Preview-Analyzer eingefuehrt (Clause-Carryover fuer letzte NPC- und Umweltziele).
- G200: Mehrfachsatz-Aggregator (`analyze_player_input_preview`) fuehrt jetzt einen Clause-Chain-Context (letztes NPC-Ziel / letztes Umweltziel) ueber Teilklauseln hinweg.
- G201: Sichere Pronomenauflosung vor der Single-Clause-Analyse fuer Folgeklauseln (`ihn/ihm/sie/ihr/es`) je nach Aktionsfamilie:
  - NPC-bezogen fuer TALK/ATTACK/APPROACH/RETREAT
  - Umweltbezogen fuer INSPECT/OPEN/SEARCH/TAKE
- G202: Konservativer Scope beibehalten (nur innerhalb derselben Mehrfachsatzkette, nur bei zuvor erfolgreich aufgeloesten Zielen; bei Unsicherheit weiterhin `clarify_required` statt stiller Fehlzuordnung).
- G203: Parser-Regressions-Tests hinzugefuegt:
  - `untersuche ... dann oeffne sie` -> `INSPECT + OPEN`
  - `rede mit Kael, dann rede mit ihm` -> zwei TALK-Aktionen auf denselben NPC
- G204: Route-Integrationstest hinzugefuegt: `rede mit Kael und untersuche die Vorratskiste, dann oeffne sie` fuehrt `talk_success`, `inspect_focus_success`, `open_focus_success` und `container_opened` im selben Turn aus (ohne `clarify_required`).
- G205-G249: Abschluss-Regression und Frontend-Build erfolgreich; Fokusblock bewusst nicht auf globale Coreference ausgedehnt (keine freie Pronomenmagie ueber Turns/Discovery-Grenzen hinweg).
- G200-G249 Tests/Builds: `pytest apps/game_api/tests/test_intent_analysis_preview.py -q` (42 passed), `pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g200_run_turn_multiclause_pronoun_carryover_opens_inspected_container -q` (1 passed), `pytest apps/game_api/tests -q` (100 passed), `npm.cmd --prefix apps/web_client run build`, finale Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 319 passed.
- Offener Punkt (naechste sinnvolle Ausbaustufe): Pronomenauflosung ist aktuell turn-lokal und klauselbasiert; echte Coreference ueber komplexere Bezuege (`diese`, `jene`, Ellipsen, implizite Ziele) bleibt bewusst offen und sollte nur mit klaren Guardrails erweitert werden.

- G250-G259 Draft (gestartet): Narration Quality Debt dokumentieren (reporthafte/auflistende Erzaehlweise im Hybrid-Modus), Zielbild + Regeln + spaetere Architektur festhalten; bewusst ohne aktive Narration-Optimierung (Token sparen waehrend Entwicklungs-/Testphase).
- G250-G259 abgeschlossen: Narration-Qualitaetsbaustelle verbindlich dokumentiert (kein aktiver Code-Ausbau, bewusst token-/zeitschonend waehrend Entwicklungs-/Testphase).
- Neue Doku: `docs/narration_quality_debt_v1.md` mit vier Blo�cken: `Narration Quality Debt`, `Zielbild`, `Regeln`, `spaetere Architektur`.
- Dokumentiert: Problem (reporthafte/auflistende Narration, Sprachmischung, schwacher Szenenfluss), Beispieltext, Zielbild mit szenischer/kausal verknuepfter Erzaehlweise und klarer Anschlussfrage.
- Verbindliche Regeln festgelegt: DE-only, keine Eventlistenform, keine erfundenen Zustandsaenderungen, relevante Fakten priorisieren, `clarify_required`/Teilparse nicht narrativ "wegraeten".
- Spaeteres Grundprinzip festgelegt (ohne Implementierung): `Rules/Persistenz -> Story Beat Composer -> Narrator` statt direkte rohe Eventlisten-Narration.
- Greenfield-Roadmap ergaenzt um aktiven Tech-Debt-/Quality-Debt-Punkt mit Verweis auf `docs/narration_quality_debt_v1.md`.
- Tests/Build: keine Ausfuehrung erforderlich (nur Doku-Aenderungen).

- G260-G299 Draft (gestartet): Vertical-Slice-Fokus fuer erste wirklich bespielbare Welt: Questflags/Quest-Status (MVP), Dialogzustands-Basis pro NPC und authored World-Pack-Grundlage (Urban Occult), inkl. UI-Sichtbarkeit und Regressionstests.
- G260-G299 abgeschlossen (Vertical-Slice-Foundation): Questflags/Quest-Status (MVP) + Dialogzustands-Basis pro NPC fuer Urban-Occult-Starterwelt integriert, inkl. Persistenz, Context-API und UI-Sichtbarkeit.
- Shared Schemas erweitert: `ls_shared_schemas.quests` (WorldQuestState, QuestObjectiveState); `GameContextResponse.quests` hinzugefuegt und exportiert.
- Neue Quest-Authoring/Progression-Logik (`apps/game_api/app/services/quest_authoring.py`): Urban-Occult-Starterquest (Kael sprechen -> Vorratskiste untersuchen -> Mira Bericht), questbezogene System-Events (`quest_objective_updated`, `quest_completed`) und leichte NPC-Dialoghinweise (`dialog_state`, `dialog_hint`).
- Persistenz erweitert (`apps/game_api/app/persistence.py`): Migration `007_g260_world_quest_states.sql`, Quest-Seeding beim World-Bootstrap, Quest-Status-Updates in `save_turn_run`, `list_world_quest_states()` fuer Context-Aufbau.
- Context-Aufbau erweitert (`main.py`, `context_assembly.py`): Quests werden in `/v1/worlds/{id}/context` ausgeliefert; NPC-Dialoghinweise aus Queststatus werden in `target_catalog.npcs[].discovery_state` eingetragen.
- Web-UI erweitert (`apps/web_client/src/api.ts`, `apps/web_client/src/App.tsx`): Questlog (MVP) im Charaktersheet, Quest-Zaehler im Story-Panel, NPC-Panel zeigt questbezogene Dialoghinweise.
- Neuer Route-Test `test_g260_urban_occult_starter_quest_progresses_via_kael_crate_mira`: validiert Quest-Seeding, Objective-Fortschritt ueber Kael/Kiste, Mira-Report-Stufe und Questabschluss-Ereignis.
- Tests/Builds: `pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g260_urban_occult_starter_quest_progresses_via_kael_crate_mira -q` (1 passed), `pytest apps/game_api/tests/test_preview_routes.py -q` (35 passed), `npm.cmd --prefix apps/web_client run build`, finale Regression `pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 320 passed.
- Offene Punkte / technische Schuld: Quest-Events werden aktuell in `save_turn_run()` nach Narration angehaengt (im selben Turn nicht narrativ reflektiert). Spaeter fuer bessere Story-Qualitaet: Quest-Fortschritt vor Narration in einen Story-Beat-Composer einspeisen (`Rules/Persistenz -> Story Beats -> Narrator`).

- G350-G399 Draft (gestartet): Urban-Occult Vertical-Slice-Ausbau mit vertieften Dialogzustaenden (stage-/flag-abhaengige Hinweise/Optionen) und Folgequest nach Mira-Bericht, inkl. Persistenz-/Context-/UI-Sichtbarkeit und Tests.

- G350-G399 abgeschlossen: Dialogzustaende fuer Urban-Occult-Vertical-Slice vertieft und Folgequest nach Mira-Bericht integriert (Quest-Unlock + Stage-gebundene Kael/Mira-Hinweise), inkl. UI-Sichtbarkeit und Route-Regressionstest.
- quest_authoring.py erweitert: neue Folgequest quest-urban-occult-resonance-followup (Runenspuren untersuchen -> versiegelten Instrumentenkoffer oeffnen -> mit Kael abgleichen). Quest wird beim Abschluss der Starterquest freigeschaltet (quest_unlocked).
- Folgequest-Progression implementiert (_advance_urban_occult_followup_quest): aktualisiert Objectives/Stufen (	race_residue, crosscheck_with_kael, completed) und emittiert bestehende Quest-Events (quest_objective_updated, quest_completed).
- Dialogzustaende erweitert (uild_npc_dialog_hints_for_context): stage-/questabhaengige dialog_state, dialog_hint und dialog_topics_hint fuer Kael/Mira (Starterquest + Folgequest).
- Web-UI (pps/web_client/src/App.tsx) zeigt jetzt zusaetzlich Dialogzustand und Themen im NPC-Panel aus discovery_state, sodass die neuen Dialogzustands-Hinweise im Playtest sichtbar sind.
- Neuer Route-Test 	est_g350_followup_quest_unlocks_and_kael_crosscheck_stage_updates_dialog_hints: validiert Quest-Unlock nach Mira-Bericht, Folgequest-Aktivierung, Kael-Dialoghint im Followup, Progress via Runenspuren+Koffer und Stage-Wechsel zu crosscheck_with_kael mit aktualisiertem Kael-Hinweis.
- Tests/Builds: pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g350_followup_quest_unlocks_and_kael_crosscheck_stage_updates_dialog_hints -q (1 passed), pytest apps/game_api/tests/test_preview_routes.py -q (36 passed), 
pm.cmd --prefix apps/web_client run build, finale Regression pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q -> 321 passed.
- Offene Punkte / technische Schuld: Dialogzustaende liefern aktuell nur Hinweise/Themen (kein echtes Topic-Auswahl-/Antwortsystem, keine authored Dialogknoten). Fuer 'erste Welt richtig bespielbar' als naechstes: authored Dialogantworten/Topic-Auswirkungen + Quest-Flag-Transitions statt reiner Objective-Progression.


- G350 Hotfix Draft (gestartet): ImportError beim Start von game_api beheben (derive_story_flags_from_quests fehlt in quest_authoring.py, wird fuer main-Kompatibilitaet wiederhergestellt).

- G350 Hotfix abgeschlossen: Fehlende Funktion derive_story_flags_from_quests in quest_authoring.py wiederhergestellt (MVP-Flag-Ableitung fuer Starter-/Followup-Quest), damit persistence.py-Import auf main wieder kompatibel ist. Tests: gezielter Route-Test G260 (1 passed) + Modulimport pps.game_api.app.main OK.

- G400-G449 Draft (gestartet): Authored Dialog-Topics/Antworten (MVP) fuer Urban Occult Vertical Slice einbauen, inkl. Quest-/Story-Flag-Auswirkungen, API-/Context-/UI-Sichtbarkeit und Tests.

- G400-G449 abgeschlossen: Authored Dialog-Topics/Antworten (MVP) fuer Urban Occult eingebaut. NPC-Context liefert dialog_topics_json, Web-UI rendert Topic-Buttons im NPC-Panel (TALK mit 	opic_id). Persistenz/Quest-Pfad wendet Topic-Effekte auf Story-Flags und Quest-Hinweise an (z.B. kael_ritual_overview, mira_crosscheck_findings, kael_sabotage_hypothesis) und emittiert dialog_topic_applied + dialog_topic_response Events.
- Tests/Builds: pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g400_authored_dialog_topic_sets_flag_and_updates_hint -q (1 passed), pytest apps/game_api/tests/test_preview_routes.py -q (37 passed), pytest apps/game_api/tests -q (103 passed), npm.cmd --prefix apps/web_client run build, finale Regression pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q -> 322 passed.
- Technische Schuld: Topics sind noch lineare Button-Ausloeser (kein echter Dialogbaum/Antwortauswahl mit Verzweigung). Topic-Effekte laufen derzeit im Persistenz-/Quest-Pfad nach Rules-Resolution; spaeter fuer bessere Narration/Struktur in einen dedizierten Story/Dialog-Composer vor Narration ziehen.

- G450-G499 Draft (gestartet): Authored Dialog-Topics erweitern um standing-/flag-abhaengige Antwortvarianten und staerkere Quest-/Story-Flag-Transitions. Struktur fuer spaetere Faehigkeitspruefungen (Attribute/Wuerfel) in Topic-Metadaten vorbereiten, ohne Dice-Engine jetzt zu aktivieren.

- G450-G499 abgeschlossen: Authored Dialog-Topics um standing-/flag-abhaengige Varianten erweitert und Quest-/Story-Flag-Transitions vertieft. Topics liefern jetzt vorbereitende Skill-Check-Metadaten (z. B. uture_check_attribute, uture_check_dc) fuer spaetere Wuerfel-/Attributpruefungen, ohne Dice-Engine bereits zu aktivieren.
- Backend: quest_authoring.py erweitert (Topic-Metadaten, 
equires_flag-Filter, variantenspezifische dialog_topic_response je nach 	arget_standing, staerkere Story-Flags wie 
itual_sabotage_suspected, scene_control_protocol_active, Hint-Updates in Starter-/Followup-Quest).
- UI: Topic-Metadaten aus dialog_topics_json geparsed und im NPC-Panel sichtbar gemacht (Probe-spaeter-Hinweis mit Attribut/DC), Topic-Buttons unveraendert direkt klickbar.
- Tests/Builds: pytest G450-Route-Test (1 passed), pytest apps/game_api/tests/test_preview_routes.py -q (38 passed), pytest apps/game_api/tests -q (104 passed), npm.cmd --prefix apps/web_client run build, finale Regression pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q -> 323 passed.
- Technische Schuld: Topic-Effekte laufen weiter im Persistenz-/Quest-Pfad nach Rules-Resolution; fuer spaetere narrative Qualitaet und echte Dialogsysteme (inkl. Skill-Checks) in einen dedizierten Dialog/Story-Composer vor Narration ziehen. Skill-Check-Metadaten sind aktuell nur Hinweise, noch keine mechanische Pruefung.

- G500-G549 Draft (gestartet): Skillcheck-MVP fuer Dialogtopics aktivieren (Attribute + d20 + DC) auf Basis der bereits vorhandenen Topic-Metadaten, mit deterministischem Wurf (teststabil), System-Event-Ausgabe und ersten Flag-/Antwortvarianten ohne komplette Dice-Engine/Rules-Refactor.

- G500-G549 abgeschlossen (Skillcheck-MVP fuer Dialogtopics): Topics mit vorhandenen `future_check_*`-Metadaten loesen jetzt echte Attributspruefungen aus (deterministischer W20 + Attributsmodifikator + DC) und emittieren `dialog_topic_skill_check` im Turn-Verlauf.
- Backend (`quest_authoring.py`): deterministische Skillcheck-Logik fuer Dialogtopics eingebaut (`_dialog_topic_skillcheck_spec`, d20-Roll aus stabiler Hash-Seed, Modifier aus Attributen), Story-Flags fuer Skillcheck-Nutzung/Ergebnis (`dialog_skillcheck_used_*`, `dialog_skillcheck_passed_*`, `dialog_skillcheck_total_*`) und erste Antwort-/Flag-Varianten je Erfolg/Misserfolg (z. B. Kael-Sabotage-Konfrontation, Mira-Lead/Scene-Control).
- Tests: bestehender G450-Route-Test erweitert, um Skillcheck-Event/Metadaten und Skillcheck-Resultatsflags zu validieren (ohne auf ein festes Wurfergebnis zu pinnen).
- UI: Topic-Metadaten-Hinweistext von `Probe spaeter` auf `Probe` umgestellt (Skillcheck jetzt aktiv statt nur vorbereitet).
- Tests/Builds: `pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g450_dialog_topic_variant_and_followup_flag_transition -q` (1 passed), `pytest apps/game_api/tests -q` (104 passed), `npm.cmd --prefix apps/web_client run build`.
- Offene Punkte / technische Schuld: Skillchecks laufen aktuell im Dialogtopic-Effektpfad nach Rules-Resolution (nicht im allgemeinen Regelkern) und sind deterministisch fuer Teststabilitaet. Spaeter fuer echtes Pen&Paper-Gefuehl: konfigurierbare Wurfquelle (seeded/random), UI-Wurftransparenz und breitere Integration in Dialog/Kampf/Discovery.

- G550-G559 Draft (gestartet): Skillcheck-Eventtext klarer machen (Attributswert + Modifikator explizit anzeigen), damit `charisma=10` und `Mod +0` im UI nicht als Rechenfehler missverstanden werden.

- G550-G559 abgeschlossen: Skillcheck-Eventtext (`dialog_topic_skill_check`) erweitert um Attributswert + Modifikator im Klartext, z. B. `Probe ... (charisma 10 / Mod +0)`, ohne Skillcheck-Logik zu aendern.
- Tests: `pytest apps/game_api/tests/test_preview_routes.py::TestGameApiPreviewRoutes::test_g450_dialog_topic_variant_and_followup_flag_transition -q` -> 1 passed.

- G560-G600 Draft (gestartet): Skillcheck-Event im Turn-Verlauf kompakter rendern (Badges fuer W20, Mod, DC, Total, Erfolg/Misserfolg) auf Basis vorhandener `dialog_topic_skill_check`-Metadaten, ohne Backend-API zu aendern.

- G560-G600 abgeschlossen: UI rendert `dialog_topic_skill_check` im Turn-Verlauf jetzt kompakt mit Badges (Erfolg/Misserfolg, W20, Mod, DC, Total) und kurzer Probe-Zeile statt nur langem Eventtext; Fallback auf normalen Eventtext bleibt bei fehlenden Metadaten aktiv.
- Tests/Builds: `npm.cmd --prefix apps/web_client run build` -> OK.

- G610-G659 Draft (gestartet): Projektordner-Aufraeumen / Archiv-Welle 1. Verschiebe klar inaktive Legacy-Pfade nach `archive/`, lasse aktive Bridge-/CI-Pfade (`backend_v2`, `backend_server`, `server_tools`, `class_folder`) vorerst stehen. Aktualisiere minimale Doku/Codecov-Ignore-Pfade.

- G610-G659 abgeschlossen (Archiv-Welle 1): Inaktive Legacy-Pfade nach `archive/` verschoben (`ai_service`, `cronjob`, `tools`, `lora_adapter`, `web_frontend`, `game_main.py`, `test_suite_analysis.py`). README/Codecov/Archiv-Doku auf neuen Stand aktualisiert.
- Bewusst nicht verschoben (aktive Referenzen / CI): `backend_v2`, `backend_server`, `server_tools`, `class_folder`; zusaetzlich `trainer`, `templates`, `analysis_dataset.jsonl` wegen indirekter Legacy-Abhaengigkeiten.
- Tests: keine Ausfuehrung (Move-/Doku-PR, keine Logikaenderung). Risiko: einzelne veraltete Doku-Verweise ausserhalb der aktualisierten Dateien koennen weiterhin historische Pfade nennen.

- G660-G699 Draft (gestartet): Archiv-Welle 2 vorbereiten (`trainer/`, `templates/`, `analysis_dataset.jsonl`) mit Referenzbereinigung vor dem eigentlichen Move. Ziel: aktive Pfade (`backend_server`, `class_folder`) migrationsfest machen und sichere Move-Reihenfolge dokumentieren.

- G660-G699 abgeschlossen (Wave-2 Vorbereitung): Referenzbereinigung fuer spaetere Archivierung vorbereitet.
- `backend_server/main.py`: Trainer-Script-Pfade auf Fallback-Resolver umgestellt (unterstuetzt `trainer/...` und spaeter `archive/legacy_training_tools/trainer/...`).
- `class_folder/core/hf_fine_tuner.py`: Analyse-Dataset-Suche auf Root + spaeteren Archivpfad erweitert (`archive/legacy_misc/analysis_dataset.jsonl`).
- Neue Doku `docs/archive_legacy_wave2_preparation.md`: Referenzmatrix, Risiken, Shim-Strategie fuer `templates/`, empfohlene Ausfuehrungsreihenfolge fuer Wave 2.
- Archiv-Doku verlinkt (`docs/archive_legacy_greenfield_plan.md`, `docs/archive_legacy_move_manifest_v1.md`).
- Tests: `python -m py_compile backend_server/main.py class_folder/core/hf_fine_tuner.py` (Syntax/Import-Basis ok). Keine Legacy-Runtime-Smokes ausgefuehrt.

- G700-G749 Draft (gestartet): Wave 2 Schritt 1 umsetzen (`templates/` ins Archiv verschieben + Top-Level-Kompatibilitaets-Shim `templates.regeln` beibehalten), damit aktive Legacy-Imports nicht brechen.

- G700-G749 abgeschlossen (Wave 2 Schritt 1): `templates/` nach `archive/legacy_desktop_core/templates/` verschoben und Top-Level-Kompatibilitaets-Shim (`templates/__init__.py`, `templates/regeln.py`) angelegt.
- Archiv-Pfad fuer Shim-Import als Python-Package vorbereitet (`archive/__init__.py`, `archive/legacy_desktop_core/__init__.py`).
- Checks: `python -c \"from templates.regeln import ...\"` erfolgreich; `py_compile` fuer mehrere aktive `templates.regeln`-Importer (`class_folder`, `server_tools`, `trainer`) erfolgreich.
- Offener Wave-2-Rest: `trainer/` verschieben (Fallback in `backend_server/main.py` vorbereitet) und `analysis_dataset.jsonl` verschieben (Fallback in `hf_fine_tuner.py` vorbereitet).

- G750-G799 Draft (gestartet): Wave 2 Schritt 2 (`trainer/` nach `archive/legacy_training_tools/trainer/` verschieben), inkl. kurzer Pfadauflosungs-Pruefung fuer `backend_server`-Trainingsskripte und Doku-Statusupdate.

- G750-G799 abgeschlossen (Wave 2 Schritt 2): `trainer/` nach `archive/legacy_training_tools/trainer/` verschoben.
- `backend_server/main.py` bleibt kompatibel dank vorbereitetem Fallback-Resolver (`trainer/...` -> `archive/legacy_training_tools/trainer/...`).
- Checks: Archiv-Zieldateien vorhanden (`train_analyst.py`, `train_narrative.py`) und `py_compile` fuer `backend_server/main.py` + beide Trainer-Skripte erfolgreich.
- Doku-Status fuer Wave 2 aktualisiert (`docs/archive_legacy_wave2_preparation.md`, Archivplan/-Manifest).

- G800-G829 Draft (gestartet): Wave 2 Schritt 3 (`analysis_dataset.jsonl` nach `archive/legacy_misc/analysis_dataset.jsonl` verschieben), inkl. Fallback-Pruefung ueber `class_folder/core/hf_fine_tuner.py` und Doku-Statusupdate.

- G800-G829 abgeschlossen (Wave 2 Schritt 3): `analysis_dataset.jsonl` nach `archive/legacy_misc/analysis_dataset.jsonl` verschoben.
- Fallback in `class_folder/core/hf_fine_tuner.py` greift wie vorbereitet: Root-Datei fehlt, Archivdatei vorhanden.
- Checks: `python -c` Dateiexistenzcheck (root=false, archive=true), `python -m py_compile class_folder/core/hf_fine_tuner.py` erfolgreich.
- Wave-2-Doku-/Archivstatus aktualisiert (`docs/archive_legacy_wave2_preparation.md`, Archivplan/-Manifest).

- G610-G699 Draft (gestartet): Doku-Nachlauf fuer veraltete Legacy-Pfadverweise + Abschluss der Archivwellen. Fokus: repo-weite Referenzsuche auf bereits archivierte Pfade, gezielte Bereinigung aktiver Doku/Config-Verweise, Abschlussdokumentation mit klarer Liste verbleibender bewusst aktiver Legacy-Komponenten.

- G610-G699 abgeschlossen: Doku-Nachlauf fuer archivierte Legacy-Pfade durchgefuehrt (codecov.yml, Archiv-Dokus, Roadmap-Hinweis zu historischem web_frontend).
- Archivthema im aktuellen Scope als abgeschlossen dokumentiert: Wave 1 + Wave 2 erledigt; verbleibende Top-Level-Legacy-Komponenten (`backend_v2`, `backend_server`, `server_tools`, `class_folder`, `templates`-Shim) bewusst aktiv/kompatibilitaetsrelevant und daher kein weiterer Archiv-Move offen.
- Finalscan: verbleibende Treffer zu archivierten Pfaden nur in historischen/Archiv-Dokus, README (korrekter Archivpfad) und aktiven Kompatibilitaets-Fallbacks/Shims.

- G700-G799 Draft (gestartet): Vertical-Slice-Produktpfad weiterziehen mit authored Dialog-Topics als kleinem Dialogbaum (Folgeoptionen), staerkeren Quest-/Flag-Transitions aus Topic-Entscheidungen und Skillcheck-Auswirkungen (MVP, ohne allgemeinen Dice-/Dialog-Engine-Refactor).

- G700-G799 abgeschlossen: Kleiner authored Dialogbaum/Folgeoptionen fuer Urban-Occult-Vertical-Slice implementiert (Kael-Crosscheck-Branch nach `kael_sabotage_hypothesis`).
- `quest_authoring.py`: skillcheck-abhaengige Folge-Topics (`kael_crosscheck_press_for_names` vs. `kael_crosscheck_reframe_with_evidence`), topicgetriebener Abschluss des Followup-Crosschecks inkl. Quest-Events aus Topic-Effekten, branch-spezifische Hinweise/Hints.
- `persistence.py`: Story-Flags nach Dialogtopic-Effekten erneut aus Queststatus abgeleitet, damit topicbedingte Questabschluesse im selben Turn konsistent in `story_flags` landen.
- `App.tsx`: Dialogtopic-UI/Parser erweitert (Folgeoption-Metadaten wie `followup_of`, `followup_condition`, `effect_hint`, `dialog_tree_step/group`) und Anzeige im NPC-Panel verbessert.
- Tests: neuer Route-Test fuer den kompletten Kael-Folgebranch bis Questabschluss (`test_g700_dialog_topic_followup_branch_completes_followup_crosscheck`), bestehender G450-Test auf branch-spezifische Hint-Texte robust gemacht.
- Validierung: `python -m pytest apps/game_api/tests -q`, `npm.cmd --prefix apps/web_client run build`, Vollregression `python -m pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 324 passed.
- Tech Debt (bewusst): Dialogtopic-Effekte/Questuebergaenge laufen weiterhin im Persistenz-/Questpfad nach Rules-Resolution; fuer spaetere Narrationsqualitaet bleibt das Ziel `Rules/Persistenz -> Story/Dialog Beats -> Narrator`.

- G800-G899 Draft (gestartet): QuestSpec/ObjectiveSpec/TransitionSpec (MVP) einfuehren, Urban-Occult-Quests auf datengesteuerte Questdefinitionen umstellen und einen validier-/kompilierbaren Andockpunkt fuer spaetere KI-Questvorschlaege vorbereiten (ohne freie KI-Questaktivierung).

- G800-G899 abgeschlossen: Datengesteuertes Quest-Modell (QuestSpec/ObjectiveSpec/TransitionSpec, MVP) eingefuehrt und Urban-Occult-Quests darauf umgestellt.
- Neues Modul `apps/game_api/app/services/quest_specs.py`:
  - `ObjectiveSpec`, `TransitionSpec`, `QuestSpec`
  - `compile_quest_spec_to_world_state(...)`
  - `apply_transition_specs_to_quest_state(...)`
  - `validate_quest_spec(...)`
  - `validate_quest_specs_for_activation(...)` (Andockpunkt fuer spaetere KI-Questvorschlaege)
- `quest_authoring.py`:
  - Urban-Occult Starter- und Followup-Quest als `QuestSpec` definiert (`URBAN_OCCULT_*_QUEST_SPEC`)
  - Initialisierung/Folgequest-Erzeugung ueber Spec-Compiler statt hart kodierter `WorldQuestState`-Bloecke
  - Stage-/Statuswechsel in Starter/Followup ueber `TransitionSpec`-Auswertung statt verstreuter If-Ketten
  - Helper `validate_authored_quest_specs()` + Registry-Funktion fuer authored Specs
- Bestehender Vertical-Slice bleibt funktional (Dialogtopics/Skillchecks/Folgebranch), aber Questdefinitionen sind jetzt datengetriebene Vorstufe fuer spaetere dynamische/validierte Quest-Aktivierung.
- Neue Tests: `apps/game_api/tests/test_quest_specs.py` (Compiler/Validator/Transitionen), bestehende Route-Tests weiter gruen.
- Validierung: `python -m pytest apps/game_api/tests -q`, `npm.cmd --prefix apps/web_client run build`, Vollregression `python -m pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 329 passed.
- Tech Debt (bewusst): Objective-Trigger selbst sind noch questspezifisch codiert; naechster Schritt fuer KI-Quests waere TriggerSpec/Predicate-Layer (z. B. action-/flag-basierte Trigger) als Datenformat.

- G900-G999 Draft (gestartet): TriggerSpec/Predicate-Layer (MVP) fuer datengetriebenen Questfortschritt einfuehren und Urban-Occult-Objective-Trigger von questspezifischen If-Ketten auf Trigger-/Predicate-Auswertung umstellen (Vorstufe fuer validierbare KI-Quest-Objectives).

- G900-G999 abgeschlossen: TriggerSpec/Predicate-Layer (MVP) fuer datengetriebenen Objective-Fortschritt eingefuehrt und Urban-Occult-Starter-/Followup-Quest auf `objective_triggers` umgestellt.
- `apps/game_api/app/services/quest_specs.py` erweitert um:
  - `PredicateSpec` (MVP: `action_seen`, `story_flag_true`)
  - `ObjectiveTriggerSpec`
  - `apply_objective_trigger_specs_to_quest_state(...)`
  - Trigger-/Predicate-Validierung in `validate_quest_spec(...)`
- `QuestSpec` traegt jetzt `objective_triggers`; Trigger werden priorisiert ausgewertet und koennen Objective-Status/Hint datengetrieben setzen (in-place auf `WorldQuestState`).
- `quest_authoring.py`:
  - Starterquest-Objective-Trigger (`Kael`, `Vorratskiste`, `Mira-Report`) als `ObjectiveTriggerSpec`
  - Followup-Objective-Trigger (`Runenspuren`, `Siegelkoffer`) als `ObjectiveTriggerSpec`
  - questspezifische If-Ketten in `advance_quests_for_turn()` und `_advance_urban_occult_followup_quest()` fuer diese Objective-Completion entfernt; stattdessen Trigger-Evaluator + bestehende `TransitionSpec`-Auswertung
  - topic-getriebener Kael-Crosscheck-Abschluss bleibt bewusst separat (Dialogtopic-Effektpfad), damit der Trigger-Layer nur generische Objective-Completion ersetzt
- Neue/erweiterte Tests:
  - `apps/game_api/tests/test_quest_specs.py`: Trigger-Evaluator (Starter-Objectives), Trigger-Voraussetzungen, Trigger-Referenzvalidierung
  - bestehende Quest-Route-Tests bleiben gruen (Starterquest + Followup-Quest-Flow)
- Validierung:
  - `python -m pytest apps/game_api/tests/test_quest_specs.py -q` (8 passed)
  - `python -m pytest apps/game_api/tests -q` (113 passed)
  - `npm.cmd --prefix apps/web_client run build`
  - Vollregression `python -m pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 332 passed
- Tech Debt (bewusst): Trigger-Predicates sind noch MVP (`action_seen`, `story_flag_true`) und Objective-Trigger setzen nur Status/Hint. Fuer spaetere KI-Questvorschlaege fehlen noch ein allgemeiner `TriggerSpec/Predicate`-Katalog (z. B. Inventory-/NPC-/Discovery-/Quest-Event-Predicates) und ein datengetriebener Transition-/Effect-Layer jenseits von Objective-Completion.

- G1000-G1099 Draft (gestartet): Predicate-Katalog fuer Quest-Trigger erweitern (Discovery/Inventory/NPC-bezogene Predicates) und Trigger-Evaluator/Validator dafuer vorbereiten. Ziel: Quest-Objective-Trigger weniger auf Action-Heuristiken beschraenken und KI-Quest-Specs spaeter auf reichere, aber weiterhin validierbare Triggerbedingungen stützen.

- G1000-G1099 abgeschlossen: Predicate-Katalog fuer datengetriebene Quest-Trigger erweitert (Discovery/Inventory/NPC), inkl. Evaluator- und Validator-Support.
- `apps/game_api/app/services/quest_specs.py` erweitert:
  - `PredicateSpec` um Katalogfelder fuer `action_seen` (u. a. `target_roles`)
  - neue Predicate-Kinds: `system_event_seen`, `inventory_item_present`, `inventory_delta_seen`, `relationship_change_seen`
  - Evaluator-Helper fuer Systemevents, Inventar-Endzustand, Inventar-Deltas (`inventory_gained`/`inventory_consumed`) und NPC-Beziehungsdeltas (`state_delta.relationship_changes`)
  - Validator-Regeln fuer neue Predicate-Kinds (Pflichtfilter, gueltige `inventory_delta_kind`-/`relationship_delta_sign`-Werte)
- `quest_authoring.py`: keine fachliche Quest-Logik geaendert; bestehende Urban-Occult-Quests bleiben auf den vorhandenen Triggern/Transitions lauffaehig (Katalog-Ausbau als Infrastruktur-Schritt).
- `apps/game_api/tests/test_quest_specs.py` erweitert:
  - `system_event_seen` (Discovery-Event als Trigger)
  - `inventory_item_present` + `inventory_delta_seen`
  - `relationship_change_seen` + `action_seen` mit `target_role`
  - Validator-Test fuer unbekannte Trigger-Objective-Referenz bleibt/ist erweitert abgesichert
- Validierung:
  - `python -m pytest apps/game_api/tests/test_quest_specs.py -q` (11 passed)
  - `python -m pytest apps/game_api/tests -q` (116 passed)
  - `npm.cmd --prefix apps/web_client run build`
  - Vollregression `python -m pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` -> 335 passed
- Tech Debt (bewusst): Der Predicate-Katalog ist jetzt breiter, aber authored Quests nutzen die neuen Predicate-Kinds noch nicht aktiv. Nächster sinnvoller Schritt fuer KI-Questvorschlaege ist ein datengetriebener Effect-/Transition-Layer (nicht nur Objective-Status/Hint) plus Spec-Validator fuer Referenzen auf NPCs/POIs/Items/Flags.

- G1100-G1199 Draft (gestartet): Datengetriebenen Effect-/Transition-Layer (MVP) auf QuestSpec-Ebene einfuehren, damit Trigger/Transitions nicht nur Objective-Status setzen, sondern auch Story-Flags, Quest-State, Objective-Hints/-Status und Systemevents strukturiert aus Specs heraus anwenden koennen.

- G1100-G1199 abgeschlossen: Effect-/Transition-Layer (MVP) in `QuestSpec` eingefuehrt und in den authored Urban-Occult-Transitions aktiv genutzt.
- `apps/game_api/app/services/quest_specs.py` erweitert:
  - neue `EffectSpec`-Struktur + Validator `_validate_effect_spec(...)`
  - `TransitionSpec.effects` und `ObjectiveTriggerSpec.effects`
  - `apply_effect_specs(...)` als zentrale Ausfuehrung fuer datengetriebene Effekte
  - erweiterte Signaturen:
    - `apply_transition_specs_to_quest_state(..., mutable_story_flags, emitted_events, ...)`
    - `apply_objective_trigger_specs_to_quest_state(..., mutable_story_flags, emitted_events, ...)`
  - unterstuetzte Effektarten (MVP): `set_story_flag`, `increment_story_flag`, `set_objective_hint`, `set_objective_status`, `set_quest_state`, `emit_system_event`
- `apps/game_api/app/services/quest_authoring.py` angepasst:
  - Starter-/Followup-Transitions emittieren jetzt authored `quest_stage_shifted`-Systemevents per `EffectSpec`
  - Quest-Advance-Pfade uebergeben `emitted_events`, damit Effekt-Events im Turn-Kontext sichtbar sind
- `apps/game_api/tests/test_quest_specs.py` erweitert:
  - Tests fuer `apply_effect_specs(...)` (Story-Flags + Event-Emission)
  - Test fuer Objective-Hint-Update per Effekt
- Validierung:
  - `.venv-v2\\Scripts\\python.exe -m pytest apps/game_api/tests/test_quest_specs.py -q` (15 passed)
  - `.venv-v2\\Scripts\\python.exe -m pytest apps/game_api/tests -q` (120 passed)
  - `npm.cmd --prefix apps/web_client run build`
  - `.venv-v2\\Scripts\\python.exe -m pytest backend_v2/tests backend_server/tests packages/shared_schemas/tests packages/rules_engine/tests apps/game_api/tests -q` (339 passed, 1 warning)
- Tech Debt (bewusst): Effekt-Validierung prueft derzeit nur Struktur/Minimalkonsistenz. Referenzvalidierung fuer Effekt-Targets (z. B. Objective-/Quest-Referenzen ueber Questgrenzen, Story-Flag-Namenskonventionen) sollte als naechster Schritt staerker formalisiert werden.
