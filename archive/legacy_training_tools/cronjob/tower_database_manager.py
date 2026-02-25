# cronjob/tower_database_manager.py
# -*- coding: utf-8 -*-
"""
Manages all interactions with the Tower's central SQLite database.
This DB aggregates training data from all worlds.
"""
import sqlite3
import logging
from pathlib import Path
import json
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)

class TowerDatabaseManager:
    """Handles all database operations for the Tower's central database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        logger.info(f"TowerDatabaseManager initialized for database at: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                logger.error(f"Error connecting to tower database: {e}", exc_info=True)
                raise
        return self.conn

    def close_connection(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def setup_database(self):
        """Creates the necessary tables for the tower if they don't exist."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # The tower only needs to know about worlds and events for training
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS worlds (
                    world_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY,
                    world_id INTEGER NOT NULL,
                    player_input TEXT,
                    ai_output TEXT,
                    quality_label TEXT,
                    UNIQUE(event_id, world_id),
                    FOREIGN KEY (world_id) REFERENCES worlds (world_id)
                );
            """)
            conn.commit()
            logger.info("Tower database schema is set up.")
        except sqlite3.Error as e:
            logger.error(f"Error setting up tower database schema: {e}", exc_info=True)
            raise

    def get_or_create_world(self, world_name: str) -> Optional[int]:
        """Gets the ID of a world, creating it if it doesn't exist."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT world_id FROM worlds WHERE name = ?", (world_name,))
            row = cursor.fetchone()
            if row:
                return row['world_id']
            else:
                logger.info(f"World '{world_name}' not found in tower DB, creating it.")
                cursor.execute("INSERT INTO worlds (name) VALUES (?)", (world_name,))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error getting or creating world '{world_name}': {e}", exc_info=True)
            return None

    def import_events_from_jsonl(self, world_id: int, file_path: Path) -> int:
        """Imports events from a JSONL file into the tower database."""
        imported_count = 0
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        # Use INSERT OR IGNORE to avoid duplicates
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

    def get_events_for_training(self, world_id: int) -> List[Dict[str, Any]]:
        """Fetches all 'good' events for a specific world for training."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT player_input, ai_output FROM events WHERE world_id = ? AND quality_label = 'gut (Training)'",
                (world_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching training events for world {world_id}: {e}")
            return []
