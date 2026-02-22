from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from apps.game_api.app.migration_runner import SqliteMigrationRunner
from ls_shared_schemas.character import CharacterResources, CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.npc_memory import NPCMemoryBundle, NPCMemoryEntry, NPCProfile, NPCRelationship
from ls_shared_schemas.turns import ActionType, NarrativeEnvelope, PersistedTurnRecord, TurnIntent, TurnResolution
from ls_shared_schemas.world import JournalEntryRecord, WorldBootstrapRequest, WorldBootstrapResult, WorldSessionResponse


def _utc_iso_now() -> str:
    return datetime.now(UTC).isoformat()


class WorldRepository:
    """SQLite persistence for Greenfield bootstrap + turn pipeline."""

    def __init__(self, db_path: str, migrations_dir: str | None = None):
        self.db_path = Path(db_path)
        self.migrations_dir = Path(migrations_dir) if migrations_dir else (Path(__file__).resolve().parent / "migrations")

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
        runner = SqliteMigrationRunner(db_path=self.db_path, migrations_dir=self.migrations_dir)
        runner.apply_all()

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
                self._upsert_world_npc_profiles(
                    conn=conn,
                    world_id=world_id,
                    profiles=world_seed.starter_npcs,
                    timestamp=created_at,
                )
                self._insert_journal_entries(conn, journal_entries)
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

            character_row = self._get_primary_character_row(conn, world_id)
            if character_row is None:
                return None

            journal_rows = conn.execute(
                "SELECT * FROM journal_entries WHERE world_id = ? ORDER BY created_at ASC",
                (world_id,),
            ).fetchall()

        return self._build_world_session_from_rows(world_row, character_row, journal_rows)

    def save_turn_run(
        self,
        *,
        world_id: str,
        intent: TurnIntent,
        resolution: TurnResolution,
        narrative: NarrativeEnvelope,
    ) -> tuple[PersistedTurnRecord, list[JournalEntryRecord]]:
        created_at = _utc_iso_now()
        turn_id = f"turn-{uuid4().hex[:12]}"

        journal_entries = [
            JournalEntryRecord(
                journal_entry_id=f"journal-{uuid4().hex[:12]}",
                world_id=world_id,
                entry_type="player_input",
                text=intent.raw_player_input,
            ),
            JournalEntryRecord(
                journal_entry_id=f"journal-{uuid4().hex[:12]}",
                world_id=world_id,
                entry_type="narrative",
                text=narrative.narrative,
            ),
        ]

        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                world_row = conn.execute("SELECT * FROM worlds WHERE world_id = ?", (world_id,)).fetchone()
                if world_row is None:
                    raise KeyError("world_not_found")

                character_row = self._get_primary_character_row(conn, world_id)
                if character_row is None:
                    raise KeyError("world_character_not_found")

                conn.execute(
                    """
                    INSERT INTO turns (
                        turn_id, world_id, world_character_id, raw_player_input,
                        intent_json, resolution_json, narrative_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn_id,
                        world_id,
                        resolution.world_character_id,
                        intent.raw_player_input,
                        intent.model_dump_json(),
                        resolution.model_dump_json(),
                        narrative.model_dump_json(),
                        created_at,
                    ),
                )

                conn.execute(
                    """
                    UPDATE world_characters
                    SET character_state_json = ?, inventory_json = ?, created_at = ?
                    WHERE world_character_id = ?
                    """,
                    (
                        resolution.resulting_character_state.model_dump_json(),
                        json.dumps(
                            [item.model_dump(mode="json") for item in resolution.resulting_inventory],
                            ensure_ascii=True,
                        ),
                        created_at,
                        resolution.world_character_id,
                    ),
                )

                self._insert_journal_entries(conn, journal_entries)
                self._apply_npc_memory_updates(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                    turn_id=turn_id,
                    intent=intent,
                    resolution=resolution,
                    timestamp=created_at,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        turn_record = PersistedTurnRecord(
            turn_id=turn_id,
            world_id=world_id,
            world_character_id=resolution.world_character_id,
            raw_player_input=intent.raw_player_input,
            intent=intent,
            resolution=resolution,
            narrative=narrative,
            created_at=datetime.fromisoformat(created_at),
        )
        return turn_record, journal_entries

    def list_turns(self, world_id: str, limit: int = 50) -> list[PersistedTurnRecord]:
        safe_limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM turns
                WHERE world_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (world_id, safe_limit),
            ).fetchall()
        return [self._turn_from_row(row) for row in rows]

    def get_world_context(self, world_id: str) -> tuple[WorldSessionResponse | None, CharacterState | None, list[InventoryItemInstance]]:
        session = self.get_world_session(world_id)
        if session is None:
            return None, None, []
        return session, session.character_state, list(session.inventory)

    def list_npc_memory_bundles(
        self,
        *,
        world_id: str,
        world_character_id: str,
        limit_memories_per_npc: int = 5,
    ) -> list[NPCMemoryBundle]:
        safe_limit = max(1, min(limit_memories_per_npc, 20))
        with self._connect() as conn:
            profile_rows = conn.execute(
                """
                SELECT * FROM npc_profiles
                WHERE world_id = ?
                ORDER BY name ASC
                """,
                (world_id,),
            ).fetchall()
            relationship_rows = conn.execute(
                """
                SELECT * FROM npc_relationships
                WHERE world_id = ? AND world_character_id = ?
                """,
                (world_id, world_character_id),
            ).fetchall()
            memory_rows = conn.execute(
                """
                SELECT * FROM npc_memories
                WHERE world_id = ? AND world_character_id = ?
                ORDER BY created_at DESC
                """,
                (world_id, world_character_id),
            ).fetchall()

        relationships_by_npc = {
            str(row["npc_id"]): self._npc_relationship_from_row(row)
            for row in relationship_rows
        }
        memories_by_npc: dict[str, list[NPCMemoryEntry]] = {}
        for row in memory_rows:
            npc_id = str(row["npc_id"])
            memories_by_npc.setdefault(npc_id, []).append(self._npc_memory_from_row(row))

        bundles: list[NPCMemoryBundle] = []
        for row in profile_rows:
            npc_id = str(row["npc_id"])
            memories = memories_by_npc.get(npc_id, [])[:safe_limit]
            bundles.append(
                NPCMemoryBundle(
                    profile=self._npc_profile_from_row(row),
                    relationship=relationships_by_npc.get(npc_id),
                    recent_memories=memories,
                    canonical_facts=[],
                )
            )
        return bundles

    def _insert_journal_entries(self, conn: sqlite3.Connection, entries: list[JournalEntryRecord]) -> None:
        for entry in entries:
            conn.execute(
                """
                INSERT INTO journal_entries (journal_entry_id, world_id, entry_type, text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry.journal_entry_id,
                    entry.world_id,
                    entry.entry_type,
                    entry.text,
                    entry.created_at.isoformat(),
                ),
            )

    def _upsert_world_npc_profiles(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        profiles: list[NPCProfile],
        timestamp: str,
    ) -> None:
        for profile in profiles:
            existing = conn.execute(
                "SELECT 1 FROM npc_profiles WHERE world_id = ? AND npc_id = ?",
                (world_id, profile.npc_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO npc_profiles (
                        world_id, npc_id, name, role, faction, personality_tags_json,
                        stats_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        world_id,
                        profile.npc_id,
                        profile.name,
                        profile.role,
                        profile.faction,
                        json.dumps(profile.personality_tags, ensure_ascii=True),
                        json.dumps(profile.stats, ensure_ascii=True),
                        timestamp,
                        timestamp,
                    ),
                )
                continue

            conn.execute(
                """
                UPDATE npc_profiles
                SET name = ?, role = ?, faction = ?, personality_tags_json = ?, stats_json = ?, updated_at = ?
                WHERE world_id = ? AND npc_id = ?
                """,
                (
                    profile.name,
                    profile.role,
                    profile.faction,
                    json.dumps(profile.personality_tags, ensure_ascii=True),
                    json.dumps(profile.stats, ensure_ascii=True),
                    timestamp,
                    world_id,
                    profile.npc_id,
                ),
            )

    def _apply_npc_memory_updates(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        turn_id: str,
        intent: TurnIntent,
        resolution: TurnResolution,
        timestamp: str,
    ) -> None:
        standing_changes_by_id: dict[str, int] = {}
        standing_changes_by_name: dict[str, int] = {}
        for change in resolution.state_delta.relationship_changes:
            npc_id = str(change.get("npc_id") or "").strip()
            npc_name = str(change.get("npc") or "").strip()
            if not npc_name and not npc_id:
                continue
            standing_delta = int(change.get("standing_delta") or 0)
            if npc_id:
                standing_changes_by_id[npc_id] = standing_changes_by_id.get(npc_id, 0) + standing_delta
            if npc_name:
                standing_changes_by_name[npc_name] = standing_changes_by_name.get(npc_name, 0) + standing_delta

        interaction_targets: dict[str, dict[str, str]] = {}
        for action in resolution.applied_actions:
            if action.action_type not in {ActionType.talk, ActionType.attack}:
                continue
            target_name = str(action.parameters.get("target_name") or "").strip()
            target_id = str(action.parameters.get("target_id") or "").strip()
            fallback_ref = (action.target_ref or "").strip()
            if not target_name and fallback_ref and not fallback_ref.startswith("npc-"):
                target_name = fallback_ref
            if not target_id and fallback_ref.startswith("npc-"):
                target_id = fallback_ref
            if not target_name and not target_id:
                continue
            interaction_targets[target_id or target_name.lower()] = {
                "target_name": target_name,
                "target_id": target_id,
                "interaction_kind": action.action_type.value.lower(),
            }

        for target_meta in interaction_targets.values():
            interaction_kind = target_meta["interaction_kind"]
            npc_name = target_meta["target_name"]
            preferred_npc_id = target_meta["target_id"] or None
            if not npc_name and preferred_npc_id:
                npc_name = self._get_npc_name_by_id(
                    conn=conn,
                    world_id=world_id,
                    npc_id=preferred_npc_id,
                ) or preferred_npc_id
            npc_id = self._find_or_create_npc_profile(
                conn=conn,
                world_id=world_id,
                npc_name=npc_name,
                timestamp=timestamp,
                preferred_npc_id=preferred_npc_id,
            )
            standing_delta = standing_changes_by_id.get(npc_id, 0)
            if standing_delta == 0 and npc_name:
                standing_delta = standing_changes_by_name.get(npc_name, 0)
            if standing_delta != 0:
                self._upsert_npc_relationship(
                    conn=conn,
                    world_id=world_id,
                    npc_id=npc_id,
                    world_character_id=world_character_id,
                    standing_delta=standing_delta,
                    timestamp=timestamp,
                )
            self._insert_npc_memory_entry(
                conn=conn,
                memory=NPCMemoryEntry(
                    memory_id=f"mem-{uuid4().hex[:12]}",
                    npc_id=npc_id,
                    world_id=world_id,
                    summary=self._build_npc_memory_summary(
                        npc_name=npc_name,
                        interaction_kind=interaction_kind,
                        player_input=intent.raw_player_input,
                    ),
                    importance=0.7 if interaction_kind == "attack" else 0.55,
                    tags=["interaction", interaction_kind],
                    source_turn_id=turn_id,
                ),
                world_character_id=world_character_id,
            )

    def _get_npc_name_by_id(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        npc_id: str,
    ) -> str | None:
        row = conn.execute(
            """
            SELECT name FROM npc_profiles
            WHERE world_id = ? AND npc_id = ?
            LIMIT 1
            """,
            (world_id, npc_id),
        ).fetchone()
        if row is None:
            return None
        return str(row["name"])

    def _find_or_create_npc_profile(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        npc_name: str,
        timestamp: str,
        preferred_npc_id: str | None = None,
    ) -> str:
        if preferred_npc_id:
            preferred_row = conn.execute(
                """
                SELECT npc_id FROM npc_profiles
                WHERE world_id = ? AND npc_id = ?
                LIMIT 1
                """,
                (world_id, preferred_npc_id),
            ).fetchone()
            if preferred_row is not None:
                return str(preferred_row["npc_id"])
        row = conn.execute(
            """
            SELECT npc_id FROM npc_profiles
            WHERE world_id = ? AND LOWER(name) = LOWER(?)
            LIMIT 1
            """,
            (world_id, npc_name),
        ).fetchone()
        if row is not None:
            return str(row["npc_id"])

        npc_id = preferred_npc_id or self._stable_npc_id_from_name(npc_name)
        profile = NPCProfile(npc_id=npc_id, name=npc_name, role="unknown")
        self._upsert_world_npc_profiles(
            conn=conn,
            world_id=world_id,
            profiles=[profile],
            timestamp=timestamp,
        )
        return npc_id

    def _upsert_npc_relationship(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        npc_id: str,
        world_character_id: str,
        standing_delta: int,
        timestamp: str,
    ) -> None:
        row = conn.execute(
            """
            SELECT standing, tags_json, notes FROM npc_relationships
            WHERE world_id = ? AND npc_id = ? AND world_character_id = ?
            """,
            (world_id, npc_id, world_character_id),
        ).fetchone()

        if row is None:
            standing = max(-100, min(100, standing_delta))
            conn.execute(
                """
                INSERT INTO npc_relationships (
                    world_id, npc_id, world_character_id, standing, tags_json, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    world_id,
                    npc_id,
                    world_character_id,
                    standing,
                    json.dumps([], ensure_ascii=True),
                    "",
                    timestamp,
                ),
            )
            return

        new_standing = max(-100, min(100, int(row["standing"]) + standing_delta))
        conn.execute(
            """
            UPDATE npc_relationships
            SET standing = ?, updated_at = ?
            WHERE world_id = ? AND npc_id = ? AND world_character_id = ?
            """,
            (
                new_standing,
                timestamp,
                world_id,
                npc_id,
                world_character_id,
            ),
        )

    def _insert_npc_memory_entry(
        self,
        *,
        conn: sqlite3.Connection,
        memory: NPCMemoryEntry,
        world_character_id: str,
    ) -> None:
        duplicate_row = conn.execute(
            """
            SELECT memory_id, importance, tags_json
            FROM npc_memories
            WHERE world_id = ? AND npc_id = ? AND world_character_id = ? AND summary = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                memory.world_id,
                memory.npc_id,
                world_character_id,
                memory.summary,
            ),
        ).fetchone()
        if duplicate_row is not None:
            existing_tags = set(json.loads(str(duplicate_row["tags_json"])))
            merged_tags = sorted(existing_tags.union(memory.tags))
            merged_importance = max(float(duplicate_row["importance"]), float(memory.importance))
            conn.execute(
                """
                UPDATE npc_memories
                SET importance = ?, tags_json = ?, source_turn_id = ?
                WHERE memory_id = ?
                """,
                (
                    merged_importance,
                    json.dumps(merged_tags, ensure_ascii=True),
                    memory.source_turn_id,
                    str(duplicate_row["memory_id"]),
                ),
            )
            return

        conn.execute(
            """
            INSERT INTO npc_memories (
                memory_id, world_id, npc_id, world_character_id, summary, importance,
                tags_json, source_turn_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.memory_id,
                memory.world_id,
                memory.npc_id,
                world_character_id,
                memory.summary,
                float(memory.importance),
                json.dumps(memory.tags, ensure_ascii=True),
                memory.source_turn_id,
                memory.created_at.isoformat(),
            ),
        )

    @staticmethod
    def _build_npc_memory_summary(*, npc_name: str, interaction_kind: str, player_input: str) -> str:
        verb = "sprach mit" if interaction_kind == "talk" else "griff an"
        summary = f"Spieler {verb} {npc_name}. Eingabe: {player_input}"
        return summary[:2000]

    @staticmethod
    def _stable_npc_id_from_name(npc_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", npc_name.lower()).strip("-")
        slug = slug or "unknown"
        return f"npc-auto-{slug[:48]}"

    @staticmethod
    def _get_primary_character_row(conn: sqlite3.Connection, world_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM world_characters WHERE world_id = ? ORDER BY created_at ASC LIMIT 1",
            (world_id,),
        ).fetchone()

    def _build_world_session_from_rows(
        self,
        world_row: sqlite3.Row,
        character_row: sqlite3.Row,
        journal_rows: list[sqlite3.Row],
    ) -> WorldSessionResponse:
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

    @staticmethod
    def _turn_from_row(row: sqlite3.Row) -> PersistedTurnRecord:
        return PersistedTurnRecord(
            turn_id=str(row["turn_id"]),
            world_id=str(row["world_id"]),
            world_character_id=str(row["world_character_id"]),
            raw_player_input=str(row["raw_player_input"]),
            intent=TurnIntent.model_validate_json(str(row["intent_json"])),
            resolution=TurnResolution.model_validate_json(str(row["resolution_json"])),
            narrative=NarrativeEnvelope.model_validate_json(str(row["narrative_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    @staticmethod
    def _npc_profile_from_row(row: sqlite3.Row) -> NPCProfile:
        return NPCProfile(
            npc_id=str(row["npc_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            faction=str(row["faction"]) if row["faction"] is not None else None,
            personality_tags=json.loads(str(row["personality_tags_json"])),
            stats=json.loads(str(row["stats_json"])),
        )

    @staticmethod
    def _npc_relationship_from_row(row: sqlite3.Row) -> NPCRelationship:
        return NPCRelationship(
            npc_id=str(row["npc_id"]),
            world_character_id=str(row["world_character_id"]),
            standing=int(row["standing"]),
            tags=json.loads(str(row["tags_json"])),
            notes=str(row["notes"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    @staticmethod
    def _npc_memory_from_row(row: sqlite3.Row) -> NPCMemoryEntry:
        return NPCMemoryEntry(
            memory_id=str(row["memory_id"]),
            npc_id=str(row["npc_id"]),
            world_id=str(row["world_id"]),
            summary=str(row["summary"]),
            importance=float(row["importance"]),
            tags=json.loads(str(row["tags_json"])),
            source_turn_id=str(row["source_turn_id"]) if row["source_turn_id"] is not None else None,
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
