import asyncio
from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from unittest.mock import patch

import httpx
import pytest

from backend_v2.app.main import app
from backend_v2.app.models import TurnResponse
from backend_v2.app.providers.base import ProviderError
from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.rate_limit import SlidingWindowRateLimiter


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _ThreadSafeMemoryRepo:
    def __init__(self) -> None:
        self._lock = Lock()
        self.worlds: dict[int, dict] = {}
        self.turns: list[dict] = []
        self.memory_items: list[dict] = []
        self.embedding_cache: dict[tuple[str, str, str], list[float]] = {}
        self._memory_id = 1
        self._world_id = 1
        self._turn_id = 1

    def create_world(self, *, owner_id, name, description=""):
        with self._lock:
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
        with self._lock:
            return self.worlds.get(world_id)

    def save_turn(self, request, response):
        with self._lock:
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
        with self._lock:
            result = [turn for turn in self.turns if turn["world_id"] == world_id]
            return list(reversed(result))[:limit]

    def list_recent_turn_events(self, world_id, limit=3):
        with self._lock:
            result = [turn for turn in self.turns if turn["world_id"] == world_id]
            result = result[-limit:]
            return [f"Player action: {turn['player_command']} | Outcome: {turn['narrative']}" for turn in result]

    def save_memory_items(self, world_id, items, source_turn_id=None):
        with self._lock:
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
        with self._lock:
            items = [item for item in self.memory_items if item["world_id"] == world_id and item["importance"] >= min_importance]
            items.sort(key=lambda item: item["importance"], reverse=True)
            return items[:limit]

    def search_memory_items(self, world_id, query, limit=5, min_importance=0.5):
        _ = query
        return self.list_memory_items(world_id=world_id, limit=limit, min_importance=min_importance)

    def get_cached_embeddings(self, provider, model, texts):
        with self._lock:
            result = {}
            for text in texts:
                key = (provider, model, text)
                if key in self.embedding_cache:
                    result[text] = self.embedding_cache[key]
            return result

    def upsert_cached_embeddings(self, provider, model, embeddings_by_text):
        with self._lock:
            for text, vector in embeddings_by_text.items():
                self.embedding_cache[(provider, model, text)] = vector
            return len(embeddings_by_text)


class _FastSuccessOrchestrator:
    async def run_turn(self, request):
        await asyncio.sleep(0.01)
        return TurnResponse(
            narrative="Die Szene geht weiter.",
            extracted_commands=[{"command": "PLAYER_MOVE", "location_name": "Nordpfad"}],
            provider="fake",
            models={"analysis": "model-a", "narrative": "model-b"},
            created_at=datetime.now(UTC),
        )


class _FastFailProviderOrchestrator:
    async def run_turn(self, request):
        _ = request
        await asyncio.sleep(0.005)
        raise ProviderError("simulated upstream outage")


async def _login_and_create_world(client: httpx.AsyncClient, *, user_id: int = 11) -> tuple[dict[str, str], int]:
    login = await client.post("/v2/auth/login", json={"user_id": user_id, "username": "load-tester"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    world_resp = await client.post(
        "/v2/worlds",
        headers=headers,
        json={"name": "Parallel-Testwelt", "description": ""},
    )
    assert world_resp.status_code == 201
    world_id = int(world_resp.json()["id"])
    return headers, world_id


@pytest.mark.anyio
async def test_parallel_turn_burst_enforces_rate_limit_with_mixed_outcomes():
    repo = _ThreadSafeMemoryRepo()
    metrics = RetrievalMetricsCollector()
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60, enabled=True)

    with patch("backend_v2.app.main.get_repository", return_value=repo), patch(
        "backend_v2.app.main.get_retrieval_metrics_collector",
        return_value=metrics,
    ), patch("backend_v2.app.main.get_turn_rate_limiter", return_value=limiter), patch(
        "backend_v2.app.main.get_orchestrator",
        return_value=_FastSuccessOrchestrator(),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            headers, world_id = await _login_and_create_world(client)

            async def _send_turn(i: int) -> httpx.Response:
                return await client.post(
                    "/v2/game/turn",
                    headers=headers,
                    json={"world_id": world_id, "player_id": 77, "player_command": f"parallel-{i}"},
                )

            responses = await asyncio.gather(*[_send_turn(i) for i in range(8)])

    status_counts = Counter(response.status_code for response in responses)
    assert status_counts[200] == 3
    assert status_counts[429] == 5
    assert sum(status_counts.values()) == 8

    snapshot = metrics.snapshot()
    assert snapshot["http_status"]["by_status"].get("429", 0) >= 5
    assert snapshot["audit_events"].get("rate_limit_exceeded", 0) >= 5
    assert snapshot["error_categories"].get("rate_limit", 0) >= 5


@pytest.mark.anyio
async def test_parallel_turn_burst_provider_failures_return_502_and_record_metrics():
    repo = _ThreadSafeMemoryRepo()
    metrics = RetrievalMetricsCollector()
    limiter = SlidingWindowRateLimiter(limit=100, window_seconds=60, enabled=True)

    with patch("backend_v2.app.main.get_repository", return_value=repo), patch(
        "backend_v2.app.main.get_retrieval_metrics_collector",
        return_value=metrics,
    ), patch("backend_v2.app.main.get_turn_rate_limiter", return_value=limiter), patch(
        "backend_v2.app.main.get_orchestrator",
        return_value=_FastFailProviderOrchestrator(),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            headers, world_id = await _login_and_create_world(client)

            async def _send_turn(i: int) -> httpx.Response:
                return await client.post(
                    "/v2/game/turn",
                    headers=headers,
                    json={"world_id": world_id, "player_id": 77, "player_command": f"provider-fail-{i}"},
                )

            responses = await asyncio.gather(*[_send_turn(i) for i in range(6)])

    assert all(response.status_code == 502 for response in responses)
    snapshot = metrics.snapshot()
    assert snapshot["http_status"]["by_status"].get("502", 0) >= 6
    assert snapshot["error_categories"].get("provider", 0) >= 6
