from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from apps.game_api.app.migration_runner import SqliteMigrationRunner
from apps.game_api.app.services.quest_authoring import (
    advance_quests_for_turn,
    derive_story_flags_from_quests,
    initial_quest_states_for_world_seed,
)
from apps.game_api.app.services.scene_point_catalog import build_scene_point_targets_for_location
from apps.game_api.app.services.urban_occult_basis import infer_canonical_role_from_text
from apps.game_api.app.services.world_pack_authoring import initial_story_flags_for_world_seed
from ls_shared_schemas.character import CharacterResources, CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.npc_memory import NPCMemoryBundle, NPCMemoryEntry, NPCProfile, NPCRelationship
from ls_shared_schemas.quests import WorldQuestState
from ls_shared_schemas.turns import (
    ActionType,
    NarrativeEnvelope,
    PersistedTurnRecord,
    TurnIntent,
    TurnResolution,
    TurnSystemEvent,
)
from ls_shared_schemas.game_context import GameTargetReference
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
            scene_zone_id="zone-market-center",
            scene_zone_name="Brunnenplatz",
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
                for starter_npc in world_seed.starter_npcs:
                    self._upsert_npc_discovery(
                        conn=conn,
                        world_id=world_id,
                        world_character_id=world_character_id,
                        npc_id=starter_npc.npc_id,
                        timestamp=created_at,
                    )
                self._insert_journal_entries(conn, journal_entries)
                self._insert_initial_world_quest_states(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=world_character_id,
                    quests=initial_quest_states_for_world_seed(world_seed),
                )
                self._upsert_world_story_flags(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=world_character_id,
                    flags=initial_story_flags_for_world_seed(world_seed),
                    allow_insert=True,
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
                current_quests = self._list_world_quest_states_conn(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                )
                current_story_flags = self._get_world_story_flags_conn(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                )

                newly_revealed_npcs, newly_revealed_scene_points = self._apply_npc_discovery_updates(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                    intent=intent,
                    resolution=resolution,
                    timestamp=created_at,
                )
                if newly_revealed_npcs > 0:
                    resolution.system_events.append(
                        TurnSystemEvent(
                            code="discovery_revealed_npcs",
                            message=f"Du erkennst {newly_revealed_npcs} neue Praesenz(en) in der Umgebung.",
                            severity="info",
                        )
                    )
                if newly_revealed_scene_points > 0:
                    resolution.system_events.append(
                        TurnSystemEvent(
                            code="discovery_revealed_scene_points",
                            message=f"Du entdeckst {newly_revealed_scene_points} neue Interaktionspunkt(e) in der Umgebung.",
                            severity="info",
                        )
                    )
                newly_revealed_scene_details = self._apply_scene_point_interaction_updates(
                    conn=conn,
                    world_id=world_id,
                    resolution=resolution,
                    timestamp=created_at,
                )
                if newly_revealed_scene_details > 0:
                    resolution.system_events.append(
                        TurnSystemEvent(
                            code="discovery_revealed_scene_details",
                            message=f"Du erkennst {newly_revealed_scene_details} Detailhinweis(e) an untersuchten Objekten.",
                            severity="info",
                        )
                    )
                if (
                    self._has_broad_inspect_action(resolution=resolution)
                    and newly_revealed_npcs == 0
                    and newly_revealed_scene_points == 0
                    and newly_revealed_scene_details == 0
                ):
                    resolution.system_events.append(
                        TurnSystemEvent(
                            code="discovery_nothing_new",
                            message="Du nimmst die Umgebung erneut in den Blick, entdeckst aber nichts Neues.",
                            severity="info",
                        )
                    )
                if current_quests:
                    quest_progress = advance_quests_for_turn(
                        quests=current_quests,
                        intent=intent,
                        resolution=resolution,
                    )
                    self._apply_world_quest_updates(
                        conn=conn,
                        world_id=world_id,
                        world_character_id=resolution.world_character_id,
                        quests=quest_progress.quests,
                    )
                    resolution.system_events.extend(quest_progress.system_events)
                    next_story_flags = derive_story_flags_from_quests(
                        quests=quest_progress.quests,
                        existing_flags=current_story_flags,
                    )
                    self._upsert_world_story_flags(
                        conn=conn,
                        world_id=world_id,
                        world_character_id=resolution.world_character_id,
                        flags=next_story_flags,
                        allow_insert=True,
                    )

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

    def list_world_quest_states(
        self,
        *,
        world_id: str,
        world_character_id: str,
    ) -> list[WorldQuestState]:
        with self._connect() as conn:
            return self._list_world_quest_states_conn(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
            )

    def get_world_story_flags(
        self,
        *,
        world_id: str,
        world_character_id: str,
    ) -> dict[str, str | int | bool]:
        with self._connect() as conn:
            return self._get_world_story_flags_conn(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
            )

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
            discovery_rows = conn.execute(
                """
                SELECT npc_id FROM npc_discoveries
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
        discovered_npc_ids = {str(row["npc_id"]) for row in discovery_rows}
        memories_by_npc: dict[str, list[NPCMemoryEntry]] = {}
        for row in memory_rows:
            npc_id = str(row["npc_id"])
            memories_by_npc.setdefault(npc_id, []).append(self._npc_memory_from_row(row))

        bundles: list[NPCMemoryBundle] = []
        for row in profile_rows:
            npc_id = str(row["npc_id"])
            if npc_id not in discovered_npc_ids:
                continue
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

    def spawn_npc_for_devtest(
        self,
        *,
        world_id: str,
        profile: NPCProfile,
        standing_for_player: int | None = None,
        revealed_to_player: bool = True,
    ) -> NPCProfile:
        session = self.get_world_session(world_id)
        if session is None:
            raise ValueError("World session not found.")

        timestamp = _utc_iso_now()
        normalized_profile = self._normalize_npc_profile(profile)
        with self._connect() as conn:
            self._upsert_world_npc_profiles(
                conn=conn,
                world_id=world_id,
                profiles=[normalized_profile],
                timestamp=timestamp,
            )
            if standing_for_player is not None:
                self._upsert_npc_relationship(
                    conn=conn,
                    world_id=world_id,
                    npc_id=normalized_profile.npc_id,
                    world_character_id=session.character_state.world_character_id,
                    standing_delta=int(standing_for_player),
                    timestamp=timestamp,
                )
            if revealed_to_player:
                self._upsert_npc_discovery(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=session.character_state.world_character_id,
                    npc_id=normalized_profile.npc_id,
                    timestamp=timestamp,
                )
            conn.commit()
        return normalized_profile

    def count_hidden_npcs_in_location(
        self,
        *,
        world_id: str,
        world_character_id: str,
        location_name: str,
    ) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT p.npc_id
                FROM npc_profiles p
                LEFT JOIN npc_discoveries d
                  ON d.world_id = p.world_id
                 AND d.world_character_id = ?
                 AND d.npc_id = p.npc_id
                WHERE p.world_id = ?
                  AND COALESCE(json_extract(p.stats_json, '$._location_name'), '') = ?
                  AND d.npc_id IS NULL
                """,
                (world_character_id, world_id, location_name),
            ).fetchall()
        return len(rows)

    def count_hidden_scene_points_in_location(
        self,
        *,
        world_id: str,
        world_character_id: str,
        location_name: str,
    ) -> int:
        session = self.get_world_session(world_id)
        if session is None:
            return 0
        points = build_scene_point_targets_for_location(world=session, location_name=location_name)
        if not points:
            return 0
        discovered_ids = set(
            self.list_discovered_scene_point_ids(
                world_id=world_id,
                world_character_id=world_character_id,
                location_name=location_name,
            )
        )
        return sum(1 for point in points if point.ref_id not in discovered_ids)

    def list_visible_scene_points_in_location(
        self,
        *,
        world_id: str,
        world_character_id: str,
        location_name: str,
    ) -> list[GameTargetReference]:
        session = self.get_world_session(world_id)
        if session is None:
            return []
        points = build_scene_point_targets_for_location(world=session, location_name=location_name)
        discovered_points = self.list_scene_point_discoveries_in_location(
            world_id=world_id,
            world_character_id=world_character_id,
            location_name=location_name,
        )
        discovered_ids = set(discovered_points.keys())
        visible_points: list[GameTargetReference] = []
        for point in points:
            if point.ref_id not in discovered_ids:
                continue
            detail = discovered_points[point.ref_id]
            detail_level = int(detail.get("detail_level", 1) or 1)
            state = detail.get("state", {})
            visible_points.append(
                point.model_copy(
                    update={
                        "detail_level": detail_level,
                        "discovery_state": state,
                    }
                )
            )
        return visible_points

    def list_scene_point_discoveries_in_location(
        self,
        *,
        world_id: str,
        world_character_id: str,
        location_name: str,
    ) -> dict[str, dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT point_ref_id, detail_level, state_json
                FROM scene_point_discoveries
                WHERE world_id = ?
                  AND world_character_id = ?
                  AND location_name = ?
                """,
                (world_id, world_character_id, location_name),
            ).fetchall()
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            raw_state = str(row["state_json"] or "{}")
            try:
                state = json.loads(raw_state)
            except json.JSONDecodeError:
                state = {}
            if not isinstance(state, dict):
                state = {}
            result[str(row["point_ref_id"])] = {
                "detail_level": int(row["detail_level"] or 1),
                "state": state,
            }
        return result

    def list_discovered_scene_point_ids(
        self,
        *,
        world_id: str,
        world_character_id: str,
        location_name: str,
    ) -> list[str]:
        return list(
            self.list_scene_point_discoveries_in_location(
                world_id=world_id,
                world_character_id=world_character_id,
                location_name=location_name,
            ).keys()
        )

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

    def _insert_initial_world_quest_states(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        quests: list[WorldQuestState],
    ) -> None:
        if not quests:
            return
        timestamp = _utc_iso_now()
        for quest in quests:
            conn.execute(
                """
                INSERT OR REPLACE INTO world_quest_states (
                    world_id, world_character_id, quest_id, quest_state_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    world_id,
                    world_character_id,
                    quest.quest_id,
                    quest.model_dump_json(),
                    timestamp,
                    timestamp,
                ),
            )

    def _apply_world_quest_updates(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        quests: list[WorldQuestState],
    ) -> None:
        if not quests:
            return
        timestamp = _utc_iso_now()
        for quest in quests:
            conn.execute(
                """
                INSERT INTO world_quest_states (
                    world_id, world_character_id, quest_id, quest_state_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, world_character_id, quest_id)
                DO UPDATE SET
                    quest_state_json = excluded.quest_state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    world_character_id,
                    quest.quest_id,
                    quest.model_dump_json(),
                    timestamp,
                    timestamp,
                ),
            )

    def _list_world_quest_states_conn(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
    ) -> list[WorldQuestState]:
        rows = conn.execute(
            """
            SELECT quest_state_json
            FROM world_quest_states
            WHERE world_id = ? AND world_character_id = ?
            ORDER BY quest_id ASC
            """,
            (world_id, world_character_id),
        ).fetchall()
        return [WorldQuestState.model_validate_json(str(row["quest_state_json"])) for row in rows]

    def _get_world_story_flags_conn(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
    ) -> dict[str, str | int | bool]:
        row = conn.execute(
            """
            SELECT flags_json
            FROM world_story_flags
            WHERE world_id = ? AND world_character_id = ?
            LIMIT 1
            """,
            (world_id, world_character_id),
        ).fetchone()
        if row is None:
            return {}
        payload = json.loads(str(row["flags_json"]))
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, (str, int, bool))
        }

    def _upsert_world_story_flags(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        flags: dict[str, str | int | bool],
        allow_insert: bool = True,
    ) -> None:
        timestamp = _utc_iso_now()
        if allow_insert:
            conn.execute(
                """
                INSERT INTO world_story_flags (
                    world_id, world_character_id, flags_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(world_id, world_character_id)
                DO UPDATE SET
                    flags_json = excluded.flags_json,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    world_character_id,
                    json.dumps(flags, ensure_ascii=True),
                    timestamp,
                    timestamp,
                ),
            )
            return
        conn.execute(
            """
            UPDATE world_story_flags
            SET flags_json = ?, updated_at = ?
            WHERE world_id = ? AND world_character_id = ?
            """,
            (
                json.dumps(flags, ensure_ascii=True),
                timestamp,
                world_id,
                world_character_id,
            ),
        )

    def _apply_npc_discovery_updates(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        intent: TurnIntent,
        resolution: TurnResolution,
        timestamp: str,
    ) -> tuple[int, int]:
        revealed_npcs = 0
        revealed_scene_points = 0
        applied_types = {action.action_type for action in resolution.applied_actions}
        current_location = (resolution.resulting_character_state.location_name or "").strip()
        if ActionType.inspect in applied_types and current_location:
            revealed_npcs += self._reveal_npcs_in_location_for_character(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
                location_name=current_location,
                timestamp=timestamp,
            )
            revealed_scene_points += self._reveal_scene_points_in_location_for_character(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
                location_name=current_location,
                timestamp=timestamp,
            )

        for action in resolution.applied_actions:
            if action.action_type not in {ActionType.talk, ActionType.attack, ActionType.approach, ActionType.retreat}:
                continue
            target_id = str(action.parameters.get("target_id") or action.target_ref or "").strip()
            if target_id.startswith("npc-"):
                revealed_npcs += self._upsert_npc_discovery(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=world_character_id,
                    npc_id=target_id,
                    timestamp=timestamp,
                )
        return revealed_npcs, revealed_scene_points

    @staticmethod
    def _has_broad_inspect_action(*, resolution: TurnResolution) -> bool:
        for action in resolution.applied_actions:
            if action.action_type != ActionType.inspect:
                continue
            inspect_mode = str(action.parameters.get("inspect_mode") or "").strip().lower()
            target_kind = str(action.target_kind or action.parameters.get("target_kind") or "").strip().lower()
            if inspect_mode in {"", "broad"} and not action.target_ref and target_kind in {"", "environment"}:
                return True
        return False

    def _apply_scene_point_interaction_updates(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        resolution: TurnResolution,
        timestamp: str,
    ) -> int:
        detail_reveals = 0
        for action in resolution.applied_actions:
            if action.action_type not in {ActionType.inspect, ActionType.open, ActionType.search, ActionType.take}:
                continue
            target_ref = str(action.parameters.get("target_id") or action.target_ref or "").strip()
            if not (target_ref.startswith("poi-") or target_ref.startswith("obj-")):
                continue
            target_kind = str(action.parameters.get("target_kind") or action.target_kind or "").strip().lower() or "scene_point"
            location_name = str(
                action.parameters.get("target_location_name")
                or resolution.resulting_character_state.location_name
                or ""
            ).strip()
            if not location_name:
                continue

            _created_count, upgraded_detail = self._upsert_scene_point_discovery(
                conn=conn,
                world_id=world_id,
                world_character_id=resolution.world_character_id,
                location_name=location_name,
                point_ref_id=target_ref,
                detail_level=2,
                timestamp=timestamp,
            )
            detail_reveals += upgraded_detail
            if target_kind == "container":
                self._apply_container_interaction_state_and_loot(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                    location_name=location_name,
                    point_ref_id=target_ref,
                    point_name=str(action.parameters.get("target_name") or target_ref),
                    action_type=action.action_type,
                    resolution=resolution,
                    timestamp=timestamp,
                )
            if target_kind == "scene_object" and action.action_type == ActionType.take:
                self._apply_scene_object_take_state_and_loot(
                    conn=conn,
                    world_id=world_id,
                    world_character_id=resolution.world_character_id,
                    location_name=location_name,
                    point_ref_id=target_ref,
                    point_name=str(action.parameters.get("target_name") or target_ref),
                    resolution=resolution,
                    timestamp=timestamp,
                )
        return detail_reveals

    def _reveal_npcs_in_location_for_character(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        location_name: str,
        timestamp: str,
    ) -> int:
        rows = conn.execute(
            """
            SELECT npc_id
            FROM npc_profiles
            WHERE world_id = ?
              AND COALESCE(json_extract(stats_json, '$._location_name'), '') = ?
            """,
            (world_id, location_name),
        ).fetchall()
        count = 0
        for row in rows:
            count += self._upsert_npc_discovery(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
                npc_id=str(row["npc_id"]),
                timestamp=timestamp,
            )
        return count

    def _reveal_scene_points_in_location_for_character(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        location_name: str,
        timestamp: str,
    ) -> int:
        world_row = conn.execute("SELECT * FROM worlds WHERE world_id = ?", (world_id,)).fetchone()
        if world_row is None:
            return 0
        character_row = self._get_primary_character_row(conn, world_id)
        if character_row is None:
            return 0
        session = self._build_world_session_from_rows(world_row, character_row, [])
        points = build_scene_point_targets_for_location(world=session, location_name=location_name)
        count = 0
        for point in points:
            created_count, _ = self._upsert_scene_point_discovery(
                conn=conn,
                world_id=world_id,
                world_character_id=world_character_id,
                location_name=location_name,
                point_ref_id=point.ref_id,
                timestamp=timestamp,
            )
            count += created_count
        return count

    def _upsert_npc_discovery(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        npc_id: str,
        timestamp: str,
    ) -> int:
        existing = conn.execute(
            """
            SELECT 1 FROM npc_discoveries
            WHERE world_id = ? AND world_character_id = ? AND npc_id = ?
            """,
            (world_id, world_character_id, npc_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO npc_discoveries (world_id, world_character_id, npc_id, discovered_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (world_id, world_character_id, npc_id, timestamp, timestamp),
            )
            return 1
        conn.execute(
            """
            UPDATE npc_discoveries
            SET updated_at = ?
            WHERE world_id = ? AND world_character_id = ? AND npc_id = ?
            """,
            (timestamp, world_id, world_character_id, npc_id),
        )
        return 0

    def _upsert_scene_point_discovery(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        location_name: str,
        point_ref_id: str,
        detail_level: int = 1,
        state_updates: dict[str, object] | None = None,
        timestamp: str,
    ) -> tuple[int, int]:
        existing = conn.execute(
            """
            SELECT detail_level, state_json
            FROM scene_point_discoveries
            WHERE world_id = ?
              AND world_character_id = ?
              AND location_name = ?
              AND point_ref_id = ?
            """,
            (world_id, world_character_id, location_name, point_ref_id),
        ).fetchone()
        if existing is None:
            state_payload = dict(state_updates or {})
            conn.execute(
                """
                INSERT INTO scene_point_discoveries (
                    world_id, world_character_id, location_name, point_ref_id, discovered_at, updated_at, detail_level, state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    world_id,
                    world_character_id,
                    location_name,
                    point_ref_id,
                    timestamp,
                    timestamp,
                    max(1, int(detail_level)),
                    json.dumps(state_payload, ensure_ascii=True),
                ),
            )
            return 1, 1 if int(detail_level) > 1 else 0
        try:
            current_state = json.loads(str(existing["state_json"] or "{}"))
        except json.JSONDecodeError:
            current_state = {}
        if not isinstance(current_state, dict):
            current_state = {}
        if state_updates:
            current_state.update(state_updates)
        current_detail = int(existing["detail_level"] or 1)
        next_detail = max(current_detail, int(detail_level))
        detail_upgraded = 1 if next_detail > current_detail else 0
        conn.execute(
            """
            UPDATE scene_point_discoveries
            SET updated_at = ?, detail_level = ?, state_json = ?
            WHERE world_id = ?
              AND world_character_id = ?
              AND location_name = ?
              AND point_ref_id = ?
            """,
            (
                timestamp,
                next_detail,
                json.dumps(current_state, ensure_ascii=True),
                world_id,
                world_character_id,
                location_name,
                point_ref_id,
            ),
        )
        return 0, detail_upgraded

    def _apply_container_interaction_state_and_loot(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        location_name: str,
        point_ref_id: str,
        point_name: str,
        action_type: ActionType,
        resolution: TurnResolution,
        timestamp: str,
    ) -> None:
        row = conn.execute(
            """
            SELECT state_json
            FROM scene_point_discoveries
            WHERE world_id = ?
              AND world_character_id = ?
              AND location_name = ?
              AND point_ref_id = ?
            """,
            (world_id, world_character_id, location_name, point_ref_id),
        ).fetchone()
        if row is None:
            return
        try:
            state = json.loads(str(row["state_json"] or "{}"))
        except json.JSONDecodeError:
            state = {}
        if not isinstance(state, dict):
            state = {}

        opened = bool(state.get("opened"))
        looted = bool(state.get("looted"))
        events = resolution.system_events
        if not opened:
            events.append(TurnSystemEvent(code="container_opened", message=f"Du oeffnest {point_name}."))
            opened = True
        elif action_type == ActionType.open:
            events.append(TurnSystemEvent(code="container_already_open", message=f"{point_name} ist bereits geoeffnet."))

        should_search_loot = action_type in {ActionType.inspect, ActionType.search}
        if should_search_loot and not looted:
            loot_item = self._deterministic_container_loot(point_ref_id)
            if loot_item is not None:
                self._grant_inventory_item(resolution.resulting_inventory, loot_item)
                resolution.state_delta.inventory_gained.append(
                    {"item_id": loot_item.inventory_item_id, "name": loot_item.name, "quantity": loot_item.quantity}
                )
                events.append(
                    TurnSystemEvent(code="container_loot_found", message=f"Du findest in {point_name}: {loot_item.name}.")
                )
            else:
                events.append(TurnSystemEvent(code="container_empty", message=f"{point_name} ist leer."))
            looted = True
        elif should_search_loot:
            events.append(TurnSystemEvent(code="container_already_searched", message=f"{point_name} wurde bereits durchsucht."))

        _, _ = self._upsert_scene_point_discovery(
            conn=conn,
            world_id=world_id,
            world_character_id=world_character_id,
            location_name=location_name,
            point_ref_id=point_ref_id,
            detail_level=2,
            state_updates={"opened": opened, "looted": looted},
            timestamp=timestamp,
        )

    def _deterministic_container_loot(self, point_ref_id: str) -> InventoryItemInstance | None:
        if "siegelkoffer" in point_ref_id:
            return InventoryItemInstance(
                inventory_item_id=f"inv-loot-{point_ref_id[-12:]}",
                item_def_id="sealed_case_notes",
                name="Ritualnotizen (Fragment)",
                category="document",
                description="Ein Fragment mit Notizen zu einem misslungenen Binder-Ritual.",
                quantity=1,
            )
        if "supply-crate" in point_ref_id:
            return InventoryItemInstance(
                inventory_item_id=f"inv-loot-{point_ref_id[-12:]}",
                item_def_id="field_bandages",
                name="Verbandspaket",
                category="consumable",
                description="Ein einfaches Verbandspaket aus einer Vorratskiste.",
                quantity=1,
            )
        if "discarded-bag" in point_ref_id:
            return InventoryItemInstance(
                inventory_item_id=f"inv-loot-{point_ref_id[-12:]}",
                item_def_id="coin_pouch_small",
                name="Kleiner Geldbeutel",
                category="misc",
                description="Ein abgegriffener Geldbeutel mit ein paar Metallmarken.",
                quantity=1,
            )
        return None

    def _grant_inventory_item(self, inventory: list[InventoryItemInstance], item: InventoryItemInstance) -> None:
        for existing in inventory:
            if existing.item_def_id == item.item_def_id and existing.stackable == item.stackable:
                existing.quantity += item.quantity
                return
        inventory.append(item)

    def _apply_scene_object_take_state_and_loot(
        self,
        *,
        conn: sqlite3.Connection,
        world_id: str,
        world_character_id: str,
        location_name: str,
        point_ref_id: str,
        point_name: str,
        resolution: TurnResolution,
        timestamp: str,
    ) -> None:
        row = conn.execute(
            """
            SELECT state_json
            FROM scene_point_discoveries
            WHERE world_id = ?
              AND world_character_id = ?
              AND location_name = ?
              AND point_ref_id = ?
            """,
            (world_id, world_character_id, location_name, point_ref_id),
        ).fetchone()
        if row is None:
            return
        try:
            state = json.loads(str(row["state_json"] or "{}"))
        except json.JSONDecodeError:
            state = {}
        if not isinstance(state, dict):
            state = {}

        taken = bool(state.get("taken"))
        looted = bool(state.get("looted"))
        events = resolution.system_events
        if taken:
            events.append(TurnSystemEvent(code="scene_object_already_taken", message=f"{point_name} wurde bereits mitgenommen."))
        else:
            events.append(TurnSystemEvent(code="scene_object_taken", message=f"Du nimmst {point_name} mit."))

        if not looted:
            loot_item = self._deterministic_container_loot(point_ref_id)
            if loot_item is not None:
                self._grant_inventory_item(resolution.resulting_inventory, loot_item)
                resolution.state_delta.inventory_gained.append(
                    {"item_id": loot_item.inventory_item_id, "name": loot_item.name, "quantity": loot_item.quantity}
                )
                events.append(TurnSystemEvent(code="scene_object_loot_found", message=f"Aus {point_name} sicherst du: {loot_item.name}."))
            else:
                events.append(TurnSystemEvent(code="scene_object_nothing_to_take", message=f"An {point_name} ist nichts Verwertbares."))
            looted = True

        _, _ = self._upsert_scene_point_discovery(
            conn=conn,
            world_id=world_id,
            world_character_id=world_character_id,
            location_name=location_name,
            point_ref_id=point_ref_id,
            detail_level=2,
            state_updates={"taken": True, "looted": looted},
            timestamp=timestamp,
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
                        json.dumps(self._npc_profile_stats_payload(profile), ensure_ascii=True),
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
                    json.dumps(self._npc_profile_stats_payload(profile), ensure_ascii=True),
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
            try:
                npc_id = self._find_or_create_npc_profile(
                    conn=conn,
                    world_id=world_id,
                    npc_name=npc_name,
                    timestamp=timestamp,
                    preferred_npc_id=preferred_npc_id,
                )
            except ValueError:
                continue
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
        if self._is_disallowed_generic_npc_name(npc_name):
            raise ValueError("Refusing to auto-create generic NPC target.")
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
        inferred_role = infer_canonical_role_from_text(npc_name or "")
        row = conn.execute(
            """
            SELECT npc_id, role FROM npc_profiles
            WHERE world_id = ? AND LOWER(name) = LOWER(?)
            LIMIT 1
            """,
            (world_id, npc_name),
        ).fetchone()
        if row is not None:
            npc_id = str(row["npc_id"])
            existing_role = str(row["role"] or "unknown")
            if inferred_role and existing_role in {"", "unknown", "npc"}:
                conn.execute(
                    """
                    UPDATE npc_profiles
                    SET role = ?, updated_at = ?
                    WHERE world_id = ? AND npc_id = ?
                    """,
                    (inferred_role, timestamp, world_id, npc_id),
                )
            return npc_id

        npc_id = preferred_npc_id or self._stable_npc_id_from_name(npc_name)
        profile = NPCProfile(npc_id=npc_id, name=npc_name, role=inferred_role or "unknown")
        self._upsert_world_npc_profiles(
            conn=conn,
            world_id=world_id,
            profiles=[profile],
            timestamp=timestamp,
        )
        return npc_id

    @staticmethod
    def _is_disallowed_generic_npc_name(npc_name: str) -> bool:
        normalized = (npc_name or "").strip().lower()
        return normalized in {"npc", "char", "charakter", "figur", "person", "gegner", "ziel"}

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
        stats_payload = json.loads(str(row["stats_json"]))
        scene_zone_id = str(stats_payload.pop("_scene_zone_id", "") or "") or None
        scene_zone_name = str(stats_payload.pop("_scene_zone_name", "") or "") or None
        location_name = str(stats_payload.pop("_location_name", "") or "") or None
        return NPCProfile(
            npc_id=str(row["npc_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            faction=str(row["faction"]) if row["faction"] is not None else None,
            location_name=location_name,
            scene_zone_id=scene_zone_id,
            scene_zone_name=scene_zone_name,
            personality_tags=json.loads(str(row["personality_tags_json"])),
            stats=stats_payload,
        )

    @staticmethod
    def _npc_profile_stats_payload(profile: NPCProfile) -> dict[str, int | float | str]:
        payload = dict(profile.stats)
        if profile.location_name:
            payload["_location_name"] = profile.location_name
        if profile.scene_zone_id:
            payload["_scene_zone_id"] = profile.scene_zone_id
        if profile.scene_zone_name:
            payload["_scene_zone_name"] = profile.scene_zone_name
        return payload

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
