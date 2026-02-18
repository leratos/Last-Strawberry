# Last Strawberry V2 Restart (OpenRouter First)

## Why restart
- Current architecture mixes product logic, infra concerns, and model orchestration in large modules.
- Shared mutable globals create concurrency risk for multi-user sessions.
- Tight coupling to Google Cloud and local model switching slows delivery.
- Testing and deployment ergonomics are weak for fast iteration.

## Product direction
- Keep: interactive AI tabletop loop (analysis -> narrative -> state updates).
- Change: inference backend is OpenRouter-first, model-agnostic, no Google Cloud dependency.
- Target: higher quality model routing (70B class, non-Llama options like MiniMax M2.5) with graceful fallback.

## Core principles for V2
1. Stateless API nodes.
2. Clear provider abstraction for LLM backends.
3. Strict schema for extracted commands.
4. Observable and testable orchestration.
5. Migration without a hard cut-over.

## Target architecture
- `backend_v2/app/main.py`: API entrypoint.
- `backend_v2/app/services/orchestrator.py`: turn orchestration.
- `backend_v2/app/providers/base.py`: provider contract.
- `backend_v2/app/providers/openrouter.py`: OpenRouter implementation.
- Persistence layer can be wired after API stabilizes (SQLite/Postgres decision in phase 2).

## Model strategy (OpenRouter)
- `analysis_model`: command extraction, high determinism, lower temperature.
- `narrative_model`: storytelling quality, broader model choice.
- Add fallback chain per role:
  - Primary: high quality (for example 70B class).
  - Secondary: lower latency / cheaper model.
- Model IDs stay config-driven, not hardcoded in business logic.

## Migration plan
1. Phase 0: Freeze legacy behavior and capture baseline responses.
2. Phase 1: Build V2 API + OpenRouter provider + turn orchestration.
3. Phase 2: Add persistence, auth, and event logs in V2.
4. Phase 3: A/B compare legacy vs V2 for quality, latency, cost.
5. Phase 4: Progressive traffic shift, then retire legacy inference path.

## Exit criteria
- No Google Cloud dependency in runtime path.
- Provider switch possible without changing orchestration code.
- Concurrency-safe processing for multi-user load.
- Measured metrics on p95 latency, cost per turn, failure rate, command extraction quality.
