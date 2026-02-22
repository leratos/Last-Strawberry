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
from ls_shared_schemas.game_context import GameContextResponse
from ls_shared_schemas.turns import NarrativeEnvelope, TurnIntent, TurnIntentAction, TurnResolution


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


@dataclass(frozen=True)
class LlmRuntimeStatus:
    mode: str
    fallback_to_preview: bool
    intent_provider: str
    narration_provider: str
    openrouter_configured: bool
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
        requested_openrouter = self.settings.llm_mode == "openrouter"
        active_openrouter = requested_openrouter and openrouter_ready
        provider_name = "openrouter" if active_openrouter else "preview"
        if requested_openrouter and not openrouter_ready and not self.settings.llm_fallback_to_preview:
            provider_name = "unavailable"
        return LlmRuntimeStatus(
            mode=self.settings.llm_mode,
            fallback_to_preview=self.settings.llm_fallback_to_preview,
            intent_provider=provider_name,
            narration_provider=provider_name,
            openrouter_configured=openrouter_ready,
            intent_model=self.settings.openrouter_intent_model,
            narrator_model=self.settings.openrouter_narrator_model,
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
        context: GameContextResponse | None = None,
    ) -> TurnIntent:
        if self.settings.llm_mode != "openrouter":
            return self._analyze_preview(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names,
                known_locations=known_locations,
                known_npc_refs=known_npc_refs,
                known_location_refs=known_location_refs,
            )

        try:
            return self._analyze_openrouter(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names or [],
                known_locations=known_locations or [],
                known_npc_refs=known_npc_refs or [],
                known_location_refs=known_location_refs or [],
                known_item_refs=known_item_refs or [],
                context=context,
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
            )
            preview_intent.analysis_notes.append(
                f"OpenRouter-Fallback auf Preview-Analyzer wegen Fehler: {type(exc).__name__}"
            )
            return preview_intent

    def narrate(
        self,
        *,
        resolution: TurnResolution,
        context_before: GameContextResponse | None = None,
    ) -> NarrativeEnvelope:
        if self.settings.llm_mode != "openrouter":
            return build_narrative_from_resolution(resolution)

        try:
            return self._narrate_openrouter(resolution=resolution, context_before=context_before)
        except Exception:
            if not self.settings.llm_fallback_to_preview:
                raise
            return build_narrative_from_resolution(resolution)

    def _analyze_preview(self, **kwargs: Any) -> TurnIntent:
        return analyze_player_input_preview(**kwargs)

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

    def _narrate_openrouter(
        self,
        *,
        resolution: TurnResolution,
        context_before: GameContextResponse | None,
    ) -> NarrativeEnvelope:
        system_prompt = (
            "You are a German RPG narrator. Return strict JSON with keys: narrative, actionable_options. "
            "Narrative must reflect the provided deterministic resolution."
        )
        context_hint = ""
        if context_before is not None:
            context_hint = json.dumps(
                {
                    "location_before": context_before.world.character_state.location_name,
                    "recent_turn_inputs": [turn.raw_player_input for turn in context_before.recent_turns[-3:]],
                },
                ensure_ascii=False,
            )
        user_prompt = (
            f"resolution={resolution.model_dump_json()}\n"
            f"context_before={context_hint}\n"
            "Return JSON only in German narrative."
        )
        payload = self._request_openrouter_json(
            model=self.settings.openrouter_narrator_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose="narration",
            response_format_candidates=[{"type": "json_object"}],
        )
        fallback_narrative = build_narrative_from_resolution(resolution)
        narrative_text = str(payload.get("narrative") or "").strip()
        if not narrative_text:
            narrative_text = fallback_narrative.narrative
        return NarrativeEnvelope(
            world_id=resolution.world_id,
            world_character_id=resolution.world_character_id,
            narrative=narrative_text,
            actionable_options=self._normalize_actionable_options(payload.get("actionable_options")),
        )

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

    def _normalize_openrouter_action_refs(
        self,
        *,
        action: TurnIntentAction,
        known_npc_refs: list[dict[str, str]],
        known_location_refs: list[dict[str, str]],
        known_item_refs: list[dict[str, str]],
    ) -> TurnIntentAction:
        params = dict(action.parameters)
        updates: dict[str, object] = {}

        npc_ref_index = self._build_ref_index(known_npc_refs)
        location_ref_index = self._build_ref_index(known_location_refs)
        item_ref_index = self._build_ref_index(known_item_refs)

        if action.action_type.value in {"TALK", "ATTACK"}:
            candidate_name = str(params.get("target_name") or "").strip()
            candidate_ref = (action.target_ref or "").strip()
            if not candidate_name and candidate_ref and not candidate_ref.startswith("npc-"):
                candidate_name = candidate_ref
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
