from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ls_shared_schemas.turns import TurnSystemEvent


@dataclass(frozen=True)
class SkillCheckSpec:
    check_id: str
    attribute: str
    label: str
    dc: int
    mode: str = "deterministic"


@dataclass(frozen=True)
class SkillCheckResult:
    check_id: str
    attribute: str
    label: str
    attribute_score: int
    modifier: int
    dc: int
    roll: int
    total: int
    success: bool
    mode: str


def attribute_modifier(attribute_score: int) -> int:
    return (int(attribute_score) - 10) // 2


def deterministic_d20_roll(*parts: str) -> int:
    seed = "|".join(parts).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(seed).digest()
    return (digest[0] % 20) + 1


def run_deterministic_skill_check(
    *,
    spec: SkillCheckSpec,
    attribute_score: int,
    seed_parts: tuple[str, ...],
) -> SkillCheckResult:
    roll = deterministic_d20_roll(*seed_parts)
    modifier = attribute_modifier(attribute_score)
    total = roll + modifier
    return SkillCheckResult(
        check_id=spec.check_id,
        attribute=spec.attribute,
        label=spec.label,
        attribute_score=int(attribute_score),
        modifier=modifier,
        dc=int(spec.dc),
        roll=roll,
        total=total,
        success=total >= int(spec.dc),
        mode=spec.mode,
    )


def build_skill_check_system_event(
    *,
    event_code: str,
    topic_id: str,
    target_name: str,
    result: SkillCheckResult,
) -> TurnSystemEvent:
    outcome_label = "Erfolg" if result.success else "Misserfolg"
    modifier_sign = "+" if result.modifier >= 0 else "-"
    return TurnSystemEvent(
        code=event_code,
        message=(
            f"Probe {result.label} ({result.attribute} {result.attribute_score} / Mod "
            f"{modifier_sign}{abs(result.modifier)}) -> {outcome_label}: W20 {result.roll} "
            f"{modifier_sign} {abs(result.modifier)} = {result.total} gegen DC {result.dc}."
        ),
        severity="info" if result.success else "warning",
        metadata={
            "topic_id": topic_id,
            "target_name": target_name,
            "check_id": result.check_id,
            "check_label": result.label,
            "check_attribute": result.attribute,
            "attribute_score": result.attribute_score,
            "modifier": result.modifier,
            "roll": result.roll,
            "total": result.total,
            "dc": result.dc,
            "success": result.success,
            "mode": result.mode,
        },
    )
