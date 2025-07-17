# class_folder/game_logic/base_game_manager.py
# -*- coding: utf-8 -*-

"""
Enthält die gemeinsame Basislogik für den Offline- und Online-Game-Manager,
um Codeduplizierung zu vermeiden.
"""

import logging
import re
import json
import random
import difflib
from typing import Optional, Dict, Any, List

from ..core.database_manager import DatabaseManager
from templates.regeln import CREATIVE_PROMPTS, ANALYSIS_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

class BaseGameManager:
    """
    Eine Basisklasse, die von beiden GameManager-Varianten (Online/Offline)
    genutzt wird, um geteilte Logik zu kapseln.
    """
    def __init__(self):
        """Initialisiert die gemeinsamen Attribute."""
        self.db_manager = DatabaseManager()
        self.db_manager.setup_database()
        self.game_state: Dict[str, Any] = {}
        self.is_new_game = False
        self.scene_npcs: List[Dict[str, Any]] = []
        logger.info("BaseGameManager initialisiert.")

    def _load_game_state(self, world_id: int, player_id: int):
        """ Lädt den Spielzustand und initialisiert das Szenen-Gedächtnis. """
        logger.info(f"Lade Spielzustand für world_id={world_id}, player_id={player_id}")
        world_info = self.db_manager.get_world_info(world_id)
        char_info = self.db_manager.get_full_character_info(player_id)
        if not world_info or not char_info:
            logger.error(f"Konnte Spielzustand nicht laden. Welt- oder Charakterinfo fehlt.")
            self.game_state = {}
            return
            
        self.game_state['world_id'] = world_id
        self.game_state['world_name'] = world_info['name']
        self.game_state['character_info'] = char_info
        self.game_state['template_key'] = world_info.get('template_key', 'system_fantasy')
        
        loc_id = char_info.get('current_location_id')
        self.game_state['location_info'] = self.db_manager.get_location_info(loc_id) if loc_id else {}

        if loc_id:
            npcs_at_location = self.db_manager.get_npcs_at_location(world_id, loc_id)
            full_npc_info_list = [self.db_manager.get_full_character_info(npc['char_id']) for npc in npcs_at_location]
            self.scene_npcs = [npc for npc in full_npc_info_list if npc]
            logger.info(f"Szenen-Gedächtnis geladen: {len(self.scene_npcs)} NSC(s) am Ort {loc_id} gefunden.")
        else:
            self.scene_npcs = []
            logger.info("Spieler hat keinen gültigen Ort, Szenen-Gedächtnis ist leer.")

    def _execute_roll_check(self, roll_data: Dict[str, Any]) -> str:
        """Führt eine Würfelprobe aus und generiert die Ergebnis-Erzählung."""
        try:
            attribut = roll_data.get('attribut', 'Unbekannt')
            schwierigkeit = int(roll_data.get('schwierigkeit', 10))
            
            char_info = self.game_state.get('character_info', {})
            attributes = char_info.get('attributes', {})
            attribut_wert = attributes.get(attribut, 10)
            modifikator = (attribut_wert - 10) // 2
            
            wurf_ergebnis = random.randint(1, 20)
            gesamtergebnis = wurf_ergebnis + modifikator
            erfolg = gesamtergebnis >= schwierigkeit
            ergebnis_str = "Erfolg" if erfolg else "Misserfolg"
            
            logger.info(f"Würfelprobe für '{attribut}': Wurf {wurf_ergebnis} + Mod {modifikator} = {gesamtergebnis} vs. SG {schwierigkeit} -> {ergebnis_str}")

            return (
                f"*Probe auf {attribut} (Wert: {attribut_wert})... "
                f"(Wurf: {wurf_ergebnis} + Mod: {modifikator} = {gesamtergebnis} vs SG: {schwierigkeit} -> {ergebnis_str})*"
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Fehler bei der Verarbeitung von ROLL_CHECK: {e}")
            return "[Ein Fehler ist im Würfelsystem aufgetreten.]"

    def _build_npc_context(self) -> str:
        """Baut den Kontext-String aus dem Szenen-Gedächtnis."""
        if not self.scene_npcs:
            return "Keine Charaktere anwesend."
            
        context_parts = ["**Anwesende Charaktere (bereits in der Szene):**"]
        for npc in self.scene_npcs:
            context_parts.append(f"- {npc['name']}: {npc.get('backstory', 'Keine Beschreibung.')}")
            
        return "\n".join(context_parts)

    def _find_best_match_npc(self, name_from_ai: str) -> Optional[Dict[str, Any]]:
        """Findet den ähnlichsten NSC im aktuellen Szenen-Gedächtnis."""
        if not self.scene_npcs: return None
        best_ratio, best_match_npc = 0.6, None
        for npc in self.scene_npcs:
            ratio = difflib.SequenceMatcher(None, name_from_ai.lower(), npc['name'].lower()).ratio()
            if ratio > best_ratio:
                best_ratio, best_match_npc = ratio, npc
        if best_match_npc:
            logger.info(f"Fuzzy Match: '{name_from_ai}' -> '{best_match_npc['name']}' (Ratio: {best_ratio:.2f})")
        return best_match_npc

    def _format_llama3_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Formatiert einen Prompt für das Llama-3-Instruct-Modell."""
        if user_prompt:
            return (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                    f"{system_prompt.strip()}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
                    f"{user_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")
        else:
            return (f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                    f"{system_prompt.strip()}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")

    def _build_creative_rag_prompt(self, player_command: str, roll_outcome: Optional[str] = None) -> str:
        """ Baut den Prompt für die kreative Erzählung. """
        template_key = self.game_state.get('template_key', 'system_fantasy')
        rules = CREATIVE_PROMPTS.get(template_key, CREATIVE_PROMPTS['system_fantasy'])
        system_prompt = "\n".join(rule[1] for rule in rules)

        char_info = self.game_state.get("character_info", {})
        loc_info = self.game_state.get("location_info", {})
        recent_events = self.db_manager.get_last_events(self.game_state["world_id"], limit=3)
        
        history_str = ""
        if recent_events:
            history_parts = ["**Letzte Ereignisse:**"]
            for p_input, ai_output in recent_events:
                history_parts.append(f"- Spieler: \"{p_input}\"\n- Spielleiter: \"{ai_output}\"")
            history_str = "\n".join(history_parts) + "\n\n"
        
        roll_context_str = f"**Ergebnis der Aktion:** {roll_outcome}\n\n" if roll_outcome else ""
        context_str = "\n".join([
            "**Aktueller Kontext:**",
            f"- Spielercharakter: {char_info.get('name', 'N/A')}",
            f"- Ort: {loc_info.get('name', 'Unbekannter Ort')}",
            self._build_npc_context()
        ])
        user_prompt = f"{context_str}\n\n{roll_context_str}{history_str}**Spieler-Aktion:**\n{player_command}"
        return self._format_llama3_prompt(system_prompt, user_prompt)

    def _build_analysis_prompt(self, player_command: str, narrative_text: str, player_name: str, npc_context: str, char_attributes: str) -> str:
        """ Baut den Prompt für die Analyse-Stufe. """
        analysis_system_prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            player_command=player_command,
            narrative_text=narrative_text,
            player_name=player_name,
            npc_context=npc_context,
            char_attributes=char_attributes
        )
        return self._format_llama3_prompt(analysis_system_prompt, "")

    def _calculate_xp_for_next_level(self, level: int) -> int:
        """Berechnet die benötigten XP für das nächste Level."""
        return 100 * level

    def _process_commands_with_logic(self, commands: List[Dict[str, Any]]):
        """Verarbeitet KI-Befehle mit Python-Logik und Fuzzy-Matching."""
        if not self.game_state: return
        world_id = self.game_state['world_id']
        player_id = self.game_state['character_info']['char_id']
        
        for cmd_data in commands:
            command = cmd_data.get("command")

            if command == "ROLL_CHECK":
                continue

            if command == "NPC_CREATE":
                name = cmd_data.get("name", "Unbekannt")
                if not self._find_best_match_npc(name):
                    new_npc_id = self.db_manager.create_npc(
                        world_id=world_id,
                        name=name,
                        backstory=cmd_data.get("backstory", ""),
                        initial_state_dict={"disposition": cmd_data.get("disposition", "neutral")}
                    )
                    if new_npc_id:
                        new_npc_data = self.db_manager.get_full_character_info(new_npc_id)
                        if new_npc_data: self.scene_npcs.append(new_npc_data)
                else:
                    logger.warning(f"NPC_CREATE for '{name}' skipped, similar NPC already in scene.")

            elif command == "PLAYER_STATE_UPDATE":
                updates = cmd_data.get("updates")
                if isinstance(updates, dict):
                    self.db_manager.update_character_state(player_id, updates)

            elif command == "NPC_STATE_UPDATE":
                npc_name = cmd_data.get("npc_name")
                updates = cmd_data.get("updates")
                if npc_name and isinstance(updates, dict):
                    npc_to_update = self._find_best_match_npc(npc_name)
                    if npc_to_update:
                        self.db_manager.update_character_state(npc_to_update['char_id'], updates)

            elif command == "PLAYER_MOVE":
                location_name = cmd_data.get("location_name")
                if location_name:
                    location = self.db_manager.get_location_by_name(world_id, location_name)
                    new_loc_id = location['location_id'] if location else self.db_manager.create_location(world_id, location_name, "Ein bisher unbeschriebener Ort.")
                    if new_loc_id:
                        self.db_manager.update_character_location(player_id, new_loc_id)
                        self._load_game_state(world_id, player_id) # Szene neu laden

            elif command == "NPC_MOVE":
                npc_name = cmd_data.get("npc_name")
                location_name = cmd_data.get("location_name")
                if npc_name and location_name:
                    npc_to_move = self._find_best_match_npc(npc_name)
                    if npc_to_move:
                        location = self.db_manager.get_location_by_name(world_id, location_name)
                        new_loc_id = location['location_id'] if location else self.db_manager.create_location(world_id, location_name, "Ein bisher unbeschriebener Ort.")
                        if new_loc_id:
                            self.db_manager.update_character_location(npc_to_move['char_id'], new_loc_id)
                            # Entferne NSC aus der aktuellen Szene
                            self.scene_npcs = [npc for npc in self.scene_npcs if npc['char_id'] != npc_to_move['char_id']]