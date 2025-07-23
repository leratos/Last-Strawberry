# trainer/training_ui_server.py
# -*- coding: utf-8 -*-

"""
Backend-Server für die interaktive Trainingsdaten-UI.
Version 2.1: Sendet jetzt Rollen im Story-Verlauf mit, um Anzeigefehler im Frontend zu beheben.
"""

import json
import logging
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

from flask import Flask, request, jsonify, render_template

# --- Konfiguration & Importe ---
try:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(project_root))
    from class_folder.core.inference_service import InferenceService
    from templates.regeln import CREATIVE_PROMPTS, ANALYSIS_PROMPT_TEMPLATE
    INFERENCE_AVAILABLE = True
except ImportError as e:
    print(f"FEHLER: Notwendige Klassen konnten nicht importiert werden: {e}")
    INFERENCE_AVAILABLE = False

app = Flask(__name__, template_folder='.')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

inference_service = None
erzaehler = None
spieler = None
analyst = None

# --- Szenario-Templates für gezielte Befehlsgenerierung ---

COMMAND_SCENARIOS = {
    "NPC_CREATE": [
        "Du betrittst eine belebte Taverne voller unbekannter Gestalten.",
        "Auf dem Marktplatz siehst du einen verdächtigen Händler.",
        "Ein mysteriöser Fremder nähert sich dir in der Gasse.",
        "Du hörst Stimmen aus einem dunklen Gebäude."
    ],
    "NPC_MOVE": [
        "Der Barkeeper verlässt plötzlich seinen Platz und geht nach hinten.",
        "Die Wache dreht sich um und marschiert davon.",
        "Ein Dieb huscht von einer Ecke zur anderen.",
        "Der alte Magier verschwindet in einer Rauchwolke."
    ],
    "PLAYER_MOVE": [
        "Vor dir öffnen sich drei Wege: links zur Bibliothek, rechts zum Hafen, geradeaus zum Palast.",
        "Du stehst vor einer verschlossenen Tür. Daneben führt eine Treppe nach oben.",
        "Der Tunnel gabelt sich - ein Pfad führt nach links, einer nach rechts.",
        "Du siehst in der Ferne eine Brücke und einen Waldpfad."
    ],
    "ROLL_CHECK": [
        "Eine schwere Truhe blockiert den Weg - sie könnte Schätze enthalten.",
        "Die steile Felswand sieht kletterbar aus, ist aber gefährlich.",
        "Du hörst verdächtige Geräusche - willst du lauschen?",
        "Der Händler wirkt nervös - vielleicht lügt er dich an?"
    ],
    "PLAYER_STATE_UPDATE": [
        "Ein giftiger Pfeil durchbohrt deinen Arm.",
        "Du trinkst einen merkwürdigen Trank und fühlst dich verändert.",
        "Die magische Aura des Ortes beeinflusst dich.",
        "Du findest eine glänzende Rüstung, die perfekt passt."
    ],
    "NPC_STATE_UPDATE": [
        "Der Händler wird misstrauisch, als du nach seltenen Waren fragst.",
        "Die Wache entspannt sich, nachdem du deine Absichten erklärst.",
        "Der verletzte Krieger erholt sich langsam von seinen Wunden.",
        "Die Prinzessin wird wütend über deine freche Antwort."
    ]
}

PERSONA_PROMPTS = {
    "aggressive": "Du bist ein aggressiver Kämpfer, der Konflikte sucht und direkt handelt.",
    "sneaky": "Du bist ein listiger Schurke, der gerne schleicht und Geheimnisse aufdeckt.",
    "curious": "Du bist ein neugieriger Abenteurer, der alles untersuchen und erforschen will.",
    "diplomatic": "Du bist ein diplomatischer Charakter, der Konflikte durch Worte löst.",
    "cautious": "Du bist sehr vorsichtig und überlegst jeden Schritt genau.",
    "impulsive": "Du handelst spontan und impulsiv, ohne lange zu überlegen."
}

# --- KI-Klassen ---

def format_chat_prompt(system_prompt: str, chat_history: List[Dict[str, str]]) -> str:
    prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt.strip()}<|eot_id|>"
    for message in chat_history:
        role, content = message.get('role', ''), message.get('content', '')
        prompt += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content.strip()}<|eot_id|>"
    prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
    return prompt

class ErzählerKI:
    def __init__(self, inference_service: 'InferenceService'):
        self.inference_service = inference_service
        self.story_context: List[Dict[str, str]] = []
        self.system_prompt = " ".join([text for _, text in sorted(CREATIVE_PROMPTS.get("system_fantasy", []))])

    def start_story(self, start_text: str = None) -> str:
        # Stelle sicher, dass der Narrative-Adapter aktiv ist
        self.inference_service.switch_to_adapter('NARRATIVE', 'default_world')
        
        if not start_text:
            start_text = "Du stehst vor den Toren einer alten, verwitterten Hafenstadt."
            
        self.story_context = [{"role": "user", "content": start_text}]
        full_prompt = format_chat_prompt(self.system_prompt, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        self.story_context.append({"role": "assistant", "content": response})
        return response

    def start_targeted_scenario(self, target_command: str) -> Tuple[str, str]:
        """Startet ein Szenario, das einen bestimmten Befehlstyp provozieren soll"""
        scenarios = COMMAND_SCENARIOS.get(target_command, ["Du befindest dich an einem mysteriösen Ort."])
        import random
        chosen_scenario = random.choice(scenarios)
        
        # Erweitere das System-Prompt für gezielte Szenarien
        enhanced_system = (
            f"{self.system_prompt} "
            f"Beschreibe die Situation so, dass der Spieler wahrscheinlich eine Aktion ausführt, "
            f"die zu einem {target_command}-Befehl führt."
        )
        
        self.story_context = [{"role": "user", "content": chosen_scenario}]
        full_prompt = format_chat_prompt(enhanced_system, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        self.story_context.append({"role": "assistant", "content": response})
        
        return chosen_scenario, response

    def continue_story(self, player_action: str) -> str:
        # Stelle sicher, dass der Narrative-Adapter aktiv ist
        self.inference_service.switch_to_adapter('NARRATIVE', 'default_world')
        
        self.story_context.append({"role": "user", "content": player_action})
        full_prompt = format_chat_prompt(self.system_prompt, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        if len(self.story_context) > 10: self.story_context = self.story_context[-10:]
        self.story_context.append({"role": "assistant", "content": response})
        return response

    def continue_targeted_story(self, player_action: str, target_command: str) -> str:
        """Fortsetzung der Geschichte mit Fokus auf einen bestimmten Befehlstyp"""
        self.story_context.append({"role": "user", "content": player_action})
        
        # Erweitere das System-Prompt für gezielte Fortsetzungen
        enhanced_system = (
            f"{self.system_prompt} "
            f"Reagiere auf die Spieleraktion so, dass wahrscheinlich ein {target_command}-Befehl ausgelöst wird."
        )
        
        full_prompt = format_chat_prompt(enhanced_system, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        if len(self.story_context) > 10: self.story_context = self.story_context[-10:]
        self.story_context.append({"role": "assistant", "content": response})
        return response

class SpielerKI:
    def __init__(self, inference_service: 'InferenceService', persona: str = "mutig und direkt"):
        self.inference_service = inference_service
        self.current_persona = persona
        self.update_system_prompt()

    def update_system_prompt(self):
        persona_text = PERSONA_PROMPTS.get(self.current_persona, self.current_persona)
        self.system_prompt = (
            f"Du bist ein Pen-and-Paper-Spieler. {persona_text} "
            "Antworte auf den folgenden Text mit einer kurzen, klaren Aktion in der Ich-Form. "
            "Gib NUR die Aktion aus."
        )

    def set_persona(self, persona: str):
        """Ändert die Persönlichkeit des KI-Spielers"""
        self.current_persona = persona
        self.update_system_prompt()

    def generate_action(self, narrative_text: str) -> str:
        # Stelle sicher, dass der Narrative-Adapter aktiv ist
        self.inference_service.switch_to_adapter('NARRATIVE', 'default_world')
        
        full_prompt = format_chat_prompt(self.system_prompt, [{"role": "user", "content": narrative_text}])
        action = self.inference_service.generate_story_response(full_prompt)
        return action.strip().replace("\"", "")

    def generate_targeted_action(self, narrative_text: str, target_command: str) -> str:
        """Generiert eine Aktion, die einen bestimmten Befehlstyp provozieren soll"""
        self.inference_service.switch_to_adapter('NARRATIVE', 'default_world')
        
        # Spezifische Anweisungen für verschiedene Befehlstypen
        command_instructions = {
            "ROLL_CHECK": "Versuche etwas Schwieriges oder Riskantes zu tun.",
            "PLAYER_MOVE": "Gehe zu einem neuen Ort oder verlasse diesen Bereich.",
            "NPC_CREATE": "Spreche jemanden an oder gehe auf eine Person zu.",
            "NPC_MOVE": "Weise jemanden an zu gehen oder verursache eine Reaktion.",
            "PLAYER_STATE_UPDATE": "Nutze oder berühre etwas Magisches oder Gefährliches.",
            "NPC_STATE_UPDATE": "Interagiere emotional mit einem Charakter."
        }
        
        instruction = command_instructions.get(target_command, "Handele normal.")
        enhanced_prompt = (
            f"{self.system_prompt} Zusätzlich: {instruction} "
            f"Reagiere auf folgenden Text:"
        )
        
        full_prompt = format_chat_prompt(enhanced_prompt, [{"role": "user", "content": narrative_text}])
        action = self.inference_service.generate_story_response(full_prompt)
        return action.strip().replace("\"", "")

class AnalyseKI:
    def __init__(self, inference_service: 'InferenceService'):
        self.inference_service = inference_service

    def _format_llama3_prompt(self, system_prompt: str) -> str:
        return (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")

    def analyze_player_action(self, player_action: str) -> List[Dict]:
        # Stelle sicher, dass der Analysis-Adapter aktiv ist
        self.inference_service.switch_to_adapter('ANALYSIS', 'global')
        
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            player_command=player_action, narrative_text="[IGNORIEREN]", player_name="Spieler",
            npc_context="[IGNORIEREN]", char_attributes="Stärke, Geschicklichkeit, Konstitution, Intelligenz, Weisheit, Charisma"
        ) + "\n\nAnalysiere NUR die SPIELER-AKTION und gib NUR `ROLL_CHECK` oder `PLAYER_MOVE` Befehle zurück."
        full_prompt = self._format_llama3_prompt(prompt)
        raw_output = self.inference_service.generate_story_response(full_prompt)
        try:
            match = re.search(r'\[.*\]', raw_output, re.DOTALL)
            if match: return json.loads(match.group(0))
        except json.JSONDecodeError: pass
        return []

    def analyze_narrative_consequence(self, narrative_text: str) -> List[Dict]:
        # Stelle sicher, dass der Analysis-Adapter aktiv ist
        self.inference_service.switch_to_adapter('ANALYSIS', 'global')
        
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            player_command="[IGNORIEREN]", narrative_text=narrative_text, player_name="Spieler",
            npc_context="Keine Charaktere anwesend.", char_attributes="Stärke, Geschicklichkeit, Konstitution, Intelligenz, Weisheit, Charisma"
        ) + "\n\nAnalysiere NUR den ERZÄHLTEXT und gib alle Befehle außer `ROLL_CHECK` und `PLAYER_MOVE` zurück."
        full_prompt = self._format_llama3_prompt(prompt)
        raw_output = self.inference_service.generate_story_response(full_prompt)
        try:
            match = re.search(r'\[.*\]', raw_output, re.DOTALL)
            if match: return json.loads(match.group(0))
        except json.JSONDecodeError: pass
        return []

# --- Hilfsfunktionen ---

def initialize_services():
    global inference_service, erzaehler, spieler, analyst
    if not INFERENCE_AVAILABLE: sys.exit(1)
    
    logger.info("Initialisiere InferenceService...")
    inference_service = InferenceService()
    if not inference_service.base_model_loaded: sys.exit(1)
        
    erzaehler = ErzählerKI(inference_service)
    spieler = SpielerKI(inference_service, "mutig und direkt")
    analyst = AnalyseKI(inference_service)
    logger.info("Alle KI-Dienste erfolgreich initialisiert.")

def create_training_example_text(player_action: str, narrative_text: str, final_commands: List[Dict]) -> str:
    system_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        npc_context="Keine Charaktere anwesend.", player_command=player_action,
        narrative_text=narrative_text, player_name="Spieler",
        char_attributes="Stärke, Geschicklichkeit, Konstitution, Intelligenz, Weisheit, Charisma"
    )
    prompt_part = (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                   f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")
    assistant_json = json.dumps(final_commands, indent=4, ensure_ascii=False)
    full_text = f"{prompt_part}{assistant_json}<|eot_id|>"
    return json.dumps({"text": full_text})

# --- API Endpunkte ---

@app.route('/')
def index():
    return render_template('enhanced_training_ui.html')

@app.route('/interactive')
def interactive():
    return render_template('interactive_training_ui.html')

@app.route('/api/generate_step', methods=['POST'])
def generate_step():
    data = request.json
    last_narrative_text = data.get('last_narrative_text')
    target_command = data.get('target_command')  # Neuer Parameter
    player_persona = data.get('player_persona', 'mutig und direkt')  # Neuer Parameter
    
    # Setze Spieler-Persona
    if player_persona != spieler.current_persona:
        spieler.set_persona(player_persona)
    
    # KORRIGIERTE LOGIK: Trennung von Spielstart und normalem Zug
    if not last_narrative_text: # Erster Aufruf -> Spielstart
        if target_command:
            start_prompt, narrative_text = erzaehler.start_targeted_scenario(target_command)
        else:
            start_prompt = "Du stehst vor den Toren einer alten, verwitterten Hafenstadt."
            narrative_text = erzaehler.start_story(start_prompt)
        
        narrative_analysis = analyst.analyze_narrative_consequence(narrative_text)
        
        return jsonify({
            "is_initial_turn": True,
            "playerAction": start_prompt,
            "narrativeText": narrative_text,
            "narrativeAnalysis": narrative_analysis,
            "targetCommand": target_command,
            "playerPersona": player_persona,
            "fullStory": [{"role": msg.get('role'), "content": msg.get('content')} for msg in erzaehler.story_context]
        })
    else: # Normaler Spielzug
        if target_command:
            player_action = spieler.generate_targeted_action(last_narrative_text, target_command)
            next_narrative_text = erzaehler.continue_targeted_story(player_action, target_command)
        else:
            player_action = spieler.generate_action(last_narrative_text)
            next_narrative_text = erzaehler.continue_story(player_action)

        action_analysis = analyst.analyze_player_action(player_action)
        narrative_analysis = analyst.analyze_narrative_consequence(next_narrative_text)

        return jsonify({
            "is_initial_turn": False,
            "playerAction": player_action,
            "narrativeText": next_narrative_text,
            "actionAnalysis": action_analysis,
            "narrativeAnalysis": narrative_analysis,
            "targetCommand": target_command,
            "playerPersona": player_persona,
            "fullStory": [{"role": msg.get('role'), "content": msg.get('content')} for msg in erzaehler.story_context]
        })

@app.route('/api/get_available_commands', methods=['GET'])
def get_available_commands():
    """Gibt verfügbare Befehlstypen und Personas zurück"""
    return jsonify({
        "commands": list(COMMAND_SCENARIOS.keys()),
        "personas": list(PERSONA_PROMPTS.keys()),
        "command_descriptions": {
            "NPC_CREATE": "Neue Charaktere einführen",
            "NPC_MOVE": "NSCs bewegen oder entfernen",
            "PLAYER_MOVE": "Spieler-Ortswechsel",
            "ROLL_CHECK": "Fähigkeitsproben",
            "PLAYER_STATE_UPDATE": "Spielerzustand ändern",
            "NPC_STATE_UPDATE": "NSC-Eigenschaften ändern"
        }
    })

@app.route('/api/generate_targeted_batch', methods=['POST'])
def generate_targeted_batch():
    """Generiert mehrere Trainingsbeispiele für einen spezifischen Befehlstyp"""
    data = request.json
    target_command = data.get('target_command')
    count = min(data.get('count', 3), 10)  # Maximal 10 Beispiele
    personas = data.get('personas', ['aggressive', 'curious', 'diplomatic'])
    
    if not target_command:
        return jsonify({"status": "error", "message": "target_command required"}), 400
    
    examples = []
    
    for i in range(count):
        # Rotiere durch verschiedene Personas
        current_persona = personas[i % len(personas)]
        spieler.set_persona(current_persona)
        
        # Generiere gezieltes Szenario
        start_prompt, narrative_text = erzaehler.start_targeted_scenario(target_command)
        player_action = spieler.generate_targeted_action(narrative_text, target_command)
        next_narrative = erzaehler.continue_targeted_story(player_action, target_command)
        
        # Analysiere
        action_analysis = analyst.analyze_player_action(player_action)
        narrative_analysis = analyst.analyze_narrative_consequence(next_narrative)
        combined_commands = action_analysis + narrative_analysis
        
        examples.append({
            "playerAction": player_action,
            "narrativeText": next_narrative,
            "commands": combined_commands,
            "persona": current_persona,
            "scenario": start_prompt
        })
        
        # Reset für nächstes Beispiel
        erzaehler.story_context = []
    
    return jsonify({
        "status": "success",
        "target_command": target_command,
        "examples": examples,
        "count": len(examples)
    })

@app.route('/api/save_example', methods=['POST'])
def save_example():
    data = request.json
    player_action = data.get('playerAction')
    narrative_text = data.get('narrativeText')
    final_commands = data.get('finalCommands')
    
    if not all([player_action, narrative_text, isinstance(final_commands, list)]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    example_line = create_training_example_text(player_action, narrative_text, final_commands)
    
    output_path = Path(__file__).resolve().parent / "analysis_dataset_final.jsonl"
    with output_path.open("a", encoding="utf-8") as f:
        f.write(example_line + "\n")
        
    logger.info(f"Ein Trainingsbeispiel wurde in {output_path.name} gespeichert.")
    return jsonify({"status": "success"})

if __name__ == '__main__':
    initialize_services()
    app.run(debug=True, port=5000)
