# class_folder/game_logic/game_manager_online.py
# -*- coding: utf-8 -*-

"""
Die zentrale Logik für den ONLINE-Modus des Spiels.
Erbt die Kernlogik von BaseGameManager und interagiert mit dem
Backend-Server über eine asynchrone `ai_caller`-Funktion.
"""

import logging
import re
import json
from typing import Optional, Dict, Any, List, Callable, Coroutine

# KORREKTUR: Importiere die neue Basisklasse
from .base_game_manager import BaseGameManager
from templates.regeln import CREATIVE_PROMPTS

logger = logging.getLogger(__name__)

# KORREKTUR: Die Klasse erbt nun von BaseGameManager
class GameManagerOnline(BaseGameManager):
    """
    Orchestriert den Spielfluss im Online-Modus.
    """
    def __init__(self, ai_caller: Callable[[str, str, str], Coroutine[Any, Any, str]]):
        super().__init__() # Ruft den Konstruktor der Basisklasse auf
        self.ai_caller = ai_caller
        logger.info("GameManagerOnline initialisiert.")

    async def process_player_command(self, command: str) -> Dict[str, Any]:
        """Verarbeitet einen Spielerbefehl im Online-Modus asynchron."""
        if not self.game_state.get("world_id"):
            return {"event_type": "ERROR", "response": "Fehler: Kein Spielstand geladen."}

        world_name = self.game_state.get('world_name', 'default')
        char_info = self.game_state.get("character_info", {})
        player_name = char_info.get("name", "")
        npc_context = self._build_npc_context()
        attributes_str = ", ".join(char_info.get("attributes", {}).keys())

        # Phase 1: Analyse der Spieleraktion
        analysis_prompt = self._build_analysis_prompt(command, "", player_name, npc_context, attributes_str)
        command_json_str = await self.ai_caller(analysis_prompt, world_name, 'ANALYSIS')
        
        roll_check_command, roll_outcome, roll_feedback = None, None, ""
        try:
            match = re.search(r'\[.*\]', command_json_str, re.DOTALL)
            commands = json.loads(match.group(0)) if match else []
            roll_check_command = next((cmd for cmd in commands if cmd.get("command") == "ROLL_CHECK"), None)
            if roll_check_command:
                roll_feedback = self._execute_roll_check(roll_check_command)
                roll_outcome = "Erfolg" if "Erfolg" in roll_feedback else "Misserfolg"
        except (json.JSONDecodeError, StopIteration): pass

        # Phase 3: Kreative Erzählung
        creative_prompt = self._build_creative_rag_prompt(command, roll_outcome)
        narrative_text = await self.ai_caller(creative_prompt, world_name, 'NARRATIVE')

        # Phase 4: Analyse der neuen Erzählung
        npc_analysis_prompt = self._build_analysis_prompt("", narrative_text, player_name, npc_context, attributes_str)
        npc_command_json_str = await self.ai_caller(npc_analysis_prompt, world_name, 'ANALYSIS')
        
        all_commands = []
        if roll_check_command: all_commands.append(roll_check_command)
        try:
            match = re.search(r'\[.*\]', npc_command_json_str, re.DOTALL)
            npc_commands = json.loads(match.group(0)) if match else []
            self._process_commands_with_logic(npc_commands)
            all_commands.extend(npc_commands)
        except json.JSONDecodeError: pass

        involved_npc_ids = [npc['char_id'] for npc in self.scene_npcs]
        self.db_manager.save_event(self.game_state['world_id'], char_info['char_id'], command, narrative_text, involved_npc_ids, all_commands)
        
        level_up_signal = self._grant_xp(xp_amount=10)
        return level_up_signal or {"event_type": "STORY", "response": f"{roll_feedback}\n\n{narrative_text}".strip()}

    async def get_initial_story_prompt(self) -> Dict[str, Any]:
        """Generiert die erste Story-Antwort für den Online-Modus."""
        logger.info("Generiere initiale Story für neues Spiel (Online).")
        char_info = self.game_state.get("character_info", {})
        world_lore = self.db_manager.get_world_lore(self.game_state["world_id"])
        intro_command = f"""
        Das Abenteuer beginnt für {char_info.get('name', 'N/A')}.
        Welt-Information: {world_lore}
        Charakter-Hintergrund: {char_info.get('backstory', 'N/A')}
        Erzeuge eine passende, einleitende Szene und stelle am Ende eine Frage an den Spieler.
        """
        return await self.process_player_command(intro_command)

    async def _generate_initial_conditions(self, world_lore: str, char_backstory: str) -> Optional[Dict[str, Any]]:
        """Generiert Startbedingungen über den externen KI-Dienst."""
        system_prompt = """
            Deine einzige Aufgabe ist es, ein JSON-Objekt zu generieren. Antworte NUR mit dem reinen JSON-Code.
            Format: {"location_name": "...", "location_description": "...", "initial_state": {"health": 100, "status": "normal"}}
            """
        user_prompt = f"Welt-Lore: {world_lore}\nCharakter-Backstory: {char_backstory}"
        full_prompt = self._format_llama3_prompt(system_prompt, user_prompt)
        ai_response_str = await self.ai_caller(full_prompt, "utility_world", "ANALYSIS")
        try:
            match = re.search(r'\{.*\}', ai_response_str, re.DOTALL)
            if not match: return None
            data = json.loads(match.group(0))
            return data if 'location_name' in data and 'location_description' in data and 'initial_state' in data else None
        except json.JSONDecodeError: return None

    async def get_load_game_summary(self) -> str:
        """Generiert eine Willkommensnachricht inklusive einer KI-Zusammenfassung der letzten Ereignisse."""
        logger.info("Generating load game summary with AI context (Online).")
        
        # --- Teil 1: Statische Informationen ---
        char = self.game_state.get('character_info', {})
        loc = self.game_state.get('location_info', {})
        inventory_str = ", ".join(char.get('inventory', [])) if char.get('inventory') else "leer"

        attr = char.get('attributes', {})
        attr_str = ", ".join([f"{k}: {v}" for k, v in attr.items()])
        
        static_summary = (
            f"Willkommen zurück, {char.get('name', 'Abenteurer')}!\n\n"
            f"Du befindest dich an einem Ort namens '{loc.get('name', 'Unbekannt')}'. "
            f"{loc.get('description', 'Die Umgebung ist unklar.')}\n\n"
            f"Dein Zustand ist {char.get('state', {}).get('status', 'normal')}.\n"
            f"Deine Attribute: {attr_str}\n"
            f"Dein Inventar ist {inventory_str}.\n\n"
        )

        # --- Teil 2: KI-generierte Zusammenfassung ---
        world_id = self.game_state.get("world_id")
        if not world_id:
            return static_summary + "Was möchtest du als Nächstes tun?"

        recent_events = self.db_manager.get_last_events(world_id, limit=3)
        if not recent_events:
            return static_summary + "Was möchtest du als Nächstes tun?"

        history_parts = []
        for p_input, ai_output in recent_events:
            history_parts.append(f"- Spieler: \"{p_input}\"\n- Spielleiter: \"{ai_output}\"")
        history_str = "\n".join(history_parts)

        system_prompt = (
            "GOLDENE REGEL: Antworte IMMER NUR auf Deutsch."
            "Du bist ein hilfreicher Assistent. Deine Aufgabe ist es, eine kurze, "
            "fesselnde Zusammenfassung der letzten Ereignisse eines Abenteuers zu schreiben. "
            "Fasse die Ereignisse in 2-3 Sätzen zusammen. Sprich den Spieler direkt mit 'Du' an. "
            "Beende deine Zusammenfassung mit den Worten 'Die aktuelle Situation ist:'"
        )
        
        user_prompt = f"Hier sind die letzten Ereignisse:\n\n{history_str}"
        summary_prompt = self._format_llama3_prompt(system_prompt, user_prompt)
        
        world_name = self.game_state.get('world_name', 'default')
        # Rufe den entfernten KI-Dienst auf
        ai_summary = await self.ai_caller(summary_prompt, world_name, 'NARRATIVE')

        # --- Teil 3: Alles kombinieren ---
        full_summary = (
            f"{static_summary}"
            f"**Zusammenfassung der letzten Ereignisse:**\n{ai_summary}\n\n"
            "Was möchtest du als Nächstes tun?"
        )
        
        return full_summary

    def _grant_xp(self, xp_amount: int) -> Optional[Dict[str, Any]]:
        """Vergibt XP und gibt ein Level-Up-Signal zurück, falls eines auftritt."""
        char_info = self.game_state.get("character_info", {})
        char_id = char_info.get("char_id")
        if not char_id: return None

        new_xp = self.db_manager.add_xp_to_character(char_id, xp_to_add=xp_amount)
        char_info["xp"] = new_xp
        
        current_level = char_info.get("level", 1)
        if new_xp >= self._calculate_xp_for_next_level(current_level):
            return self._handle_level_up()
        return None

    def _handle_level_up(self) -> Dict[str, Any]:
        """Bereitet die Daten für ein Level-Up-Signal für den Server vor."""
        char_info = self.game_state.get("character_info", {})
        char_id = char_info.get("char_id")
        current_level = char_info.get("level", 1)
        new_level = current_level + 1
        excess_xp = char_info.get("xp", 0) - self._calculate_xp_for_next_level(current_level)
        self.db_manager.update_character_level_and_xp(char_id, new_level, excess_xp)
        
        logger.info(f"LEVEL UP! Charakter {char_id} hat Level {new_level} erreicht!")
        
        # Lade Charakterdaten neu, um aktuelle Attribute zu erhalten
        char_info = self.db_manager.get_full_character_info(char_id) or char_info
        
        return {
            "event_type": "LEVEL_UP",
            "message": f"Glückwunsch, du hast Level {new_level} erreicht! Du erhältst 2 Attributspunkte.",
            "data": {
                "new_level": new_level,
                "points_to_spend": 2,
                "current_attributes": char_info.get("attributes", {})
            }
        }