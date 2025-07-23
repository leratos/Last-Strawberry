# class/core/database_manager.py
# -*- coding: utf-8 -*-

"""
Manages all interactions with the game's SQLite database.
This includes setting up the initial schema and handling all CRUD
(Create, Read, Update, Delete) operations for worlds, characters, etc.
VERSION 2: Added character attributes.
"""

import sqlite3
import logging
import re
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple
import json

logger = logging.getLogger(__name__)
class DatabaseManager:
    """Handles all database operations for the game."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else Path("laststrawberry.db")
        self.conn: Optional[sqlite3.Connection] = None
        logger.info(f"DatabaseManager initialized for database at: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                logger.error(f"Error connecting to database: {e}", exc_info=True)
                raise
        return self.conn

    def close_connection(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def setup_database(self):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    hashed_password TEXT NOT NULL,
                    roles_json TEXT DEFAULT '[]',
                    is_active BOOLEAN DEFAULT 1
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS worlds (
                    world_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    lore_prompt TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    template_key TEXT DEFAULT 'system_fantasy'
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    char_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    is_player BOOLEAN DEFAULT 0,
                    backstory TEXT,
                    current_location_id INTEGER,
                    state_json TEXT DEFAULT '{}',
                    inventory_json TEXT DEFAULT '[]',
                    attributes_json TEXT DEFAULT '{}',
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    FOREIGN KEY (world_id) REFERENCES worlds (world_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    location_id INTEGER PRIMARY KEY AUTOINCREMENT, world_id INTEGER NOT NULL, name TEXT NOT NULL,
                    description TEXT, rules_json TEXT DEFAULT '{}', connections_json TEXT DEFAULT '{}',
                    UNIQUE(world_id, name),
                    FOREIGN KEY (world_id) REFERENCES worlds (world_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, world_id INTEGER NOT NULL, char_id INTEGER,
                    player_input TEXT, ai_output TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quality_label TEXT DEFAULT 'neutral',
                    involved_npcs_json TEXT DEFAULT '[]',
                    extracted_commands_json TEXT DEFAULT '[]',
                    FOREIGN KEY (world_id) REFERENCES worlds (world_id),
                    FOREIGN KEY (char_id) REFERENCES characters (char_id)
                );
            """)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error setting up database schema: {e}", exc_info=True)
            raise

    def create_world_and_player(
        self,
        world_name: str,
        lore: str,
        template_key: str,
        user_id: int,
        char_name: str,
        backstory: str,
        char_attributes: Dict[str, Any],
        initial_location_name: str,
        initial_location_desc: str,
        initial_state_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a new world and a player character linked to a user.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO worlds (name, lore_prompt, template_key) VALUES (?, ?, ?)", (world_name, lore, template_key))
            world_id = cursor.lastrowid
            
            loc_id = self.create_location(world_id, initial_location_name, initial_location_desc)
            if not loc_id:
                loc_id = self.create_location(world_id, "Leere", "Ein undefinierter Ort.")
            
            initial_state_json = json.dumps(initial_state_dict)
            attributes_json = json.dumps(char_attributes)

            cursor.execute(
                """INSERT INTO characters
                   (world_id, user_id, name, is_player, backstory, current_location_id, state_json, inventory_json, attributes_json)
                   VALUES (?, ?, ?, 1, ?, ?, ?, '[]', ?)""",
                (world_id, user_id, char_name, backstory, loc_id, initial_state_json, attributes_json)
            )
            char_id = cursor.lastrowid
            conn.commit()
            return {"world_id": world_id, "player_id": char_id, "location_id": loc_id}
        except sqlite3.Error as e:
            logger.error(f"Error creating world and player: {e}", exc_info=True)
            conn.rollback()
            return None

    def is_user_authorized_for_player(self, user_id: int, char_id: int) -> bool:
        """
        Checks if a user is the owner of a specific character.
        Admins are implicitly authorized (checked in API layer).
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM characters WHERE char_id = ?", (char_id,))
            row = cursor.fetchone()
            if not row:
                return False # Character does not exist
            return row['user_id'] == user_id
        except sqlite3.Error as e:
            logger.error(f"DB error during authorization check for user {user_id} and char {char_id}: {e}")
            return False

    def get_npcs_at_location(self, world_id: int, location_id: int) -> List[Dict[str, Any]]:
        """NEU: Holt alle NSCs an einem bestimmten Ort."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM characters WHERE world_id = ? AND current_location_id = ? AND is_player = 0",
                (world_id, location_id)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching NPCs at location {location_id}: {e}")
            return []

    def get_world_info(self, world_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM worlds WHERE world_id = ?", (world_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"DB error fetching info for world {world_id}: {e}")
            return None

    def create_npc(self, world_id: int, name: str, backstory: str, initial_state_dict: Dict[str, Any]) -> Optional[int]:
        """ Erstellt einen neuen NSC und speichert seine Beschreibung in 'backstory'. """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            state_json = json.dumps(initial_state_dict)
            player_loc_id = self.get_player_location(world_id)
            system_user_id = 1 
            cursor.execute(
                "INSERT INTO characters (world_id, user_id, name, is_player, backstory, current_location_id, state_json) VALUES (?, ?, ?, 0, ?, ?, ?)",
                (world_id, system_user_id, name, backstory, player_loc_id, state_json)
            )

            conn.commit()
            npc_id = cursor.lastrowid
            logger.info(f"NSC '{name}' (ID: {npc_id}) wurde in Welt {world_id} erstellt und User {system_user_id} zugeordnet.")
            return npc_id
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Erstellen von NSC '{name}': {e}", exc_info=True)
            conn.rollback()
            return None

    def get_player_location(self, world_id: int) -> Optional[int]:
        """Hilfsfunktion, um den Ort des Spielers zu finden."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT current_location_id FROM characters WHERE world_id = ? AND is_player = 1", (world_id,))
            row = cursor.fetchone()
            return row['current_location_id'] if row else None
        except sqlite3.Error:
            return None

    def get_full_character_info(self, char_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM characters WHERE char_id = ?", (char_id,))
            row = cursor.fetchone()
            if row:
                char_data = dict(row)
                char_data['state'] = json.loads(char_data.pop('state_json', '{}') or '{}')
                char_data['inventory'] = json.loads(char_data.pop('inventory_json', '[]') or '[]')
                char_data['attributes'] = json.loads(char_data.pop('attributes_json', '{}') or '{}')
                return char_data
            return None
        except sqlite3.Error: return None

    def find_npc_by_name(self, world_id: int, name: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM characters WHERE world_id = ? AND name = ? AND is_player = 0",
                (world_id, name)
            )
            row = cursor.fetchone()
            if row:
                npc_data = dict(row)
                npc_data['state'] = json.loads(npc_data.pop('state_json', '{}') or '{}')
                npc_data['inventory'] = json.loads(npc_data.pop('inventory_json', '[]') or '[]')
                npc_data['attributes'] = json.loads(npc_data.pop('attributes_json', '{}') or '{}')
                return npc_data
            return None
        except sqlite3.Error as e:
            logger.error(f"Fehler bei der Suche nach NSC '{name}': {e}", exc_info=True)
            return None

    def get_last_events(self, world_id: int, limit: int = 3) -> List[Tuple[str, str]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT player_input, ai_output FROM events WHERE world_id = ? ORDER BY timestamp DESC LIMIT ?", (world_id, limit))
            events = cursor.fetchall()
            return [tuple(row) for row in reversed(events)]
        except sqlite3.Error: return []

    def get_all_worlds_and_players(self) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    w.world_id, 
                    w.name as world_name, 
                    c.char_id as player_id, 
                    c.name as player_name,
                    u.username as owner_name
                FROM worlds w 
                JOIN characters c ON w.world_id = c.world_id
                JOIN users u ON c.user_id = u.user_id
                WHERE c.is_player = 1 ORDER BY w.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"DB error fetching worlds and players: {e}")
            return []
            
    def save_world_rules_as_template(self, world_id: int, new_template_name: str) -> bool:
        sanitized_name = re.sub(r'\s+', '_', new_template_name.strip())
        sanitized_name = re.sub(r'[^\w-]', '', sanitized_name)
        full_template_name = f"user_{sanitized_name.lower()}"
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM prompt_rules WHERE template_name = ? LIMIT 1", (full_template_name,))
            if cursor.fetchone():
                logger.warning(f"A template named '{full_template_name}' already exists. Aborting.")
                return False
            world_rules = self.get_rules_for_world(world_id)
            if not world_rules:
                logger.warning(f"No rules found for world_id {world_id} to save as template.")
                return False
            logger.info(f"Saving rules from world {world_id} as new template '{full_template_name}'")
            cursor.execute(
                "SELECT rule_type, content, order_index FROM prompt_rules WHERE world_id = ? AND is_active = 1",
                (world_id,)
            )
            rules_to_copy = cursor.fetchall()
            for rule in rules_to_copy:
                cursor.execute(
                    "INSERT INTO prompt_rules (world_id, template_name, rule_type, content, order_index) VALUES (?, ?, ?, ?, ?)",
                    (None, full_template_name, rule['rule_type'], rule['content'], rule['order_index'])
                )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving rules as template: {e}", exc_info=True)
            conn.rollback()
            return False

    def get_all_template_names(self) -> List[str]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT template_name FROM prompt_rules WHERE template_name IS NOT NULL ORDER BY template_name")
            return [row['template_name'] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching template names: {e}")
            return []

    def get_rules_for_template(self, template_name: str) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content, order_index, is_active, rule_type FROM prompt_rules WHERE template_name = ? ORDER BY order_index ASC",
                (template_name,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching rules for template {template_name}: {e}")
            return []

    def get_full_rules_for_world(self, world_id: int) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rule_id, content, order_index, is_active, rule_type FROM prompt_rules WHERE world_id = ? ORDER BY order_index ASC",
                (world_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching full rules for world {world_id}: {e}")
            return []

    def update_world_rules(self, world_id: int, rules: List[Dict[str, Any]]) -> bool:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            cursor.execute("DELETE FROM prompt_rules WHERE world_id = ?", (world_id,))
            for rule in rules:
                cursor.execute(
                    "INSERT INTO prompt_rules (world_id, rule_type, content, order_index, is_active) VALUES (?, ?, ?, ?, ?)",
                    (world_id, rule.get('rule_type', 'RULE'), rule['content'], rule['order_index'], rule.get('is_active', True))
                )
            conn.commit()
            logger.info(f"Successfully updated rules for world_id {world_id}.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating world rules for world_id {world_id}: {e}", exc_info=True)
            conn.rollback()
            return False
            
    def get_rules_for_world(self, world_id: int) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content FROM prompt_rules WHERE world_id = ? AND is_active = 1 ORDER BY order_index ASC",
                (world_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching rules for world {world_id}: {e}")
            return []

    def update_npc_state(self, npc_id: int, updates_dict: Dict[str, Any]):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT state_json FROM characters WHERE char_id = ?", (npc_id,))
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Konnte NSC mit ID {npc_id} für Update nicht finden.")
                return
            current_state = json.loads(row['state_json'] or '{}')
            notes_to_add = updates_dict.pop("notes_add", None)
            current_state.update(updates_dict)
            if notes_to_add:
                if 'notes' not in current_state:
                    current_state['notes'] = []
                if notes_to_add not in current_state['notes']:
                    current_state['notes'].append(notes_to_add)
            new_state_json = json.dumps(current_state)
            cursor.execute("UPDATE characters SET state_json = ? WHERE char_id = ?", (new_state_json, npc_id))
            conn.commit()
            logger.info(f"Zustand für NSC ID {npc_id} erfolgreich aktualisiert.")
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren von NSC ID {npc_id}: {e}", exc_info=True)
            conn.rollback()

    def get_location_info(self, location_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM locations WHERE location_id = ?", (location_id,))
            row = cursor.fetchone()
            if row:
                loc_data = dict(row)
                loc_data['rules'] = json.loads(loc_data.pop('rules_json', '{}') or '{}')
                loc_data['connections'] = json.loads(loc_data.pop('connections_json', '{}') or '{}')
                return loc_data
            return None
        except sqlite3.Error: return None

    def save_event(self, world_id: int, char_id: int, player_input: str, ai_output: str, involved_npc_ids: List[int], extracted_commands: List[Dict[str, Any]]):
        """Speichert ein Event inklusive der anwesenden NSC-IDs und der extrahierten Befehle."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            involved_npcs_json = json.dumps(involved_npc_ids)
            commands_json = json.dumps(extracted_commands, indent=2)
            cursor.execute(
                "INSERT INTO events (world_id, char_id, player_input, ai_output, involved_npcs_json, extracted_commands_json) VALUES (?, ?, ?, ?, ?, ?)",
                (world_id, char_id, player_input, ai_output, involved_npcs_json, commands_json)
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving event to database: {e}", exc_info=True)

    def create_location(self, world_id: int, name: str, description: str) -> Optional[int]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO locations (world_id, name, description) VALUES (?, ?, ?)", (world_id, name, description))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error:
            conn.rollback()
            return None

    def update_npc_name(self, npc_id: int, new_name: str) -> bool:
        """Aktualisiert den Namen eines NSCs anhand seiner ID."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE characters SET name = ? WHERE char_id = ?", (new_name, npc_id))
            if cursor.rowcount == 0:
                logger.warning(f"Konnte NSC mit ID {npc_id} zum Umbenennen nicht finden.")
                return False
            conn.commit()
            logger.info(f"NSC ID {npc_id} wurde erfolgreich in '{new_name}' umbenannt.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Umbenennen von NSC ID {npc_id}: {e}", exc_info=True)
            conn.rollback()
            return False

    def get_location_by_name(self, world_id: int, name: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM locations WHERE world_id = ? AND name = ?", (world_id, name))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error: return None

    def update_character_inventory(self, char_id: int, action: str, item_name: str):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT inventory_json FROM characters WHERE char_id = ?", (char_id,))
            row = cursor.fetchone()
            if not row: return
            inventory = json.loads(row['inventory_json'] or '[]')
            if action.upper() == 'ADD': inventory.append(item_name)
            elif action.upper() == 'REMOVE' and item_name in inventory: inventory.remove(item_name)
            cursor.execute("UPDATE characters SET inventory_json = ? WHERE char_id = ?", (json.dumps(inventory), char_id))
            conn.commit()
        except sqlite3.Error: conn.rollback()

    def update_character_state(self, char_id: int, state_updates: Dict[str, Any]):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT state_json FROM characters WHERE char_id = ?", (char_id,))
            row = cursor.fetchone()
            if not row: return
            current_state = json.loads(row['state_json'] or '{}')
            current_state.update(state_updates)
            cursor.execute("UPDATE characters SET state_json = ? WHERE char_id = ?", (json.dumps(current_state), char_id))
            conn.commit()
        except sqlite3.Error: conn.rollback()

    def update_character_location(self, char_id: int, new_location_id: int):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE characters SET current_location_id = ? WHERE char_id = ?", (new_location_id, char_id))
            conn.commit()
        except sqlite3.Error: conn.rollback()
            
    def get_world_lore(self, world_id: int) -> Optional[str]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT lore_prompt FROM worlds WHERE world_id = ?", (world_id,))
            row = cursor.fetchone()
            return row['lore_prompt'] if row else None
        except sqlite3.Error as e:
            logger.error(f"DB error fetching lore for world {world_id}: {e}")
            return None

    def get_events_for_review(self, label: str = 'neutral', world_id: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM events WHERE quality_label = ? "
            params = [label]
            if world_id is not None:
                query += "AND world_id = ? "
                params.append(world_id)
            query += "ORDER BY timestamp ASC"
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"DB error fetching events for review with label '{label}': {e}")
            return []

    def update_event_quality(self, event_id: int, new_label: str) -> bool:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET quality_label = ? WHERE event_id = ?", (new_label, event_id))
            conn.commit()
            logger.info(f"Updated quality label for event_id {event_id} to '{new_label}'.")
            return True
        except sqlite3.Error as e:
            logger.error(f"DB error updating quality for event_id {event_id}: {e}")
            conn.rollback()
            return False

    def import_events_from_jsonl(self, world_id: int, file_path: Path) -> int:
        imported_count = 0
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO events (event_id, world_id, player_input, ai_output, quality_label)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                event['event_id'],
                                world_id,
                                event['player_input'],
                                event['ai_output'],
                                event.get('quality_label', 'gut (Training)')
                            )
                        )
                        if cursor.rowcount > 0:
                            imported_count += 1
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping malformed line in {file_path.name}: {e}")
            conn.commit()
            logger.info(f"Imported {imported_count} new events from '{file_path.name}'.")
        except sqlite3.Error as e:
            logger.error(f"DB error during import from '{file_path.name}': {e}", exc_info=True)
            conn.rollback()
        return imported_count

    def get_or_create_world(self, world_name: str) -> Optional[int]:
        world_info = self.get_world_by_name(world_name)
        if world_info:
            return world_info['world_id']
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            placeholder_lore = f"This world ('{world_name}') was created automatically by the Tower process. Lore is managed on the client."
            cursor.execute(
                "INSERT INTO worlds (name, lore_prompt) VALUES (?, ?)",
                (world_name, placeholder_lore)
            )
            conn.commit()
            new_world_id = cursor.lastrowid
            logger.info(f"World '{world_name}' not found in tower DB, created it with ID: {new_world_id}.")
            return new_world_id
        except sqlite3.Error as e:
            logger.error(f"Error creating world '{world_name}' in tower DB: {e}", exc_info=True)
            conn.rollback()
            return None

    def get_world_by_name(self, world_name: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM worlds WHERE name = ?", (world_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"DB error fetching world by name '{world_name}': {e}")
            return None

    def get_last_event_with_npcs(self, world_id: int) -> Optional[Dict[str, Any]]:
        """Holt das letzte Event und die daran beteiligten NSCs."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT player_input, ai_output, involved_npcs_json FROM events WHERE world_id = ? ORDER BY timestamp DESC LIMIT 1",
                (world_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            event_data = dict(row)
            npc_ids = json.loads(event_data.get('involved_npcs_json', '[]'))
            
            npcs = []
            if npc_ids:
                # Erstelle eine Abfrage mit Platzhaltern für die IDs
                placeholders = ','.join('?' for _ in npc_ids)
                cursor.execute(f"SELECT char_id, name, backstory FROM characters WHERE char_id IN ({placeholders})", npc_ids)
                npcs = [dict(r) for r in cursor.fetchall()]
            
            event_data['involved_npcs'] = npcs
            return event_data

        except sqlite3.Error as e:
            logger.error(f"Error fetching last event with NPCs: {e}")
            return None

    def update_event_text_and_quality(self, event_id: int, corrected_text: str, new_label: str = "human_corrected") -> bool:
        """Aktualisiert den KI-Output eines Events und sein Qualitätslabel."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE events SET ai_output = ?, quality_label = ? WHERE event_id = ?",
                (corrected_text, new_label, event_id)
            )
            conn.commit()
            if cursor.rowcount == 0:
                logger.warning(f"Konnte Event mit ID {event_id} für Korrektur nicht finden.")
                return False
            logger.info(f"Event {event_id} erfolgreich mit neuem Text und Label '{new_label}' aktualisiert.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren von Event {event_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        
    def get_last_event_details(self, world_id: int) -> Optional[Dict[str, Any]]:
        """Holt die Details (ID, ai_output) des letzten Events für eine Welt."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_id, ai_output, extracted_commands_json FROM events WHERE world_id = ? ORDER BY event_id DESC LIMIT 1",
                (world_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Holen des letzten Events für Welt {world_id}: {e}")
            return None

    def update_event_correction(self, event_id: int, corrected_text: str, corrected_commands: List[Dict[str, Any]]) -> bool:
        """Aktualisiert den Text und die Befehle eines Events und markiert es als korrigiert."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            commands_json = json.dumps(corrected_commands, indent=2, ensure_ascii=False)
            
            cursor.execute(
                "UPDATE events SET ai_output = ?, extracted_commands_json = ?, quality_label = ? WHERE event_id = ?",
                (corrected_text, commands_json, "human_corrected", event_id)
            )
            conn.commit()
            if cursor.rowcount == 0:
                logger.warning(f"Konnte Event mit ID {event_id} für Korrektur nicht finden.")
                return False
            logger.info(f"Event {event_id} erfolgreich mit neuem Text und Befehlen aktualisiert.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren von Event {event_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        
    def create_user(self, username: str, hashed_password: str, roles: List[str]) -> Optional[int]:
        """Erstellt einen neuen Benutzer und gibt seine ID zurück."""
        roles_json = json.dumps(roles)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, hashed_password, roles_json) VALUES (?, ?, ?)",
                (username, hashed_password, roles_json)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.error(f"Benutzername '{username}' existiert bereits.")
            return None
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Erstellen des Benutzers: {e}", exc_info=True)
            conn.rollback()
            return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Holt einen Benutzer anhand seines Benutzernamens."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                user_data = dict(row)
                user_data['roles'] = json.loads(user_data.pop('roles_json', '[]'))
                return user_data
            return None
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Abrufen des Benutzers '{username}': {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Holt einen Benutzer anhand seiner ID."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                user_data = dict(row)
                user_data['roles'] = json.loads(user_data.pop('roles_json', '[]'))
                return user_data
            return None
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Abrufen von Benutzer-ID {user_id}: {e}")
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Holt eine Liste aller Benutzer aus der Datenbank."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, username, roles_json, is_active FROM users")
            users = []
            for row in cursor.fetchall():
                user_data = dict(row)
                user_data['roles'] = json.loads(user_data.pop('roles_json', '[]'))
                users.append(user_data)
            return users
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Abrufen aller Benutzer: {e}")
            return []

    def update_user_password(self, user_id: int, new_hashed_password: str) -> bool:
        """Aktualisiert das Passwort eines Benutzers."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET hashed_password = ? WHERE user_id = ?", (new_hashed_password, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren des Passworts für UserID {user_id}: {e}")
            conn.rollback()
            return False

    def update_user_roles(self, user_id: int, roles: List[str]) -> bool:
        """Aktualisiert die Rollen eines Benutzers."""
        roles_json = json.dumps(roles)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET roles_json = ? WHERE user_id = ?", (roles_json, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren der Rollen für UserID {user_id}: {e}")
            conn.rollback()
            return False

    def update_user_status(self, user_id: int, is_active: bool) -> bool:
        """Aktiviert oder deaktiviert einen Benutzer."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren des Status für UserID {user_id}: {e}")
            conn.rollback()
            return False

    def add_xp_to_character(self, char_id: int, xp_to_add: int) -> int:
        """Fügt einem Charakter Erfahrungspunkte hinzu und gibt die neuen Gesamt-XP zurück."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Hole die aktuellen XP
            cursor.execute("SELECT xp FROM characters WHERE char_id = ?", (char_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            
            current_xp = row['xp']
            new_xp = current_xp + xp_to_add
            
            # Aktualisiere die XP in der Datenbank
            cursor.execute("UPDATE characters SET xp = ? WHERE char_id = ?", (new_xp, char_id))
            conn.commit()
            
            logger.info(f"Charakter {char_id} erhält {xp_to_add} XP. Gesamt-XP: {new_xp}")
            return new_xp
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Hinzufügen von XP für Charakter {char_id}: {e}")
            conn.rollback()
            return 0
        
    def update_character_level_and_xp(self, char_id: int, new_level: int, new_xp: int) -> bool:
        """Aktualisiert den Level und die Erfahrungspunkte eines Charakters."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE characters SET level = ?, xp = ? WHERE char_id = ?", (new_level, new_xp, char_id))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren von Level und XP für Charakter {char_id}: {e}")
            conn.rollback()
            return False

    # --- Story Export & Statistics Methods ---
    
    def get_story_events_for_world(self, world_id: int) -> List[Dict[str, Any]]:
        """Holt alle Story-Events für eine Welt in chronologischer Reihenfolge."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT event_id, world_id, player_id, event_type, content, timestamp, metadata
                FROM events 
                WHERE world_id = ? 
                ORDER BY timestamp ASC
            """, (world_id,))
            
            events = []
            for row in cursor.fetchall():
                event = {
                    "event_id": row['event_id'],
                    "world_id": row['world_id'],
                    "player_id": row['player_id'],
                    "event_type": row['event_type'],
                    "content": row['content'],
                    "timestamp": row['timestamp'],
                    "metadata": json.loads(row['metadata']) if row['metadata'] else {}
                }
                events.append(event)
            
            return events
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Laden der Story-Events für Welt {world_id}: {e}")
            return []

    def get_world_info(self, world_id: int) -> Dict[str, Any]:
        """Holt detaillierte Informationen über eine Welt."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT world_id, world_name, lore, created_at, is_active
                FROM worlds 
                WHERE world_id = ?
            """, (world_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "world_id": row['world_id'],
                    "world_name": row['world_name'],
                    "lore": row['lore'],
                    "created_at": row['created_at'],
                    "is_active": row['is_active']
                }
            return {}
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Laden der Welt-Info für {world_id}: {e}")
            return {}

    def get_player_info_for_world(self, world_id: int) -> Dict[str, Any]:
        """Holt Spieler-Informationen für eine Welt."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.char_id, c.character_name, c.backstory, c.level, c.xp,
                       c.strength, c.dexterity, c.constitution, c.intelligence, 
                       c.wisdom, c.charisma, c.perception
                FROM characters c
                WHERE c.world_id = ?
                LIMIT 1
            """, (world_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "char_id": row['char_id'],
                    "character_name": row['character_name'],
                    "backstory": row['backstory'],
                    "level": row['level'],
                    "xp": row['xp'],
                    "attributes": {
                        "strength": row['strength'],
                        "dexterity": row['dexterity'],
                        "constitution": row['constitution'],
                        "intelligence": row['intelligence'],
                        "wisdom": row['wisdom'],
                        "charisma": row['charisma'],
                        "perception": row['perception']
                    }
                }
            return {}
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Laden der Spieler-Info für Welt {world_id}: {e}")
            return {}

    def get_world_statistics(self, world_id: int) -> Dict[str, Any]:
        """Berechnet und gibt Statistiken für eine Welt zurück."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Gesamt-Events
            cursor.execute("SELECT COUNT(*) as total_events FROM events WHERE world_id = ?", (world_id,))
            total_events = cursor.fetchone()['total_events']
            
            # Events nach Typ
            cursor.execute("""
                SELECT event_type, COUNT(*) as count 
                FROM events 
                WHERE world_id = ? 
                GROUP BY event_type
            """, (world_id,))
            events_by_type = {row['event_type']: row['count'] for row in cursor.fetchall()}
            
            # Erstes und letztes Event
            cursor.execute("""
                SELECT MIN(timestamp) as first_event, MAX(timestamp) as last_event 
                FROM events 
                WHERE world_id = ?
            """, (world_id,))
            event_times = cursor.fetchone()
            
            # Charakter-Level und XP
            cursor.execute("""
                SELECT level, xp 
                FROM characters 
                WHERE world_id = ? 
                LIMIT 1
            """, (world_id,))
            char_info = cursor.fetchone()
            
            # Spielzeit berechnen (grob basierend auf Events)
            playtime_hours = 0
            if event_times['first_event'] and event_times['last_event']:
                from datetime import datetime
                first = datetime.fromisoformat(event_times['first_event'])
                last = datetime.fromisoformat(event_times['last_event'])
                playtime_hours = round((last - first).total_seconds() / 3600, 1)
            
            return {
                "total_events": total_events,
                "events_by_type": events_by_type,
                "first_event": event_times['first_event'],
                "last_event": event_times['last_event'],
                "estimated_playtime_hours": playtime_hours,
                "character_level": char_info['level'] if char_info else 1,
                "character_xp": char_info['xp'] if char_info else 0,
                "player_actions": events_by_type.get('PLAYER_ACTION', 0),
                "story_events": events_by_type.get('STORY', 0),
                "level_ups": events_by_type.get('LEVEL_UP', 0)
            }
            
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Berechnen der Statistiken für Welt {world_id}: {e}")
            return {}
            return False

    def update_character_attributes(self, char_id: int, new_attributes: Dict[str, int]) -> bool:
        """Aktualisiert die Attributwerte eines Charakters in der Datenbank."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            attributes_json = json.dumps(new_attributes)
            cursor.execute("UPDATE characters SET attributes_json = ? WHERE char_id = ?", (attributes_json, char_id))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Fehler beim Aktualisieren der Attribute für Charakter {char_id}: {e}")
            conn.rollback()
            return False
