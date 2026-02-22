from pathlib import Path
import tempfile
import unittest


from apps.game_api.scripts.check_mariadb_compatibility import scan_migration_sql_for_mariadb_compatibility


class TestMariaDbCompatibilityCheck(unittest.TestCase):
    def test_detects_sqlite_specific_syntax(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations_dir = Path(tmpdir) / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            (migrations_dir / "001_test.sql").write_text(
                "PRAGMA foreign_keys=ON;\n"
                "CREATE TABLE demo (id INTEGER PRIMARY KEY AUTOINCREMENT);\n",
                encoding="utf-8",
            )

            report = scan_migration_sql_for_mariadb_compatibility(migrations_dir)

            self.assertFalse(report["ok"])
            self.assertEqual(report["files_scanned"], 1)
            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("sqlite_pragma", codes)
            self.assertIn("sqlite_autoincrement", codes)


if __name__ == "__main__":
    unittest.main()
