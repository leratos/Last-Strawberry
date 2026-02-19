from dataclasses import dataclass

from backend_v2.app.models import TurnRequest, TurnResponse


@dataclass(frozen=True)
class MemoryCandidate:
    memory_type: str
    content: str
    importance: float
    source_turn_id: int | None = None


class MemoryWritePolicy:
    def __init__(self, min_importance: float = 0.6):
        self.min_importance = max(0.0, min(1.0, min_importance))

    def build_items(self, request: TurnRequest, response: TurnResponse) -> list[dict]:
        candidates: list[MemoryCandidate] = []

        intent = request.player_command.strip()
        if intent:
            candidates.append(
                MemoryCandidate(
                    memory_type="player_intent",
                    content=f"Player intent: {intent}",
                    importance=0.55,
                )
            )

        for command in response.extracted_commands:
            if not isinstance(command, dict):
                continue
            command_type = str(command.get("command", "")).strip().upper()
            if not command_type:
                continue

            if command_type == "NPC_CREATE":
                npc_name = str(command.get("name", "unknown")).strip() or "unknown"
                candidates.append(
                    MemoryCandidate(
                        memory_type="npc_profile",
                        content=f"NPC introduced: {npc_name}",
                        importance=0.9,
                    )
                )
            elif command_type == "PLAYER_MOVE":
                location_name = str(command.get("location_name", "unknown")).strip() or "unknown"
                candidates.append(
                    MemoryCandidate(
                        memory_type="location_state",
                        content=f"Player moved to: {location_name}",
                        importance=0.8,
                    )
                )
            elif command_type == "ROLL_CHECK":
                attribute = str(command.get("attribut", "unknown")).strip() or "unknown"
                candidates.append(
                    MemoryCandidate(
                        memory_type="challenge",
                        content=f"Check requested on attribute: {attribute}",
                        importance=0.65,
                    )
                )

        narrative = response.narrative.strip()
        if narrative:
            summary = narrative[:220]
            candidates.append(
                MemoryCandidate(
                    memory_type="story_beat",
                    content=f"Story beat: {summary}",
                    importance=0.6,
                )
            )

        results: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            if candidate.importance < self.min_importance:
                continue
            key = (candidate.memory_type, candidate.content)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "memory_type": candidate.memory_type,
                    "content": candidate.content,
                    "importance": candidate.importance,
                    "source_turn_id": candidate.source_turn_id,
                }
            )
        return results
