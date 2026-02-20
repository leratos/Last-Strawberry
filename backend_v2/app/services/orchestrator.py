import json
import re
from datetime import datetime, UTC
from typing import Any

from backend_v2.app.config import Settings
from backend_v2.app.models import TurnRequest, TurnResponse
from backend_v2.app.providers.base import LLMProvider, ProviderError
from backend_v2.app.services.metrics import RetrievalMetricsCollector


class GameOrchestrator:
    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings,
        metrics_collector: RetrievalMetricsCollector | None = None,
    ):
        self.provider = provider
        self.settings = settings
        self.metrics_collector = metrics_collector

    async def run_turn(self, request: TurnRequest) -> TurnResponse:
        analysis_system, analysis_user = self._build_analysis_prompts(request)
        analysis_text, analysis_model = await self._generate_with_fallback(
            system_prompt=analysis_system,
            user_prompt=analysis_user,
            primary_model=self.settings.analysis_model,
            fallback_models=self.settings.analysis_fallback_models,
            temperature=self.settings.analysis_temperature,
            max_tokens=self.settings.analysis_max_tokens,
            stage_name="analysis",
        )
        extracted_commands = self._extract_commands(analysis_text)

        narrative_system, narrative_user = self._build_narrative_prompts(request, extracted_commands)
        narrative_text, narrative_model = await self._generate_with_fallback(
            system_prompt=narrative_system,
            user_prompt=narrative_user,
            primary_model=self.settings.narrative_model,
            fallback_models=self.settings.narrative_fallback_models,
            temperature=self.settings.narrative_temperature,
            max_tokens=self.settings.narrative_max_tokens,
            stage_name="narrative",
        )

        return TurnResponse(
            narrative=narrative_text,
            extracted_commands=extracted_commands,
            provider=self.provider.name,
            models={
                "analysis": analysis_model,
                "narrative": narrative_model,
            },
            created_at=datetime.now(UTC),
        )

    async def _generate_with_fallback(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        primary_model: str,
        fallback_models: tuple[str, ...],
        temperature: float,
        max_tokens: int,
        stage_name: str,
    ) -> tuple[str, str]:
        errors: list[str] = []
        for model in self._iter_candidate_models(primary_model, fallback_models):
            try:
                text = await self.provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if self.metrics_collector is not None:
                    self.metrics_collector.record_model_route(
                        stage=stage_name,
                        requested_model=primary_model,
                        used_model=model,
                    )
                return text, model
            except ProviderError as exc:
                if self.metrics_collector is not None:
                    self.metrics_collector.record_model_attempt_error(stage=stage_name, model=model)
                errors.append(f"{model}: {exc}")

        details = " | ".join(errors) if errors else "No model candidates configured."
        raise ProviderError(f"All {stage_name} models failed. {details}")

    def _iter_candidate_models(self, primary_model: str, fallback_models: tuple[str, ...]) -> tuple[str, ...]:
        candidates: list[str] = []
        for model in (primary_model, *fallback_models):
            clean = model.strip()
            if not clean or clean in candidates:
                continue
            candidates.append(clean)
        return tuple(candidates)

    def _build_analysis_prompts(self, request: TurnRequest) -> tuple[str, str]:
        memory_block = "\n".join(request.memory_context[:5]) if request.memory_context else "No memory context."
        system_prompt = (
            "You are a strict game command extractor. "
            "Return only a JSON array. No markdown, no explanation."
        )
        user_prompt = (
            f"Player: {request.player_name}\n"
            f"NPC context: {request.npc_context}\n"
            f"Memory context:\n{memory_block}\n"
            f"Player command: {request.player_command}\n\n"
            "Allowed commands: NPC_CREATE, NPC_UPDATE, PLAYER_MOVE, NPC_MOVE, "
            "PLAYER_STATE_UPDATE, NPC_STATE_UPDATE, ROLL_CHECK.\n"
            "Output: JSON array only."
        )
        return system_prompt, user_prompt

    def _build_narrative_prompts(
        self,
        request: TurnRequest,
        extracted_commands: list[dict[str, Any]],
    ) -> tuple[str, str]:
        history_block = "\n".join(request.recent_events[-3:]) if request.recent_events else "No recent events."
        memory_block = "\n".join(request.memory_context[:5]) if request.memory_context else "No memory context."
        system_prompt = (
            "You are a creative game master for a text RPG. "
            "Write immersive German narrative text. Do not emit system tags."
        )
        user_prompt = (
            f"World: {request.world_name}\n"
            f"Player: {request.player_name}\n"
            f"Recent events:\n{history_block}\n\n"
            f"Relevant memory:\n{memory_block}\n\n"
            f"Current command: {request.player_command}\n"
            f"Extracted commands: {json.dumps(extracted_commands, ensure_ascii=False)}\n\n"
            "Write the next scene and end with an actionable question for the player."
        )
        return system_prompt, user_prompt

    def _extract_commands(self, raw_text: str) -> list[dict[str, Any]]:
        if not raw_text:
            return []
        try:
            data = json.loads(raw_text)
            return self._normalize_extracted_commands(data)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", raw_text)
            if not match:
                return []
            try:
                data = json.loads(match.group(0))
                return self._normalize_extracted_commands(data)
            except json.JSONDecodeError:
                return []

    def _normalize_extracted_commands(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                normalized.append(item)
                continue

            if isinstance(item, str):
                command_name = item.strip()
                if command_name:
                    normalized.append({"command": command_name})
                continue

            if isinstance(item, list) and item and isinstance(item[0], str):
                # Accept compact tuple-like shape from some model outputs,
                # e.g. ["PLAYER_MOVE", {"location_name":"Bridge"}].
                command_name = item[0].strip()
                payload = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
                if command_name:
                    normalized.append({"command": command_name, **payload})

        return normalized
