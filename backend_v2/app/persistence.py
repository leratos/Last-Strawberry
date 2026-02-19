import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backend_v2.app.models import TurnRequest, TurnResponse


class PersistenceError(RuntimeError):
    pass


class SQLiteRepository:
    def __init__(self, database_url: str, auto_init: bool = True):
        self.database_url = database_url
        self.database_path = self._resolve_sqlite_path(database_url)
        if auto_init:
            self.initialize()

    @staticmethod
    def _resolve_sqlite_path(database_url: str) -> Path:
        if not database_url.startswith("sqlite:///"):
            raise PersistenceError("Only sqlite:/// URLs are supported in V2 phase 2 foundation.")
        raw_path = database_url[len("sqlite:///") :]
        if not raw_path:
            raise PersistenceError("SQLite URL path must not be empty.")

        path = Path(raw_path)
        if path == Path(":memory:"):
            return path
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    @contextmanager
    def _connect(self):
        if self.database_path == Path(":memory:"):
            conn = sqlite3.connect(":memory:")
        else:
            conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        if self.database_path != Path(":memory:"):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worlds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    player_command TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    extracted_commands TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    analysis_model TEXT NOT NULL,
                    narrative_model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_id INTEGER NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    source_turn_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_turns_world_created_at
                ON turns(world_id, created_at DESC);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_world_importance_updated
                ON memory_items(world_id, importance DESC, updated_at DESC);
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_dedupe
                ON memory_items(world_id, memory_type, content);
                """
            )
            conn.commit()

    def create_world(self, *, owner_id: int, name: str, description: str = "") -> dict:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO worlds(owner_id, name, description, created_at)
                VALUES(?, ?, ?, ?);
                """,
                (owner_id, name, description, created_at),
            )
            conn.commit()
            world_id = int(cursor.lastrowid)
        return {
            "id": world_id,
            "owner_id": owner_id,
            "name": name,
            "description": description,
            "created_at": created_at,
        }

    def get_world(self, world_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, owner_id, name, description, created_at FROM worlds WHERE id = ?;",
                (world_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "owner_id": int(row["owner_id"]),
            "name": str(row["name"]),
            "description": str(row["description"]),
            "created_at": str(row["created_at"]),
        }

    def is_world_owner(self, world_id: int, owner_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM worlds WHERE id = ? AND owner_id = ?;",
                (world_id, owner_id),
            ).fetchone()
        return row is not None

    def save_turn(self, request: TurnRequest, response: TurnResponse) -> dict:
        created_at = response.created_at.isoformat()
        extracted_commands_json = json.dumps(response.extracted_commands, ensure_ascii=False)
        analysis_model = response.models.get("analysis", "")
        narrative_model = response.models.get("narrative", "")

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO turns(
                    world_id,
                    player_id,
                    player_command,
                    narrative,
                    extracted_commands,
                    provider,
                    analysis_model,
                    narrative_model,
                    created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    request.world_id,
                    request.player_id,
                    request.player_command,
                    response.narrative,
                    extracted_commands_json,
                    response.provider,
                    analysis_model,
                    narrative_model,
                    created_at,
                ),
            )
            conn.commit()
            turn_id = int(cursor.lastrowid)

        return {
            "id": turn_id,
            "world_id": request.world_id,
            "player_id": request.player_id,
            "player_command": request.player_command,
            "narrative": response.narrative,
            "extracted_commands": response.extracted_commands,
            "provider": response.provider,
            "analysis_model": analysis_model,
            "narrative_model": narrative_model,
            "created_at": created_at,
        }

    def list_turns(self, world_id: int, limit: int = 20) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    world_id,
                    player_id,
                    player_command,
                    narrative,
                    extracted_commands,
                    provider,
                    analysis_model,
                    narrative_model,
                    created_at
                FROM turns
                WHERE world_id = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (world_id, safe_limit),
            ).fetchall()

        results: list[dict] = []
        for row in rows:
            try:
                extracted_commands = json.loads(str(row["extracted_commands"]))
            except json.JSONDecodeError:
                extracted_commands = []

            results.append(
                {
                    "id": int(row["id"]),
                    "world_id": int(row["world_id"]),
                    "player_id": int(row["player_id"]),
                    "player_command": str(row["player_command"]),
                    "narrative": str(row["narrative"]),
                    "extracted_commands": extracted_commands if isinstance(extracted_commands, list) else [],
                    "provider": str(row["provider"]),
                    "analysis_model": str(row["analysis_model"]),
                    "narrative_model": str(row["narrative_model"]),
                    "created_at": str(row["created_at"]),
                }
            )
        return results

    def list_recent_turn_events(self, world_id: int, limit: int = 3) -> list[str]:
        safe_limit = max(1, min(limit, 20))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT player_command, narrative
                FROM turns
                WHERE world_id = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (world_id, safe_limit),
            ).fetchall()

        events: list[str] = []
        for row in reversed(rows):
            command = str(row["player_command"]).strip()
            narrative = str(row["narrative"]).strip()
            events.append(f"Player action: {command} | Outcome: {narrative}")
        return events

    def save_memory_items(self, world_id: int, items: list[dict], source_turn_id: int | None = None) -> int:
        if not items:
            return 0

        now = datetime.now(UTC).isoformat()
        written = 0

        with self._connect() as conn:
            for item in items:
                memory_type = str(item.get("memory_type", "")).strip()
                content = str(item.get("content", "")).strip()
                if not memory_type or not content:
                    continue
                importance = float(item.get("importance", 0.0))
                importance = max(0.0, min(1.0, importance))
                local_source_turn_id = item.get("source_turn_id", source_turn_id)

                conn.execute(
                    """
                    INSERT INTO memory_items(
                        world_id,
                        memory_type,
                        content,
                        importance,
                        source_turn_id,
                        created_at,
                        updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(world_id, memory_type, content)
                    DO UPDATE SET
                        importance = CASE
                            WHEN excluded.importance > memory_items.importance
                            THEN excluded.importance
                            ELSE memory_items.importance
                        END,
                        source_turn_id = COALESCE(excluded.source_turn_id, memory_items.source_turn_id),
                        updated_at = excluded.updated_at;
                    """,
                    (
                        world_id,
                        memory_type,
                        content,
                        importance,
                        local_source_turn_id,
                        now,
                        now,
                    ),
                )
                written += 1
            conn.commit()

        return written

    def list_memory_items(
        self,
        world_id: int,
        limit: int = 20,
        min_importance: float = 0.0,
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        safe_min_importance = max(0.0, min(1.0, min_importance))

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    world_id,
                    memory_type,
                    content,
                    importance,
                    source_turn_id,
                    created_at,
                    updated_at
                FROM memory_items
                WHERE world_id = ? AND importance >= ?
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT ?;
                """,
                (world_id, safe_min_importance, safe_limit),
            ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "world_id": int(row["world_id"]),
                "memory_type": str(row["memory_type"]),
                "content": str(row["content"]),
                "importance": float(row["importance"]),
                "source_turn_id": int(row["source_turn_id"]) if row["source_turn_id"] is not None else None,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]

    def search_memory_items(
        self,
        world_id: int,
        query: str,
        limit: int = 5,
        min_importance: float = 0.5,
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 20))
        candidates = self.list_memory_items(
            world_id=world_id,
            limit=200,
            min_importance=min_importance,
        )
        if not candidates:
            return []

        query_terms = {term for term in re.split(r"\W+", query.lower()) if term}
        if not query_terms:
            return candidates[:safe_limit]

        ranked: list[tuple[float, dict]] = []
        for item in candidates:
            content_terms = {term for term in re.split(r"\W+", item["content"].lower()) if term}
            overlap = len(query_terms.intersection(content_terms))
            score = overlap * 3.0 + float(item["importance"])
            if overlap > 0:
                ranked.append((score, item))

        if not ranked:
            return candidates[:safe_limit]

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ranked[:safe_limit]]
