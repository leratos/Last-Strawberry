from __future__ import annotations

import json
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

    def chat_completion(self, *, model: str, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LlmRuntimeError("OpenRouter API key is not configured.")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
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
            return str(parsed["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmRuntimeError("OpenRouter response format was unexpected.") from exc


class LlmRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._openrouter_client = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
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
        except Exception:
            if not self.settings.llm_fallback_to_preview:
                raise
            return self._analyze_preview(
                world_id=world_id,
                world_character_id=world_character_id,
                player_input=player_input,
                inventory=inventory,
                known_npc_names=known_npc_names,
                known_locations=known_locations,
            )

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
        content = self._openrouter_client.chat_completion(
            model=self.settings.openrouter_intent_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload = json.loads(content)
        actions_raw = payload.get("actions") or []
        actions = [TurnIntentAction.model_validate(action) for action in actions_raw]
        analysis_notes = [str(note) for note in (payload.get("analysis_notes") or [])]
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
        content = self._openrouter_client.chat_completion(
            model=self.settings.openrouter_narrator_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload = json.loads(content)
        return NarrativeEnvelope(
            world_id=resolution.world_id,
            world_character_id=resolution.world_character_id,
            narrative=str(payload.get("narrative") or "").strip() or build_narrative_from_resolution(resolution).narrative,
            actionable_options=[str(item) for item in (payload.get("actionable_options") or [])][:5],
        )


def build_llm_runtime(settings: Settings) -> LlmRuntime:
    return LlmRuntime(settings=settings)
