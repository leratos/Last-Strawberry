import unittest
from datetime import UTC, datetime

from backend_v2.app.models import TurnRequest, TurnResponse
from backend_v2.app.services.memory import MemoryWritePolicy


class TestMemoryWritePolicy(unittest.TestCase):
    def test_build_items_filters_by_importance_and_extracts_domain_facts(self):
        policy = MemoryWritePolicy(min_importance=0.6)
        request = TurnRequest(
            world_id=1,
            player_id=1,
            player_command="Ich gehe zum Tempel und suche Elara.",
        )
        response = TurnResponse(
            narrative="Du erreichst den Tempel und entdeckst eine frische Spur.",
            extracted_commands=[
                {"command": "PLAYER_MOVE", "location_name": "Tempel"},
                {"command": "NPC_CREATE", "name": "Elara"},
                {"command": "ROLL_CHECK", "attribut": "Wahrnehmung"},
            ],
            provider="fake",
            models={"analysis": "a", "narrative": "b"},
            created_at=datetime.now(UTC),
        )

        items = policy.build_items(request, response)
        content_blob = " | ".join(item["content"] for item in items)
        self.assertNotIn("Player intent", content_blob)  # filtered at 0.6 threshold
        self.assertIn("NPC introduced: Elara", content_blob)
        self.assertIn("Player moved to: Tempel", content_blob)
        self.assertIn("Check requested on attribute: Wahrnehmung", content_blob)
        self.assertTrue(any(item["memory_type"] == "story_beat" for item in items))


if __name__ == "__main__":
    unittest.main()
