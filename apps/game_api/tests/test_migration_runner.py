from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.game_api.app.migration_runner import SqliteMigrationRunner


class TestSqliteMigrationRunner(unittest.TestCase):
    def test_apply_all_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            migrations_dir = Path(tmpdir) / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            (migrations_dir / "001_init.sql").write_text(
                "CREATE TABLE IF NOT EXISTS demo (id TEXT PRIMARY KEY);\n",
                encoding="utf-8",
            )
            (migrations_dir / "002_more.sql").write_text(
                "CREATE TABLE IF NOT EXISTS demo2 (id TEXT PRIMARY KEY);\n",
                encoding="utf-8",
            )

            runner = SqliteMigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
            first = runner.apply_all()
            second = runner.apply_all()

            self.assertEqual(first, ["001_init.sql", "002_more.sql"])
            self.assertEqual(second, [])

            conn = sqlite3.connect(db_path)
            try:
                versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            finally:
                conn.close()

            self.assertEqual(versions, ["001", "002"])


if __name__ == "__main__":
    unittest.main()
