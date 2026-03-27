from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from apps.game_api.app.config import Settings
from apps.game_api.app.services.intent_analysis_preview import analyze_player_input_preview
from apps.game_api.app.services.narration_preview import build_narrative_from_resolution
from apps.game_api.app.services.urban_occult_basis import resolve_unique_role_title_npc_reference
from ls_shared_schemas.game_context import GameContextResponse
from ls_shared_schemas.turns import LlmCapabilityTrace, NarrativeEnvelope, TurnIntent, TurnIntentAction, TurnResolution
from ls_shared_schemas.world import ScenePointSeed, WorldBootstrapRequest, WorldBootstrapResult, WorldSessionResponse


class LlmRuntimeError(RuntimeError):
    pass


_OPENROUTER_INTENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "turn_intent_response",
        "strict": False,
        "schema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "action_type": {"type": "string"},
                            "target_ref": {"type": ["string", "null"]},
                            "destination": {"type": ["string", "null"]},
                            "item_ref": {"type": ["string", "null"]},
                            "target_kind": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"]},
                            "parameters": {"type": ["object", "null"]},
                        },
                        "required": ["action_type"],
                    },
                },
                "analysis_notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["actions"],
        },
    },
}

_OPENROUTER_BOOTSTRAP_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "world_bootstrap_enrichment",
        "strict": False,
        "schema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "world_name": {"type": ["string", "null"]},
                "start_hook": {"type": ["string", "null"]},
                "factions": {"type": ["array", "null"], "items": {"type": "string"}},
                "open_threads": {"type": ["array", "null"], "items": {"type": "string"}},
                "initial_narrative": {"type": ["string", "null"]},
                "player_orientation": {"type": ["array", "null"], "items": {"type": "string"}},
                "design_notes": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["initial_narrative"],
        },
    },
}

_OPENROUTER_SCENE_POINT_PROPOSAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "scene_point_proposal_response",
        "strict": False,
        "schema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "scene_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "ref_id": {"type": ["string", "null"]},
                            "name": {"type": "string"},
                            "kind": {"type": ["string", "null"]},
                            "location_name": {"type": ["string", "null"]},
                            "scene_zone_id": {"type": ["string", "null"]},
                            "scene_zone_name": {"type": ["string", "null"]},
                            "aliases": {"type": ["array", "null"], "items": {"type": "string"}},
                        },
                        "required": ["name"],
                    },
                },
                "analysis_notes": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["scene_points"],
        },
    },
}


@dataclass(frozen=True)
class LlmRuntimeStatus:
    mode: str
    fallback_to_preview: bool
    hybrid_intent_llm_for_complex_inputs: bool
    bootstrap_provider: str
    intent_provider: str
    narration_provider: str
    openrouter_configured: bool
    bootstrap_model: str
    intent_model: str
    narrator_model: str


class OpenRouterClient:
    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float = 20.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def chat_completion(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        if not self.api_key:
            raise LlmRuntimeError("OpenRouter API key is not configured.")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": response_format or {"type": "json_object"},
            "provider": {"require_parameters": True},
        }
        req = urllib_request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LlmRuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc
        except urllib_error.URLError as exc:
            raise LlmRuntimeError(f"OpenRouter request failed: {exc}") from exc

        try:
            parsed = json.loads(raw)
            message_content = parsed["choices"][0]["message"]["content"]
            if isinstance(message_content, str):
                return message_content
            if isinstance(message_content, list):
                text_parts = []
                for item in message_content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(str(item.get("text") or ""))
                if text_parts:
                    return "".join(text_parts)
            raise LlmRuntimeError("OpenRouter response contained no text content.")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmRuntimeError("OpenRouter response format was unexpected.") from exc


class LlmRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._openrouter_client = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout_seconds=settings.openrouter_timeout_seconds,
        )

    def status(self) -> LlmRuntimeStatus:
        openrouter_ready = bool(self.settings.openrouter_api_key)
        bootstrap_provider = self._provider_name_for_capability("bootstrap", openrouter_ready=openrouter_ready)
        intent_provider = self._provider_name_for_capability("intent", openrouter_ready=openrouter_ready)
        narration_provider = self._provider_name_for_capability("narration", openrouter_ready=openrouter_ready)
        return LlmRuntimeStatus(
            mode=self.settings.llm_mode,
            fallback_to_preview=self.settings.llm_fallback_to_preview,
            hybrid_intent_llm_for_complex_inputs=self.settings.hybrid_intent_llm_for_complex_inputs,
            bootstrap_provider=bootstrap_provider,
            intent_provider=intent_provider,
            narration_provider=narration_provider,
            openrouter_configured=openrouter_ready,
            bootstrap_model=self.settings.openrouter_bootstrap_model,
            intent_model=self.settings.openrouter_intent_model,
            narrator_model=self.settings.openrouter_narrator_model,
        )

    def enrich_world_bootstrap_preview(
        self,
        *,
        request: WorldBootstrapRequest,
        preview: WorldBootstrapResult,
    ) -> WorldBootstrapResult:
        enriched, _trace = self.enrich_world_bootstrap_preview_with_trace(request=request, preview=preview)
        return enriched

    def enrich_world_bootstrap_preview_with_trace(
        self,
        *,
        request: WorldBootstrapRequest,
        preview: WorldBootstrapResult,
    ) -> tuple[WorldBootstrapResult, LlmCapabilityTrace]:
        provider_policy = "openrouter" if self._should_use_openrouter_for_capability("bootstrap") else "preview"
        if provider_policy == "preview":
            return (
                preview,
                self._build_capability_trace(
                    capability="bootstrap",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                ),
            )

        try:
            enriched = self._bootstrap_openrouter(request=request, preview=preview)
            return (
                enriched,
                self._build_capability_trace(
                    capability="bootstrap",
                    provider_policy=provider_policy,
                    provider_used="openrouter",
                    model=self.settings.openrouter_bootstrap_model,
                ),
            )
        except Exception as exc:
            if not self.settings.llm_fallback_to_preview:
                raise
            return (
                preview,
                self._build_capability_trace(
                    capability="bootstrap",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                    fallback_used=True,
                    fallback_reason=type(exc).__name__,
                ),
            )

    def analyze_intent(
        self,
        *,
        world_id: str,
        world_character_id: str,
        player_input: str,
        inventory: list,
        known_npc_names: list[str] | None = None,
        known_locations: list[str] | None = None,
        known_npc_refs: list[dict[str, str]] | None = None,
        known_location_refs: list[dict[str, str]] | None = None,
        known_item_refs: list[dict[str, str]] | None = None,
        known_scene_point_refs: list[dict[str, str]] | None = None,
        context: GameContextResponse | None = None,
    ) -> TurnIntent:
        intent, _trace = self.analyze_intent_with_trace(
            world_id=world_id,
            world_character_id=world_character_id,
            player_input=player_input,
            inventory=inventory,
            known_npc_names=known_npc_names,
            known_locations=known_locations,
            known_npc_refs=known_npc_refs,
            known_location_refs=known_location_refs,
            known_item_refs=known_item_refs,
            known_scene_point_refs=known_scene_point_refs,
            context=context,
        )
        return intent

    def propose_scene_points_with_trace(
        self,
        *,
        world: WorldSessionResponse,
        context: GameContextResponse | None = None,
        location_name: str | None = None,
        max_items: int = 3,
    ) -> tuple[list[ScenePointSeed], LlmCapabilityTrace]:
        provider_policy = "openrouter" if self._should_use_openrouter_for_capability("narration") else "preview"
        safe_max_items = max(1, min(max_items, 5))
        if provider_policy == "preview":
            return (
                [],
                self._build_capability_trace(
                    capability="scene_point_proposals",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                ),
            )

        try:
            proposals = self._propose_scene_points_openrouter(
                world=world,
                context=context,
                location_name=location_name,
                max_items=safe_max_items,
            )
            return (
                proposals,
                self._build_capability_trace(
                    capability="scene_point_proposals",
                    provider_policy=provider_policy,
                    provider_used="openrouter",
                    model=self.settings.openrouter_narrator_model,
                ),
            )
        except Exception as exc:
            if not self.settings.llm_fallback_to_preview:
                raise
            return (
                [],
                self._build_capability_trace(
                    capability="scene_point_proposals",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                    fallback_used=True,
                    fallback_reason=type(exc).__name__,
                ),
            )

    def analyze_intent_with_trace(
        self,
        *,
        world_id: str,
        world_character_id: str,
        player_input: str,
        inventory: list,
        known_npc_names: list[str] | None = None,
        known_locations: list[str] | None = None,
        known_npc_refs: list[dict[str, str]] | None = None,
        known_location_refs: list[dict[str, str]] | None = None,
        known_item_refs: list[dict[str, str]] | None = None,
        known_scene_point_refs: list[dict[str, str]] | None = None,
        context: GameContextResponse | None = None,
    ) -> tuple[TurnIntent, LlmCapabilityTrace]:
        provider_policy = self._intent_provider_policy_for_request(player_input=player_input)
        if provider_policy == "preview":
            intent = self._analyze_preview(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names,
                known_locations=known_locations,
                known_npc_refs=known_npc_refs,
                known_location_refs=known_location_refs,
                known_scene_point_refs=known_scene_point_refs,
            )
            return intent, self._build_capability_trace(
                capability="intent",
                provider_policy=provider_policy,
                provider_used="preview",
                model=None,
            )

        try:
            intent = self._analyze_openrouter(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names or [],
                known_locations=known_locations or [],
                known_npc_refs=known_npc_refs or [],
                known_location_refs=known_location_refs or [],
                known_item_refs=known_item_refs or [],
                known_scene_point_refs=known_scene_point_refs or [],
                context=context,
            )
            return intent, self._build_capability_trace(
                capability="intent",
                provider_policy=provider_policy,
                provider_used="openrouter",
                model=self.settings.openrouter_intent_model,
            )
        except Exception as exc:
            if not self.settings.llm_fallback_to_preview:
                raise
            preview_intent = self._analyze_preview(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names,
                known_locations=known_locations,
                known_npc_refs=known_npc_refs,
                known_location_refs=known_location_refs,
                known_scene_point_refs=known_scene_point_refs,
            )
            preview_intent.analysis_notes.append(
                f"OpenRouter-Fallback auf Preview-Analyzer wegen Fehler: {type(exc).__name__}"
            )
            return preview_intent, self._build_capability_trace(
                capability="intent",
                provider_policy=provider_policy,
                provider_used="preview",
                model=None,
                fallback_used=True,
                fallback_reason=type(exc).__name__,
            )

    def narrate(
        self,
        *,
        resolution: TurnResolution,
        context_before: GameContextResponse | None = None,
    ) -> NarrativeEnvelope:
        narrative, _trace = self.narrate_with_trace(resolution=resolution, context_before=context_before)
        return narrative

    def narrate_with_trace(
        self,
        *,
        resolution: TurnResolution,
        context_before: GameContextResponse | None = None,
    ) -> tuple[NarrativeEnvelope, LlmCapabilityTrace]:
        provider_policy = "openrouter" if self._should_use_openrouter_for_capability("narration") else "preview"
        if provider_policy == "preview":
            return (
                build_narrative_from_resolution(resolution),
                self._build_capability_trace(
                    capability="narration",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                ),
            )

        try:
            narrative, used_preview_consistency_fallback, consistency_fallback_reason = self._narrate_openrouter(
                resolution=resolution,
                context_before=context_before,
            )
            if used_preview_consistency_fallback:
                return (
                    narrative,
                    self._build_capability_trace(
                        capability="narration",
                        provider_policy=provider_policy,
                        provider_used="preview",
                        model=None,
                        fallback_used=True,
                        fallback_reason=consistency_fallback_reason or "NarrationConsistencyConflict",
                    ),
                )
            return (
                narrative,
                self._build_capability_trace(
                    capability="narration",
                    provider_policy=provider_policy,
                    provider_used="openrouter",
                    model=self.settings.openrouter_narrator_model,
                ),
            )
        except Exception as exc:
            if not self.settings.llm_fallback_to_preview:
                raise
            return (
                build_narrative_from_resolution(resolution),
                self._build_capability_trace(
                    capability="narration",
                    provider_policy=provider_policy,
                    provider_used="preview",
                    model=None,
                    fallback_used=True,
                    fallback_reason=type(exc).__name__,
                ),
            )

    def _analyze_preview(self, **kwargs: Any) -> TurnIntent:
        return analyze_player_input_preview(**kwargs)

    def _bootstrap_openrouter(
        self,
        *,
        request: WorldBootstrapRequest,
        preview: WorldBootstrapResult,
    ) -> WorldBootstrapResult:
        system_prompt = (
            "You generate an IP-safe German RPG world bootstrap enrichment. "
            "Keep all mechanics deterministic and only enrich text/lists. "
            "Return strict JSON with keys world_name, start_hook, factions, open_threads, initial_narrative, player_orientation."
        )
        user_prompt = (
            f"world_request={request.model_dump_json()}\n"
            f"preview_bootstrap={preview.model_dump_json()}\n"
            "Constraints:\n"
            "- Keep it IP-safe and original.\n"
            "- Preserve the setting concept, but do not invent canon IP names.\n"
            "- German text.\n"
            "- 3-6 Orientierungspunkte, 2-6 Fraktionen/Threads.\n"
            "- Return JSON only."
        )
        payload = self._request_openrouter_json(
            model=self.settings.openrouter_bootstrap_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose="bootstrap_enrichment",
            response_format_candidates=[_OPENROUTER_BOOTSTRAP_JSON_SCHEMA, {"type": "json_object"}],
        )

        world_seed_updates: dict[str, Any] = {}
        world_name = self._safe_text(payload.get("world_name"), max_len=120)
        if world_name:
            world_seed_updates["name"] = world_name
        start_hook = self._safe_text(payload.get("start_hook"), max_len=2000)
        if start_hook:
            world_seed_updates["start_hook"] = start_hook
        factions = self._safe_text_list(payload.get("factions"), max_items=8, max_len=120)
        if factions:
            world_seed_updates["factions"] = factions
        open_threads = self._safe_text_list(payload.get("open_threads"), max_items=8, max_len=240)
        if open_threads:
            world_seed_updates["open_threads"] = open_threads

        world_seed = preview.world_seed.model_copy(update=world_seed_updates) if world_seed_updates else preview.world_seed

        initial_narrative = self._safe_text(payload.get("initial_narrative"), max_len=8000) or preview.initial_narrative
        player_orientation = (
            self._safe_text_list(payload.get("player_orientation"), max_items=8, max_len=240) or preview.player_orientation
        )

        return preview.model_copy(
            update={
                "world_seed": world_seed,
                "initial_narrative": initial_narrative,
                "player_orientation": player_orientation,
            }
        )

    def _analyze_openrouter(
        self,
        *,
        world_id: str,
        world_character_id: str,
        player_input: str,
        inventory: list,
        known_npc_names: list[str],
        known_locations: list[str],
        known_npc_refs: list[dict[str, str]],
        known_location_refs: list[dict[str, str]],
        known_item_refs: list[dict[str, str]],
        known_scene_point_refs: list[dict[str, str]],
        context: GameContextResponse | None,
    ) -> TurnIntent:
        system_prompt = (
            "You are an RPG intent analyzer. Return strict JSON with keys: actions, analysis_notes. "
            "Each action must include action_type and may include target_ref, destination, item_ref, target_kind, parameters, confidence."
        )
        context_hint = ""
        if context is not None:
            context_hint = json.dumps(
                {
                    "location": context.world.character_state.location_name,
                    "inventory_names": [item.name for item in context.world.inventory],
                    "known_npcs": known_npc_names,
                    "known_locations": known_locations,
                    "target_refs": {
                        "npcs": known_npc_refs,
                        "locations": known_location_refs,
                        "items": known_item_refs,
                        "scene_points": known_scene_point_refs,
                    },
                },
                ensure_ascii=False,
            )
        user_prompt = (
            f"world_id={world_id}\nworld_character_id={world_character_id}\n"
            f"player_input={player_input}\n"
            f"context={context_hint}\n"
            "Return JSON only."
        )
        payload = self._request_openrouter_json(
            model=self.settings.openrouter_intent_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose="intent_analysis",
            response_format_candidates=[_OPENROUTER_INTENT_JSON_SCHEMA, {"type": "json_object"}],
        )
        actions_raw = payload.get("actions") or []
        if isinstance(actions_raw, dict):
            actions_raw = [actions_raw]
        actions = []
        for action in actions_raw:
            if not isinstance(action, dict):
                continue
            normalized_action = dict(action)
            normalized_action.setdefault("analysis_source", "openrouter_llm")
            validated = TurnIntentAction.model_validate(normalized_action)
            validated = self._normalize_openrouter_action_refs(
                action=validated,
                known_npc_refs=known_npc_refs,
                known_location_refs=known_location_refs,
                known_item_refs=known_item_refs,
                known_scene_point_refs=known_scene_point_refs,
            )
            actions.append(validated)
        analysis_notes = [str(note) for note in (payload.get("analysis_notes") or [])]
        if not actions:
            actions = [
                TurnIntentAction(
                    action_type="CLARIFY",
                    analysis_source="openrouter_llm",
                    parameters={"intent": "clarify"},
                    confidence=0.2,
                )
            ]
            analysis_notes.append("OpenRouter lieferte keine validen Aktionen, Rueckfrage-Aktion erzeugt.")
        return TurnIntent(
            world_id=world_id,
            world_character_id=world_character_id,
            raw_player_input=player_input,
            actions=actions,
            analysis_notes=analysis_notes,
        )

    def _propose_scene_points_openrouter(
        self,
        *,
        world: WorldSessionResponse,
        context: GameContextResponse | None,
        location_name: str | None,
        max_items: int,
    ) -> list[ScenePointSeed]:
        focus_location = (
            (location_name or "").strip()
            or (context.world.character_state.location_name if context is not None else "").strip()
            or world.world_seed.start_location_name
        )
        existing_points = list(world.world_seed.scene_points)
        existing_ref_ids = {point.ref_id for point in existing_points}
        existing_names = {point.name.lower() for point in existing_points}
        system_prompt = (
            "You suggest optional NEW scene interaction points for a German RPG world. "
            "Return strict JSON with key scene_points (array). "
            "Each scene point must be IP-safe, compact, and gameplay-relevant. "
            "Do not repeat existing scene points and do not modify existing world facts."
        )
        user_prompt = (
            f"world_name={world.world_seed.name}\n"
            f"world_summary={world.world_seed.summary}\n"
            f"factions={json.dumps(world.world_seed.factions, ensure_ascii=False)}\n"
            f"open_threads={json.dumps(world.world_seed.open_threads, ensure_ascii=False)}\n"
            f"focus_location={focus_location}\n"
            f"max_items={max_items}\n"
            f"existing_scene_points={json.dumps([point.model_dump(mode='json') for point in existing_points], ensure_ascii=False)}\n"
            "Constraints:\n"
            "- return 1..max_items entries\n"
            "- kind must be one of: scene_point, container, scene_object\n"
            "- ref_id must be unique and stable slug-like (or null)\n"
            "- aliases optional, up to 6\n"
            "- German labels\n"
            "- JSON only."
        )
        payload = self._request_openrouter_json(
            model=self.settings.openrouter_narrator_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose="scene_point_proposals",
            response_format_candidates=[_OPENROUTER_SCENE_POINT_PROPOSAL_JSON_SCHEMA, {"type": "json_object"}],
        )
        raw_points = payload.get("scene_points")
        if isinstance(raw_points, dict):
            raw_points = [raw_points]
        if not isinstance(raw_points, list):
            return []
        out: list[ScenePointSeed] = []
        seen_ref_ids = set(existing_ref_ids)
        seen_names = set(existing_names)
        for idx, raw_point in enumerate(raw_points):
            if len(out) >= max_items:
                break
            if not isinstance(raw_point, dict):
                continue
            normalized = self._normalize_scene_point_proposal_entry(
                raw_point=raw_point,
                fallback_location=focus_location,
                index=idx,
                seen_ref_ids=seen_ref_ids,
            )
            if normalized is None:
                continue
            if normalized.name.lower() in seen_names:
                continue
            out.append(normalized)
            seen_ref_ids.add(normalized.ref_id)
            seen_names.add(normalized.name.lower())
        return out

    def _narrate_openrouter(
        self,
        *,
        resolution: TurnResolution,
        context_before: GameContextResponse | None,
    ) -> tuple[NarrativeEnvelope, bool, str | None]:
        fallback_narrative = build_narrative_from_resolution(resolution)
        system_prompt = (
            "You are a German RPG narrator for an interactive turn-based game. "
            "Return strict JSON with keys: narrative, actionable_options, story_beats. "
            "Narrative must reflect the provided deterministic resolution and stay consistent with story beats. "
            "Write in flowing scene prose, not as a report and not as bullet-style enumeration. "
            "Avoid rigid recap patterns like 'Anschliessend ... Danach ...'. "
            "Blend action outcomes into one coherent scene paragraph with natural transitions. "
            "Avoid event-log phrasing like 'Du hast X getan, dann Y getan'. "
            "Keep NPC references consistent across the paragraph. "
            "If grammatical gender is unclear, repeat the NPC name instead of using 'er/sie'. "
            "If an NPC appears in known_npc_names_before, never claim that this NPC is absent, not visible, or nowhere to be seen. "
            "Keep NPC distance wording consistent with known_npc_distance_before. "
            "Do not describe a near/adjacent NPC as far away or not nearby. "
            "Only mention status values when they matter for the immediate next decision. "
            "Do not invent state changes that are not present in the resolution."
        )
        context_hint = ""
        visible_npc_names: list[str] = []
        visible_npc_distance_bands: dict[str, str] = {}
        if context_before is not None:
            visible_npc_names = [
                str(npc.name).strip()
                for npc in context_before.target_catalog.npcs
                if str(npc.name).strip()
            ]
            visible_npc_distance_bands = {
                str(npc.name).strip().lower(): str(npc.distance_band_to_player or "").strip().lower()
                for npc in context_before.target_catalog.npcs
                if str(npc.name).strip() and str(npc.distance_band_to_player or "").strip()
            }
            context_hint = json.dumps(
                {
                    "location_before": context_before.world.character_state.location_name,
                    "recent_turn_inputs": [turn.raw_player_input for turn in context_before.recent_turns[-3:]],
                    "known_npc_names_before": [npc.name for npc in context_before.target_catalog.npcs[:12]],
                    "known_npc_distance_before": visible_npc_distance_bands,
                },
                ensure_ascii=False,
            )
        user_prompt = (
            f"resolution={resolution.model_dump_json()}\n"
            f"story_beats={json.dumps(fallback_narrative.story_beats, ensure_ascii=False)}\n"
            f"context_before={context_hint}\n"
            "Style goals:\n"
            "- no list-like recaps\n"
            "- no developer/debug wording\n"
            "- keep NPC naming consistent (prefer names over pronouns when uncertain)\n"
            "- concise but atmospheric scene continuity\n"
            "Return JSON only in German narrative."
        )
        payload = self._request_openrouter_json(
            model=self.settings.openrouter_narrator_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose="narration",
            response_format_candidates=[{"type": "json_object"}],
        )
        narrative_text = str(payload.get("narrative") or "").strip()
        if not narrative_text:
            narrative_text = fallback_narrative.narrative
        if self._narrative_has_visibility_contradiction(
            narrative_text=narrative_text,
            visible_npc_names=visible_npc_names,
        ):
            return fallback_narrative, True, "NarrationVisibilityConflict"
        if self._narrative_has_distance_contradiction(
            narrative_text=narrative_text,
            visible_npc_distance_bands=visible_npc_distance_bands,
        ):
            return fallback_narrative, True, "NarrationDistanceConflict"
        return (
            NarrativeEnvelope(
                world_id=resolution.world_id,
                world_character_id=resolution.world_character_id,
                narrative=narrative_text,
                story_beats=self._normalize_story_beats(payload.get("story_beats"), fallback_narrative.story_beats),
                actionable_options=self._normalize_actionable_options(payload.get("actionable_options")),
            ),
            False,
            None,
        )

    def _narrative_has_visibility_contradiction(
        self,
        *,
        narrative_text: str,
        visible_npc_names: list[str],
    ) -> bool:
        text = (narrative_text or "").strip().lower()
        if not text or not visible_npc_names:
            return False
        absence_markers = (
            "nirgendwo",
            "nicht zu sehen",
            "nicht sichtbar",
            "nicht in sicht",
            "ausser sicht",
            "außer sicht",
            "nicht auffindbar",
            "nicht zu entdecken",
        )
        visibility_markers = (
            "sehen",
            "sicht",
            "sichtbar",
            "in sicht",
            "entdeck",
            "auffind",
        )
        sentences = [segment.strip() for segment in re.split(r"[.!?]+", text) if segment.strip()]
        for sentence in sentences:
            if not any(marker in sentence for marker in absence_markers):
                continue
            if not any(marker in sentence for marker in visibility_markers):
                continue
            for raw_name in visible_npc_names:
                npc_name = str(raw_name).strip().lower()
                if npc_name and npc_name in sentence:
                    return True
        return False

    def _narrative_has_distance_contradiction(
        self,
        *,
        narrative_text: str,
        visible_npc_distance_bands: dict[str, str],
    ) -> bool:
        text = (narrative_text or "").strip().lower()
        if not text or not visible_npc_distance_bands:
            return False
        far_distance_markers = (
            "nicht in unmittelbarer naehe",
            "nicht in unmittelbarer nähe",
            "nicht in der naehe",
            "nicht in der nähe",
            "weit weg",
            "weit entfernt",
            "aus der ferne",
            "in der ferne",
            "fern von",
        )
        close_distance_markers = (
            "in unmittelbarer naehe",
            "in unmittelbarer nähe",
            "direkt neben",
            "direkt bei",
            "direkt vor dir",
            "in greifweite",
            "in schlagdistanz",
            "nah bei",
            "nah an",
        )
        sentences = [segment.strip() for segment in re.split(r"[.!?]+", text) if segment.strip()]
        for sentence in sentences:
            for raw_name, raw_band in visible_npc_distance_bands.items():
                npc_name = str(raw_name or "").strip().lower()
                band = str(raw_band or "").strip().lower()
                if not npc_name or npc_name not in sentence:
                    continue
                if band in {"near", "adjacent"} and any(marker in sentence for marker in far_distance_markers):
                    return True
                if band == "far" and any(marker in sentence for marker in close_distance_markers):
                    return True
        return False

    def _request_openrouter_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        purpose: str,
        response_format_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        formats = response_format_candidates or [{"type": "json_object"}]
        last_error: Exception | None = None
        for response_format in formats:
            try:
                content = self._openrouter_client.chat_completion(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                )
                return self._parse_or_repair_json_object(
                    model=model,
                    content=content,
                    purpose=purpose,
                    response_format=response_format,
                )
            except Exception as exc:
                last_error = exc
                continue
        if last_error is None:
            raise LlmRuntimeError("OpenRouter request failed before response parsing.")
        raise LlmRuntimeError(f"OpenRouter JSON request failed for all response formats: {last_error}") from last_error

    def _parse_or_repair_json_object(
        self,
        *,
        model: str,
        content: str,
        purpose: str,
        response_format: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._parse_json_object_from_llm_text(content)
        except LlmRuntimeError as first_error:
            if self.settings.openrouter_json_repair_attempts <= 0:
                raise
            last_error: Exception = first_error
            for _ in range(self.settings.openrouter_json_repair_attempts):
                try:
                    repaired_content = self._openrouter_client.chat_completion(
                        model=model,
                        system_prompt=(
                            "You convert model output into a strict JSON object. "
                            "Return JSON only. Do not add markdown fences or prose."
                        ),
                        user_prompt=(
                            f"Purpose: {purpose}\n"
                            "Convert the following content to a valid JSON object preserving meaning.\n"
                            f"{content}"
                        ),
                        response_format=response_format,
                    )
                    return self._parse_json_object_from_llm_text(repaired_content)
                except Exception as exc:  # pragma: no cover - retry path exercised in tests
                    last_error = exc
            raise LlmRuntimeError(f"OpenRouter JSON parsing failed after repair attempts: {last_error}") from last_error

    def _parse_json_object_from_llm_text(self, raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            raise LlmRuntimeError("OpenRouter returned empty content.")

        # Common success path.
        direct = self._try_parse_json_object(text)
        if direct is not None:
            return direct

        # Strip fenced code block if present.
        fenced = self._strip_json_fences(text)
        if fenced != text:
            parsed = self._try_parse_json_object(fenced)
            if parsed is not None:
                return parsed

        # Extract first balanced JSON object from mixed prose responses.
        for candidate in self._extract_json_object_candidates(text):
            parsed = self._try_parse_json_object(candidate)
            if parsed is not None:
                return parsed

        raise LlmRuntimeError("OpenRouter response did not contain a valid JSON object.")

    def _try_parse_json_object(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _strip_json_fences(self, text: str) -> str:
        stripped = text.strip()
        fenced_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.I | re.S)
        if fenced_match:
            return fenced_match.group(1).strip()
        return text

    def _extract_json_object_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        depth = 0
        start_index: int | None = None
        in_string = False
        escaped = False
        for idx, char in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                if depth == 0:
                    start_index = idx
                depth += 1
            elif char == "}":
                if depth <= 0:
                    continue
                depth -= 1
                if depth == 0 and start_index is not None:
                    candidates.append(text[start_index : idx + 1])
                    if len(candidates) >= 3:
                        break
                    start_index = None
        return candidates

    def _normalize_actionable_options(self, raw_options: Any) -> list[str]:
        if not isinstance(raw_options, list):
            return []
        normalized: list[str] = []
        for item in raw_options:
            text = str(item).strip()
            if not text:
                continue
            normalized.append(text)
            if len(normalized) >= 5:
                break
        return normalized

    def _normalize_story_beats(self, raw_beats: Any, fallback_beats: list[str]) -> list[str]:
        if not isinstance(raw_beats, list):
            return list(fallback_beats[:8])
        normalized: list[str] = []
        for item in raw_beats:
            text = str(item).strip()
            if not text:
                continue
            normalized.append(text)
            if len(normalized) >= 8:
                break
        if not normalized:
            return list(fallback_beats[:8])
        return normalized

    def _safe_text(self, value: Any, *, max_len: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text[:max_len].strip()

    def _safe_text_list(self, raw: Any, *, max_items: int, max_len: int) -> list[str]:
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            text = self._safe_text(item, max_len=max_len)
            if not text:
                continue
            out.append(text)
            if len(out) >= max_items:
                break
        return out

    def _normalize_scene_point_proposal_entry(
        self,
        *,
        raw_point: dict[str, Any],
        fallback_location: str,
        index: int,
        seen_ref_ids: set[str],
    ) -> ScenePointSeed | None:
        name = self._safe_text(raw_point.get("name"), max_len=120)
        if not name:
            return None
        kind = self._safe_text(raw_point.get("kind"), max_len=40).lower() or "scene_point"
        if kind not in {"scene_point", "container", "scene_object"}:
            kind = "scene_point"
        location_name = self._safe_text(raw_point.get("location_name"), max_len=120) or fallback_location
        if not location_name:
            return None
        aliases = self._safe_text_list(raw_point.get("aliases"), max_items=6, max_len=80)
        ref_id_raw = self._safe_text(raw_point.get("ref_id"), max_len=120).lower()
        ref_id = self._build_scene_point_ref_id(
            ref_id_raw=ref_id_raw,
            kind=kind,
            name=name,
            index=index,
            seen_ref_ids=seen_ref_ids,
        )
        scene_zone_id = self._safe_text(raw_point.get("scene_zone_id"), max_len=120) or None
        scene_zone_name = self._safe_text(raw_point.get("scene_zone_name"), max_len=120) or None
        return ScenePointSeed(
            ref_id=ref_id,
            name=name,
            kind=kind,
            location_name=location_name,
            scene_zone_id=scene_zone_id,
            scene_zone_name=scene_zone_name,
            aliases=aliases,
        )

    def _build_scene_point_ref_id(
        self,
        *,
        ref_id_raw: str,
        kind: str,
        name: str,
        index: int,
        seen_ref_ids: set[str],
    ) -> str:
        prefix = "poi"
        if kind == "container":
            prefix = "ctr"
        elif kind == "scene_object":
            prefix = "obj"
        base_slug = self._slugify_for_ref(ref_id_raw or name)
        candidate = base_slug
        if not candidate.startswith(f"{prefix}-"):
            candidate = f"{prefix}-{candidate}"
        candidate = candidate[:120].strip("-")
        if not candidate:
            candidate = f"{prefix}-proposal-{index + 1}"
        unique_candidate = candidate
        serial = 2
        while unique_candidate in seen_ref_ids:
            suffix = f"-{serial}"
            unique_candidate = f"{candidate[: max(1, 120 - len(suffix))]}{suffix}"
            serial += 1
        return unique_candidate

    def _slugify_for_ref(self, value: str) -> str:
        lowered = (value or "").strip().lower()
        if not lowered:
            return ""
        slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
        return slug[:110]

    def _should_use_openrouter_for_capability(self, capability: str) -> bool:
        mode = (self.settings.llm_mode or "preview").strip().lower()
        if mode == "preview":
            return False
        if mode == "openrouter":
            return True
        if mode == "hybrid":
            return capability in {"bootstrap", "narration"}
        return False

    def _intent_provider_policy_for_request(self, *, player_input: str) -> str:
        if self._should_use_openrouter_for_capability("intent"):
            return "openrouter"
        mode = (self.settings.llm_mode or "preview").strip().lower()
        if mode != "hybrid":
            return "preview"
        if not self.settings.hybrid_intent_llm_for_complex_inputs:
            return "preview"
        if self._looks_like_complex_intent_input(player_input):
            return "openrouter"
        return "preview"

    def _looks_like_complex_intent_input(self, player_input: str) -> bool:
        text = (player_input or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if re.search(r"\b(dann|danach|anschlie(?:ss|ß)end)\b", lowered):
            return True
        if ";" in text:
            return True
        action_verb_hits = len(
            re.findall(
                (
                    r"\b(?:gehe|geh|laufe|reise|betrete|bewege|begib|"
                    r"rede|spreche|frage|unterhalte|"
                    r"untersuche|schaue|schau|suche|durchsuche|oeffne|öffne|nimm|nehme|"
                    r"greife|attackiere|schlage|haue|steche|schiesse|schieße|feuere|werfe|"
                    r"benutze|verwende|nutze|trinke|iss|aktiviere|"
                    r"entferne|halte|weiche|naehere|nähere|annaehern|annähern|trete)\b"
                ),
                lowered,
                flags=re.I,
            )
        )
        return action_verb_hits >= 2 and " und " in f" {lowered} "

    def _provider_name_for_capability(self, capability: str, *, openrouter_ready: bool) -> str:
        wants_openrouter = self._should_use_openrouter_for_capability(capability)
        if wants_openrouter and openrouter_ready:
            return "openrouter"
        if wants_openrouter and not openrouter_ready and not self.settings.llm_fallback_to_preview:
            return "unavailable"
        return "preview"

    def _build_capability_trace(
        self,
        *,
        capability: str,
        provider_policy: str,
        provider_used: str,
        model: str | None,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
    ) -> LlmCapabilityTrace:
        return LlmCapabilityTrace(
            capability=capability,
            mode=self.settings.llm_mode,
            provider_policy=provider_policy,
            provider_used=provider_used,
            model=(model if provider_used == "openrouter" else None),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    def _normalize_openrouter_action_refs(
        self,
        *,
        action: TurnIntentAction,
        known_npc_refs: list[dict[str, str]],
        known_location_refs: list[dict[str, str]],
        known_item_refs: list[dict[str, str]],
        known_scene_point_refs: list[dict[str, str]],
    ) -> TurnIntentAction:
        params = dict(action.parameters)
        updates: dict[str, object] = {}

        npc_ref_index = self._build_ref_index(known_npc_refs)
        location_ref_index = self._build_ref_index(known_location_refs)
        item_ref_index = self._build_ref_index(known_item_refs)
        scene_point_ref_index = self._build_ref_index(known_scene_point_refs)

        if action.action_type.value in {"TALK", "ATTACK", "RETREAT", "APPROACH"}:
            candidate_name = str(params.get("target_name") or "").strip()
            candidate_ref = (action.target_ref or "").strip()
            if not candidate_name and candidate_ref and not candidate_ref.startswith("npc-"):
                candidate_name = candidate_ref
            if candidate_name and not candidate_ref.startswith("npc-"):
                role_resolution = resolve_unique_role_title_npc_reference(candidate_name, known_npc_refs)
                if role_resolution and str(role_resolution.get("status")) == "ambiguous":
                    role_name = str(role_resolution.get("role") or "npc")
                    candidate_names = [
                        str(name) for name in (role_resolution.get("candidates") or []) if str(name).strip()
                    ]
                    message = (
                        f"Mehrdeutige Rollen-Anrede erkannt ({role_name}). Bitte praezisieren: "
                        f"{', '.join(candidate_names[:4])}."
                        if candidate_names
                        else f"Mehrdeutige Rollen-Anrede erkannt ({role_name}). Bitte praezisieren."
                    )
                    return TurnIntentAction(
                        action_type="CLARIFY",
                        analysis_source=action.analysis_source or "openrouter_llm",
                        target_kind="npc",
                        parameters={
                            "intent": "clarify",
                            "reason": "ambiguous_npc_role_title",
                            "message": message,
                        },
                        confidence=min(float(action.confidence or 0.4), 0.4),
                    )
                if role_resolution and str(role_resolution.get("status")) == "resolved":
                    candidate_name = str((role_resolution.get("entry") or {}).get("name") or candidate_name).strip() or candidate_name
            resolved_id = candidate_ref if candidate_ref.startswith("npc-") else self._lookup_ref_id(candidate_name, npc_ref_index)
            if resolved_id:
                updates["target_ref"] = resolved_id
                params["target_id"] = resolved_id
            if candidate_name:
                params.setdefault("target_name", candidate_name)
            target_meta = self._lookup_ref_entry(candidate_name, npc_ref_index) or {}
            params.setdefault("target_location_name", str(target_meta.get("location_name") or "") or None)
            params.setdefault("target_zone_id", str(target_meta.get("scene_zone_id") or "") or None)
            params.setdefault("target_zone_name", str(target_meta.get("scene_zone_name") or "") or None)
            params.setdefault("target_distance_band", str(target_meta.get("distance_band_to_player") or "") or None)

        if action.action_type.value == "MOVE":
            destination_name = str(params.get("destination_name") or action.destination or "").strip()
            candidate_ref = (action.target_ref or "").strip()
            resolved_id = (
                candidate_ref if candidate_ref.startswith("loc-") else self._lookup_ref_id(destination_name, location_ref_index)
            )
            location_meta = self._lookup_ref_entry(destination_name, location_ref_index) or {}
            if destination_name:
                updates["destination"] = destination_name
                params["destination_name"] = destination_name
            if resolved_id:
                updates["target_ref"] = resolved_id
                params["destination_id"] = resolved_id
            params.setdefault("target_location_name", str(location_meta.get("location_name") or destination_name) or None)
            params.setdefault("target_zone_id", str(location_meta.get("scene_zone_id") or "") or None)
            params.setdefault("target_zone_name", str(location_meta.get("scene_zone_name") or "") or None)

        if action.action_type.value == "USE_ITEM":
            item_name = str(params.get("item_name") or params.get("target_name") or "").strip()
            item_ref = (action.item_ref or "").strip()
            resolved_item_id = item_ref if item_ref.startswith("inv-") else self._lookup_ref_id(item_name, item_ref_index)
            if resolved_item_id:
                updates["item_ref"] = resolved_item_id
                params["item_id"] = resolved_item_id
            if item_name:
                params.setdefault("item_name", item_name)
                params.setdefault("target_name", item_name)
                if not action.target_ref:
                    updates["target_ref"] = item_name

        if action.action_type.value in {"INSPECT", "OPEN", "SEARCH", "TAKE"}:
            target_name = str(params.get("target_name") or "").strip()
            target_ref = (action.target_ref or "").strip()
            target_kind = str(params.get("target_kind") or action.target_kind or "").strip()
            if not target_name and target_ref and not target_ref.startswith(("sp-", "poi-", "obj-", "ctr-")):
                target_name = target_ref
            target_meta = self._lookup_ref_entry(target_name, scene_point_ref_index) or {}
            resolved_target_id = (
                target_ref if target_ref.startswith(("sp-", "poi-", "obj-", "ctr-", "env-")) else self._lookup_ref_id(target_name, scene_point_ref_index)
            )
            if resolved_target_id:
                updates["target_ref"] = resolved_target_id
                params["target_id"] = resolved_target_id
            if target_name:
                params.setdefault("target_name", target_name)
            if target_meta:
                target_kind = str(target_meta.get("kind") or target_kind or "").strip() or target_kind
                params.setdefault("target_kind", target_kind or None)
                params.setdefault("target_location_name", str(target_meta.get("location_name") or "") or None)
                params.setdefault("target_zone_id", str(target_meta.get("scene_zone_id") or "") or None)
                params.setdefault("target_zone_name", str(target_meta.get("scene_zone_name") or "") or None)
                if target_kind and not action.target_kind:
                    updates["target_kind"] = target_kind

        updates["parameters"] = params
        if not updates:
            return action
        return action.model_copy(update=updates)

    def _build_ref_index(self, refs: list[dict[str, str]]) -> dict[str, dict[str, str]]:
        index: dict[str, dict[str, str]] = {}
        for entry in refs:
            name = str(entry.get("name") or "").strip()
            ref_id = str(entry.get("ref_id") or "").strip()
            if not name or not ref_id:
                continue
            index[name.lower()] = {str(k): str(v) for k, v in entry.items() if v is not None}
        return index

    def _lookup_ref_id(self, name: str, ref_index: dict[str, dict[str, str]]) -> str | None:
        normalized = (name or "").strip().lower()
        if not normalized:
            return None
        if normalized in ref_index:
            return str(ref_index[normalized].get("ref_id") or "")
        for known_name, ref_meta in ref_index.items():
            if normalized in known_name or known_name in normalized:
                return str(ref_meta.get("ref_id") or "")
        return None

    def _lookup_ref_entry(self, name: str, refs: dict[str, dict[str, str]]) -> dict[str, str] | None:
        normalized = (name or "").strip().lower()
        if not normalized:
            return None
        if normalized in refs:
            return refs[normalized]
        for known_name, ref_meta in refs.items():
            if normalized in known_name or known_name in normalized:
                return ref_meta
        return None


def build_llm_runtime(settings: Settings) -> LlmRuntime:
    return LlmRuntime(settings=settings)
