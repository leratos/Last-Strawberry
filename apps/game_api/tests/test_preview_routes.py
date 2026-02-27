import json
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
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("bootstrap_provider", payload)
        self.assertIn("intent_provider", payload)
        self.assertIn("narration_provider", payload)
        self.assertIn("hybrid_intent_llm_for_complex_inputs", payload)

    def test_quest_spec_schema_endpoints(self):
        effect_response = self.client.get("/v1/quest-specs/effects/schema")
        self.assertEqual(effect_response.status_code, 200)
        effect_payload = effect_response.json()
        effect_kinds = {entry["kind"] for entry in effect_payload["effect_kinds"]}
        self.assertIn("set_story_flag", effect_kinds)
        self.assertIn("emit_system_event", effect_kinds)

        predicate_response = self.client.get("/v1/quest-specs/predicates/schema")
        self.assertEqual(predicate_response.status_code, 200)
        predicate_payload = predicate_response.json()
        predicate_kinds = {entry["kind"] for entry in predicate_payload["predicate_kinds"]}
        self.assertIn("action_seen", predicate_kinds)
        self.assertIn("inventory_item_present", predicate_kinds)

    def test_validate_quest_specs_endpoint(self):
        payload = {
            "specs": [
                {
                    "quest_id": "quest-api-validate-smoke",
                    "title": "Validate Smoke",
                    "description": "Validation smoke test.",
                    "initial_stage": "start",
                    "tags": ["test"],
                    "objectives": [{"objective_id": "obj-a", "title": "A", "hint": "h"}],
                    "objective_triggers": [
                        {
                            "trigger_id": "trig-a",
                            "objective_id": "obj-a",
                            "predicates": [{"predicate_id": "pred-a", "kind": "action_seen", "action_types": ["TALK"]}],
                        }
                    ],
                    "transitions": [
                        {
                            "transition_id": "done",
                            "to_stage": "completed",
                            "to_status": "completed",
                            "requires_all_objectives_completed": True,
                        }
                    ],
                }
            ],
            "existing_quest_ids": [],
        }
        response = self.client.post("/v1/quest-specs/validate", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["parsed_count"], 1)

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
        self.assertIn("bootstrap_trace", payload)
        self.assertEqual(payload["bootstrap_trace"]["capability"], "bootstrap")

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
        self.assertIn("bootstrap_trace", created)
        self.assertEqual(created["bootstrap_trace"]["capability"], "bootstrap")

        get_response = self.client.get(f"/v1/worlds/{world_id}")
        self.assertEqual(get_response.status_code, 200)
        fetched = get_response.json()
        self.assertEqual(fetched["world_id"], world_id)
        self.assertEqual(fetched["world_seed"]["world_id"], world_id)
        self.assertEqual(fetched["initial_narrative"], created["initial_narrative"])
        self.assertIsNone(fetched.get("bootstrap_trace"))

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
        self.assertIn("provider_trace", run_payload)
        self.assertEqual(run_payload["provider_trace"]["intent"]["provider_used"], "preview")
        self.assertEqual(run_payload["provider_trace"]["narration"]["provider_used"], "preview")
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

    def test_g260_urban_occult_starter_quest_progresses_via_kael_crate_mira(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g260-quest",
                "world_description": (
                    "Eine moderne Stadt mit geheimer Magie, einem fehlgeschlagenen Binder-Ritual und rivalisierenden Zirkeln."
                ),
                "character_description": "Ein Ermittler, der den Vorfall am Marktplatz untersucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.json()
        self.assertGreaterEqual(len(context_payload["quests"]), 1)
        self.assertEqual(context_payload["world_pack"]["genre"], "urban_occult_investigation")
        self.assertIn("kael_interviewed", context_payload["story_flags"])
        self.assertFalse(context_payload["story_flags"]["kael_interviewed"])
        quest = context_payload["quests"][0]
        self.assertEqual(quest["current_stage"], "investigate_scene")
        kael_ref = next(entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Kael")
        mira_ref = next(entry for entry in context_payload["target_catalog"]["npcs"] if entry["name"] == "Mira")
        self.assertEqual(kael_ref.get("discovery_state", {}).get("dialog_state"), "quest_hook")

        talk_kael = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Kael",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": kael_ref["ref_id"],
                            "target_name": kael_ref["name"],
                            "target_role": kael_ref.get("role"),
                            "target_location_name": kael_ref.get("location_name"),
                            "target_zone_id": kael_ref.get("scene_zone_id"),
                            "target_zone_name": kael_ref.get("scene_zone_name"),
                            "target_distance_band": kael_ref.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_kael.status_code, 200)
        ctx_after_kael = talk_kael.json()["context_after_turn"]
        quest_after_kael = ctx_after_kael["quests"][0]
        objective_states_after_kael = {obj["objective_id"]: obj["status"] for obj in quest_after_kael["objectives"]}
        self.assertEqual(objective_states_after_kael["speak_with_kael"], "completed")
        self.assertEqual(objective_states_after_kael["inspect_supply_crate"], "pending")
        self.assertTrue(ctx_after_kael["story_flags"]["kael_interviewed"])
        self.assertFalse(ctx_after_kael["story_flags"]["supply_crate_inspected"])

        broad_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "ich schau mich um"},
        )
        self.assertEqual(broad_inspect.status_code, 200)
        ctx_after_broad = broad_inspect.json()["context_after_turn"]
        crate_ref = next(
            entry for entry in ctx_after_broad["target_catalog"]["scene_points"] if "supply-crate" in entry["ref_id"]
        )

        inspect_crate = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Vorratskiste",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": crate_ref["ref_id"],
                        "target_kind": crate_ref["kind"],
                        "parameters": {
                            "intent": "inspect",
                            "target_id": crate_ref["ref_id"],
                            "target_name": crate_ref["name"],
                            "target_kind": crate_ref["kind"],
                        },
                    }
                ],
            },
        )
        self.assertEqual(inspect_crate.status_code, 200)
        ctx_after_crate = inspect_crate.json()["context_after_turn"]
        quest_after_crate = ctx_after_crate["quests"][0]
        objective_states_after_crate = {obj["objective_id"]: obj["status"] for obj in quest_after_crate["objectives"]}
        self.assertEqual(objective_states_after_crate["speak_with_kael"], "completed")
        self.assertEqual(objective_states_after_crate["inspect_supply_crate"], "completed")
        self.assertEqual(quest_after_crate["current_stage"], "report_to_mira")
        self.assertTrue(ctx_after_crate["story_flags"]["supply_crate_inspected"])
        self.assertFalse(ctx_after_crate["story_flags"]["mira_report_completed"])

        mira_ref_after = next(entry for entry in ctx_after_crate["target_catalog"]["npcs"] if entry["ref_id"] == mira_ref["ref_id"])
        self.assertEqual(mira_ref_after.get("discovery_state", {}).get("dialog_state"), "quest_report")

        talk_mira = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref_after["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": mira_ref_after["ref_id"],
                            "target_name": mira_ref_after["name"],
                            "target_role": mira_ref_after.get("role"),
                            "target_location_name": mira_ref_after.get("location_name"),
                            "target_zone_id": mira_ref_after.get("scene_zone_id"),
                            "target_zone_name": mira_ref_after.get("scene_zone_name"),
                            "target_distance_band": mira_ref_after.get("distance_band_to_player"),
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_mira.status_code, 200)
        talk_mira_payload = talk_mira.json()
        quest_codes = [event["code"] for event in talk_mira_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("quest_completed", quest_codes)
        final_quest = talk_mira_payload["context_after_turn"]["quests"][0]
        self.assertEqual(final_quest["status"], "completed")
        self.assertTrue(all(obj["status"] == "completed" for obj in final_quest["objectives"]))
        final_flags = talk_mira_payload["context_after_turn"]["story_flags"]
        self.assertTrue(final_flags["mira_report_completed"])
        self.assertTrue(final_flags["ritual_leads_quest_completed"])

    def test_g350_followup_quest_unlocks_and_kael_crosscheck_stage_updates_dialog_hints(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g350-followup",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Binder-Ritual und Fraktionsdruck am Marktplatz.",
                "character_description": "Ein Ermittler mit Fokus auf Relikte und Ritualspuren.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        # Starterquest lösen: Kael -> Vorratskiste -> Mira
        ctx0 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        kael_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Kael")
        mira_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Mira")

        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Kael",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {"target_id": kael_ref["ref_id"], "target_name": "Kael"},
                    }
                ],
            },
        )
        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "ich schau mich um"})
        ctx1 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        supply_crate_ref = next(entry for entry in ctx1["target_catalog"]["scene_points"] if "supply-crate" in entry["ref_id"])
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Vorratskiste",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": supply_crate_ref["ref_id"],
                        "target_kind": supply_crate_ref["kind"],
                        "parameters": {
                            "target_id": supply_crate_ref["ref_id"],
                            "target_name": supply_crate_ref["name"],
                            "target_kind": supply_crate_ref["kind"],
                        },
                    }
                ],
            },
        )
        talk_mira = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": mira_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {"target_id": mira_ref["ref_id"], "target_name": "Mira"},
                    }
                ],
            },
        )
        self.assertEqual(talk_mira.status_code, 200)
        talk_mira_payload = talk_mira.json()
        event_codes = [event["code"] for event in talk_mira_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("quest_unlocked", event_codes)

        ctx_after_unlock = talk_mira_payload["context_after_turn"]
        quests_by_id = {quest["quest_id"]: quest for quest in ctx_after_unlock["quests"]}
        self.assertIn("quest-urban-occult-resonance-followup", quests_by_id)
        followup_quest = quests_by_id["quest-urban-occult-resonance-followup"]
        self.assertEqual(followup_quest["status"], "active")
        self.assertEqual(followup_quest["current_stage"], "trace_residue")
        kael_hint_1 = next(entry for entry in ctx_after_unlock["target_catalog"]["npcs"] if entry["ref_id"] == kael_ref["ref_id"])
        self.assertEqual(kael_hint_1.get("discovery_state", {}).get("dialog_state"), "followup_suspicious")
        self.assertIn("Ritualkreis", str(kael_hint_1.get("discovery_state", {}).get("dialog_topics_hint", "")))

        # Folgequest: breite Suche -> Runenspuren inspizieren + Koffer öffnen
        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "ich schau mich um"})
        ctx_followup = self.client.get(f"/v1/worlds/{world_id}/context").json()
        rune_ref = next(entry for entry in ctx_followup["target_catalog"]["scene_points"] if entry["ref_id"] == "poi-marktplatz-runenspuren")
        case_ref = next(entry for entry in ctx_followup["target_catalog"]["scene_points"] if entry["ref_id"] == "obj-marktplatz-siegelkoffer")

        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Runenspuren",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": rune_ref["ref_id"],
                        "target_kind": rune_ref["kind"],
                        "parameters": {"target_id": rune_ref["ref_id"], "target_name": rune_ref["name"], "target_kind": rune_ref["kind"]},
                    }
                ],
            },
        )
        open_case = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Oeffne Instrumentenkoffer",
                "actions_override": [
                    {
                        "action_type": "OPEN",
                        "target_ref": case_ref["ref_id"],
                        "target_kind": case_ref["kind"],
                        "parameters": {"target_id": case_ref["ref_id"], "target_name": case_ref["name"], "target_kind": case_ref["kind"]},
                    }
                ],
            },
        )
        self.assertEqual(open_case.status_code, 200)
        ctx_crosscheck = open_case.json()["context_after_turn"]
        followup_after_clues = next(q for q in ctx_crosscheck["quests"] if q["quest_id"] == "quest-urban-occult-resonance-followup")
        self.assertEqual(followup_after_clues["current_stage"], "crosscheck_with_kael")
        kael_hint_2 = next(entry for entry in ctx_crosscheck["target_catalog"]["npcs"] if entry["ref_id"] == kael_ref["ref_id"])
        self.assertEqual(kael_hint_2.get("discovery_state", {}).get("dialog_state"), "followup_crosscheck")
        self.assertIn("Koffer", str(kael_hint_2.get("discovery_state", {}).get("dialog_hint", "")))

    def test_g400_authored_dialog_topic_sets_flag_and_updates_hint(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g400-dialog-topic",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Binder-Ritual und Fraktionsdruck am Marktplatz.",
                "character_description": "Ein Ermittler mit Fokus auf Aussagen und Widersprueche.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        context_before = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_before.status_code, 200)
        ctx_before = context_before.json()
        kael_ref = next(entry for entry in ctx_before["target_catalog"]["npcs"] if entry["name"] == "Kael")
        topics_json = str(kael_ref.get("discovery_state", {}).get("dialog_topics_json") or "")
        self.assertIn("kael_ritual_overview", topics_json)

        talk_topic = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Frage Kael zum Ritualablauf",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "intent": "talk",
                            "target_id": kael_ref["ref_id"],
                            "target_name": kael_ref["name"],
                            "target_role": kael_ref.get("role"),
                            "target_location_name": kael_ref.get("location_name"),
                            "target_zone_id": kael_ref.get("scene_zone_id"),
                            "target_zone_name": kael_ref.get("scene_zone_name"),
                            "target_distance_band": kael_ref.get("distance_band_to_player"),
                            "topic_id": "kael_ritual_overview",
                            "topic_label": "Ritualablauf",
                        },
                    }
                ],
            },
        )
        self.assertEqual(talk_topic.status_code, 200)
        payload = talk_topic.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("dialog_topic_applied", event_codes)
        self.assertIn("dialog_topic_response", event_codes)

        story_flags = payload["context_after_turn"]["story_flags"]
        self.assertTrue(story_flags["dialog_topic_used_kael_ritual_overview"])
        self.assertTrue(story_flags["kael_ritual_background_heard"])

        starter_quest = next(q for q in payload["context_after_turn"]["quests"] if q["quest_id"] == "quest-urban-occult-market-ritual-leads")
        speak_obj = next(obj for obj in starter_quest["objectives"] if obj["objective_id"] == "speak_with_kael")
        self.assertIn("Ritualablauf", speak_obj["hint"])

    def test_g450_dialog_topic_variant_and_followup_flag_transition(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g450-dialog-variant",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Binder-Ritual und Fraktionsdruck am Marktplatz.",
                "character_description": "Ein Ermittler, der Kael mit Verdacht konfrontiert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        # Starterquest abschliessen: Kael -> Kiste -> Mira, damit Followup freigeschaltet ist.
        ctx0 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        kael_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Kael")
        mira_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Mira")
        kael_topics = json.loads(str(kael_ref.get("discovery_state", {}).get("dialog_topics_json") or "[]"))
        ritual_topic = next(topic for topic in kael_topics if topic["topic_id"] == "kael_ritual_overview")
        self.assertEqual(ritual_topic.get("future_check_attribute"), "intelligence")
        self.assertEqual(ritual_topic.get("future_check_dc"), 12)

        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Kael",
                "actions_override": [{"action_type": "TALK", "target_ref": kael_ref["ref_id"], "target_kind": "npc", "parameters": {"target_id": kael_ref["ref_id"], "target_name": "Kael"}}],
            },
        )
        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "ich schau mich um"})
        ctx1 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        supply_crate_ref = next(entry for entry in ctx1["target_catalog"]["scene_points"] if "supply-crate" in entry["ref_id"])
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Vorratskiste",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": supply_crate_ref["ref_id"],
                        "target_kind": supply_crate_ref["kind"],
                        "parameters": {"target_id": supply_crate_ref["ref_id"], "target_name": supply_crate_ref["name"], "target_kind": supply_crate_ref["kind"]},
                    }
                ],
            },
        )
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [{"action_type": "TALK", "target_ref": mira_ref["ref_id"], "target_kind": "npc", "parameters": {"target_id": mira_ref["ref_id"], "target_name": "Mira"}}],
            },
        )

        ctx_follow = self.client.get(f"/v1/worlds/{world_id}/context").json()
        kael_ref_follow = next(entry for entry in ctx_follow["target_catalog"]["npcs"] if entry["ref_id"] == kael_ref["ref_id"])
        follow_topics = json.loads(str(kael_ref_follow.get("discovery_state", {}).get("dialog_topics_json") or "[]"))
        sabotage_topic = next(topic for topic in follow_topics if topic["topic_id"] == "kael_sabotage_hypothesis")
        self.assertEqual(sabotage_topic.get("future_check_attribute"), "charisma")
        self.assertEqual(sabotage_topic.get("future_check_dc"), 13)

        topic_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Konfrontiere Kael mit Sabotageverdacht",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref_follow["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "target_id": kael_ref_follow["ref_id"],
                            "target_name": "Kael",
                            "target_standing": -2,
                            "topic_id": "kael_sabotage_hypothesis",
                            "topic_label": "Sabotageverdacht",
                        },
                    }
                ],
            },
        )
        self.assertEqual(topic_response.status_code, 200)
        payload = topic_response.json()
        response_events = [e for e in payload["turn"]["resolution"]["system_events"] if e["code"] == "dialog_topic_response"]
        self.assertGreaterEqual(len(response_events), 1)
        skill_events = [e for e in payload["turn"]["resolution"]["system_events"] if e["code"] == "dialog_topic_skill_check"]
        self.assertGreaterEqual(len(skill_events), 1)
        skill_event = skill_events[-1]
        self.assertTrue(skill_event.get("metadata"))
        self.assertEqual(skill_event["metadata"].get("check_attribute"), "charisma")
        self.assertEqual(int(skill_event["metadata"].get("dc") or 0), 13)
        self.assertIn("roll", skill_event["metadata"])
        self.assertIn("total", skill_event["metadata"])
        self.assertIn("success", skill_event["metadata"])
        self.assertTrue(skill_event["message"].startswith("Probe Konfrontation"))
        self.assertTrue(
            ("gereizt" in response_events[-1]["message"])
            or ("wahrscheinlich absichtlich gesetzt" in response_events[-1]["message"])
        )

        flags = payload["context_after_turn"]["story_flags"]
        self.assertTrue(flags["ritual_sabotage_suspected"])
        self.assertTrue(flags["dialog_skillcheck_used_kael_sabotage_hypothesis"])
        self.assertIn("dialog_skillcheck_passed_kael_sabotage_hypothesis", flags)
        self.assertIn("dialog_skillcheck_total_kael_sabotage_hypothesis", flags)
        if bool(flags["dialog_skillcheck_passed_kael_sabotage_hypothesis"]):
            self.assertTrue(flags["kael_sabotage_hypothesis_pressure_success"])
        else:
            self.assertTrue(flags["kael_defensive_under_pressure"])
        self.assertEqual(int(flags["occult_heat_level"]), 2)

        followup = next(q for q in payload["context_after_turn"]["quests"] if q["quest_id"] == "quest-urban-occult-resonance-followup")
        crosscheck_obj = next(obj for obj in followup["objectives"] if obj["objective_id"] == "crosscheck_with_kael")
        self.assertTrue(
            ("Sabotage" in crosscheck_obj["hint"])
            or ("Kael blockt" in crosscheck_obj["hint"])
            or ("unter Druck" in crosscheck_obj["hint"])
        )

    def test_g700_dialog_topic_followup_branch_completes_followup_crosscheck(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g700-dialog-branch",
                "world_description": "Eine moderne Stadt mit geheimer Magie, Binder-Ritual und Fraktionsdruck am Marktplatz.",
                "character_description": "Eine Ermittlerin, die Gespraeche und Spuren kombiniert.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        # Starter-Quest vorbereiten: Kael -> Kiste -> Mira.
        ctx0 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        kael_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Kael")
        mira_ref = next(entry for entry in ctx0["target_catalog"]["npcs"] if entry["name"] == "Mira")
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Kael",
                "actions_override": [{"action_type": "TALK", "target_ref": kael_ref["ref_id"], "target_kind": "npc", "parameters": {"target_id": kael_ref["ref_id"], "target_name": "Kael"}}],
            },
        )
        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "ich schau mich um"})
        ctx1 = self.client.get(f"/v1/worlds/{world_id}/context").json()
        supply_crate_ref = next(entry for entry in ctx1["target_catalog"]["scene_points"] if "supply-crate" in entry["ref_id"])
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Vorratskiste",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": supply_crate_ref["ref_id"],
                        "target_kind": supply_crate_ref["kind"],
                        "parameters": {"target_id": supply_crate_ref["ref_id"], "target_name": supply_crate_ref["name"], "target_kind": supply_crate_ref["kind"]},
                    }
                ],
            },
        )
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Spreche mit Mira",
                "actions_override": [{"action_type": "TALK", "target_ref": mira_ref["ref_id"], "target_kind": "npc", "parameters": {"target_id": mira_ref["ref_id"], "target_name": "Mira"}}],
            },
        )

        # Followup clues vorbereiten: Runenspuren + Koffer.
        ctx_follow = self.client.get(f"/v1/worlds/{world_id}/context").json()
        rune_ref = next(entry for entry in ctx_follow["target_catalog"]["scene_points"] if "runenspuren" in entry["ref_id"])
        case_ref = next(entry for entry in ctx_follow["target_catalog"]["scene_points"] if "siegelkoffer" in entry["ref_id"])
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Untersuche Runenspuren",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": rune_ref["ref_id"],
                        "target_kind": rune_ref["kind"],
                        "parameters": {"target_id": rune_ref["ref_id"], "target_name": rune_ref["name"], "target_kind": rune_ref["kind"]},
                    }
                ],
            },
        )
        self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Oeffne Instrumentenkoffer",
                "actions_override": [
                    {
                        "action_type": "OPEN",
                        "target_ref": case_ref["ref_id"],
                        "target_kind": case_ref["kind"],
                        "parameters": {"target_id": case_ref["ref_id"], "target_name": case_ref["name"], "target_kind": case_ref["kind"]},
                    }
                ],
            },
        )

        ctx_crosscheck = self.client.get(f"/v1/worlds/{world_id}/context").json()
        kael_ref_crosscheck = next(entry for entry in ctx_crosscheck["target_catalog"]["npcs"] if entry["ref_id"] == kael_ref["ref_id"])
        kael_topics = json.loads(str(kael_ref_crosscheck.get("discovery_state", {}).get("dialog_topics_json") or "[]"))
        self.assertTrue(any(topic["topic_id"] == "kael_sabotage_hypothesis" for topic in kael_topics))

        sabotage_topic_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": "UI: Konfrontiere Kael mit Sabotageverdacht",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref_crosscheck["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "target_id": kael_ref_crosscheck["ref_id"],
                            "target_name": "Kael",
                            "target_standing": -1,
                            "topic_id": "kael_sabotage_hypothesis",
                            "topic_label": "Sabotageverdacht",
                        },
                    }
                ],
            },
        )
        self.assertEqual(sabotage_topic_response.status_code, 200)
        sabotage_payload = sabotage_topic_response.json()
        followup_after_topic = next(
            q for q in sabotage_payload["context_after_turn"]["quests"] if q["quest_id"] == "quest-urban-occult-resonance-followup"
        )
        crosscheck_obj_before_branch = next(obj for obj in followup_after_topic["objectives"] if obj["objective_id"] == "crosscheck_with_kael")
        self.assertEqual(crosscheck_obj_before_branch["status"], "active")

        kael_ref_after_topic = next(
            entry for entry in sabotage_payload["context_after_turn"]["target_catalog"]["npcs"] if entry["ref_id"] == kael_ref["ref_id"]
        )
        kael_topics_after = json.loads(str(kael_ref_after_topic.get("discovery_state", {}).get("dialog_topics_json") or "[]"))
        branch_topics = [topic for topic in kael_topics_after if str(topic.get("followup_of") or "") == "kael_sabotage_hypothesis"]
        self.assertEqual(len(branch_topics), 1)
        branch_topic = branch_topics[0]
        self.assertIn(branch_topic["topic_id"], {"kael_crosscheck_press_for_names", "kael_crosscheck_reframe_with_evidence"})
        self.assertIn(branch_topic.get("followup_condition"), {"skillcheck_success", "skillcheck_failure"})

        branch_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": f"UI: Folgetopic {branch_topic['label']}",
                "actions_override": [
                    {
                        "action_type": "TALK",
                        "target_ref": kael_ref_after_topic["ref_id"],
                        "target_kind": "npc",
                        "parameters": {
                            "target_id": kael_ref_after_topic["ref_id"],
                            "target_name": "Kael",
                            "topic_id": branch_topic["topic_id"],
                            "topic_label": branch_topic["label"],
                        },
                    }
                ],
            },
        )
        self.assertEqual(branch_response.status_code, 200)
        branch_payload = branch_response.json()
        branch_codes = [event["code"] for event in branch_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("dialog_topic_applied", branch_codes)
        self.assertIn("dialog_topic_response", branch_codes)
        self.assertIn("quest_objective_updated", branch_codes)
        self.assertIn("quest_completed", branch_codes)

        flags = branch_payload["context_after_turn"]["story_flags"]
        self.assertTrue(flags["kael_followup_crosscheck_dialog_resolved"])
        self.assertTrue(flags["urban_occult_next_hook_ready"])

        followup_after_branch = next(
            q for q in branch_payload["context_after_turn"]["quests"] if q["quest_id"] == "quest-urban-occult-resonance-followup"
        )
        self.assertEqual(followup_after_branch["status"], "completed")
        crosscheck_obj_after_branch = next(
            obj for obj in followup_after_branch["objectives"] if obj["objective_id"] == "crosscheck_with_kael"
        )
        self.assertEqual(crosscheck_obj_after_branch["status"], "completed")
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
        clarify_event = next(event for event in payload["turn"]["resolution"]["system_events"] if event["code"] == "clarify_required")
        self.assertTrue(clarify_event.get("metadata"))
        self.assertIn("reason", clarify_event["metadata"])
        self.assertGreaterEqual(int(clarify_event["metadata"].get("candidate_count") or 0), 1)
        self.assertTrue(clarify_event.get("clarify"))
        self.assertIn(
            clarify_event["clarify"].get("reason"),
            {"ambiguous_npc_role_title", "unknown_or_ambiguous_npc_talk_target"},
        )
        self.assertGreaterEqual(len(clarify_event["clarify"].get("candidates") or []), 1)
        first_candidate = clarify_event["clarify"]["candidates"][0]
        self.assertEqual(first_candidate.get("target_kind"), "npc")
        self.assertIn("role", first_candidate)

        memory_response = self.client.get(f"/v1/worlds/{world_id}/npc-memory")
        self.assertEqual(memory_response.status_code, 200)
        bundles = memory_response.json()
        auto_plain_beschwoerer = [
            bundle
            for bundle in bundles
            if bundle["profile"]["npc_id"] == "npc-auto-beschwoerer" or bundle["profile"]["name"] == "Beschwoerer"
        ]
        self.assertEqual(auto_plain_beschwoerer, [])

    def test_g60_ordinal_role_reference_resolves_second_visible_beschwoerer(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g60-second-summoner",
                "world_description": "Eine okkulte Stadt mit mehreren Beschwoerern auf dem Marktplatz.",
                "character_description": "Eine Beobachterin, die gezielt die zweite Person anspricht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-liora-second",
                "name": "Liora",
                "role": "beschwoerer",
                "location_name": "Marktplatz",
                "revealed_to_player": True,
            },
        )

        # G35 hides NPC roles until interaction. Prime both Beschwoerer as known/identified first.
        for player_input in ("Ich rede mit Kael.", "Ich rede mit Liora."):
            prime_response = self.client.post(
                f"/v1/worlds/{world_id}/turns/run",
                json={"player_input": player_input},
            )
            self.assertEqual(prime_response.status_code, 200)

        response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich spreche den zweiten Beschwoerer an."},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("talk_success", event_codes)
        self.assertNotIn("clarify_required", event_codes)
        applied_talk = next(action for action in payload["turn"]["resolution"]["applied_actions"] if action["action_type"] == "TALK")
        self.assertEqual(applied_talk["target_ref"], "npc-liora-second")

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

    def test_g35_discovered_npc_role_hidden_until_talk_memory_exists(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g35-role-hide",
                "world_description": "Eine okkulte Stadt mit Marktplatz und versteckten Beschwoerern.",
                "character_description": "Ein Beobachter, der Personen erst nach Kontakt richtig einordnet.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        spawn_response = self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-g35-lyra",
                "name": "Lyra",
                "role": "beschwoerer",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-fountain-ring",
                "scene_zone_name": "Brunnenplatz",
                "revealed_to_player": True,
            },
        )
        self.assertEqual(spawn_response.status_code, 200)

        before_context = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(before_context.status_code, 200)
        before_payload = before_context.json()
        lyra_ref_before = next(entry for entry in before_payload["target_catalog"]["npcs"] if entry["ref_id"] == "npc-g35-lyra")
        self.assertEqual(lyra_ref_before["role"], "unknown")

        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich rede mit Lyra."})

        after_context = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(after_context.status_code, 200)
        after_payload = after_context.json()
        lyra_ref_after = next(entry for entry in after_payload["target_catalog"]["npcs"] if entry["ref_id"] == "npc-g35-lyra")
        self.assertEqual(lyra_ref_after["role"], "beschwoerer")

    def test_g36_discovered_npc_faction_hidden_until_talk_memory_exists(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g36-faction-hide",
                "world_description": "Eine okkulte Stadt mit rivalisierenden Binder-Fraktionen.",
                "character_description": "Ein Beobachter, der Zugehoerigkeiten erst nach Kontakt versteht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        spawn_response = self.client.post(
            f"/v1/devtest/worlds/{world_id}/npcs/spawn",
            json={
                "npc_id": "npc-g36-lyra",
                "name": "Lyra",
                "role": "beschwoerer",
                "faction": "binder_konklave",
                "location_name": "Marktplatz",
                "revealed_to_player": True,
            },
        )
        self.assertEqual(spawn_response.status_code, 200)

        before_payload = self.client.get(f"/v1/worlds/{world_id}/context").json()
        lyra_ref_before = next(entry for entry in before_payload["target_catalog"]["npcs"] if entry["ref_id"] == "npc-g36-lyra")
        self.assertIsNone(lyra_ref_before.get("faction"))

        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich rede mit Lyra."})

        after_payload = self.client.get(f"/v1/worlds/{world_id}/context").json()
        lyra_ref_after = next(entry for entry in after_payload["target_catalog"]["npcs"] if entry["ref_id"] == "npc-g36-lyra")
        self.assertEqual(lyra_ref_after.get("faction"), "binder_konklave")

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
        self.assertGreaterEqual(before_payload["discovery_counts"]["hidden_npc_count"], 1)
        self.assertTrue(any("unbekannte Praesenz" in note for note in before_payload["retrieval_notes"]))
        self.assertEqual(before_payload["target_catalog"]["scene_points"], [])
        self.assertGreaterEqual(before_payload["discovery_counts"]["hidden_scene_point_count"], 1)
        self.assertTrue(any("Interaktions-/Objektpunkt" in note for note in before_payload["retrieval_notes"]))

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
        self.assertEqual(after_payload["discovery_counts"]["hidden_npc_count"], 0)
        self.assertGreaterEqual(len(after_payload["target_catalog"]["scene_points"]), 1)
        self.assertEqual(after_payload["discovery_counts"]["hidden_scene_point_count"], 0)
        visible_scene_point_kinds = {entry["kind"] for entry in after_payload["target_catalog"]["scene_points"]}
        self.assertIn("scene_point", visible_scene_point_kinds)
        self.assertTrue({"container", "scene_object"} & visible_scene_point_kinds)
        self.assertFalse(any("Interaktions-/Objektpunkt" in note for note in after_payload["retrieval_notes"]))

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

    def test_g29_container_inspect_upgrades_detail_and_grants_loot_once(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g29-container",
                "world_description": "Eine moderne Stadt mit geheimer Magie und einem gestoerten Ritual auf dem Marktplatz.",
                "character_description": "Ein aufmerksamer Binder, der Hinweise und Ausruestung sammelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        # Broad inspect reveals environment targets at low detail.
        broad_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(broad_inspect.status_code, 200)
        broad_payload = broad_inspect.json()
        broad_codes = [event["code"] for event in broad_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("discovery_revealed_scene_points", broad_codes)

        context_after_broad = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_after_broad.status_code, 200)
        context_payload = context_after_broad.json()
        container_ref = next(
            entry for entry in context_payload["target_catalog"]["scene_points"] if entry["kind"] == "container"
        )
        self.assertEqual(container_ref.get("detail_level"), 1)

        inspect_container = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": f"UI: Untersuche {container_ref['name']}",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": container_ref["ref_id"],
                        "target_kind": "container",
                        "parameters": {
                            "intent": "inspect",
                            "target_id": container_ref["ref_id"],
                            "target_name": container_ref["name"],
                            "target_kind": "container",
                            "target_location_name": "Marktplatz",
                        },
                    }
                ],
            },
        )
        self.assertEqual(inspect_container.status_code, 200)
        inspect_payload = inspect_container.json()
        inspect_codes = [event["code"] for event in inspect_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("inspect_focus_success", inspect_codes)
        self.assertIn("discovery_revealed_scene_details", inspect_codes)
        self.assertTrue("container_opened" in inspect_codes or "container_already_searched" in inspect_codes)
        self.assertTrue("container_loot_found" in inspect_codes or "container_empty" in inspect_codes)

        inventory_after_first = inspect_payload["resulting_inventory"]
        self.assertGreaterEqual(len(inventory_after_first), 1)

        after_first_ctx = inspect_payload["context_after_turn"]
        updated_container = next(
            entry for entry in after_first_ctx["target_catalog"]["scene_points"] if entry["ref_id"] == container_ref["ref_id"]
        )
        self.assertEqual(updated_container.get("detail_level"), 2)
        self.assertIn("opened", updated_container.get("discovery_state", {}))

        inspect_again = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={
                "player_input": f"UI: Untersuche {container_ref['name']} erneut",
                "actions_override": [
                    {
                        "action_type": "INSPECT",
                        "target_ref": container_ref["ref_id"],
                        "target_kind": "container",
                        "parameters": {
                            "intent": "inspect",
                            "target_id": container_ref["ref_id"],
                            "target_name": container_ref["name"],
                            "target_kind": "container",
                            "target_location_name": "Marktplatz",
                        },
                    }
                ],
            },
        )
        self.assertEqual(inspect_again.status_code, 200)
        again_payload = inspect_again.json()
        again_codes = [event["code"] for event in again_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("container_already_searched", again_codes)

    def test_g30_freetext_inspect_visible_container_maps_to_focused_inspect(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g30-freetext-inspect",
                "world_description": "Eine moderne Stadt mit geheimer Magie und Spuren eines fehlgeschlagenen Rituals.",
                "character_description": "Ein aufmerksamer Binder, der verdaechtige Objekte untersucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        broad_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(broad_inspect.status_code, 200)

        context_response = self.client.get(f"/v1/worlds/{world_id}/context")
        self.assertEqual(context_response.status_code, 200)
        ctx = context_response.json()
        container_ref = next(entry for entry in ctx["target_catalog"]["scene_points"] if entry["kind"] == "container")

        focused_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": f"Ich untersuche die {container_ref['name']}."},
        )
        self.assertEqual(focused_inspect.status_code, 200)
        payload = focused_inspect.json()
        intent_actions = payload["turn"]["intent"]["actions"]
        self.assertEqual(intent_actions[0]["action_type"], "INSPECT")
        self.assertEqual(intent_actions[0]["target_ref"], container_ref["ref_id"])
        self.assertEqual(intent_actions[0]["target_kind"], "container")
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("inspect_focus_success", event_codes)

    def test_g42_repeated_broad_inspect_emits_discovery_nothing_new(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g42-broad-repeat",
                "world_description": "Eine urban-okkulte Marktszene mit versteckten Praesenzen und Objekten.",
                "character_description": "Eine aufmerksame Ermittlerin, die ihre Umgebung wiederholt scannt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        first_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(first_inspect.status_code, 200)
        first_codes = [event["code"] for event in first_inspect.json()["turn"]["resolution"]["system_events"]]
        self.assertIn("inspect_broad_success", first_codes)
        self.assertTrue("discovery_revealed_npcs" in first_codes or "discovery_revealed_scene_points" in first_codes)

        second_inspect = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(second_inspect.status_code, 200)
        second_codes = [event["code"] for event in second_inspect.json()["turn"]["resolution"]["system_events"]]
        self.assertIn("inspect_broad_success", second_codes)
        self.assertIn("discovery_nothing_new", second_codes)

    def test_g31_open_then_search_container_preserves_open_and_loot_sequence(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g31-open-search",
                "world_description": "Eine okkulte Marktszene mit Kisten und Ritualspuren.",
                "character_description": "Ein Ermittler, der Behaeltnisse erst oeffnet und dann durchsucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        reveal_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(reveal_response.status_code, 200)

        ctx = self.client.get(f"/v1/worlds/{world_id}/context").json()
        container_ref = next(entry for entry in ctx["target_catalog"]["scene_points"] if entry["kind"] == "container")

        open_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": f"Ich oeffne die {container_ref['name']}."},
        )
        self.assertEqual(open_response.status_code, 200)
        open_payload = open_response.json()
        self.assertEqual(open_payload["turn"]["intent"]["actions"][0]["action_type"], "OPEN")
        open_codes = [event["code"] for event in open_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("open_focus_success", open_codes)
        self.assertIn("container_opened", open_codes)
        self.assertNotIn("container_loot_found", open_codes)

        search_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": f"Ich durchsuche die {container_ref['name']}."},
        )
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.json()
        self.assertEqual(search_payload["turn"]["intent"]["actions"][0]["action_type"], "SEARCH")
        search_codes = [event["code"] for event in search_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("search_focus_success", search_codes)
        self.assertTrue("container_loot_found" in search_codes or "container_empty" in search_codes)

    def test_g37_take_scene_object_marks_taken_and_updates_context(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g37-take-object",
                "world_description": "Ein urban-okkulter Marktplatz mit herumliegenden Gegenstaenden.",
                "character_description": "Ein aufmerksamer Binder, der verwertbare Dinge einsammelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        self.client.post(f"/v1/worlds/{world_id}/turns/run", json={"player_input": "Ich schau mich um."})
        context_payload = self.client.get(f"/v1/worlds/{world_id}/context").json()
        scene_object = next(entry for entry in context_payload["target_catalog"]["scene_points"] if entry["kind"] == "scene_object")

        take_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": f"Ich nehme die {scene_object['name']}."},
        )
        self.assertEqual(take_response.status_code, 200)
        take_payload = take_response.json()
        self.assertEqual(take_payload["turn"]["intent"]["actions"][0]["action_type"], "TAKE")
        take_codes = [event["code"] for event in take_payload["turn"]["resolution"]["system_events"]]
        self.assertIn("take_focus_success", take_codes)
        self.assertIn("scene_object_taken", take_codes)

        updated_obj = next(
            entry for entry in take_payload["context_after_turn"]["target_catalog"]["scene_points"] if entry["ref_id"] == scene_object["ref_id"]
        )
        self.assertTrue(updated_obj.get("discovery_state", {}).get("taken"))

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
        self.assertIn("discovery_counts", payload)
        self.assertIn("hidden_npc_count", payload["discovery_counts"])
        self.assertIn("hidden_scene_point_count", payload["discovery_counts"])
        self.assertIn("visible_scene_point_count", payload["discovery_counts"])
        self.assertIn("detail_verified_scene_point_count", payload["discovery_counts"])

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

    def test_g100_run_turn_multiclause_dann_executes_talk_and_inspect(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g100-1",
                "world_description": "Ein Markt mit Kisten und einem angespannten Beschwoerer am Brunnen.",
                "character_description": "Eine vorsichtige Ermittlerin, die spricht und dann gezielt untersucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        # Broad inspect first so a container becomes visible for the second clause.
        inspect_broad = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(inspect_broad.status_code, 200)

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich gehe zu Kael und rede mit ihm, dann untersuche die Vorratskiste."},
        )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("talk_success", event_codes)
        self.assertIn("inspect_focus_success", event_codes)
        self.assertNotIn("clarify_required", event_codes)
        self.assertIn("Mehrteilige Eingabe erkannt", " ".join(payload["turn"]["intent"]["analysis_notes"]))

    def test_g110_run_turn_multiclause_safe_und_executes_talk_and_inspect(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g110-1",
                "world_description": "Ein Markt mit Kisten und einem Binder am Brunnen.",
                "character_description": "Eine Ermittlerin, die erst spricht und dann Dinge untersucht.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        inspect_broad = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(inspect_broad.status_code, 200)

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit Kael und untersuche die Vorratskiste."},
        )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("talk_success", event_codes)
        self.assertIn("inspect_focus_success", event_codes)
        self.assertNotIn("clarify_required", event_codes)

    def test_g200_run_turn_multiclause_pronoun_carryover_opens_inspected_container(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g200-1",
                "world_description": "Ein urbaner Markt mit Binder, Kisten und Spuren eines Rituals.",
                "character_description": "Eine Ermittlerin, die in Sequenzen spricht, untersucht und dann handelt.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        world_id = create_response.json()["world_id"]

        inspect_broad = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich schau mich um."},
        )
        self.assertEqual(inspect_broad.status_code, 200)

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich rede mit Kael und untersuche die Vorratskiste, dann oeffne sie."},
        )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        event_codes = [event["code"] for event in payload["turn"]["resolution"]["system_events"]]
        self.assertIn("talk_success", event_codes)
        self.assertIn("inspect_focus_success", event_codes)
        self.assertIn("open_focus_success", event_codes)
        self.assertIn("container_opened", event_codes)
        self.assertNotIn("clarify_required", event_codes)
        self.assertIn("Pronomenziel", " ".join(payload["turn"]["intent"]["analysis_notes"]))

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
