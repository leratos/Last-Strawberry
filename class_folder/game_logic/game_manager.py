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
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtWidgets import QWidget, QMessageBox, QInputDialog

from .base_game_manager import BaseGameManager
from ..core.inference_service import InferenceService
from ..ui.setup_dialogs import LoadGameDialog, WorldCreationDialog, CharacterCreationDialog
from ..ui.correction_dialog import CorrectionDialog
from ..ui.attribute_dialog import AttributeAllocationDialog
from ..ui.level_up_dialog import LevelUpDialog
from templates.regeln import CREATIVE_PROMPTS

logger = logging.getLogger(__name__)

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
        template_key = self.game_state.get('template_key', 'system_fantasy')
        self.inference_service.switch_to_adapter(template_key, world_name)  # Verwende template_key statt 'NARRATIVE'
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
        """Generiert eine intelligente Zusammenfassung beim Laden eines Spiels mit KI-Unterstützung."""
        logger.info("Generating load game summary with AI context (Offline).")
        
        # --- Teil 1: Statische Informationen ---
        char = self.game_state.get('character_info', {})
        loc = self.game_state.get('location_info', {})
        inventory_str = ", ".join(char.get('inventory', [])) if char.get('inventory') else "leer"

        attr = char.get('attributes', {})
        attr_str = ", ".join([f"{k}: {v}" for k, v in attr.items()])
        
        static_summary = (
            f"Willkommen zurück, {char.get('name', 'Abenteurer')}!\n\n"
            f"**Dein aktueller Status:**\n"
            f"Du befindest dich an einem Ort namens '{loc.get('name', 'Unbekannt')}'. "
            f"{loc.get('description', 'Die Umgebung ist unklar.')}\n\n"
            f"Dein Zustand ist {char.get('state', {}).get('status', 'normal')}.\n"
            f"Deine Attribute: {attr_str}\n"
            f"Dein Inventar ist {inventory_str}.\n\n"
        )

        # --- Teil 2: KI-generierte Zusammenfassung der letzten Ereignisse ---
        world_id = self.game_state.get("world_id")
        if not world_id:
            return static_summary + "Was möchtest du als Nächstes tun?"
        
        recent_events = self.db_manager.get_last_events(world_id, limit=3)
        if not recent_events:
            return static_summary + "Was möchtest du als Nächstes tun?"

        # Erstelle lokale Zusammenfassung als Standardverhalten
        local_summary = self._create_local_event_summary(recent_events)
        summary_text = local_summary

        # Versuche KI-Zusammenfassung zu generieren
        try:
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
            
            world_name = self.game_state.get('world_name', 'default')
            # Nutze die lokale KI für die Zusammenfassung
            self.inference_service.switch_to_adapter('NARRATIVE', world_name)
            summary_prompt = self._format_llama3_prompt(system_prompt, user_prompt)
            
            ai_summary = self.inference_service.generate_story_response(summary_prompt)
            
            # Verwende AI-Zusammenfassung wenn verfügbar und nicht leer
            if ai_summary and ai_summary.strip():
                summary_text = ai_summary
                logger.info("KI-Zusammenfassung erfolgreich generiert")
            else:
                logger.warning("KI gab leere Antwort - verwende lokale Zusammenfassung")
                
        except Exception as e:
            logger.error(f"Fehler bei der KI-Zusammenfassung - verwende lokale Zusammenfassung: {e}")

        # --- Teil 3: Alles kombinieren ---
        full_summary = (
            f"{static_summary}"
            f"**Zusammenfassung der letzten Ereignisse:**\n{summary_text}\n\n"
            "Was möchtest du als Nächstes tun?"
        )
        
        return full_summary

    def _create_local_event_summary(self, recent_events: List[tuple]) -> str:
        """Erstellt eine lokale Zusammenfassung der Events falls KI nicht verfügbar ist."""
        if not recent_events:
            return "Bisher sind noch keine besonderen Ereignisse aufgetreten. Die aktuelle Situation ist:"
        
        # Nimm die letzten 2-3 Events für die Zusammenfassung
        latest_events = recent_events[:3]
        
        summary_parts = []
        for i, (player_input, ai_output) in enumerate(latest_events):
            # Extrahiere wichtige Informationen aus der AI-Ausgabe
            # Kürze auf etwa 80-100 Zeichen und entferne Anführungszeichen
            clean_output = ai_output.replace('"', '').replace('\n', ' ')
            
            # Finde den ersten Satz oder kürze auf 100 Zeichen
            first_sentence_end = clean_output.find('.') 
            if first_sentence_end != -1 and first_sentence_end < 100:
                short_output = clean_output[:first_sentence_end + 1]
            else:
                short_output = clean_output[:100] + "..." if len(clean_output) > 100 else clean_output
            
            if i == 0:  # Neuestes Event
                summary_parts.append(f"Zuletzt hast du '{player_input}' getan. {short_output}")
            else:  # Ältere Events
                summary_parts.append(f"Davor: '{player_input}' - {short_output}")
        
        summary = " ".join(summary_parts)
        
        # Füge eine zusammenfassende Aussage hinzu
        if len(latest_events) >= 2:
            char_name = self.game_state.get('character_info', {}).get('name', 'Du')
            location_name = self.game_state.get('location_info', {}).get('name', 'diesem Ort')
            summary += f" {char_name} befindet sich nun an {location_name}. Die aktuelle Situation ist:"
        else:
            summary += " Die aktuelle Situation ist:"
            
        return summary

    # --- UI-bezogene Methoden ---

    def start_or_load_game(self, parent_widget: QWidget, user_id: Optional[int] = None) -> bool:
        """Öffnet den Lade-Dialog."""
        # Filtere die gespeicherten Spiele nach dem ausgewählten User, falls angegeben
        if user_id:
            saved_games = self.db_manager.get_all_worlds_and_players_for_user(user_id)
        else:
            saved_games = self.db_manager.get_all_worlds_and_players()
            
        dialog = LoadGameDialog(saved_games, parent_widget)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection:
                self.is_new_game = False
                self._load_game_state(selection['world_id'], selection['player_id'])
                return True
            else:
                return self._create_new_game_flow(parent_widget, user_id)
        return False

    def _create_new_game_flow(self, parent_widget: QWidget, user_id: Optional[int] = None) -> bool:
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
            initial_state_dict=initial_conditions['initial_state'], user_id=user_id
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