from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages" / "shared_schemas") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
if str(REPO_ROOT / "packages" / "rules_engine") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.services.world_pack_files import (  # noqa: E402
    discover_world_pack_dirs,
    load_world_pack_specs,
)


def validate_world_packs(root_dir: Path) -> tuple[bool, list[str]]:
    messages: list[str] = []
    pack_dirs = discover_world_pack_dirs(root_dir)
    if not pack_dirs:
        return False, [f"No world packs discovered under {root_dir}"]

    seen_pack_ids: set[str] = set()
    for pack_dir in pack_dirs:
        try:
            loaded = load_world_pack_specs(pack_dir)
        except Exception as exc:
            messages.append(f"FAIL [{pack_dir.name}]: {exc}")
            continue
        if loaded.manifest.pack_id in seen_pack_ids:
            messages.append(f"FAIL [{pack_dir.name}]: duplicate pack_id {loaded.manifest.pack_id}")
            continue
        seen_pack_ids.add(loaded.manifest.pack_id)
        messages.append(
            f"PASS [{pack_dir.name}] pack_id={loaded.manifest.pack_id} version={loaded.manifest.version} quests={len(loaded.specs)}"
        )

    ok = all(message.startswith("PASS") for message in messages)
    return ok, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate file-based world pack manifests + quest specs.")
    parser.add_argument(
        "--root-dir",
        default=str(REPO_ROOT / "world_packs"),
        help="Root directory that contains world pack folders.",
    )
    args = parser.parse_args()
    ok, messages = validate_world_packs(Path(args.root_dir).resolve())
    for message in messages:
        print(message)
    if ok:
        print("PASS: world pack validation succeeded")
        return 0
    print("FAIL: world pack validation failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
