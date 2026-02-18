import json
import re
from datetime import datetime, UTC
from typing import Any

from backend_v2.app.config import Settings
from backend_v2.app.models import TurnRequest, TurnResponse
from backend_v2.app.providers.base import LLMProvider


class GameOrchestrator:
    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    async def run_turn(self, request: TurnRequest) -> TurnResponse:
        analysis_system, analysis_user = self._build_analysis_prompts(request)
        analysis_text = await self.provider.generate(
            system_prompt=analysis_system,
            user_prompt=analysis_user,
            model=self.settings.analysis_model,
            temperature=self.settings.analysis_temperature,
            max_tokens=self.settings.analysis_max_tokens,
        )
        extracted_commands = self._extract_commands(analysis_text)

        narrative_system, narrative_user = self._build_narrative_prompts(request, extracted_commands)
        narrative_text = await self.provider.generate(
            system_prompt=narrative_system,
            user_prompt=narrative_user,
            model=self.settings.narrative_model,
            temperature=self.settings.narrative_temperature,
            max_tokens=self.settings.narrative_max_tokens,
        )

        return TurnResponse(
            narrative=narrative_text,
            extracted_commands=extracted_commands,
            provider=self.provider.name,
            models={
                "analysis": self.settings.analysis_model,
                "narrative": self.settings.narrative_model,
            },
            created_at=datetime.now(UTC),
        )

    def _build_analysis_prompts(self, request: TurnRequest) -> tuple[str, str]:
        system_prompt = (
            "You are a strict game command extractor. "
            "Return only a JSON array. No markdown, no explanation."
        )
        user_prompt = (
            f"Player: {request.player_name}\n"
            f"NPC context: {request.npc_context}\n"
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
        system_prompt = (
            "You are a creative game master for a text RPG. "
            "Write immersive German narrative text. Do not emit system tags."
        )
        user_prompt = (
            f"World: {request.world_name}\n"
            f"Player: {request.player_name}\n"
            f"Recent events:\n{history_block}\n\n"
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
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", raw_text)
            if not match:
                return []
            try:
                data = json.loads(match.group(0))
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []
