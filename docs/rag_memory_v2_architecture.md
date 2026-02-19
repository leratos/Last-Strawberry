# RAG/Memory Architecture for V2 (No Retraining Path)

Stand: 19 February 2026

## Decision
- We do not retrain models on world data in the runtime path.
- We use retrieval-augmented generation (RAG) and structured memory.
- OpenRouter is used for inference/routing only.

## Why this is the right tradeoff
- Faster iteration: no training jobs, no model version rollout overhead.
- Better control: memory can be corrected immediately by data updates.
- Lower operational risk: no accidental drift from repeated fine-tunes.
- Provider flexibility: model can change without re-training pipeline changes.

## Memory layers
1. Short-term turn memory (last N turns per world/session).
2. Long-term world memory (facts, NPC profiles, unresolved hooks).
3. Rule memory (hard constraints, lore rules, safety rails).

## Data model foundation
- `worlds`
  - `id`, `owner_id`, `name`, `description`, `created_at`
- `turns`
  - `id`, `world_id`, `player_id`, `player_command`, `narrative`,
    `extracted_commands`, `provider`, `analysis_model`, `narrative_model`, `created_at`
- Next (Phase 2b/3): `memory_items`
  - `id`, `world_id`, `memory_type`, `content`, `importance`, `source_turn_id`,
    `embedding`, `created_at`, `updated_at`

## Runtime flow (target)
1. Authenticate user.
2. Validate world ownership.
3. Fetch short-term memory (recent turns).
4. Retrieve top-k long-term memory items (semantic + metadata filter).
5. Build analysis prompt with relevant context.
6. Execute analysis model.
7. Build narrative prompt with analysis output + selected memory.
8. Execute narrative model.
9. Persist turn + extracted commands.
10. Write memory updates:
    - append critical facts
    - decay/remove low-value memory
    - refresh embeddings asynchronously

## Retrieval strategy
- Hybrid retrieval:
  - lexical filter for exact entities (NPC names, places)
  - vector similarity for semantic recall
- Ranking signals:
  - similarity score
  - recency
  - importance
  - unresolved quest/hook weight
- Hard token budget per section to avoid context bloat.

## Quality and safety controls
- Deterministic extraction path (lower temperature, strict JSON output).
- Memory write policy:
  - only write facts with confidence >= threshold
  - never overwrite without source trace
- Prompt guardrails:
  - world rules as immutable section
  - anti-contradiction checks before narrative output

## Implementation phases
1. Phase 2a (now): SQLite persistence + JWT + ownership checks.
2. Phase 2b: memory tables + write/read adapters + prompt assembler.
3. Phase 3: vector index + hybrid retrieval + observability.
4. Phase 4: optimization (cost/latency), canary rollout.

## Current status
- Completed: Phase 2a.
- Completed: Phase 2b foundation (`memory_items` schema, lexical retrieval, prompt memory context, write policy).
- Completed: Phase 3 prep (`hybrid` retriever strategy abstraction + retrieval telemetry logging).
- Completed: Phase 3 vector enrichment (`embeddings` provider interface + semantic scoring path).
- Completed: external embeddings adapter hardening (`openrouter` adapter, resilience baseline).
- Completed: embeddings caching baseline (SQLite cache for repeated query/item embeddings).
- In progress: metrics hardening and production tuning (latency/cost optimization).

## Success metrics
- Narrative contradiction rate per 100 turns.
- Memory hit-rate in prompts.
- p95 latency impact of retrieval step.
- Cost per turn split by analysis vs narrative model.
