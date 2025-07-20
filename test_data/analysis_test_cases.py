# test_data/analysis_test_cases.py
# -*- coding: utf-8 -*-

"""
Zentrale Datenbank für alle Testfälle der Analyse-KI.
Version 2.0 - Synchronisiert mit regeln.py V7.0
"""
from typing import List, Dict, Any

TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "TC1: Einfache NSC-Erstellung",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich gehe auf den Mann zu.",
        "narrative_text": "Ein alter Mann in einer schlichten Robe lehnt an einer Kiste und beobachtet das Treiben.",
        "expected_commands": [{
            "command": "NPC_CREATE", 
            "name": "Alter Mann in schlichter Robe",
            "backstory": "Lehnt an einer Kiste und beobachtet das Treiben.",
            "disposition": "neutral"
        }]
    },
    {
        "name": "TC2: Einfaches NSC-Update",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Alter Mann in schlichter Robe: ...",
        "player_command": "Wie ist Euer Name?",
        "narrative_text": "Der alte Mann hebt langsam den Kopf. 'Man nennt mich Lyseios', sagt er mit ruhiger Stimme.",
        "expected_commands": [{"command": "NPC_UPDATE", "old_name": "Alter Mann in schlichter Robe", "new_name": "Lyseios"}]
    },
    {
        "name": "TC3: Erstellung mehrerer NSCs (Streit-Szenario)",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich gehe näher an die Gruppe heran, um zu lauschen.",
        "narrative_text": "Als du näher kommst, siehst du eine hitzige Diskussion. Ein Mann mittleren Alters mit markanten Falten im Gesicht schreit beinahe. Ein jüngerer Mann mit Bart, der wie ein Krieger aussieht, widerspricht ihm. Eine dritte Person, eine Frau mit freundlichem Gesicht, versucht zu schlichten.",
        "expected_commands": [
            { "command": "NPC_CREATE", "name": "Mann mittleren Alters mit Falten", "backstory": "Schreit in einer hitzigen Diskussion.", "disposition": "aufgebracht" },
            { "command": "NPC_CREATE", "name": "Junger Mann mit Bart", "backstory": "Sieht aus wie ein Krieger und widerspricht.", "disposition": "oppositionell" },
            { "command": "NPC_CREATE", "name": "Frau mit freundlichem Gesicht", "backstory": "Versucht zu schlichten.", "disposition": "vermittelnd" }
        ]
    },
    {
        "name": "TC4: Spieler wird ignoriert",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich trete aus dem Schatten.",
        "narrative_text": "Du, Leratos, trittst aus dem Schatten. Deine Augen gewöhnen sich langsam an das Licht. Du siehst dich um.",
        "expected_commands": []
    },
    {
        "name": "TC5: Kein relevanter Befehl",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich atme tief durch und genieße die Atmosphäre.",
        "narrative_text": "Die Sonne steht hoch am Himmel. Ein leichter Wind weht durch die Gassen. Es riecht nach Sand und Gewürzen.",
        "expected_commands": []
    },
    {
        "name": "TC6: Saubere Namens-Extraktion",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich betrete die Taverne.",
        "narrative_text": "An der Theke lehnt eine Frau namens Elara. Sie wischt einen Krug sauber und blickt auf.",
        "expected_commands": [{
            "command": "NPC_CREATE", 
            "name": "Elara",
            "backstory": "Lehnt an der Theke und wischt einen Krug sauber.",
            "disposition": "neutral"
        }]
    },
    {
        "name": "TC7: Stärke-Probe (ROLL_CHECK)",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich versuche, die schwere Eichentür aufzubrechen.",
        "narrative_text": "Du stemmst dich gegen die Tür. Das Holz knarrt unter dem Druck.",
        "expected_commands": [{"command": "ROLL_CHECK", "attribut": "Stärke", "schwierigkeit": 15}]
    },
    {
        "name": "TC8: Charisma-Probe (ROLL_CHECK)",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Elara: Eine Wirtin...",
        "player_command": "Ich versuche Elara mit einem Lächeln zu überzeugen, mir einen Rabatt zu geben.",
        "narrative_text": "Du lächelst die Wirtin an und beginnst zu verhandeln.",
        "expected_commands": [{"command": "ROLL_CHECK", "attribut": "Charisma", "schwierigkeit": 12}]
    },
    {
        "name": "TC9: PLAYER_MOVE - Expliziter Befehl",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich gehe jetzt zur alten Mühle am Fluss.",
        "narrative_text": "Du lässt den Marktplatz hinter dir und machst dich auf den Weg.",
        "expected_commands": [{"command": "PLAYER_MOVE", "location_name": "Alte Mühle am Fluss"}]
    },
    {
        "name": "TC10: PLAYER_STATE_UPDATE - Spieler heilt sich",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich trinke einen Heiltrank.",
        "narrative_text": "Du ziehst ein kleines Fläschchen hervor. Die rote Flüssigkeit darin schimmert und eine wohlige Wärme durchströmt dich, als du sie trinkst.",
        "expected_commands": [{"command": "PLAYER_STATE_UPDATE", "updates": {"health": "+20", "status": "erfrischt"}}]
    },
    {
        "name": "TC11: NPC_STATE_UPDATE - Konsequenz aus Erzählung",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Wache: Steht grimmig am Tor.",
        "player_command": "Ich zeige der Wache das königliche Siegel.",
        "narrative_text": "Als die Wache das Siegel erkennt, weicht ihre grimmige Miene einem Ausdruck des Respekts. Sie salutiert.",
        "expected_commands": [{"command": "NPC_STATE_UPDATE", "npc_name": "Wache", "updates": {"disposition": "respektvoll"}}]
    },
    {
        "name": "TC12: NPC_MOVE - NSC verlässt die Szene",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Bote: Ein junger Mann...",
        "player_command": "Danke für die Nachricht.",
        "narrative_text": "Der Bote nickt kurz, dreht sich um und eilt die Straße hinunter, um in der Menge zu verschwinden.",
        "expected_commands": [{"command": "NPC_MOVE", "npc_name": "Bote", "location_name": "Straße"}]
    },
    {
        "name": "TC13: Weisheits-Probe (ROLL_CHECK)",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich untersuche die seltsamen Runen an der Wand.",
        "narrative_text": "Du trittst näher an die Wand und fährst mit den Fingern über die verwitterten Symbole. Du konzentrierst dich, um ihre Bedeutung zu entschlüsseln.",
        "expected_commands": [{"command": "ROLL_CHECK", "attribut": "Weisheit", "schwierigkeit": 14}]
    },
    {
        "name": "TC14: Intelligenz-Probe (ROLL_CHECK)",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich versuche, das Rätsel auf der Truhe zu lösen.",
        "narrative_text": "Die Inschrift ist komplex. Du überlegst, wie die verschiedenen Teile des Rätsels zusammenpassen könnten.",
        "expected_commands": [{"command": "ROLL_CHECK", "attribut": "Intelligenz", "schwierigkeit": 15}]
    },
    {
        "name": "TC15: Komplexer Fall - Mehrere Befehle",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich versuche, mich an der Wache vorbeizuschleichen.",
        "narrative_text": "Du huschst in den Schatten. Eine zweite Wache, eine Frau mit einem scharfen Blick, tritt aus einem Torbogen.",
        "expected_commands": [
            {"command": "ROLL_CHECK", "attribut": "Geschicklichkeit", "schwierigkeit": 13},
            {"command": "NPC_CREATE", "name": "Frau mit scharfem Blick", "backstory": "Tritt aus einem Torbogen.", "disposition": "wachsam"}
        ]
    },
    {
        "name": "TC16: Kein relevanter Befehl - Nur Beschreibung",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Schmied: ...",
        "player_command": "Ich beobachte den Schmied.",
        "narrative_text": "Der Schmied arbeitet unermüdlich weiter. Funken sprühen von seinem Hammer.",
        "expected_commands": []
    },
    {
        "name": "TC17: PLAYER_STATE_UPDATE - Vergiftung aus Erzählung",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Goblin: ...",
        "player_command": "Ich greife den Goblin an!",
        "narrative_text": "Du weichst dem ersten Hieb aus, aber der vergiftete Dolch des Goblins erwischt dich am Arm. Ein brennender Schmerz breitet sich aus.",
        "expected_commands": [
            {"command": "ROLL_CHECK", "attribut": "Stärke"},
            {"command": "PLAYER_STATE_UPDATE", "updates": {"status": "vergiftet", "health": "-5"}}
        ]
    },
    {
        "name": "TC18: NPC_MOVE - NSC verlässt Szene ohne Ziel",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Geist: Eine schemenhafte Gestalt.",
        "player_command": "Ich spreche ein Gebet.",
        "narrative_text": "Als du die heiligen Worte sprichst, löst sich der Geist langsam in Luft auf.",
        "expected_commands": [{"command": "NPC_MOVE", "npc_name": "Geist"}]
    },
    {
        "name": "TC19: Falscher Alarm - Spieler erwähnt Ort, geht aber nicht",
        "player_name": "Leratos", "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich frage mich, wie es wohl in der alten Mühle aussieht.",
        "narrative_text": "Du stehst auf dem Marktplatz und denkst über dein nächstes Ziel nach.",
        "expected_commands": []
    },
    {
        "name": "TC20: Komplexes NSC-Update",
        "player_name": "Leratos", "npc_context": "**Anwesende Charaktere:**\n- Die Gestalt in der Kapuze: ...",
        "player_command": "Zeig mir dein Gesicht!",
        "narrative_text": "Die Gestalt senkt langsam ihre Kapuze. Darunter kommt das Gesicht von Elara zum Vorschein, der Wirtin, die du seit Tagen suchst.",
        "expected_commands": [{"command": "NPC_UPDATE", "old_name": "Die Gestalt in der Kapuze", "new_name": "Elara"}]
    },
    {
        "name": "TC21: Offene Frage – Kein Befehl",
        "player_name": "Leratos",
        "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich bleibe still.",
        "narrative_text": "Der alte Mann sieht dich prüfend an. 'Und, wie möchtest du antworten?'",
        "expected_commands": []
    },
    {
        "name": "TC22: Erwähnung eines Ortes, aber kein Wechsel",
        "player_name": "Leratos",
        "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich frage mich, was im Tempel vorgeht.",
        "narrative_text": "Du blickst zur Tempelspitze. Sie wirkt fremd und unergründlich.",
        "expected_commands": []
    },
    {
        "name": "TC23: NPC_MOVE ohne Ziel",
        "player_name": "Leratos",
        "npc_context": "**Anwesende Charaktere:**\n- Händler: ...",
        "player_command": "Ich bedanke mich beim Händler.",
        "narrative_text": "Der Händler nickt kurz und verschwindet im Gedränge.",
        "expected_commands": [{"command": "NPC_MOVE", "npc_name": "Händler"}]
    },
    {
        "name": "TC24: PLAYER_STATE_UPDATE – Schaden",
        "player_name": "Leratos",
        "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich gehe durch das Feuer.",
        "narrative_text": "Die Flammen verbrennen dir die Haut, als du hindurchläufst.",
        "expected_commands": [{"command": "PLAYER_STATE_UPDATE", "updates": {"health": "-10", "status": "verbrannt"}}]
    },
    {
        "name": "TC25: Kombiniert – Probe & neuer NSC",
        "player_name": "Leratos",
        "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich durchsuche die dunkle Gasse.",
        "narrative_text": "Als du in die Schatten blickst, tritt ein maskierter Fremder hervor.",
        "expected_commands": [
            {"command": "ROLL_CHECK", "attribut": "Wahrnehmung", "schwierigkeit": 14},
            {"command": "NPC_CREATE", "name": "Maskierter Fremder", "backstory": "Tritt aus den Schatten hervor.", "disposition": "mysteriös"}
        ]
    },
    {
        "name": "TC26: NSC schon im Kontext – kein zweites CREATE",
        "player_name": "Leratos",
        "npc_context": "**Anwesende Charaktere:**\n- Elara: Die Wirtin ...",
        "player_command": "Ich winke Elara zu.",
        "narrative_text": "Elara lächelt und kommt zu dir an den Tresen.",
        "expected_commands": []
    },
    {
        "name": "TC27: Unzulässiges Feld – wird ignoriert",
        "player_name": "Leratos",
        "npc_context": "Keine Charaktere anwesend.",
        "player_command": "Ich kontrolliere mein Inventar.",
        "narrative_text": "Du öffnest deine Tasche. Ein silberner Ring liegt ganz unten.",
        "expected_commands": []
    }
]