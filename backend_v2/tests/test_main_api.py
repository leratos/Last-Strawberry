from datetime import UTC, datetime
import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_v2.app.config import Settings
from backend_v2.app.main import app
from backend_v2.app.models import TurnResponse
from backend_v2.app.persistence import PersistenceError
from backend_v2.app.providers.base import ProviderError
from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.rate_limit import RateLimitDecision


class _SuccessOrchestrator:
    async def run_turn(self, request):
        return TurnResponse(
            narrative="Die Szene geht weiter. Was tust du als naechstes?",
            extracted_commands=[{"command": "ROLL_CHECK", "attribut": "Geschicklichkeit"}],
            provider="fake",
            models={"analysis": "model-a", "narrative": "model-b"},
            created_at=datetime.now(UTC),
        )


class _ProviderErrorOrchestrator:
    async def run_turn(self, request):
        raise ProviderError("upstream provider unavailable")


class _LeakyProviderErrorOrchestrator:
    async def run_turn(self, request):
        raise ProviderError("Authorization: Bearer super-secret-token api_key=secret123")


class _UnexpectedErrorOrchestrator:
    async def run_turn(self, request):
        raise RuntimeError("boom")


class _MemoryRepo:
    def __init__(self):
        self.worlds = {}
        self.turns = []
        self.memory_items = []
        self.embedding_cache = {}
        self._memory_id = 1
        self._world_id = 1
        self._turn_id = 1

    def create_world(self, *, owner_id, name, description=""):
        world = {
            "id": self._world_id,
            "owner_id": owner_id,
            "name": name,
            "description": description,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.worlds[self._world_id] = world
        self._world_id += 1
        return world

    def get_world(self, world_id):
        return self.worlds.get(world_id)

    def is_world_owner(self, world_id, owner_id):
        world = self.worlds.get(world_id)
        return world is not None and int(world["owner_id"]) == int(owner_id)

    def save_turn(self, request, response):
        turn = {
            "id": self._turn_id,
            "world_id": request.world_id,
            "player_id": request.player_id,
            "player_command": request.player_command,
            "narrative": response.narrative,
            "extracted_commands": response.extracted_commands,
            "provider": response.provider,
            "analysis_model": response.models["analysis"],
            "narrative_model": response.models["narrative"],
            "created_at": response.created_at.isoformat(),
        }
        self.turns.append(turn)
        self._turn_id += 1
        return turn

    def list_turns(self, world_id, limit=20):
        result = [turn for turn in self.turns if turn["world_id"] == world_id]
        return list(reversed(result))[:limit]

    def list_recent_turn_events(self, world_id, limit=3):
        result = [turn for turn in self.turns if turn["world_id"] == world_id]
        result = result[-limit:]
        return [f"Player action: {turn['player_command']} | Outcome: {turn['narrative']}" for turn in result]

    def save_memory_items(self, world_id, items, source_turn_id=None):
        written = 0
        now = datetime.now(UTC).isoformat()
        for item in items:
            stored = {
                "id": self._memory_id,
                "world_id": world_id,
                "memory_type": item["memory_type"],
                "content": item["content"],
                "importance": float(item["importance"]),
                "source_turn_id": source_turn_id,
                "created_at": now,
                "updated_at": now,
            }
            self.memory_items.append(stored)
            self._memory_id += 1
            written += 1
        return written

    def list_memory_items(self, world_id, limit=20, min_importance=0.0):
        items = [item for item in self.memory_items if item["world_id"] == world_id and item["importance"] >= min_importance]
        items.sort(key=lambda item: item["importance"], reverse=True)
        return items[:limit]

    def search_memory_items(self, world_id, query, limit=5, min_importance=0.5):
        return self.list_memory_items(world_id=world_id, limit=limit, min_importance=min_importance)

    def get_cached_embeddings(self, provider, model, texts):
        result = {}
        for text in texts:
            key = (provider, model, text)
            if key in self.embedding_cache:
                result[text] = self.embedding_cache[key]
        return result

    def upsert_cached_embeddings(self, provider, model, embeddings_by_text):
        for text, vector in embeddings_by_text.items():
            self.embedding_cache[(provider, model, text)] = vector
        return len(embeddings_by_text)


class _FailingRepo:
    def get_world(self, world_id):
        return {
            "id": world_id,
            "owner_id": 11,
            "name": "Testwelt",
            "description": "",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def save_turn(self, request, response):
        raise PersistenceError("db write failed")

    def list_recent_turn_events(self, world_id, limit=3):
        return []

    def search_memory_items(self, world_id, query, limit=5, min_importance=0.5):
        return []

    def list_memory_items(self, world_id, limit=20, min_importance=0.0):
        return []

    def get_cached_embeddings(self, provider, model, texts):
        return {}

    def upsert_cached_embeddings(self, provider, model, embeddings_by_text):
        return len(embeddings_by_text)


class _FailingCreateWorldRepo:
    def create_world(self, *, owner_id, name, description=""):
        _ = (owner_id, name, description)
        raise PersistenceError("db unavailable token=abc123")


class _FailingGetWorldRepo:
    def get_world(self, world_id):
        _ = world_id
        raise PersistenceError("db unavailable password=hunter2")


class _NoopRateLimiter:
    def check(self, key):
        _ = key
        return RateLimitDecision(allowed=True, retry_after_seconds=None, remaining=999)


class _BlockedRateLimiter:
    def __init__(self, retry_after_seconds=12):
        self.retry_after_seconds = retry_after_seconds

    def check(self, key):
        _ = key
        return RateLimitDecision(allowed=False, retry_after_seconds=self.retry_after_seconds, remaining=0)


class TestMainApi(unittest.TestCase):
    def setUp(self):
        self.repo = _MemoryRepo()
        self.metrics = RetrievalMetricsCollector()
        self.repo_patcher = patch("backend_v2.app.main.get_repository", return_value=self.repo)
        self.metrics_patcher = patch("backend_v2.app.main.get_retrieval_metrics_collector", return_value=self.metrics)
        self.rate_limit_patcher = patch("backend_v2.app.main.get_turn_rate_limiter", return_value=_NoopRateLimiter())
        self.repo_patcher.start()
        self.metrics_patcher.start()
        self.rate_limit_patcher.start()
        self.addCleanup(self.repo_patcher.stop)
        self.addCleanup(self.metrics_patcher.stop)
        self.addCleanup(self.rate_limit_patcher.stop)
        self.client = TestClient(app)

    def _auth_headers(self, user_id=11, username="tester"):
        response = self.client.post(
            "/v2/auth/login",
            json={"user_id": user_id, "username": username},
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "last-strawberry-backend-v2")
        self.assertEqual(body["health"], "/v2/health")

    def test_health_degraded_without_api_key(self):
        with patch(
            "backend_v2.app.main.get_settings",
            return_value=Settings(openrouter_api_key=None, analysis_model="a", narrative_model="b"),
        ):
            response = self.client.get("/v2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")

    def test_health_ok_with_api_key(self):
        with patch(
            "backend_v2.app.main.get_settings",
            return_value=Settings(openrouter_api_key="secret", analysis_model="a", narrative_model="b"),
        ):
            response = self.client.get("/v2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_request_id_header_is_echoed_when_provided(self):
        response = self.client.get("/v2/health", headers={"X-Request-ID": "req-123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-request-id"), "req-123")

    def test_request_id_header_generated_when_missing(self):
        response = self.client.get("/v2/health")
        self.assertEqual(response.status_code, 200)
        request_id = response.headers.get("x-request-id")
        self.assertIsNotNone(request_id)
        self.assertRegex(request_id, re.compile(r"^[0-9a-f]{32}$"))

    def test_login_returns_token(self):
        response = self.client.post("/v2/auth/login", json={"user_id": 1, "username": "alice"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["token_type"], "bearer")

    def test_protected_world_endpoint_requires_auth(self):
        response = self.client.post("/v2/worlds", json={"name": "Schattenforst", "description": "..."})
        self.assertEqual(response.status_code, 401)

    def test_create_world_binds_owner_to_token_user(self):
        headers = self._auth_headers(user_id=11)
        response = self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Schattenforst", "description": "Ein dunkler Wald."},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["owner_id"], 11)
        self.assertEqual(body["name"], "Schattenforst")

    def test_get_world_not_found(self):
        headers = self._auth_headers(user_id=11)
        response = self.client.get("/v2/worlds/404", headers=headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "World not found.")

    def test_get_world_forbidden_for_other_owner(self):
        owner_headers = self._auth_headers(user_id=11)
        create_response = self.client.post(
            "/v2/worlds",
            headers=owner_headers,
            json={"name": "Testwelt", "description": ""},
        )
        world_id = int(create_response.json()["id"])

        other_headers = self._auth_headers(user_id=22)
        response = self.client.get(f"/v2/worlds/{world_id}", headers=other_headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "World access forbidden.")

    def test_game_turn_success(self):
        headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Dorf", "description": ""},
        )
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich schleiche voran."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "fake")
        self.assertEqual(body["models"]["analysis"], "model-a")
        self.assertEqual(len(body["extracted_commands"]), 1)
        self.assertEqual(len(self.repo.turns), 1)
        self.assertGreaterEqual(len(self.repo.memory_items), 1)

    def test_game_turn_forbidden_for_other_owner(self):
        owner_headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=owner_headers,
            json={"name": "Dorf", "description": ""},
        )
        other_headers = self._auth_headers(user_id=22)
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich warte."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            response = self.client.post("/v2/game/turn", headers=other_headers, json=payload)
        self.assertEqual(response.status_code, 403)

    def test_game_turn_provider_error_maps_to_502(self):
        headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Dorf", "description": ""},
        )
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich warte."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_ProviderErrorOrchestrator()):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("upstream provider", response.json()["detail"])
        self.assertIsNone(response.headers.get("x-ls-error-category"))

    def test_game_turn_provider_error_redacts_sensitive_fields(self):
        headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Dorf", "description": ""},
        )
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich warte."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_LeakyProviderErrorOrchestrator()):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)
        self.assertEqual(response.status_code, 502)
        detail = response.json()["detail"]
        self.assertIn("[REDACTED]", detail)
        self.assertNotIn("super-secret-token", detail)
        self.assertNotIn("secret123", detail)

    def test_game_turn_unexpected_error_maps_to_500(self):
        headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Dorf", "description": ""},
        )
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich schaue mich um."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_UnexpectedErrorOrchestrator()):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Internal v2 error.")

    def test_game_turn_persistence_error_maps_to_500(self):
        headers = self._auth_headers(user_id=11)
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich sichere die Umgebung."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()), patch(
            "backend_v2.app.main.get_repository", return_value=_FailingRepo()
        ):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Persistence error.")

    def test_create_world_persistence_error_is_sanitized(self):
        headers = self._auth_headers(user_id=11)
        with patch("backend_v2.app.main.get_repository", return_value=_FailingCreateWorldRepo()):
            response = self.client.post(
                "/v2/worlds",
                headers=headers,
                json={"name": "Schattenforst", "description": "Ein dunkler Wald."},
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Persistence error.")

    def test_get_world_persistence_error_is_sanitized(self):
        headers = self._auth_headers(user_id=11)
        with patch("backend_v2.app.main.get_repository", return_value=_FailingGetWorldRepo()):
            response = self.client.get("/v2/worlds/1", headers=headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Persistence error.")

    def test_game_turn_rate_limited_returns_429_with_retry_after(self):
        headers = self._auth_headers(user_id=11)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Dorf", "description": ""},
        )
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich warte."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()), patch(
            "backend_v2.app.main.get_turn_rate_limiter",
            return_value=_BlockedRateLimiter(retry_after_seconds=12),
        ):
            response = self.client.post("/v2/game/turn", headers=headers, json=payload)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Rate limit exceeded.")
        self.assertEqual(response.headers.get("retry-after"), "12")

    def test_list_world_turns(self):
        headers = self._auth_headers(user_id=1)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Testwelt", "description": ""},
        )
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            self.client.post(
                "/v2/game/turn",
                headers=headers,
                json={"world_id": 1, "player_id": 7, "player_command": "Ich gehe weiter."},
            )
        response = self.client.get("/v2/worlds/1/turns?limit=10", headers=headers)
        self.assertEqual(response.status_code, 200)
        turns = response.json()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["world_id"], 1)
        self.assertEqual(turns[0]["player_id"], 7)

    def test_list_world_memory(self):
        headers = self._auth_headers(user_id=1)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Testwelt", "description": ""},
        )
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            self.client.post(
                "/v2/game/turn",
                headers=headers,
                json={"world_id": 1, "player_id": 7, "player_command": "Ich untersuche die Szene."},
            )

        response = self.client.get("/v2/worlds/1/memory?limit=10&min_importance=0.6", headers=headers)
        self.assertEqual(response.status_code, 200)
        memory_items = response.json()
        self.assertGreaterEqual(len(memory_items), 1)
        self.assertEqual(memory_items[0]["world_id"], 1)

    def test_retrieval_metrics_requires_auth(self):
        response = self.client.get("/v2/metrics/retrieval")
        self.assertEqual(response.status_code, 401)

    def test_prometheus_metrics_requires_auth(self):
        response = self.client.get("/v2/metrics/prometheus")
        self.assertEqual(response.status_code, 401)

    def test_retrieval_metrics_endpoint(self):
        headers = self._auth_headers(user_id=1)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Metrik-Welt", "description": ""},
        )
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            self.client.post(
                "/v2/game/turn",
                headers=headers,
                json={"world_id": 1, "player_id": 7, "player_command": "Ich teste die Metriken."},
            )

        response = self.client.get("/v2/metrics/retrieval", headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["totals"]["requests"], 1)
        self.assertIn("latency_ms", payload["histograms"])
        self.assertIn("http_status", payload)
        self.assertIn("audit_events", payload)
        self.assertIn("error_categories", payload)
        self.assertIn("windowed_rates", payload)
        self.assertIn("60s", payload["windowed_rates"])
        self.assertGreaterEqual(payload["windowed_rates"]["60s"]["requests_per_minute"], 0.0)

    def test_prometheus_metrics_endpoint(self):
        headers = self._auth_headers(user_id=1)
        self.client.post(
            "/v2/worlds",
            headers=headers,
            json={"name": "Prom-Welt", "description": ""},
        )
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            self.client.post(
                "/v2/game/turn",
                headers=headers,
                json={"world_id": 1, "player_id": 7, "player_command": "Ich teste Prometheus."},
            )

        response = self.client.get("/v2/metrics/prometheus", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers.get("content-type", ""))
        payload = response.text
        self.assertIn("ls_backend_v2_retrieval_requests_total", payload)
        self.assertIn("ls_backend_v2_http_requests_total", payload)
        self.assertIn('ls_backend_v2_requests_per_minute{window="60s"}', payload)

    def test_retrieval_metrics_collect_http_status_and_audit_events(self):
        unauthorized = self.client.post("/v2/worlds", json={"name": "NoAuth", "description": ""})
        self.assertEqual(unauthorized.status_code, 401)

        owner_headers = self._auth_headers(user_id=11)
        create_response = self.client.post(
            "/v2/worlds",
            headers=owner_headers,
            json={"name": "Audit-Welt", "description": ""},
        )
        world_id = int(create_response.json()["id"])

        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()), patch(
            "backend_v2.app.main.get_turn_rate_limiter",
            return_value=_BlockedRateLimiter(retry_after_seconds=5),
        ):
            rate_limited = self.client.post(
                "/v2/game/turn",
                headers=owner_headers,
                json={"world_id": world_id, "player_id": 7, "player_command": "Ich warte."},
            )
        self.assertEqual(rate_limited.status_code, 429)

        with patch("backend_v2.app.main.get_orchestrator", return_value=_ProviderErrorOrchestrator()):
            provider_error = self.client.post(
                "/v2/game/turn",
                headers=owner_headers,
                json={"world_id": world_id, "player_id": 7, "player_command": "Ich teste Provider."},
            )
        self.assertEqual(provider_error.status_code, 502)

        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()), patch(
            "backend_v2.app.main.get_repository",
            return_value=_FailingRepo(),
        ):
            persistence_error = self.client.post(
                "/v2/game/turn",
                headers=owner_headers,
                json={"world_id": world_id, "player_id": 7, "player_command": "Ich teste Persistenz."},
            )
        self.assertEqual(persistence_error.status_code, 500)

        with patch("backend_v2.app.main.get_orchestrator", return_value=_UnexpectedErrorOrchestrator()):
            server_error = self.client.post(
                "/v2/game/turn",
                headers=owner_headers,
                json={"world_id": world_id, "player_id": 7, "player_command": "Ich teste Fehler."},
            )
        self.assertEqual(server_error.status_code, 500)

        other_headers = self._auth_headers(user_id=22)
        forbidden = self.client.get(f"/v2/worlds/{world_id}", headers=other_headers)
        self.assertEqual(forbidden.status_code, 403)

        response = self.client.get("/v2/metrics/retrieval", headers=owner_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        by_status = payload["http_status"]["by_status"]
        self.assertGreaterEqual(by_status.get("401", 0), 1)
        self.assertGreaterEqual(by_status.get("429", 0), 1)
        self.assertGreaterEqual(by_status.get("502", 0), 1)
        self.assertGreaterEqual(by_status.get("500", 0), 1)

        audit = payload["audit_events"]
        self.assertGreaterEqual(audit.get("auth_failed", 0), 1)
        self.assertGreaterEqual(audit.get("auth_login_success", 0), 2)
        self.assertGreaterEqual(audit.get("auth_forbidden", 0), 1)
        self.assertGreaterEqual(audit.get("rate_limit_exceeded", 0), 1)

        categories = payload["error_categories"]
        self.assertGreaterEqual(categories.get("auth", 0), 1)
        self.assertGreaterEqual(categories.get("rate_limit", 0), 1)
        self.assertGreaterEqual(categories.get("provider", 0), 1)
        self.assertGreaterEqual(categories.get("persistence", 0), 1)
        self.assertGreaterEqual(categories.get("server", 0), 1)

        rates_60s = payload["windowed_rates"]["60s"]
        self.assertGreater(rates_60s["requests_per_minute"], 0.0)
        self.assertGreater(rates_60s["errors_5xx_per_minute"], 0.0)
        self.assertGreater(rates_60s["rate_limit_429_per_minute"], 0.0)


if __name__ == "__main__":
    unittest.main()
