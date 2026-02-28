from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.services.world_pack_files import (  # noqa: E402
    discover_world_pack_dirs,
    load_world_pack_specs,
)


class TestWorldPackFiles(unittest.TestCase):
    def test_discover_world_pack_dirs_finds_urban_occult_pack(self):
        root = REPO_ROOT / "world_packs"
        pack_dirs = discover_world_pack_dirs(root)
        names = [entry.name for entry in pack_dirs]
        self.assertIn("urban_occult_v1", names)

    def test_load_world_pack_specs_parses_and_validates_urban_occult(self):
        pack_dir = REPO_ROOT / "world_packs" / "urban_occult_v1"
        loaded = load_world_pack_specs(pack_dir)
        self.assertEqual(loaded.manifest.pack_id, "worldpack-urban-occult-fuyora-market-v1")
        self.assertEqual(loaded.manifest.version, "1.0.0")
        self.assertGreaterEqual(len(loaded.specs), 2)
        spec_ids = {spec.quest_id for spec in loaded.specs}
        self.assertIn("quest-urban-occult-market-ritual-leads", spec_ids)
        self.assertIn("quest-urban-occult-resonance-followup", spec_ids)


if __name__ == "__main__":
    unittest.main()
