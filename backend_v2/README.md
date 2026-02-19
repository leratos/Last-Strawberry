# Last Strawberry Backend V2

OpenRouter-first backend scaffold for the restart.

## Goals
- Model-agnostic orchestration.
- No Google Cloud runtime dependency.
- Fast path to 70B and non-Llama models through OpenRouter.

## Quick start
```bash
cd backend_v2
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
cd ..
uvicorn backend_v2.app.main:app --reload --port 8002
```

## Endpoints
- `POST /v2/auth/login`
- `GET /v2/health`
- `POST /v2/game/turn`
- `POST /v2/worlds`
- `GET /v2/worlds/{world_id}`
- `GET /v2/worlds/{world_id}/turns`
- `GET /v2/worlds/{world_id}/memory`

## Notes
- `LS_ANALYSIS_MODEL` and `LS_NARRATIVE_MODEL` are fully configurable.
- OpenRouter headers (`HTTP-Referer`, `X-Title`) are included when configured.
- Local persistence uses SQLite by default (`LS_DATABASE_URL`).
- World and turn endpoints require Bearer auth (JWT).
- Use a JWT secret with at least 32 characters in production.
- Runtime strategy is RAG/Memory, not online retraining.
- Memory retrieval behavior is configurable (`LS_MEMORY_CONTEXT_LIMIT`, `LS_MEMORY_MIN_IMPORTANCE`, `LS_MEMORY_RETRIEVAL_STRATEGY`).
- Hybrid strategy can use pluggable embeddings (`LS_EMBEDDINGS_PROVIDER`, `LS_EMBEDDINGS_DIMENSIONS`).
- Hybrid scoring weights are configurable (`LS_RETRIEVAL_VECTOR_WEIGHT`, `LS_RETRIEVAL_SEMANTIC_MIN_SIMILARITY`).
- Turn processing logs retrieval telemetry (`strategy`, `scanned`, `lexical_hits`, `semantic_hits`, `returned`, `fallback`).
- API key lookup order:
  1. `LS_OPENROUTER_API_KEY`
  2. `OPENROUTER_API_KEY`
  3. System keyring (default tries `OPENROUTER_API_KEY` / `default`)
