from __future__ import annotations

import sqlite3
from datetime import datetime, UTC
from pathlib import Path


class SqliteMigrationRunner:
    """Very small SQLite migration runner with a schema_migrations table.

    This is the lightweight migration basis for local development. It keeps the
    migration flow explicit and testable without introducing a full migration
    framework too early.
    """

    def __init__(self, *, db_path: Path, migrations_dir: Path):
        self.db_path = db_path
        self.migrations_dir = migrations_dir

    def apply_all(self) -> list[str]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            self._ensure_migration_table(conn)
            applied_versions = self._get_applied_versions(conn)
            executed: list[str] = []

            for migration_file in self._iter_migration_files():
                version = migration_file.name.split("_", 1)[0]
                if version in applied_versions:
                    continue
                sql = migration_file.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (version, migration_file.name, datetime.now(UTC).isoformat()),
                )
                conn.commit()
                executed.append(migration_file.name)
            return executed
        finally:
            conn.close()

    def _iter_migration_files(self) -> list[Path]:
        if not self.migrations_dir.exists():
            return []
        return sorted(
            [
                path
                for path in self.migrations_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".sql"
            ],
            key=lambda item: item.name,
        )

    @staticmethod
    def _ensure_migration_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        conn.commit()

    @staticmethod
    def _get_applied_versions(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {str(row["version"]) for row in rows}
