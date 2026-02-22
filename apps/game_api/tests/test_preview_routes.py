from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.main import app  # noqa: E402
from apps.game_api.app.persistence import WorldRepository  # noqa: E402
from ls_shared_schemas.npc_memory import NPCProfile  # noqa: E402


class TestGameApiPreviewRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "greenfield_test.db"
        repository = WorldRepository(str(db_path))
        repository.initialize()
        app.state.world_repository = repository

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_world_bootstrap_preview(self):
        response = self.client.post(
            "/v1/worlds/bootstrap/preview",
            json={
                "user_id": "u1",
                "world_description": "Eine Hafenstadt mit Intrigen, Wetterumschlag und rivalisierenden Fraktionen.",
                "character_description": "Eine neugierige Kartografin auf der Suche nach ihrer Schwester.",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("world_seed", payload)
        self.assertIn("initial_narrative", payload)

    def test_g23_world_bootstrap_preview_uses_ip_safe_urban_occult_preset(self):
        response = self.client.post(
            "/v1/worlds/bootstrap/preview",
            json={
                "user_id": "u-g23-preview",
                "world_description": (
                    "Eine moderne Stadt mit geheimer Magie, Relikten und rivalisierenden Fraktionen. "
                    "Ein Ritual fuer einen Champion ist fehlgeschlagen."
                ),
                "character_description": (
                    "Ein junger Binder mit schwachen Mana-Reserven, der ein verbotenes Beschwoerungsritual "
                    "untersucht."
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        world_seed = payload["world_seed"]
        self.assertIn("Urban Occult", world_seed["name"])
        self.assertIn("Binder-Konklave", world_seed["factions"])
        self.assertTrue(any(npc["role"] == "beschwoerer" for npc in world_seed["starter_npcs"]))
        orientation_text = " ".join(payload["player_orientation"])
        self.assertIn("Binder", orientation_text)
        self.assertIn("Champion", orientation_text)

    def test_world_bootstrap_create_and_get_session(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-create-1",
                "world_description": "Eine windige Grenzstadt zwischen Wald und Sumpf mit einem zerbrochenen Waffenstillstand.",
                "character_description": "Ein ehemaliger Spaeher mit Heilerfahrung und schlechten Erinnerungen an den Krieg.",
                "tone": "grim_adventure",
                "difficulty": "challenging",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()

        world_id = created["world_id"]
        self.assertTrue(world_id.startswith("world-"))
        self.assertEqual(created["user_id"], "u-create-1")
        self.assertEqual(created["character_state"]["location_name"], created["world_seed"]["start_location_name"])
        self.assertGreaterEqual(len(created["inventory"]), 1)
        self.assertGreaterEqual(len(created["journal"]), 1)

        get_response = self.client.get(f"/v1/worlds/{world_id}")
        self.assertEqual(get_response.status_code, 200)
        fetched = get_response.json()
        self.assertEqual(fetched["world_id"], world_id)
        self.assertEqual(fetched["world_seed"]["world_id"], world_id)
        self.assertEqual(fetched["initial_narrative"], created["initial_narrative"])

    def test_get_world_session_returns_404_for_unknown_world(self):
        response = self.client.get("/v1/worlds/world-does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_g2_analyze_run_and_list_turns_persists_updates(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g2-1",
                "world_description": "Eine Stadt im Dauerregen, deren Unterstadt von Geruechten und Schulden beherrscht wird.",
                "character_description": "Ein abgekaempfter Kundschafter mit Sinn fuer Heilmittel und schlechte Deals.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        world_id = created["world_id"]
        before_quantity = created["inventory"][0]["quantity"]

        analyze_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/analyze/preview",
            json={"player_input": "Ich gehe zur Taverne und benutze den Starter-Heiltrank."},
        )
        self.assertEqual(analyze_response.status_code, 200)
        intent = analyze_response.json()
        action_types = [action["action_type"] for action in intent["actions"]]
        self.assertIn("MOVE", action_types)
        self.assertIn("USE_ITEM", action_types)

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich gehe zur Taverne und benutze den Starter-Heiltrank."},
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertIn("turn", run_payload)
        self.assertTrue(run_payload["turn"]["turn_id"].startswith("turn-"))
        self.assertGreaterEqual(len(run_payload["journal_entry_ids"]), 2)
        self.assertIn("context_after_turn", run_payload)
        self.assertIsNotNone(run_payload["context_after_turn"])
        self.assertEqual(run_payload["context_after_turn"]["world"]["world_id"], world_id)

        session_response = self.client.get(f"/v1/worlds/{world_id}")
        self.assertEqual(session_response.status_code, 200)
        session_payload = session_response.json()
        self.assertEqual(session_payload["character_state"]["location_name"], "Taverne")
        self.assertEqual(session_payload["inventory"][0]["quantity"], max(0, before_quantity - 1))
        self.assertGreaterEqual(len(session_payload["journal"]), 3)

        turns_response = self.client.get(f"/v1/worlds/{world_id}/turns")
        self.assertEqual(turns_response.status_code, 200)
        turns_payload = turns_response.json()
        self.assertEqual(len(turns_payload), 1)
        self.assertEqual(turns_payload[0]["world_id"], world_id)
        self.assertEqual(
            turns_payload[0]["resolution"]["resulting_character_state"]["location_name"],
            "Taverne",
        )

    def test_g3_talk_turn_creates_npc_memory_bundle(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g3-1",
                "world_description": "Eine regennasse Handelsstadt mit engen Gassen, Wachen und Schuldeneintreibern.",
                "character_description": "Eine wortgewandte Kundschafterin, die Informationen gegen Gefallen tauscht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        run_response = self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich spreche mit Mira."})
        self.assertEqual(run_response.status_code, 200)

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        self.assertGreaterEqual(len(bundles), 1)

        mira = next((bundle for bundle in bundles if bundle["profile"]["name"] == "Mira"), None)
        self.assertIsNotNone(mira)
        self.assertIsNotNone(mira["relationship"])
        self.assertEqual(mira["relationship"]["standing"], 1)
        self.assertGreaterEqual(len(mira["recent_memories"]), 1)
        self.assertIn("talk", mira["recent_memories"][0]["tags"])

    def test_g23_talk_turn_resolves_role_title_to_existing_beschwoerer_npc(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g23-role",
                "world_description": "Eine moderne Stadt mit geheimer Magie und rivalisierenden Zirkeln.",
                "character_description": "Ein Ermittler, der Beschwoerer und Relikte beobachtet.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit dem Beschwoerer ueber das gestoerte Ritual."},
        )
        self.assertEqual(run_response.status_code, 200)

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        beschwoerer_bundle = next((bundle for bundle in bundles if bundle["profile"]["npc_id"] == "npc-circle-binder"), None)
        self.assertIsNotNone(beschwoerer_bundle)
        self.assertEqual(beschwoerer_bundle["profile"]["name"], "Kael")
        self.assertEqual(beschwoerer_bundle["profile"]["role"], "beschwoerer")
        auto_beschwoerer = [
            bundle for bundle in bundles if bundle["profile"]["npc_id"].startswith("npc-auto-") and "beschwoer" in bundle["profile"]["name"].lower()
        ]
        self.assertEqual(auto_beschwoerer, [])

    def test_g24_ambiguous_role_title_talk_returns_clarify_instead_of_creating_new_npc(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g24-ambiguity",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Ritualen und rivalisierenden Zirkeln.",
                "character_description": "Eine Beobachterin, die Binder und Champions im Blick behaelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        repository = app.state.world_repository
        with repository._connect() as conn:  # noqa: SLF001 - test helper access
            repository._upsert_world_npc_profiles(  # noqa: SLF001 - test helper access
                conn=conn,
                world_id=world_id,
                profiles=[
                    NPCProfile(
                        npc_id="npc-liora-circle",
                        name="Liora",
                        role="beschwoerer",
                        faction="binder_konklave",
                        location_name="Marktplatz",
                        scene_zone_id="zone-market-stalls",
                        scene_zone_name="Marktstaende",
                    )
                ],
                timestamp="2026-02-22T00:00:00Z",
            )
            character_row = repository._get_primary_character_row(conn, world_id)  # noqa: SLF001 - test helper access
            self.assertIsNotNone(character_row)
            repository._upsert_npc_discovery(  # noqa: SLF001 - test helper access
                conn=conn,
                world_id=world_id,
                world_character_id=str(character_row["world_character_id"]),
                npc_id="npc-liora-circle",
                timestamp="2026-02-22T00:00:00Z",
            )
            conn.commit()

        ambiguous_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit dem Beschwoerer."},
        )
        self.assertEqual(ambiguous_response.status_code, 200)
        payload = ambiguous_response.json()
        applied_action_types = [action["action_type"] for action in payload["turn"]["resolution"]["applied_actions"]]
        self.assertEqual(applied_action_types, [])

        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("clarify_required", event_codes)

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        auto_plain_beschwoerer = [
            bundle
            for bundle in bundles
            if bundle["profile"]["npc_id"] == "npc-auto-beschwoerer" or bundle["profile"]["name"] == "Beschwoerer"
        ]
        self.assertEqual(auto_plain_beschwoerer, [])

    def test_devtest_spawn_npc_endpoint_creates_visible_npc_profile(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-devspawn-1",
                "world_description": "Eine Stadt mit geheimer Magie, Markt und Fraktionen im Schatten.",
                "character_description": "Ein Beobachter, der neue Kontakte im Verborgenen sucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        spawn_response = self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-test-lyra",
                "name": "Lyra",
                "role": "beschwoerer",
                "faction": "binder_konklave",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-fountain-ring",
                "scene_zone_name": "Brunnenplatz",
                "standing_for_player": 2,
            },
        )
        self.assertEqual(spawn_response.status_code, 200)
        self.assertEqual(spawn_response.json()["npc_id"], "npc-test-lyra")

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        lyra_bundle = next(bundle for bundle in bundles if bundle["profile"]["npc_id"] == "npc-test-lyra")
        self.assertEqual(lyra_bundle["profile"]["name"], "Lyra")
        self.assertEqual(lyra_bundle["profile"]["role"], "beschwoerer")
        self.assertEqual(lyra_bundle["relationship"]["standing"], 2)

    def test_g26_hidden_spawned_npc_is_revealed_after_inspect(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g26-discovery",
                "world_description": "Eine moderne Stadt mit geheimer Magie und versteckten Beobachtern.",
                "character_description": "Ein aufmerksamer Binder, der unbekannte Praesenzen bemerkt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        spawn_response = self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-hidden-lyra",
                "name": "Lyra",
                "role": "beschwoerer",
                "faction": "binder_konklave",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-fountain-ring",
                "scene_zone_name": "Brunnenplatz",
                "revealed_to_player": False,
            },
        )
        self.assertEqual(spawn_response.status_code, 200)

        context_before = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_before.status_code, 200)
        before_payload = context_before.json()
        before_npc_ids = [entry["ref_id"] for entry in before_payload["target_catalog"]["npcs"]]
        self.assertNotIn("npc-hidden-lyra", before_npc_ids)
        self.assertTrue(any("unbekannte Praesenz" in note for note in before_payload["retrieval_notes"]))
        self.assertEqual(before_payload["target_catalog"]["scene_points"], [])
        self.assertTrue(any("Interaktionspunkt" in note for note in before_payload["retrieval_notes"]))

        inspect_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(inspect_response.status_code, 200)
        inspect_payload = inspect_response.json()
        inspect_event_codes = [event["code"] for event in inspect_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("discovery_revealed_npcs", inspect_event_codes)
        self.assertIn("discovery_revealed_scene_points", inspect_event_codes)

        context_after = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_after.status_code, 200)
        after_payload = context_after.json()
        after_npc_ids = [entry["ref_id"] for entry in after_payload["target_catalog"]["npcs"]]
        self.assertIn("npc-hidden-lyra", after_npc_ids)
        self.assertGreaterEqual(len(after_payload["target_catalog"]["scene_points"]), 1)
        self.assertFalse(any("Interaktionspunkt" in note for note in after_payload["retrieval_notes"]))

    def test_g25_descriptive_talk_reference_returns_clarify_and_does_not_create_fake_npc(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g25-desc",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Ritualen und rivalisierenden Zirkeln.",
                "character_description": "Eine Beobachterin, die Binder und Champions im Blick behaelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich spreche den zweiten Beschwoerer an."},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("clarify_required", event_codes)
        applied_action_types = [action["action_type"] for action in payload["turn"]["resolution"]["applied_actions"]]
        self.assertEqual(applied_action_types, [])

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        bundles = memory_response.json()
        fake_targets = [
            bundle
            for bundle in bundles
            if bundle["profile"]["npc_id"].startswith("npc-auto-")
            and ("zweiten" in bundle["profile"]["name"].lower() or bundle["profile"]["name"].lower() == "npc")
        ]
        self.assertEqual(fake_targets, [])

    def test_g26_talk_to_unknown_name_requires_clarify_until_revealed(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g26-talk-hidden",
                "world_description": "Eine moderne Stadt mit geheimer Magie und unerkannten Akteuren.",
                "character_description": "Eine Ermittlerin, die erst die Umgebung sondiert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-hidden-nyx",
                "name": "Nyx",
                "role": "magier",
                "location_name": "Marktplatz",
                "revealed_to_player": False,
            },
        )

        hidden_talk_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit Nyx."},
        )
        self.assertEqual(hidden_talk_response.status_code, 200)
        hidden_payload = hidden_talk_response.json()
        hidden_codes = [event["code"] for event in hidden_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("clarify_required", hidden_codes)

        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich schau mich um."})
        revealed_talk_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit Nyx."},
        )
        self.assertEqual(revealed_talk_response.status_code, 200)
        revealed_payload = revealed_talk_response.json()
        applied_actions = [action["action_type"] for action in revealed_payload["turn"]["resolution"]["applied_actions"]]
        self.assertIn("TALK", applied_actions)

    def test_g27_inspect_visible_scene_point_via_structured_action_succeeds(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g27-scenepoint",
                "world_description": "Eine moderne Stadt mit geheimer Magie und einem verstoerten Ritual am Marktplatz.",
                "character_description": "Ein aufmerksamer Ermittler, der Spuren systematisch untersucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        payload = context_response.json()
        point = next((entry for entry in payload["target_catalog"]["scene_points"]), None)
        self.assertIsNotNone(point)

        inspect_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": f"UI: Untersuche {point['name']}",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": point["ref_id"],
                        "target_kind": "scene_point",
                        "parameters": {
                            "intent": "inspect",
                            "target_id": point["ref_id"],
                            "target_name": point["name"],
                            "target_kind": "scene_point",
                        },
                    }
                ],
            },
        )
        self.assertEqual(inspect_response.status_code, 200)
        inspect_payload = inspect_response.json()
        event_codes = [event["code"] for event in inspect_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("inspect_focus_success", event_codes)

    def test_g4_context_endpoint_assembles_turns_journal_and_npc_memory(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g4-1",
                "world_description": "Eine Hafenstadt voller Schmuggler, Nachtmaerkte und korrupten Zollbeamten.",
                "character_description": "Eine ehemalige Kartografin, die ueber Kontakte und Wissen handelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich spreche mit Mira ueber Schmuggler im Hafen."})
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich gehe zum Hafen und schaue mich um."},
        )

        context_response = self.client.get(
            f"/v1/worlds/{world_id}/context",
            params={"player_input": "Ich will mehr ueber Mira und Schmuggler wissen."},
        )
        self.assertEqual(context_response.status_code, 200)
        payload = context_response.json()

        self.assertEqual(payload["world"]["world_id"], world_id)
        self.assertGreaterEqual(len(payload["recent_turns"]), 2)
        self.assertGreaterEqual(len(payload["recent_journal"]), 3)
        self.assertGreaterEqual(len(payload["npc_memory"]), 1)
        self.assertIn("target_catalog", payload)
        self.assertGreaterEqual(len(payload["target_catalog"]["items"]), 1)
        self.assertGreaterEqual(len(payload["target_catalog"]["locations"]), 1)
        self.assertEqual(payload["retrieval_player_input"], "Ich will mehr ueber Mira und Schmuggler wissen.")
        self.assertTrue(payload["retrieval_notes"])

        top_bundle = payload["npc_memory"][0]
        self.assertIn("bundle", top_bundle)
        self.assertIn("relevance_score", top_bundle)
        self.assertIn("retrieval_reasons", top_bundle)

    def test_g6_repeated_identical_talk_dedupes_npc_memory_summary(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g6-1",
                "world_description": "Eine Handelsstadt mit Informanten in Tavernen und auf dem Markt.",
                "character_description": "Ein Reisender, der mit Gespraechen Informationen sammelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        for _ in range(2):
            run_response = self.client.post(
                f"/v1/worlds/{world_id}/turns/run",
                json={"player_input": "Ich spreche mit Mira."},
            )
            self.assertEqual(run_response.status_code, 200)
            applied_actions = run_response.json()["turn"]["resolution"]["applied_actions"]
            talk_action = next(action for action in applied_actions if action["action_type"] == "TALK")
            self.assertTrue(
                talk_action["target_ref"].startswith("npc-") or talk_action["target_ref"] == "Mira",
                msg=f"unexpected target_ref={talk_action['target_ref']}",
            )

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        mira = next(bundle for bundle in bundles if bundle["profile"]["name"] == "Mira")
        summaries = [memory["summary"] for memory in mira["recent_memories"]]
        self.assertEqual(len(summaries), len(set(summaries)))
        self.assertEqual(len(summaries), 1)
        self.assertEqual(mira["relationship"]["standing"], 2)

    def test_g10_run_turn_accepts_structured_actions_override(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g10-1",
                "world_description": "Eine Hafenstadt mit Markt, Taverne und mehreren Informanten.",
                "character_description": "Eine Beobachterin, die gezielt mit Leuten spricht und Orte ansteuert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        world_id = created["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        zorak_ref = next(
            (entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira"),
            None,
        )
        if zorak_ref is None:
            self.skipTest("Kein Mira im Target-Catalog vorhanden.")

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": zorak_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": zorak_ref["ref_id"],
                            "target_name": "Mira",
                        },
                    }
                ],
            },
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertIn("UI structured action override", " ".join(run_payload["turn"]["intent"]["analysis_notes"]))

        talk_action = next(
            action for action in run_payload["turn"]["resolution"]["applied_actions"] if action["action_type"] == "TALK"
        )
        self.assertEqual(talk_action["target_ref"], zorak_ref["ref_id"])

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        zorak_bundle = next(bundle for bundle in bundles if bundle["profile"]["npc_id"] == zorak_ref["ref_id"])
        self.assertEqual(zorak_bundle["relationship"]["standing"], 1)

    def test_g11_run_turn_accepts_multi_action_override_queue(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g11-1",
                "world_description": "Eine Stadt mit Markt und Taverne sowie einem gesprächigen Haendler.",
                "character_description": "Eine Reisende, die zuerst Orte aufsucht und dann Informationen sammelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        market_ref = next(
            (entry for entry in context_payload["target_catalog"]["locations"] if entry["name"] == "Marktplatz"),
            None,
        )
        if market_ref is None:
            market_ref = context_payload["target_catalog"]["locations"][0]
        npc_ref = context_payload["target_catalog"]["npcs"][0]

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI Queue: Gehe zum Marktplatz und rede mit Haendler",
                "actions_override": [
                    {
                        "action_type": "MOVE",
                        "target_ref": market_ref["ref_id"],
                        "destination": "Marktplatz",
                        "target_kind": "location",
                        "parameters": {
                            "intent": "move",
                            "destination_id": market_ref["ref_id"],
                            "destination_name": "Marktplatz",
                        },
                    },
                    {
                        "action_type": "TALK",
                        "target_ref": npc_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": npc_ref["ref_id"],
                            "target_name": npc_ref["name"],
                        },
                    },
                ],
            },
        )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["resulting_character_state"]["location_name"], "Marktplatz")
        applied = payload["turn"]["resolution"]["applied_actions"]
        self.assertEqual([a["action_type"] for a in applied], ["MOVE", "TALK"])
        self.assertIn("UI structured action override", " ".join(payload["turn"]["intent"]["analysis_notes"]))

    def test_g13_context_marks_same_location_other_zone_as_near_and_attack_auto_approaches(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g13-1",
                "world_description": "Ein Marktplatz mit Haendlern, Wachen und einer Heilerin an den Marktstaenden.",
                "character_description": "Eine kampferprobte Reisende, die schnell auf Konflikte reagiert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()

        mira_ref = next(
            (entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira"),
            None,
        )
        if mira_ref is None:
            self.skipTest("Mira nicht im Target-Catalog gefunden.")

        self.assertEqual(mira_ref["location_name"], "Marktplatz")
        self.assertEqual(mira_ref["distance_band_to_player"], "near")

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Greife Mira an",
                "actions_override": [
                    {
                        "action_type": "ATTACK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "attack",
                            "target_id": mira_ref["ref_id"],
                            "target_name": "Mira",
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        event_codes = [event["code"] for event in run_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("auto_approach_for_attack", event_codes)
        self.assertIn("attack_resolved", event_codes)

        after_context = run_payload["context_after_turn"]
        self.assertIsNotNone(after_context)
        updated_mira_ref = next(
            (entry for entry in after_context["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"]),
            None,
        )
        self.assertIsNotNone(updated_mira_ref)
        self.assertEqual(updated_mira_ref["distance_band_to_player"], "adjacent")

    def test_g14_queue_talk_then_attack_updates_standing_and_keeps_adjacent_context(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g14-1",
                "world_description": "Ein ueberfuellter Marktplatz mit Heilerin Mira und gereizten Stadtwachen.",
                "character_description": "Ein direkter Abenteurer, der erst redet und dann zuschlaegt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        mira_ref = next(
            (entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira"),
            None,
        )
        if mira_ref is None:
            self.skipTest("Mira nicht im Target-Catalog gefunden.")

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI Queue: Rede mit Mira und greife sie an",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": mira_ref["ref_id"],
                            "target_name": mira_ref["name"],
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    },
                    {
                        "action_type": "ATTACK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "attack",
                            "attack_mode": "melee",
                            "target_id": mira_ref["ref_id"],
                            "target_name": mira_ref["name"],
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    },
                ],
            },
        )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("talk_success", event_codes)
        self.assertIn("attack_resolved", event_codes)

        after_context = payload["context_after_turn"]
        self.assertIsNotNone(after_context)
        updated_mira_ref = next(
            (entry for entry in after_context["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"]),
            None,
        )
        self.assertIsNotNone(updated_mira_ref)
        self.assertEqual(updated_mira_ref["distance_band_to_player"], "adjacent")

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        mira_bundle = next(bundle for bundle in bundles if bundle["profile"]["npc_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_bundle["relationship"]["standing"], -4)

    def test_g15_retreat_from_adjacent_npc_changes_distance_to_near(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g15-1",
                "world_description": "Ein dichter Marktplatz mit Mira an den Marktstaenden.",
                "character_description": "Ein vorsichtiger Abenteurer, der Abstand halten will.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        mira_ref = next(entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira")

        # First become adjacent via TALK auto-approach.
        talk_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": mira_ref["ref_id"],
                            "target_name": mira_ref["name"],
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_response.status_code, 200)

        talk_after = talk_response.json()["context_after_turn"]
        adjacent_mira_ref = next(entry for entry in talk_after["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(adjacent_mira_ref["distance_band_to_player"], "adjacent")

        retreat_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Abstand zu Mira",
                "actions_override": [
                    {
                        "action_type": "RETREAT",
                        "target_ref": adjacent_mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "retreat",
                            "target_id": adjacent_mira_ref["ref_id"],
                            "target_name": adjacent_mira_ref["name"],
                            "target_location_name": adjacent_mira_ref.get("location_name"),
                            "target_zone_id": adjacent_mira_ref.get("scene_zone_id"),
                            "target_zone_name": adjacent_mira_ref.get("scene_zone_name"),
                            "target_distance_band": adjacent_mira_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(retreat_response.status_code, 200)
        retreat_payload = retreat_response.json()
        retreat_codes = [event["code"] for event in retreat_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("retreat_success", retreat_codes)

        retreat_after = retreat_payload["context_after_turn"]
        updated_mira_ref = next(entry for entry in retreat_after["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(updated_mira_ref["distance_band_to_player"], "near")

    def test_g16_second_retreat_advances_distance_from_near_to_far(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g16-1",
                "world_description": "Ein enger Marktplatz mit Mira und wenig Platz zwischen den Staenden.",
                "character_description": "Ein vorsichtiger Schuetze, der Distanz kontrolliert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        mira_ref = next(entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira")

        # Become adjacent.
        talk_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": mira_ref["ref_id"],
                            "target_name": mira_ref["name"],
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_response.status_code, 200)
        ctx_adjacent = talk_response.json()["context_after_turn"]
        mira_adjacent = next(entry for entry in ctx_adjacent["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_adjacent["distance_band_to_player"], "adjacent")

        # First retreat => near.
        retreat_1 = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Abstand zu Mira",
                "actions_override": [
                    {
                        "action_type": "RETREAT",
                        "target_ref": mira_adjacent["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "retreat",
                            "target_id": mira_adjacent["ref_id"],
                            "target_name": mira_adjacent["name"],
                            "target_location_name": mira_adjacent.get("location_name"),
                            "target_zone_id": mira_adjacent.get("scene_zone_id"),
                            "target_zone_name": mira_adjacent.get("scene_zone_name"),
                            "target_distance_band": mira_adjacent.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(retreat_1.status_code, 200)
        ctx_near = retreat_1.json()["context_after_turn"]
        mira_near = next(entry for entry in ctx_near["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_near["distance_band_to_player"], "near")

        # Second retreat => far.
        retreat_2 = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Mehr Abstand zu Mira",
                "actions_override": [
                    {
                        "action_type": "RETREAT",
                        "target_ref": mira_near["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "retreat",
                            "target_id": mira_near["ref_id"],
                            "target_name": mira_near["name"],
                            "target_location_name": mira_near.get("location_name"),
                            "target_zone_id": mira_near.get("scene_zone_id"),
                            "target_zone_name": mira_near.get("scene_zone_name"),
                            "target_distance_band": mira_near.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(retreat_2.status_code, 200)
        retreat_2_payload = retreat_2.json()
        codes = [event["code"] for event in retreat_2_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("retreat_success", codes)
        ctx_far = retreat_2_payload["context_after_turn"]
        mira_far = next(entry for entry in ctx_far["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_far["distance_band_to_player"], "far")

    def test_g17_two_approaches_after_far_restore_adjacent_distance(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g17-1",
                "world_description": "Ein Marktplatz mit Mira, viel Raum zum Manövrieren und mehreren Fluchtwegen.",
                "character_description": "Ein vorsichtiger Abenteurer, der Distanz taktisch steuert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        mira_ref = next(entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira")

        # Get adjacent first via talk.
        talk_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": mira_ref["ref_id"],
                            "target_name": mira_ref["name"],
                            "target_location_name": mira_ref.get("location_name"),
                            "target_zone_id": mira_ref.get("scene_zone_id"),
                            "target_zone_name": mira_ref.get("scene_zone_name"),
                            "target_distance_band": mira_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_response.status_code, 200)
        ctx_adjacent = talk_response.json()["context_after_turn"]
        mira_current = next(entry for entry in ctx_adjacent["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_current["distance_band_to_player"], "adjacent")

        # Retreat twice to far.
        for expected in ("near", "far"):
            retreat_response = self.client.post(
                f"/v1/worlds/{world_id}/turns/run",
                json={
                    "player_input": f"UI: Abstand {expected}",
                    "actions_override": [
                        {
                            "action_type": "RETREAT",
                            "target_ref": mira_current["ref_id"],
                            "target_kind": "npc",
                            "parameters": {
                                "intent": "retreat",
                                "target_id": mira_current["ref_id"],
                                "target_name": mira_current["name"],
                                "target_location_name": mira_current.get("location_name"),
                                "target_zone_id": mira_current.get("scene_zone_id"),
                                "target_zone_name": mira_current.get("scene_zone_name"),
                                "target_distance_band": mira_current.get("distance_band_to_player"),
                            },
                        }
                    ],
                },
            )
            self.assertEqual(retreat_response.status_code, 200)
            ctx_next = retreat_response.json()["context_after_turn"]
            mira_current = next(entry for entry in ctx_next["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
            self.assertEqual(mira_current["distance_band_to_player"], expected)

        # Approach twice back to adjacent.
        for expected in ("near", "adjacent"):
            approach_response = self.client.post(
                f"/v1/worlds/{world_id}/turns/run",
                json={
                    "player_input": f"UI: Annaehern {expected}",
                    "actions_override": [
                        {
                            "action_type": "APPROACH",
                            "target_ref": mira_current["ref_id"],
                            "target_kind": "npc",
                            "parameters": {
                                "intent": "approach",
                                "target_id": mira_current["ref_id"],
                                "target_name": mira_current["name"],
                                "target_location_name": mira_current.get("location_name"),
                                "target_zone_id": mira_current.get("scene_zone_id"),
                                "target_zone_name": mira_current.get("scene_zone_name"),
                                "target_distance_band": mira_current.get("distance_band_to_player"),
                            },
                        }
                    ],
                },
            )
            self.assertEqual(approach_response.status_code, 200)
            payload = approach_response.json()
            codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
            self.assertIn("approach_success", codes)
            ctx_next = payload["context_after_turn"]
            mira_current = next(entry for entry in ctx_next["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
            self.assertEqual(mira_current["distance_band_to_player"], expected)


if __name__ == "__main__":
    unittest.main()
