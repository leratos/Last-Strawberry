# trainer/training_ui_server.py
# -*- coding: utf-8 -*-

"""
Backend-Server für die interaktive Trainingsdaten-UI.
Dieses Skript startet einen Flask-Webserver, der die KI-Logik ausführt
und mit dem HTML-Frontend kommuniziert.
"""

import json
import logging
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

# WICHTIG: Flask muss installiert sein -> pip install Flask
from flask import Flask, request, jsonify, render_template

# --- Konfiguration & Importe ---
# Annahme: Alle relevanten Klassen sind im Projektpfad verfügbar
try:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(project_root))
    from class_folder.core.inference_service import InferenceService
    from templates.regeln import CREATIVE_PROMPTS, ANALYSIS_PROMPT_TEMPLATE
    INFERENCE_AVAILABLE = True
except ImportError as e:
    print(f"FEHLER: Notwendige Klassen konnten nicht importiert werden: {e}")
    INFERENCE_AVAILABLE = False

# --- Flask App Initialisierung ---
app = Flask(__name__, template_folder='.')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Globale Objekte (für eine einzelne Benutzersitzung) ---
inference_service = None
erzaehler = None
spieler = None
analyst = None

# --- KI-Klassen (angepasst aus dem vorherigen Skript) ---

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

    def start_story(self, start_text: str) -> str:
        self.story_context = [{"role": "user", "content": start_text}]
        full_prompt = format_chat_prompt(self.system_prompt, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        self.story_context.append({"role": "assistant", "content": response})
        return response

    def continue_story(self, player_action: str) -> str:
        self.story_context.append({"role": "user", "content": player_action})
        full_prompt = format_chat_prompt(self.system_prompt, self.story_context)
        response = self.inference_service.generate_story_response(full_prompt)
        if len(self.story_context) > 10: self.story_context = self.story_context[-10:]
        self.story_context.append({"role": "assistant", "content": response})
        return response

class SpielerKI:
    def __init__(self, inference_service: 'InferenceService', persona: str):
        self.inference_service = inference_service
        self.system_prompt = (
            f"Du bist ein Pen-and-Paper-Spieler. Deine Persönlichkeit ist {persona}. "
            "Antworte auf den folgenden Text mit einer kurzen, klaren Aktion in der Ich-Form. "
            "Gib NUR die Aktion aus."
        )

    def generate_action(self, narrative_text: str) -> str:
        full_prompt = format_chat_prompt(self.system_prompt, [{"role": "user", "content": narrative_text}])
        action = self.inference_service.generate_story_response(full_prompt)
        return action.strip().replace("\"", "")

class AnalyseKI:
    def __init__(self, inference_service: 'InferenceService'):
        self.inference_service = inference_service

    def _format_llama3_prompt(self, system_prompt: str) -> str:
        return (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")

    def analyze_player_action(self, player_action: str) -> List[Dict]:
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

# --- Hilfsfunktionen für das Backend ---

def initialize_services():
    """Initialisiert die KI-Dienste beim Serverstart."""
    global inference_service, erzaehler, spieler, analyst
    if not INFERENCE_AVAILABLE:
        logger.error("Abhängigkeiten nicht installiert. Server kann nicht starten.")
        sys.exit(1)
    
    logger.info("Initialisiere InferenceService...")
    inference_service = InferenceService()
    if not inference_service.base_model_loaded:
        logger.error("Basis-Modell konnte nicht geladen werden. Server wird beendet.")
        sys.exit(1)
        
    erzaehler = ErzählerKI(inference_service)
    spieler = SpielerKI(inference_service, "mutig und direkt")
    analyst = AnalyseKI(inference_service)
    logger.info("Alle KI-Dienste erfolgreich initialisiert.")

def create_training_example_text(player_action: str, narrative_text: str, final_commands: List[Dict]) -> str:
    """Erstellt den finalen String für die .jsonl-Datei."""
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
    """Liefert die HTML-Oberfläche aus."""
    # Annahme: Die HTML-Datei heißt 'interactive_training_ui.html' und liegt im selben Ordner
    return render_template('interactive_training_ui.html')

@app.route('/api/generate_step', methods=['POST'])
def generate_step():
    """Generiert die nächste Runde des Dialogs und die KI-Analysen."""
    data = request.json
    last_narrative_text = data.get('last_narrative_text')
    
    if not last_narrative_text: # Erster Aufruf
        narrative_text = erzaehler.start_story("Du stehst vor den Toren einer alten, verwitterten Hafenstadt.")
        player_action = spieler.generate_action(narrative_text)
        next_narrative_text = erzaehler.continue_story(player_action)
    else:
        player_action = spieler.generate_action(last_narrative_text)
        next_narrative_text = erzaehler.continue_story(player_action)

    action_analysis = analyst.analyze_player_action(player_action)
    narrative_analysis = analyst.analyze_narrative_consequence(next_narrative_text)

    return jsonify({
        "playerAction": player_action,
        "narrativeText": next_narrative_text,
        "actionAnalysis": action_analysis,
        "narrativeAnalysis": narrative_analysis,
        "fullStory": [msg['content'] for msg in erzaehler.story_context]
    })

@app.route('/api/save_example', methods=['POST'])
def save_example():
    """Speichert ein fertiges Trainingsbeispiel in die .jsonl-Datei."""
    data = request.json
    player_action = data.get('playerAction')
    narrative_text = data.get('narrativeText')
    final_commands = data.get('finalCommands')
    
    if not all([player_action, narrative_text, isinstance(final_commands, list)]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    example_line = create_training_example_text(player_action, narrative_text, final_commands)
    
    # Speichere in die Datei
    output_path = Path(__file__).resolve().parent / "analysis_dataset_final.jsonl"
    with output_path.open("a", encoding="utf-8") as f:
        f.write(example_line + "\n")
        
    logger.info(f"Ein Trainingsbeispiel wurde in {output_path.name} gespeichert.")
    return jsonify({"status": "success"})

# --- Serverstart ---
if __name__ == '__main__':
    initialize_services()
    # Startet den Server auf http://127.0.0.1:5000
    app.run(debug=True, port=5000)

