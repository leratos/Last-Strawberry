import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException

from backend_v2.app.config import get_settings
from backend_v2.app.models import HealthResponse, TurnRequest, TurnResponse
from backend_v2.app.providers.base import ProviderError
from backend_v2.app.providers.openrouter import OpenRouterProvider
from backend_v2.app.services.orchestrator import GameOrchestrator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Last Strawberry Backend V2",
    version="2.0.0-alpha",
    description="OpenRouter-first restart backend for game orchestration.",
)


@lru_cache
def get_orchestrator() -> GameOrchestrator:
    settings = get_settings()
    provider = OpenRouterProvider(settings)
    return GameOrchestrator(provider=provider, settings=settings)


@app.get("/v2/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok" if settings.openrouter_api_key else "degraded",
        provider="openrouter",
        configured_models={
            "analysis": settings.analysis_model,
            "narrative": settings.narrative_model,
        },
    )


@app.post("/v2/game/turn", response_model=TurnResponse)
async def run_turn(request: TurnRequest) -> TurnResponse:
    orchestrator = get_orchestrator()
    try:
        return await orchestrator.run_turn(request)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected v2 turn processing error.")
        raise HTTPException(status_code=500, detail="Internal v2 error.") from exc


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "last-strawberry-backend-v2", "docs": "/docs", "health": "/v2/health"}
