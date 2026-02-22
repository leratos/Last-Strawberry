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
            )

        try:
            return self._analyze_openrouter(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names or [],
                known_locations=known_locations or [],
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
            actions.append(TurnIntentAction.model_validate(normalized_action))
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
    ) -> dict[str, Any]:
        content = self._openrouter_client.chat_completion(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )
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
                        response_format={"type": "json_object"},
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


def build_llm_runtime(settings: Settings) -> LlmRuntime:
    return LlmRuntime(settings=settings)
