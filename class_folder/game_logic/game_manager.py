# class_folder/game_logic/game_manager.py
# -*- coding: utf-8 -*-

"""
Die zentrale Logik für den OFFLINE-Modus des Spiels.
Erbt die Kernlogik von BaseGameManager und interagiert direkt
mit dem InferenceService und den UI-Dialogen.
"""

import logging
import re
import json
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QMessageBox, QInputDialog

# KORREKTUR: Importiere die neue Basisklasse
from .base_game_manager import BaseGameManager
from ..core.inference_service import InferenceService
from ..ui.setup_dialogs import LoadGameDialog, WorldCreationDialog, CharacterCreationDialog
from ..ui.correction_dialog import CorrectionDialog
from ..ui.attribute_dialog import AttributeAllocationDialog
from ..ui.level_up_dialog import LevelUpDialog
from templates.regeln import CREATIVE_PROMPTS

logger = logging.getLogger(__name__)

# KORREKTUR: Die Klasse erbt nun von BaseGameManager
class GameManager(BaseGameManager):
    """
    Orchestriert den Spielfluss im Offline-Modus.
    """

    def __init__(self, inference_service: InferenceService):
        super().__init__() # Ruft den Konstruktor der Basisklasse auf
        self.inference_service = inference_service
        logger.info("GameManager (Offline) initialisiert.")

    def process_player_command(self, command: str, parent_widget: QWidget) -> str:
        """Verarbeitet den Befehl des Spielers im Offline-Modus."""
        if not self.game_state.get("world_id"):
            return "Fehler: Es ist kein Spielstand geladen."

        world_name = self.game_state.get('world_name', 'default')
        char_info = self.game_state.get("character_info", {})
        player_name = char_info.get("name", "")
        npc_context = self._build_npc_context()
        attributes_str = ", ".join(char_info.get("attributes", {}).keys())

        # Phase 1: Analyse der Spieleraktion
        self.inference_service.switch_to_adapter('ANALYSIS', world_name)
        analysis_prompt = self._build_analysis_prompt(command, "", player_name, npc_context, attributes_str)
        command_json_str = self.inference_service.generate_story_response(analysis_prompt)
        
        roll_check_command, roll_outcome, roll_feedback = None, None, ""
        try:
            match = re.search(r'\[.*\]', command_json_str, re.DOTALL)
            commands = json.loads(match.group(0)) if match else []
            roll_check_command = next((cmd for cmd in commands if cmd.get("command") == "ROLL_CHECK"), None)
            if roll_check_command:
                roll_feedback = self._execute_roll_check(roll_check_command)
                roll_outcome = "Erfolg" if "Erfolg" in roll_feedback else "Misserfolg"
        except (json.JSONDecodeError, StopIteration):
            pass
        
        # Phase 3: Kreative Erzählung
        self.inference_service.switch_to_adapter('NARRATIVE', world_name)
        creative_prompt = self._build_creative_rag_prompt(command, roll_outcome)
        narrative_text = self.inference_service.generate_story_response(creative_prompt)

        # Phase 4: Analyse der neuen Erzählung
        self.inference_service.switch_to_adapter('ANALYSIS', world_name)
        npc_analysis_prompt = self._build_analysis_prompt("", narrative_text, player_name, npc_context, attributes_str)
        npc_command_json_str = self.inference_service.generate_story_response(npc_analysis_prompt)
        
        all_commands = []
        if roll_check_command: all_commands.append(roll_check_command)
        try:
            match = re.search(r'\[.*\]', npc_command_json_str, re.DOTALL)
            npc_commands = json.loads(match.group(0)) if match else []
            self._process_commands_with_logic(npc_commands)
            all_commands.extend(npc_commands)
        except json.JSONDecodeError: pass

        # Speichern und XP
        involved_npc_ids = [npc['char_id'] for npc in self.scene_npcs]
        self.db_manager.save_event(self.game_state['world_id'], char_info['char_id'], command, narrative_text, involved_npc_ids, all_commands)
        self._grant_xp(parent_widget, xp_amount=10)

        return f"{roll_feedback}\n\n{narrative_text}".strip()

    def get_initial_story_prompt(self) -> str:
        """Generiert die erste Story-Antwort für ein neues Spiel."""
        if not self.is_new_game:
            return self.get_load_game_summary()

        logger.info("Generiere initiale Story für neues Spiel (Offline).")
        char_info = self.game_state.get("character_info", {})
        world_lore = self.db_manager.get_world_lore(self.game_state["world_id"])
        
        # Statt eines komplexen Prompts wird der Start einfach als "Befehl" verarbeitet
        intro_command = f"""
        Das Abenteuer beginnt für {char_info.get('name', 'N/A')}.
        Welt-Information: {world_lore}
        Charakter-Hintergrund: {char_info.get('backstory', 'N/A')}
        Erzeuge eine passende, einleitende Szene und stelle am Ende eine Frage an den Spieler.
        """
        # Wir übergeben `self` als Platzhalter für das parent_widget
        return self.process_player_command(intro_command, self)

    def _generate_initial_conditions(self, world_lore: str, char_backstory: str) -> Optional[Dict[str, Any]]:
        """Generiert Startbedingungen mit der lokalen KI."""
        system_prompt = """
            Deine einzige Aufgabe ist es, ein JSON-Objekt zu generieren. Antworte NUR mit dem reinen JSON-Code.
            Format: {"location_name": "...", "location_description": "...", "initial_state": {"health": 100, "status": "normal"}}
            """
        user_prompt = f"Welt-Lore: {world_lore}\nCharakter-Backstory: {char_backstory}"
        full_prompt = self._format_llama3_prompt(system_prompt, user_prompt)
        ai_response_str = self.inference_service.generate_story_response(full_prompt)
        try:
            match = re.search(r'\{.*\}', ai_response_str, re.DOTALL)
            if not match: return None
            data = json.loads(match.group(0))
            return data if 'location_name' in data and 'location_description' in data and 'initial_state' in data else None
        except json.JSONDecodeError: return None

    def get_load_game_summary(self) -> str:
        """Generiert eine Zusammenfassung beim Laden eines Spiels."""
        char = self.game_state.get('character_info', {})
        loc = self.game_state.get('location_info', {})
        static_summary = (
            f"Willkommen zurück, {char.get('name', 'Abenteurer')}!\n"
            f"Du befindest dich an einem Ort namens '{loc.get('name', 'Unbekannt')}'. {loc.get('description', '')}\n"
        )
        # Für den Offline-Modus ist eine einfache Zusammenfassung ausreichend.
        return static_summary + "\nWas möchtest du als Nächstes tun?"

    # --- UI-bezogene Methoden ---

    def start_or_load_game(self, parent_widget: QWidget) -> bool:
        """Öffnet den Lade-Dialog."""
        saved_games = self.db_manager.get_all_worlds_and_players()
        dialog = LoadGameDialog(saved_games, parent_widget)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection:
                self.is_new_game = False
                self._load_game_state(selection['world_id'], selection['player_id'])
                return True
            else:
                return self._create_new_game_flow(parent_widget)
        return False

    def _create_new_game_flow(self, parent_widget: QWidget) -> bool:
        """Führt den User durch die Erstellung von Welt und Charakter."""
        self.is_new_game = True
        world_dialog = WorldCreationDialog(parent_widget)
        if not world_dialog.exec(): return False
        world_data = world_dialog.get_data()
        
        char_dialog = CharacterCreationDialog(parent_widget)
        if not char_dialog.exec(): return False
        char_data = char_dialog.get_data()
        
        attr_dialog = AttributeAllocationDialog(parent_widget)
        if not attr_dialog.exec(): return False
        char_attributes = attr_dialog.get_attributes()

        if not all([world_data, char_data, char_attributes]): return False

        initial_conditions = self._generate_initial_conditions(world_data['lore'], char_data['backstory'])
        if not initial_conditions:
            QMessageBox.critical(parent_widget, "Fehler", "KI konnte keine Startbedingungen erstellen.")
            return False
            
        new_ids = self.db_manager.create_world_and_player(
            world_name=world_data['name'], lore=world_data['lore'], template_key=world_data.get('template_key', 'system_fantasy'),
            char_name=char_data['name'], backstory=char_data['backstory'], char_attributes=char_attributes,
            initial_location_name=initial_conditions['location_name'], initial_location_desc=initial_conditions['location_description'],
            initial_state_dict=initial_conditions['initial_state']
        )
        if new_ids:
            self._load_game_state(new_ids['world_id'], new_ids['player_id'])
            return True
        return False

    def correct_last_narrative(self, parent_widget: QWidget):
        """Öffnet den Korrektur-Dialog."""
        if not self.game_state.get("world_id"): return
        event_data = self.db_manager.get_last_event_details(self.game_state["world_id"])
        if not event_data: return
        
        try: original_commands = json.loads(event_data['extracted_commands_json'])
        except (json.JSONDecodeError, TypeError): original_commands = []

        dialog = CorrectionDialog(event_data['ai_output'], original_commands, parent_widget)
        if dialog.exec():
            corrected_data = dialog.get_corrected_data()
            if corrected_data:
                self.db_manager.update_event_correction(event_data['event_id'], corrected_data[0], corrected_data[1])
                QMessageBox.information(parent_widget, "Gespeichert", "Korrektur wurde gespeichert.")

    def _grant_xp(self, parent_widget: QWidget, xp_amount: int):
        """Vergibt XP und prüft auf Level-Up."""
        char_info = self.game_state.get("character_info", {})
        char_id = char_info.get("char_id")
        if not char_id: return

        new_xp = self.db_manager.add_xp_to_character(char_id, xp_to_add=xp_amount)
        char_info["xp"] = new_xp
        
        current_level = char_info.get("level", 1)
        if new_xp >= self._calculate_xp_for_next_level(current_level):
            self._handle_level_up(parent_widget)

    def _handle_level_up(self, parent_widget: QWidget):
        """Behandelt den Stufenaufstieg des Spielers via UI-Dialog."""
        char_info = self.game_state.get("character_info", {})
        char_id = char_info.get("char_id")
        current_level = char_info.get("level", 1)
        
        new_level = current_level + 1
        excess_xp = char_info.get("xp", 0) - self._calculate_xp_for_next_level(current_level)
        
        self.db_manager.update_character_level_and_xp(char_id, new_level, excess_xp)
        
        dialog = LevelUpDialog(char_info.get("attributes", {}), 2, parent_widget)
        if dialog.exec():
            new_attributes = dialog.get_new_attributes()
            self.db_manager.update_character_attributes(char_id, new_attributes)
            QMessageBox.information(parent_widget, "Attribute verbessert!", "Deine Attribute wurden aktualisiert!")
        
        self._load_game_state(self.game_state['world_id'], char_id)