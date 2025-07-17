# server_tools/generate_analysis_data_from_db.py
# -*- coding: utf-8 -*-

"""
Dieses Skript liest alle als "human_corrected" markierten Events aus der
Datenbank und generiert daraus eine Trainingsdatei im JSONL-Format,
die für das Fine-Tuning des Analyse-Modells verwendet werden kann.
"""

import sys
import json
import logging
from pathlib import Path

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from class_folder.core.database_manager import DatabaseManager
from templates.regeln import ANALYSIS_PROMPT_TEMPLATE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_FILE = project_root / "dm_corrected_analysis_dataset.jsonl"

def create_training_example(event: dict, char_attributes: str, player_name: str, npc_context: str) -> str:
    """Formatiert ein Event als Llama-3-Trainingsbeispiel."""
    
    system_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        player_command=event['player_input'],
        narrative_text=event['ai_output'],
        player_name=player_name,
        npc_context=npc_context,
        char_attributes=char_attributes
    )
    
    try:
        # Die korrigierten Befehle aus der DB
        assistant_output = json.dumps(json.loads(event["extracted_commands_json"]), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Skipping event {event['event_id']} due to invalid command JSON.")
        return ""

    full_prompt = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{assistant_output}<|eot_id|>"
    )
    return json.dumps({"text": full_prompt}) + "\n"

def main():
    db_manager = DatabaseManager()
    
    logger.info("Suche nach von Menschen korrigierten Events ('human_corrected')...")
    # Wir holen uns die korrigierten Events aus ALLEN Welten
    corrected_events = db_manager.get_events_for_review(label='human_corrected')

    if not corrected_events:
        logger.info("Keine neuen, von Menschen korrigierten Events gefunden.")
        return

    logger.info(f"{len(corrected_events)} korrigierte Events gefunden. Generiere Trainingsdatei unter '{OUTPUT_FILE}'...")

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for event in corrected_events:
            # Für jeden Event müssen wir den Kontext (Spielername, Attribute etc.) laden
            player_info = db_manager.get_full_character_info(event['char_id'])
            if not player_info:
                continue

            player_name = player_info.get("name", "Spieler")
            attributes_str = ", ".join(player_info.get("attributes", {}).keys())
            
            # Der NPC-Kontext ist schwieriger zu rekonstruieren, wir nehmen hier einen einfachen Platzhalter.
            # Für eine exakte Rekonstruktion müsste der Zustand der `scene_npcs` mitgespeichert werden.
            # Für das Training der Befehlsextraktion ist dies aber oft ausreichend.
            npc_context = "Kontext der anwesenden NPCs." 

            example_line = create_training_example(event, attributes_str, player_name, npc_context)
            if example_line:
                f.write(example_line)

    logger.info("Trainingsdatei wurde erfolgreich erstellt/aktualisiert.")

if __name__ == "__main__":
    main()
