# generate_interactive_training_data.py
# -*- coding: utf-8 -*-

"""
Phase 1a & 2 kombiniert: Interaktiver Generator für Trainingsdaten

Dieses Skript generiert synthetische Dialog-Paare und führt den Experten
durch einen zweistufigen, geführten Korrekturprozess, um die Spieleraktion
und die Erzähl-Konsequenz getrennt zu bewerten.
"""

import json
import logging
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

# --- KONFIGURATION ---
ANZAHL_BEISPIELE = 50
AUSGABE_DATEI_FINAL = "analysis_dataset_final.jsonl"
AUSGABE_DATEI_POSTPONED = "postponed_for_review.jsonl"
START_PROMPT = "Du stehst vor den Toren einer alten, verwitterten Hafenstadt. Eine einzelne Wache lehnt gelangweilt am Tor. Der Geruch von Salz und Teer liegt in der Luft. Was tust du?"
SPIELER_PERSONA = "mutig und direkt"

COMMAND_SCHEMA = {
    "NPC_CREATE": {"name": "string", "backstory": "string (optional)", "disposition": "string (optional)"},
    "NPC_UPDATE": {"old_name": "string", "new_name": "string"},
    "PLAYER_MOVE": {"location_name": "string"},
    "NPC_MOVE": {"npc_name": "string", "location_name": "string (optional)"},
    "PLAYER_STATE_UPDATE": {"updates": "object"},
    "NPC_STATE_UPDATE": {"npc_name": "string", "updates": "object"},
    "ROLL_CHECK": {"attribut": "string", "schwierigkeit": "integer (optional)"},
}

# --- Skript-Code ---
try:
    project_root = Path(__file__).resolve().parent
    sys.path.append(str(project_root.parent))
    from class_folder.core.inference_service import InferenceService
    from templates.regeln import CREATIVE_PROMPTS, ANALYSIS_PROMPT_TEMPLATE
    INFERENCE_AVAILABLE = True
except ImportError as e:
    print(f"FEHLER: Notwendige Klassen konnten nicht importiert werden: {e}")
    INFERENCE_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class styles:
    HEADER = '\033[95m'; BLUE = '\033[94m'; GREEN = '\033[92m'; YELLOW = '\033[93m'; RED = '\033[91m'; ENDC = '\033[0m'; BOLD = '\033[1m'

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
        self.story_context.append({"role": "user", "content": start_text})
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
            "Gib NUR die Aktion aus. Zum Beispiel: 'Ich ziehe mein Schwert.'."
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
        """Analysiert NUR die Spieleraktion auf ROLL_CHECK und PLAYER_MOVE."""
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
        """Analysiert NUR den Erzähltext auf Konsequenzen."""
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

def create_training_example(player_action: str, narrative_text: str, final_commands: List[Dict]) -> Dict[str, str]:
    system_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        npc_context="Keine Charaktere anwesend.", player_command=player_action,
        narrative_text=narrative_text, player_name="Spieler",
        char_attributes="Stärke, Geschicklichkeit, Konstitution, Intelligenz, Weisheit, Charisma"
    )
    prompt_part = (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                   f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")
    assistant_json = json.dumps(final_commands, indent=4, ensure_ascii=False)
    full_text = f"{prompt_part}{assistant_json}<|eot_id|>"
    return {"text": full_text}

def save_to_jsonl(filepath: Path, data: Dict):
    with filepath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

def guided_correction(allowed_commands: List[str]) -> List[Dict] | None:
    corrected_commands = []
    command_list = [cmd for cmd in COMMAND_SCHEMA.keys() if cmd in allowed_commands]

    while True:
        print(styles.YELLOW + "\n--- Korrigiere/Erstelle einen Befehl ---" + styles.ENDC)
        for i, cmd_name in enumerate(command_list):
            print(f"  [{i+1}] {cmd_name}")
        
        try:
            choice_str = input(f"Wähle einen Befehl (Nummer) oder drücke Enter zum Beenden: ")
            if not choice_str: break
            choice = int(choice_str) - 1
            if not 0 <= choice < len(command_list):
                print(styles.RED + "Ungültige Auswahl." + styles.ENDC); continue
            
            command_name = command_list[choice]
            command_obj = {"command": command_name}
            schema = COMMAND_SCHEMA[command_name]

            for param, param_type in schema.items():
                # Parameter-Eingabe-Logik... (wie zuvor)
                if param_type == "object":
                    print(f"Gib die Werte für das Objekt '{param}' ein (z.B. 'health: -10, status: vergiftet'):")
                    obj_str = input(f"  > {param}: ")
                    try:
                        updates = dict(item.split(":") for item in obj_str.split(","))
                        command_obj[param] = {k.strip(): v.strip() for k, v in updates.items()}
                    except ValueError:
                        print(styles.RED + "Fehlerhaftes Format. Überspringe Parameter." + styles.ENDC)
                        command_obj[param] = {}
                else:
                    value = input(f"  > Gib den Wert für '{param}' ({param_type}) ein: ")
                    if "optional" in param_type and not value: continue
                    if "integer" in param_type and value.isdigit(): command_obj[param] = int(value)
                    else: command_obj[param] = value
            
            corrected_commands.append(command_obj)

        except (ValueError, IndexError):
            print(styles.RED + "Ungültige Eingabe." + styles.ENDC); continue
        
        add_another = input("Einen weiteren Befehl für diesen Schritt hinzufügen? [j]a/[n]ein: ").lower()
        if add_another != 'j': break
            
    return corrected_commands

def main():
    if not INFERENCE_AVAILABLE: return

    inference_service = InferenceService()
    if not inference_service.base_model_loaded: return

    erzähler = ErzählerKI(inference_service)
    spieler = SpielerKI(inference_service, SPIELER_PERSONA)
    analyst = AnalyseKI(inference_service)

    output_path_final = project_root / AUSGABE_DATEI_FINAL
    output_path_postponed = project_root / AUSGABE_DATEI_POSTPONED
    
    logger.info(f"Starte interaktive Generierung von {ANZAHL_BEISPIELE} Beispielen...")
    narrative_text = erzähler.start_story(START_PROMPT)

    for i in range(ANZAHL_BEISPIELE):
        print(f"\n{styles.HEADER}--- Generiere und bewerte Beispiel {i+1}/{ANZAHL_BEISPIELE} ---{styles.ENDC}")
        
        player_action = spieler.generate_action(narrative_text)
        
        # --- SCHRITT 1: SPIELERAKTION ANALYSIEREN ---
        print(f"\n{styles.BOLD}SPIELER-AKTION:{styles.ENDC} {player_action}")
        action_commands = analyst.analyze_player_action(player_action)
        print(f"\n{styles.BLUE}{styles.BOLD}KI-VORSCHLAG (Aktion):{styles.ENDC}")
        print(json.dumps(action_commands, indent=4, ensure_ascii=False))
        
        choice = input(f"\n{styles.YELLOW}Ist dieser Vorschlag korrekt? [j]a/[k]orrigieren: {styles.ENDC}").lower()
        if choice == 'k':
            corrected_action_commands = guided_correction(["ROLL_CHECK", "PLAYER_MOVE"])
        else:
            corrected_action_commands = action_commands
        
        # --- SCHRITT 2: ERZÄHLTEXT GENERIEREN & ANALYSIEREN ---
        next_narrative_text = erzähler.continue_story(player_action)
        print(f"\n{styles.BOLD}ERZÄHLTEXT:{styles.ENDC} {next_narrative_text}")
        narrative_commands = analyst.analyze_narrative_consequence(next_narrative_text)
        print(f"\n{styles.BLUE}{styles.BOLD}KI-VORSCHLAG (Konsequenz):{styles.ENDC}")
        print(json.dumps(narrative_commands, indent=4, ensure_ascii=False))

        choice = input(f"\n{styles.YELLOW}Ist dieser Vorschlag korrekt? [j]a/[k]orrigieren: {styles.ENDC}").lower()
        if choice == 'k':
            allowed_narrative_cmds = [cmd for cmd in COMMAND_SCHEMA.keys() if cmd not in ["ROLL_CHECK", "PLAYER_MOVE"]]
            corrected_narrative_commands = guided_correction(allowed_narrative_cmds)
        else:
            corrected_narrative_commands = narrative_commands
            
        # --- SCHRITT 3: FINALES BEISPIEL SPEICHERN ---
        final_commands = (corrected_action_commands or []) + (corrected_narrative_commands or [])
        
        print(f"\n{styles.GREEN}{styles.BOLD}FINALES TRAININGSBEISPIEL:{styles.ENDC}")
        print(json.dumps(final_commands, indent=4, ensure_ascii=False))
        
        save_choice = input(f"\n{styles.YELLOW}Dieses Beispiel speichern? [j]a/[l]öschen/[v]erschieben: {styles.ENDC}").lower()
        if save_choice == 'j':
            training_example = create_training_example(player_action, next_narrative_text, final_commands)
            save_to_jsonl(output_path_final, training_example)
            print(styles.GREEN + "-> Gespeichert." + styles.ENDC)
        elif save_choice == 'v':
            postponed_data = {
                "player_action": player_action, "narrative_text": next_narrative_text,
                "final_commands": final_commands
            }
            save_to_jsonl(output_path_postponed, postponed_data)
            print(styles.YELLOW + "-> Verschoben." + styles.ENDC)
        else:
            print(styles.RED + "-> Gelöscht." + styles.ENDC)
        
        narrative_text = next_narrative_text

    logger.info(f"Sitzung beendet. Daten in '{output_path_final}', verschobene in '{output_path_postponed}'.")

if __name__ == "__main__":
    main()
