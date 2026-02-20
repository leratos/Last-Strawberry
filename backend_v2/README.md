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
- `GET /v2/metrics/retrieval`
- `GET /v2/metrics/prometheus`

## Notes
- `LS_ANALYSIS_MODEL` and `LS_NARRATIVE_MODEL` are fully configurable.
- Optional fallback chains are supported via `LS_ANALYSIS_FALLBACK_MODELS` and `LS_NARRATIVE_FALLBACK_MODELS` (comma-separated, used on provider errors).
- OpenRouter headers (`HTTP-Referer`, `X-Title`) are included when configured.
- Turn timeout guard is configurable (`LS_TURN_TIMEOUT_SECONDS`, default `60`) and returns `504` when orchestration exceeds the limit.
- Local persistence uses SQLite by default (`LS_DATABASE_URL`).
- World and turn endpoints require Bearer auth (JWT).
- Use a JWT secret with at least 32 characters in production.
- Runtime strategy is RAG/Memory, not online retraining.
- Memory retrieval behavior is configurable (`LS_MEMORY_CONTEXT_LIMIT`, `LS_MEMORY_MIN_IMPORTANCE`, `LS_MEMORY_RETRIEVAL_STRATEGY`).
- Hybrid strategy can use pluggable embeddings (`LS_EMBEDDINGS_PROVIDER`, `LS_EMBEDDINGS_DIMENSIONS`, `LS_EMBEDDINGS_MODEL`, `LS_EMBEDDINGS_TIMEOUT_SECONDS`).
- `LS_EMBEDDINGS_PROVIDER=openrouter` uses OpenRouter's embeddings endpoint with key-based auth.
- Hybrid scoring weights are configurable (`LS_RETRIEVAL_VECTOR_WEIGHT`, `LS_RETRIEVAL_SEMANTIC_MIN_SIMILARITY`).
- Retrieval embeddings are cached in SQLite (`embeddings_cache`) to reduce repeated embedding calls.
- Turn processing logs retrieval telemetry (`strategy`, `scanned`, `lexical_hits`, `semantic_hits`, `cache_hits`, `cache_misses`, `returned`, `fallback`).
- Retrieval metrics endpoint exposes retrieval counters/histograms plus API status buckets (`2xx/4xx/5xx`, `429`), audit event counters (auth/rate-limit), error categories (`auth`, `rate_limit`, `provider`, `persistence`, `server`), and windowed request/error rates (`60s`, `300s`).
- Retrieval metrics also expose model-routing telemetry (`model_routing.routes`, `model_routing.attempt_errors`) for fallback analysis per stage (`analysis`/`narrative`).
- Prometheus-compatible export is available at `GET /v2/metrics/prometheus` (Bearer by default, optional API-key mode).
- Optional metrics API key hardening for Prometheus endpoint: `LS_METRICS_API_KEY` and `LS_METRICS_API_KEY_HEADER`.
- If `LS_METRICS_API_KEY` is set, `/v2/metrics/prometheus` requires that header and no Bearer token.
- Monitoring runbook and scrape examples: `docs/monitoring_prometheus_v2.md`.
- Parallel turn burst test helper: `backend_v2/scripts/run_parallel_turn_load.py` (guide: `docs/parallel_turn_load_tests_v2.md`).
- Each response includes `X-Request-ID`; provide the same header on request to keep end-to-end correlation IDs.
- Turn endpoint rate limits are configurable (`LS_TURN_RATE_LIMIT_ENABLED`, `LS_TURN_RATE_LIMIT_REQUESTS`, `LS_TURN_RATE_LIMIT_WINDOW_SECONDS`).
- Turn endpoint IP rate limits are configurable (`LS_TURN_IP_RATE_LIMIT_ENABLED`, `LS_TURN_IP_RATE_LIMIT_REQUESTS`, `LS_TURN_IP_RATE_LIMIT_WINDOW_SECONDS`).
- Login endpoint rate limit is configurable (`LS_LOGIN_RATE_LIMIT_ENABLED`, `LS_LOGIN_RATE_LIMIT_REQUESTS`, `LS_LOGIN_RATE_LIMIT_WINDOW_SECONDS`).
- Request-body guard is configurable (`LS_MAX_REQUEST_BODY_BYTES`, default `262144`) and returns `413` on oversized payloads.
- Security response headers are always set (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`).
- Provider and persistence error details are sanitized to avoid leaking secrets or internal details.
- API key lookup order:
  1. `LS_OPENROUTER_API_KEY`
  2. `OPENROUTER_API_KEY`
  3. System keyring (default tries `OPENROUTER_API_KEY` / `default`)
