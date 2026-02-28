from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.game_api.app.services.quest_authoring_api import quest_spec_payload_to_spec
from apps.game_api.app.services.quest_authoring_api import QuestSpecPayload
from apps.game_api.app.services.quest_specs import QuestSpec, validate_quest_specs_for_activation


@dataclass(frozen=True)
class WorldPackSpecRef:
    quest_id: str
    file: str


@dataclass(frozen=True)
class WorldPackManifest:
    schema_version: str
    pack_id: str
    version: str
    display_name: str
    genre: str
    changelog: str
    quest_specs: tuple[WorldPackSpecRef, ...]


@dataclass(frozen=True)
class WorldPackLoadResult:
    manifest: WorldPackManifest
    raw_specs: list[dict[str, Any]]
    specs: list[QuestSpec]


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def load_world_pack_manifest(pack_dir: Path) -> WorldPackManifest:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest.json in {pack_dir}")
    payload = _read_json_file(manifest_path)

    required_fields = ("schema_version", "pack_id", "version", "display_name", "genre", "changelog", "quest_specs")
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"Manifest missing fields {missing}: {manifest_path}")

    raw_specs = payload.get("quest_specs")
    if not isinstance(raw_specs, list):
        raise ValueError(f"Manifest field 'quest_specs' must be list: {manifest_path}")

    refs: list[WorldPackSpecRef] = []
    for index, entry in enumerate(raw_specs):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest quest_specs[{index}] must be object: {manifest_path}")
        quest_id = str(entry.get("quest_id") or "").strip()
        file_name = str(entry.get("file") or "").strip()
        if not quest_id or not file_name:
            raise ValueError(f"Manifest quest_specs[{index}] requires quest_id+file: {manifest_path}")
        refs.append(WorldPackSpecRef(quest_id=quest_id, file=file_name))

    return WorldPackManifest(
        schema_version=str(payload["schema_version"]),
        pack_id=str(payload["pack_id"]),
        version=str(payload["version"]),
        display_name=str(payload["display_name"]),
        genre=str(payload["genre"]),
        changelog=str(payload["changelog"]),
        quest_specs=tuple(refs),
    )


def load_world_pack_specs(pack_dir: Path) -> WorldPackLoadResult:
    manifest = load_world_pack_manifest(pack_dir)
    changelog_path = pack_dir / manifest.changelog
    if not changelog_path.exists():
        raise ValueError(f"Missing changelog file: {changelog_path}")

    raw_specs: list[dict[str, Any]] = []
    specs: list[QuestSpec] = []
    seen_quest_ids: set[str] = set()
    for entry in manifest.quest_specs:
        spec_path = pack_dir / entry.file
        if not spec_path.exists():
            raise ValueError(f"Missing quest spec file: {spec_path}")
        payload = _read_json_file(spec_path)
        raw_specs.append(payload)
        parsed = QuestSpecPayload.model_validate(payload)
        if parsed.quest_id != entry.quest_id:
            raise ValueError(
                f"Quest id mismatch in {spec_path}: manifest={entry.quest_id} file={parsed.quest_id}"
            )
        if parsed.quest_id in seen_quest_ids:
            raise ValueError(f"Duplicate quest_id in pack {manifest.pack_id}: {parsed.quest_id}")
        seen_quest_ids.add(parsed.quest_id)
        specs.append(quest_spec_payload_to_spec(parsed))

    validation = validate_quest_specs_for_activation(specs, existing_quest_ids=set())
    if not validation.ok:
        raise ValueError(
            f"World pack quest validation failed for {manifest.pack_id}: " + ", ".join(validation.errors)
        )

    return WorldPackLoadResult(manifest=manifest, raw_specs=raw_specs, specs=specs)


def discover_world_pack_dirs(world_packs_root: Path) -> list[Path]:
    if not world_packs_root.exists():
        return []
    return sorted(
        [path for path in world_packs_root.iterdir() if path.is_dir() and (path / "manifest.json").exists()],
        key=lambda path: path.name,
    )
