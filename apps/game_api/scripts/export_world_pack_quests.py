from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages" / "shared_schemas") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
if str(REPO_ROOT / "packages" / "rules_engine") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.services.quest_authoring import (  # noqa: E402
    URBAN_OCCULT_FOLLOWUP_QUEST_ID,
    URBAN_OCCULT_QUEST_ID,
    get_authored_quest_spec_registry,
)
from apps.game_api.app.services.quest_authoring_api import quest_spec_to_authoring_payload  # noqa: E402
from apps.game_api.app.services.world_pack_authoring import (  # noqa: E402
    URBAN_OCCULT_WORLD_PACK,
)


def export_urban_occult_world_pack(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    quest_dir = target_dir / "quest_specs"
    quest_dir.mkdir(parents=True, exist_ok=True)

    registry = get_authored_quest_spec_registry()
    quest_ids = [URBAN_OCCULT_QUEST_ID, URBAN_OCCULT_FOLLOWUP_QUEST_ID]

    quest_refs: list[dict[str, str]] = []
    for quest_id in quest_ids:
        if quest_id not in registry:
            raise KeyError(f"Quest spec not found in authored registry: {quest_id}")
        file_name = f"{quest_id}.json"
        quest_path = quest_dir / file_name
        payload = quest_spec_to_authoring_payload(registry[quest_id])
        quest_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        quest_refs.append({"quest_id": quest_id, "file": f"quest_specs/{file_name}"})

    manifest = {
        "schema_version": "1.0.0",
        "pack_id": URBAN_OCCULT_WORLD_PACK.pack_id,
        "version": URBAN_OCCULT_WORLD_PACK.version,
        "display_name": URBAN_OCCULT_WORLD_PACK.display_name,
        "genre": URBAN_OCCULT_WORLD_PACK.genre,
        "changelog": "CHANGELOG.md",
        "quest_specs": quest_refs,
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    changelog = target_dir / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text(
            "# Changelog - Urban Occult Pack\n\n"
            "## 1.0.0\n"
            "- Initial exported quest-spec baseline from authored in-code registry.\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export in-code authored quest specs into world_packs format.")
    parser.add_argument(
        "--target-dir",
        default=str(REPO_ROOT / "world_packs" / "urban_occult_v1"),
        help="Target world pack directory.",
    )
    args = parser.parse_args()
    target_dir = Path(args.target_dir).resolve()
    export_urban_occult_world_pack(target_dir)
    print(f"PASS: exported urban occult world pack to {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
