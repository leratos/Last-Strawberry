from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from ls_shared_schemas.character import CharacterResources, CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.npc_memory import NPCProfile
from ls_shared_schemas.world import JournalEntryRecord, WorldBootstrapRequest, WorldBootstrapResult, WorldSessionResponse


def _utc_iso_now() -> str:
    return datetime.now(UTC).isoformat()


class WorldRepository:
    """SQLite persistence for Greenfield G1 world bootstrap sessions."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worlds (
                    world_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    world_seed_json TEXT NOT NULL,
                    initial_narrative TEXT NOT NULL,
                    player_orientation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS world_characters (
                    world_character_id TEXT PRIMARY KEY,
                    world_id TEXT NOT NULL,
                    character_state_json TEXT NOT NULL,
                    inventory_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    journal_entry_id TEXT PRIMARY KEY,
                    world_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_world_characters_world_id ON world_characters(world_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_entries_world_id ON journal_entries(world_id, created_at);")
            conn.commit()

    def create_world_session(
        self,
        *,
        request: WorldBootstrapRequest,
        bootstrap: WorldBootstrapResult,
    ) -> WorldSessionResponse:
        created_at = _utc_iso_now()
        world_id = f"world-{uuid4().hex[:12]}"
        world_character_id = f"wc-{uuid4().hex[:12]}"

        world_seed = bootstrap.world_seed.model_copy(deep=True)
        world_seed.world_id = world_id
        world_seed.starter_npcs = [self._normalize_npc_profile(npc) for npc in world_seed.starter_npcs]
        world_seed.starter_inventory = [self._normalize_inventory_item(item) for item in world_seed.starter_inventory]

        template = world_seed.created_character_seed.template
        initial_state = CharacterState(
            world_character_id=world_character_id,
            name=world_seed.created_character_seed.display_name,
            level=1,
            xp=0,
            location_name=world_seed.start_location_name,
            attributes=template.attributes.model_copy(deep=True),
            resources=CharacterResources(hp=10, max_hp=10, stamina=10, max_stamina=10, focus=3, max_focus=3),
            status_effects=[],
        )

        journal_entries = [
            JournalEntryRecord(
                journal_entry_id=f"journal-{uuid4().hex[:12]}",
                world_id=world_id,
                entry_type="system_world_bootstrap",
                text=bootstrap.initial_narrative,
            )
        ]

        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    """
                    INSERT INTO worlds (
                        world_id, user_id, tone, difficulty, world_seed_json,
                        initial_narrative, player_orientation_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        world_id,
                        request.user_id,
                        request.tone,
                        request.difficulty,
                        world_seed.model_dump_json(),
                        bootstrap.initial_narrative,
                        json.dumps(bootstrap.player_orientation, ensure_ascii=True),
                        created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO world_characters (
                        world_character_id, world_id, character_state_json, inventory_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        world_character_id,
                        world_id,
                        initial_state.model_dump_json(),
                        json.dumps([item.model_dump(mode="json") for item in world_seed.starter_inventory], ensure_ascii=True),
                        created_at,
                    ),
                )
                for entry in journal_entries:
                    conn.execute(
                        """
                        INSERT INTO journal_entries (journal_entry_id, world_id, entry_type, text, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            entry.journal_entry_id,
                            world_id,
                            entry.entry_type,
                            entry.text,
                            entry.created_at.isoformat(),
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return WorldSessionResponse(
            world_id=world_id,
            user_id=request.user_id,
            tone=request.tone,
            difficulty=request.difficulty,
            world_seed=world_seed,
            initial_narrative=bootstrap.initial_narrative,
            player_orientation=bootstrap.player_orientation,
            character_state=initial_state,
            inventory=world_seed.starter_inventory,
            journal=journal_entries,
            created_at=datetime.fromisoformat(created_at),
        )

    def get_world_session(self, world_id: str) -> WorldSessionResponse | None:
        with self._connect() as conn:
            world_row = conn.execute("SELECT * FROM worlds WHERE world_id = ?", (world_id,)).fetchone()
            if world_row is None:
                return None

            character_row = conn.execute(
                "SELECT * FROM world_characters WHERE world_id = ? ORDER BY created_at ASC LIMIT 1",
                (world_id,),
            ).fetchone()
            if character_row is None:
                return None

            journal_rows = conn.execute(
                "SELECT * FROM journal_entries WHERE world_id = ? ORDER BY created_at ASC",
                (world_id,),
            ).fetchall()

        world_seed = self._load_world_seed_json(str(world_row["world_seed_json"]))
        character_state = CharacterState.model_validate_json(str(character_row["character_state_json"]))
        inventory = self._load_inventory_json(str(character_row["inventory_json"]))
        journal = [self._journal_from_row(row) for row in journal_rows]

        return WorldSessionResponse(
            world_id=str(world_row["world_id"]),
            user_id=str(world_row["user_id"]),
            tone=str(world_row["tone"]),
            difficulty=str(world_row["difficulty"]),
            world_seed=world_seed,
            initial_narrative=str(world_row["initial_narrative"]),
            player_orientation=json.loads(str(world_row["player_orientation_json"])),
            character_state=character_state,
            inventory=inventory,
            journal=journal,
            created_at=datetime.fromisoformat(str(world_row["created_at"])),
        )

    @staticmethod
    def _normalize_npc_profile(npc: NPCProfile) -> NPCProfile:
        if npc.npc_id and not npc.npc_id.startswith("npc-"):
            return npc.model_copy(update={"npc_id": f"npc-{uuid4().hex[:10]}"})
        if npc.npc_id == "npc-market-guide":
            return npc.model_copy(update={"npc_id": f"npc-{uuid4().hex[:10]}"})
        return npc

    @staticmethod
    def _normalize_inventory_item(item: InventoryItemInstance) -> InventoryItemInstance:
        updates: dict[str, object] = {}
        if item.inventory_item_id.startswith("inv-starter-") or item.inventory_item_id.startswith("inv-"):
            updates["inventory_item_id"] = f"inv-{uuid4().hex[:10]}"
        return item.model_copy(update=updates) if updates else item

    @staticmethod
    def _load_world_seed_json(raw_json: str):
        from ls_shared_schemas.world import WorldSeed

        return WorldSeed.model_validate_json(raw_json)

    @staticmethod
    def _load_inventory_json(raw_json: str) -> list[InventoryItemInstance]:
        payload = json.loads(raw_json)
        return [InventoryItemInstance.model_validate(item) for item in payload]

    @staticmethod
    def _journal_from_row(row: sqlite3.Row) -> JournalEntryRecord:
        return JournalEntryRecord(
            journal_entry_id=str(row["journal_entry_id"]),
            world_id=str(row["world_id"]),
            entry_type=str(row["entry_type"]),
            text=str(row["text"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
