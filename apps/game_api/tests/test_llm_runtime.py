from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.config import Settings  # noqa: E402
from apps.game_api.app.services.llm_runtime import LlmRuntime, build_llm_runtime  # noqa: E402
from ls_shared_schemas.character import CharacterAttributes, CharacterResources, CharacterState  # noqa: E402
from ls_shared_schemas.inventory import InventoryItemInstance, ItemUseMode  # noqa: E402
from ls_shared_schemas.turns import ActionType, TurnResolution, TurnSystemEvent  # noqa: E402


class TestLlmRuntime(unittest.TestCase):
    def _base_settings(self, **overrides):
        defaults = dict(
            environment="test",
            api_title="t",
            api_version="t",
            database_path=":memory:",
            public_game_domain="last-strawberry.com",
            llm_mode="preview",
            llm_fallback_to_preview=True,
            openrouter_api_key="",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_intent_model="model-intent",
            openrouter_narrator_model="model-narr",
            cors_allowed_origins=("http://127.0.0.1:3001",),
        )
        defaults.update(overrides)
        return Settings(**defaults)

    def test_status_preview_default(self):
        runtime = build_llm_runtime(self._base_settings())
        status = runtime.status()
        self.assertEqual(status.intent_provider, "preview")
        self.assertEqual(status.narration_provider, "preview")
        self.assertFalse(status.openrouter_configured)

    def test_openrouter_mode_without_key_falls_back_to_preview(self):
        runtime = LlmRuntime(self._base_settings(llm_mode="openrouter", llm_fallback_to_preview=True, openrouter_api_key=""))
        intent = runtime.analyze_intent(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich spreche mit Zorak.",
            inventory=[],
            known_npc_names=["Zorak"],
            known_locations=["Marktplatz"],
            context=None,
        )
        self.assertEqual(intent.actions[0].action_type, ActionType.talk)
        self.assertEqual(intent.actions[0].target_ref, "Zorak")

    def test_narrate_fallback_preview_when_openrouter_unconfigured(self):
        runtime = LlmRuntime(self._base_settings(llm_mode="openrouter", llm_fallback_to_preview=True, openrouter_api_key=""))
        resolution = TurnResolution(
            world_id="w1",
            world_character_id="wc1",
            resulting_character_state=CharacterState(
                world_character_id="wc1",
                name="Ari",
                location_name="Taverne",
                attributes=CharacterAttributes(strength=10, dexterity=10, intelligence=10, charisma=10),
                resources=CharacterResources(hp=10, max_hp=10, stamina=9, max_stamina=10, focus=3, max_focus=3),
            ),
            resulting_inventory=[
                InventoryItemInstance(
                    inventory_item_id="inv-1",
                    item_def_id="potion",
                    name="Trank",
                    use_modes=[ItemUseMode.inspect],
                )
            ],
            system_events=[TurnSystemEvent(code="move_success", message="Bewegung nach Taverne.")],
        )
        narrative = runtime.narrate(resolution=resolution, context_before=None)
        self.assertIn("Taverne", narrative.narrative)


if __name__ == "__main__":
    unittest.main()
