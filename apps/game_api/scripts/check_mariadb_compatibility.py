from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


SQLITE_ERROR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("sqlite_pragma", r"\bPRAGMA\b"),
    ("sqlite_autoincrement", r"\bAUTOINCREMENT\b"),
    ("sqlite_without_rowid", r"\bWITHOUT\s+ROWID\b"),
    ("sqlite_insert_or_replace", r"\bINSERT\s+OR\s+REPLACE\b"),
)

SQLITE_WARNING_PATTERNS: tuple[tuple[str, str], ...] = (
    ("sqlite_json_text_storage", r"\bJSON\b"),
    ("sqlite_specific_datetime_fn", r"\bstrftime\s*\("),
)


@dataclass(frozen=True)
class SqlIssue:
    severity: str
    code: str
    file: str
    line: int
    snippet: str


def scan_migration_sql_for_mariadb_compatibility(migrations_dir: Path) -> dict[str, object]:
    issues: list[SqlIssue] = []
    files_scanned = 0

    if not migrations_dir.exists():
        return {
            "ok": False,
            "error": f"Migrations directory not found: {migrations_dir}",
            "files_scanned": 0,
            "issues": [],
            "notes": [],
        }

    for path in sorted(migrations_dir.glob("*.sql")):
        files_scanned += 1
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for line_number, line in enumerate(lines, start=1):
            for code, pattern in SQLITE_ERROR_PATTERNS:
                if re.search(pattern, line, re.I):
                    issues.append(
                        SqlIssue(
                            severity="error",
                            code=code,
                            file=str(path),
                            line=line_number,
                            snippet=line.strip(),
                        )
                    )
            for code, pattern in SQLITE_WARNING_PATTERNS:
                if re.search(pattern, line, re.I):
                    issues.append(
                        SqlIssue(
                            severity="warning",
                            code=code,
                            file=str(path),
                            line=line_number,
                            snippet=line.strip(),
                        )
                    )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    notes = [
        "Check scannt nur Migrations-SQL auf offensichtliche SQLite-Syntax.",
        "Python-Repository-Queries (Platzhalterstil `?`) muessen fuer MariaDB-Driver separat angepasst werden.",
        "MariaDB-Deployment sollte InnoDB + utf8mb4 verwenden.",
    ]
    return {
        "ok": error_count == 0,
        "files_scanned": files_scanned,
        "issue_counts": {"errors": error_count, "warnings": warning_count},
        "issues": [issue.__dict__ for issue in issues],
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Greenfield migration SQL for MariaDB portability issues.")
    parser.add_argument(
        "--migrations-dir",
        default="apps/game_api/app/migrations",
        help="Directory with SQL migrations to scan.",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Return exit code 1 when warnings are present.",
    )
    args = parser.parse_args()

    report = scan_migration_sql_for_mariadb_compatibility(Path(args.migrations_dir))
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if not report.get("ok", False):
        return 1
    if args.strict_warnings and int(report.get("issue_counts", {}).get("warnings", 0)) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
