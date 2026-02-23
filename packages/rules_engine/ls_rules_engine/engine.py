from __future__ import annotations

import json

from ls_shared_schemas.character import CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance, ItemUseMode
from ls_shared_schemas.turns import (
    ActionType,
    ClarifyCandidate,
    ClarifyPayload,
    StateDelta,
    TurnIntent,
    TurnIntentAction,
    TurnResolution,
    TurnSystemEvent,
)


class RulesEngine:
    """Deterministic MVP rules engine.

    This is intentionally small but authoritative:
    - applies structured actions
    - mutates state/inventory deterministically
    - emits state delta + system events
    """

    def resolve(
        self,
        *,
        intent: TurnIntent,
        character_state: CharacterState,
        inventory: list[InventoryItemInstance],
    ) -> TurnResolution:
        state = character_state.model_copy(deep=True)
        items = [item.model_copy(deep=True) for item in inventory]
        applied: list[TurnIntentAction] = []
        rejected: list[TurnIntentAction] = []
        events: list[TurnSystemEvent] = []
        delta = StateDelta()

        for action in intent.actions:
            handled = self._apply_action(action=action, state=state, inventory=items, delta=delta, events=events)
            if handled:
                applied.append(action)
            else:
                rejected.append(action)

        state.updated_at = intent.created_at
        return TurnResolution(
            world_id=intent.world_id,
            world_character_id=intent.world_character_id,
            applied_actions=applied,
            rejected_actions=rejected,
            system_events=events,
            state_delta=delta,
            resulting_character_state=state,
            resulting_inventory=items,
        )

    def _apply_action(
        self,
        *,
        action: TurnIntentAction,
        state: CharacterState,
        inventory: list[InventoryItemInstance],
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        if action.action_type == ActionType.move:
            return self._apply_move(action, state, delta, events)
        if action.action_type == ActionType.approach:
            return self._apply_approach(action, state, delta, events)
        if action.action_type == ActionType.retreat:
            return self._apply_retreat(action, state, delta, events)
        if action.action_type == ActionType.inspect:
            return self._apply_inspect(action, inventory, events)
        if action.action_type == ActionType.open:
            return self._apply_open(action, events)
        if action.action_type == ActionType.search:
            return self._apply_search(action, events)
        if action.action_type == ActionType.take:
            return self._apply_take(action, events)
        if action.action_type == ActionType.talk:
            return self._apply_talk(action, state, delta, events)
        if action.action_type == ActionType.attack:
            return self._apply_attack(action, state, delta, events)
        if action.action_type == ActionType.use_item:
            return self._apply_use_item(action, state, inventory, delta, events)
        if action.action_type == ActionType.skill_check:
            return self._apply_skill_check(action, state, events)
        if action.action_type == ActionType.clarify:
            message = str(action.parameters.get("message") or "").strip() or "Die Eingabe war nicht eindeutig genug. Bitte praezisieren."
            metadata, clarify_payload = self._clarify_event_details(action)
            events.append(
                TurnSystemEvent(
                    code="clarify_required",
                    message=message,
                    severity="warning",
                    metadata=metadata,
                    clarify=clarify_payload,
                )
            )
            return False

        events.append(
            TurnSystemEvent(code="unsupported_action", message=f"Aktion nicht unterstuetzt: {action.action_type}", severity="warning")
        )
        return False

    @staticmethod
    def _clarify_event_details(
        action: TurnIntentAction,
    ) -> tuple[dict[str, str | int | float | bool | None], ClarifyPayload | None]:
        metadata: dict[str, str | int | float | bool | None] = {}
        clarify_candidates: list[ClarifyCandidate] = []
        reason = str(action.parameters.get("reason") or "").strip()
        if reason:
            metadata["reason"] = reason
        suggested_action = str(action.parameters.get("suggested_action") or "").strip()
        if suggested_action:
            metadata["suggested_action"] = suggested_action
        candidates_json = str(action.parameters.get("candidates_json") or "").strip()
        if candidates_json:
            metadata["candidates_json"] = candidates_json
            try:
                parsed = json.loads(candidates_json)
                if isinstance(parsed, list):
                    metadata["candidate_count"] = len(parsed)
                    for entry in parsed:
                        if not isinstance(entry, dict):
                            continue
                        action_type = str(entry.get("action_type") or "").strip()
                        target_ref = str(entry.get("target_ref") or "").strip()
                        if not action_type or not target_ref:
                            continue
                        clarify_candidates.append(
                            ClarifyCandidate(
                                action_type=action_type,
                                target_ref=target_ref,
                                target_kind=str(entry.get("target_kind") or "").strip() or None,
                                label=str(entry.get("label") or "").strip() or None,
                                name=str(entry.get("name") or "").strip() or None,
                                role=str(entry.get("role") or "").strip() or None,
                                kind=str(entry.get("kind") or "").strip() or None,
                            )
                        )
            except json.JSONDecodeError:
                pass
        clarify_payload = None
        if reason or suggested_action or clarify_candidates:
            clarify_payload = ClarifyPayload(
                reason=reason or None,
                suggested_action=suggested_action or None,
                candidates=clarify_candidates,
            )
        return metadata, clarify_payload

    @staticmethod
    def _append_distance_reaction_event(
        *,
        action: TurnIntentAction,
        target_display: str,
        events: list[TurnSystemEvent],
        phase: str,
    ) -> None:
        target_role = str(action.parameters.get("target_role") or "").strip().lower()
        try:
            standing = int(action.parameters.get("target_standing"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        aggressive_roles = {"guard", "soldier", "mercenary", "bandit", "raider", "thug", "warrior", "krieger", "tank"}
        friendly_roles = {"healer", "heiler", "merchant", "haendler", "händler", "innkeeper", "guide", "ally"}
        arcane_roles = {"mage", "magier", "wizard", "sorcerer", "summoner", "beschwoerer", "beschwörer"}

        if standing >= 3:
            style = "friendly"
        elif standing <= -4:
            style = "aggressive"
        elif standing <= -2 and target_role in aggressive_roles:
            style = "aggressive"
        elif standing <= 0:
            style = "cautious"
        elif target_role in friendly_roles:
            style = "friendly"
        else:
            style = "cautious"

        if phase == "approach":
            if style == "aggressive":
                message = f"{target_display} reagiert aggressiv auf deine Annaeherung."
                if target_role in {"tank"}:
                    message = f"{target_display} stemmt sich wie ein Tank gegen deine Annaeherung und wirkt kampfbereit."
                elif target_role in {"warrior", "krieger"}:
                    message = f"{target_display} reagiert aggressiv auf deine Annaeherung und geht in Kampfhaltung."
                elif target_role in {"summoner", "beschwoerer", "beschwörer"}:
                    message = f"{target_display} reagiert aggressiv auf deine Annaeherung; die Beschwoerungszeichen um ihn flackern auf."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_aggressive_to_approach",
                        message=message,
                        severity="warning",
                    )
                )
            elif style == "friendly":
                message = f"{target_display} reagiert freundlich auf deine Annaeherung."
                if target_role in {"healer", "heiler"}:
                    message = f"{target_display} reagiert freundlich auf deine Annaeherung und beobachtet dich aufmerksam wie ein Heiler."
                elif target_role in {"merchant", "haendler", "händler"}:
                    message = f"{target_display} reagiert freundlich auf deine Annaeherung und taxiert dich wie ein erfahrener Haendler."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_friendly_to_approach",
                        message=message,
                        severity="info",
                    )
                )
            else:
                message = f"{target_display} reagiert vorsichtig auf deine Annaeherung."
                if target_role in {"warrior", "krieger", "tank"}:
                    message = f"{target_display} reagiert vorsichtig auf deine Annaeherung und mustert deine Bewegungen."
                elif target_role in arcane_roles:
                    message = f"{target_display} reagiert vorsichtig auf deine Annaeherung und beobachtet dich mit arkaner Wachsamkeit."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_cautious_to_approach",
                        message=message,
                        severity="info",
                    )
                )
            return

        if phase == "retreat":
            if style == "aggressive":
                message = f"{target_display} beobachtet deinen Rueckzug aggressiv."
                if target_role in {"tank"}:
                    message = f"{target_display} haelt die Front wie ein Tank und verfolgt deinen Rueckzug mit Druck."
                elif target_role in {"warrior", "krieger"}:
                    message = f"{target_display} verfolgt deinen Rueckzug mit aggressiver Kampfbereitschaft."
                elif target_role in {"summoner", "beschwoerer", "beschwörer"}:
                    message = f"{target_display} verfolgt deinen Rueckzug aggressiv, waehrend Beschwoerungsenergie um ihn knistert."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_aggressive_to_retreat",
                        message=message,
                        severity="warning",
                    )
                )
            elif style == "friendly":
                message = f"{target_display} laesst dir freundlich Raum."
                if target_role in {"healer", "heiler"}:
                    message = f"{target_display} laesst dir freundlich Raum und senkt sichtbar die Anspannung."
                elif target_role in {"merchant", "haendler", "händler"}:
                    message = f"{target_display} laesst dir freundlich Raum und behaelt dabei wachsam den Warenstand im Blick."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_friendly_to_retreat",
                        message=message,
                        severity="info",
                    )
                )
            else:
                message = f"{target_display} haelt vorsichtig Distanz, waehrend du dich zurueckziehst."
                if target_role in arcane_roles:
                    message = f"{target_display} haelt vorsichtig Distanz, waehrend arkane Energie um ihn kreist."
                events.append(
                    TurnSystemEvent(
                        code="npc_reacts_cautious_to_retreat",
                        message=message,
                        severity="info",
                    )
                )

    def _apply_move(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        destination = (action.destination or action.target_ref or "").strip()
        if not destination:
            events.append(TurnSystemEvent(code="move_missing_destination", message="Kein Ziel fuer Bewegung angegeben.", severity="warning"))
            return False
        state.location_name = destination
        state.scene_zone_id = "zone-center"
        state.scene_zone_name = "Zentrum"
        delta.location_changed_to = destination
        delta.scene_zone_changed_to_id = state.scene_zone_id
        delta.scene_zone_changed_to_name = state.scene_zone_name
        events.append(TurnSystemEvent(code="move_success", message=f"Bewegung nach {destination}."))
        return True

    def _apply_inspect(
        self,
        action: TurnIntentAction,
        inventory: list[InventoryItemInstance],
        events: list[TurnSystemEvent],
    ) -> bool:
        target = (action.item_ref or action.target_ref or "").strip()
        if not target:
            events.append(TurnSystemEvent(code="inspect_success", message="Umgebung aufmerksam untersucht."))
            return True
        item = self._find_item(inventory, target)
        if item is None:
            target_name = str(action.parameters.get("target_name") or target).strip()
            target_kind = str(action.target_kind or action.parameters.get("target_kind") or "").strip().lower()
            if target_kind and target_kind != "item":
                events.append(
                    TurnSystemEvent(
                        code="inspect_focus_success",
                        message=f"Du untersuchst {target_name} genauer.",
                    )
                )
                return True
            events.append(
                TurnSystemEvent(code="inspect_item_missing", message=f"Item nicht gefunden: {target}", severity="warning")
            )
            return False
        events.append(TurnSystemEvent(code="inspect_item_success", message=f"{item.name} untersucht."))
        return True

    def _apply_open(self, action: TurnIntentAction, events: list[TurnSystemEvent]) -> bool:
        target_name = str(action.parameters.get("target_name") or action.target_ref or "Objekt").strip()
        target_kind = str(action.parameters.get("target_kind") or action.target_kind or "").strip().lower()
        if target_kind in {"container", "scene_object", "scene_point"}:
            events.append(TurnSystemEvent(code="open_focus_success", message=f"Du oeffnest {target_name}."))
            return True
        events.append(TurnSystemEvent(code="open_target_invalid", message="Dieses Ziel kann nicht geoeffnet werden.", severity="warning"))
        return False

    def _apply_search(self, action: TurnIntentAction, events: list[TurnSystemEvent]) -> bool:
        target_name = str(action.parameters.get("target_name") or action.target_ref or "Bereich").strip()
        target_kind = str(action.parameters.get("target_kind") or action.target_kind or "").strip().lower()
        if target_kind in {"container", "scene_object", "scene_point"}:
            events.append(TurnSystemEvent(code="search_focus_success", message=f"Du durchsuchst {target_name}."))
            return True
        events.append(
            TurnSystemEvent(
                code="search_target_invalid",
                message="Dieses Ziel kann nicht durchsucht werden.",
                severity="warning",
            )
        )
        return False

    def _apply_take(self, action: TurnIntentAction, events: list[TurnSystemEvent]) -> bool:
        target_name = str(action.parameters.get("target_name") or action.target_ref or "Objekt").strip()
        target_kind = str(action.parameters.get("target_kind") or action.target_kind or "").strip().lower()
        if target_kind in {"scene_object", "container"}:
            events.append(TurnSystemEvent(code="take_focus_success", message=f"Du nimmst {target_name} an dich."))
            return True
        events.append(
            TurnSystemEvent(
                code="take_target_invalid",
                message="Dieses Ziel kann nicht aufgenommen werden.",
                severity="warning",
            )
        )
        return False

    def _apply_approach(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        target_name = str(action.parameters.get("target_name") or "").strip()
        target_display = target_name or (action.target_ref or "Ziel").strip()
        target_distance_band = str(action.parameters.get("target_distance_band") or "").strip().lower()
        target_zone_id = str(action.parameters.get("target_zone_id") or "").strip()
        target_zone_name = str(action.parameters.get("target_zone_name") or "").strip()
        target_location_name = str(action.parameters.get("target_location_name") or "").strip()

        if target_distance_band == "adjacent":
            events.append(
                TurnSystemEvent(
                    code="approach_not_needed",
                    message=f"Du bist bereits direkt bei {target_display}.",
                )
            )
            return True

        if target_location_name and target_location_name != state.location_name:
            state.location_name = target_location_name
            delta.location_changed_to = target_location_name
            events.append(
                TurnSystemEvent(
                    code="auto_move_location_for_approach",
                    message=f"Du bewegst dich zu {target_location_name}, um {target_display} naeherzukommen.",
                )
            )

        if target_distance_band == "far":
            state.scene_zone_id = "zone-distance-near"
            state.scene_zone_name = f"Naeher an {target_display}"
        elif target_distance_band in {"near", "unreachable"} and target_zone_id:
            state.scene_zone_id = target_zone_id
            state.scene_zone_name = target_zone_name or f"Bei {target_display}"
        elif target_distance_band in {"near", "unreachable"}:
            state.scene_zone_id = "zone-distance-near"
            state.scene_zone_name = f"Naeher an {target_display}"
        else:
            state.scene_zone_id = "zone-distance-near"
            state.scene_zone_name = f"Naeher an {target_display}"

        delta.scene_zone_changed_to_id = state.scene_zone_id
        delta.scene_zone_changed_to_name = state.scene_zone_name
        events.append(TurnSystemEvent(code="approach_success", message=f"Du naeherst dich {target_display} an."))
        self._append_distance_reaction_event(action=action, target_display=target_display, events=events, phase="approach")
        return True

    def _apply_retreat(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        target_id = str(action.parameters.get("target_id") or "").strip() or None
        target_name = str(action.parameters.get("target_name") or "").strip()
        target_display = target_name or (action.target_ref or "Bedrohung").strip()
        target_distance_band = str(action.parameters.get("target_distance_band") or "").strip().lower()
        target_zone_id = str(action.parameters.get("target_zone_id") or "").strip()
        target_zone_name = str(action.parameters.get("target_zone_name") or "").strip()

        if target_distance_band in {"far", "unreachable"}:
            events.append(
                TurnSystemEvent(
                    code="retreat_not_needed",
                    message=f"Zu {target_display} besteht bereits ausreichend Abstand.",
                )
            )
            return True

        if target_distance_band == "near":
            state.scene_zone_id = "zone-distance-far"
            state.scene_zone_name = f"Weit weg von {target_display}"
        elif target_zone_id and (state.scene_zone_id or "").strip() == target_zone_id:
            state.scene_zone_id = "zone-distance-near"
            state.scene_zone_name = f"Abstand zu {target_display}"
        else:
            state.scene_zone_id = "zone-distance-near"
            state.scene_zone_name = "Rueckzugsposition"

        delta.scene_zone_changed_to_id = state.scene_zone_id
        delta.scene_zone_changed_to_name = state.scene_zone_name

        message = f"Du gewinnst Abstand zu {target_display}."
        if target_zone_name:
            message = f"Du weichst von {target_display} zurueck ({state.scene_zone_name})."
        events.append(TurnSystemEvent(code="retreat_success", message=message))
        self._append_distance_reaction_event(action=action, target_display=target_display, events=events, phase="retreat")
        return True

    def _apply_talk(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        target_id = str(action.parameters.get("target_id") or "").strip() or None
        target_name = str(action.parameters.get("target_name") or "").strip()
        target_display = target_name or (action.target_ref or "NPC").strip()
        target_distance_band = str(action.parameters.get("target_distance_band") or "").strip().lower()
        target_zone_id = str(action.parameters.get("target_zone_id") or "").strip()
        target_zone_name = str(action.parameters.get("target_zone_name") or "").strip()
        target_location_name = str(action.parameters.get("target_location_name") or "").strip()

        if target_location_name and target_location_name != state.location_name:
            state.location_name = target_location_name
            delta.location_changed_to = target_location_name
            events.append(
                TurnSystemEvent(
                    code="auto_move_location_for_talk",
                    message=f"Automatisch zu {target_location_name} bewegt, um {target_display} zu erreichen.",
                )
            )

        if target_distance_band in {"near", "far", "unreachable"} and target_zone_id:
            state.scene_zone_id = target_zone_id
            if target_zone_name:
                state.scene_zone_name = target_zone_name
            delta.scene_zone_changed_to_id = target_zone_id
            if target_zone_name:
                delta.scene_zone_changed_to_name = target_zone_name
            events.append(
                TurnSystemEvent(
                    code="auto_approach_for_talk",
                    message=f"Du naeherst dich {target_display} an ({target_zone_name or target_zone_id}).",
                )
            )
        relationship_change = {"npc": target_display, "standing_delta": 1}
        if target_id:
            relationship_change["npc_id"] = target_id
        delta.relationship_changes.append(relationship_change)
        events.append(TurnSystemEvent(code="talk_success", message=f"Gespraech mit {target_display} gefuehrt."))
        return True

    def _apply_attack(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        target_id = str(action.parameters.get("target_id") or "").strip() or None
        target_name = str(action.parameters.get("target_name") or "").strip()
        target = target_name or (action.target_ref or "Ziel").strip()
        attack_mode = str(action.parameters.get("attack_mode") or "melee").strip().lower()
        if attack_mode not in {"melee", "ranged"}:
            attack_mode = "melee"
        target_distance_band = str(action.parameters.get("target_distance_band") or "").strip().lower()
        target_zone_id = str(action.parameters.get("target_zone_id") or "").strip()
        target_zone_name = str(action.parameters.get("target_zone_name") or "").strip()
        target_location_name = str(action.parameters.get("target_location_name") or "").strip()

        if attack_mode == "melee":
            if target_location_name and target_location_name != state.location_name:
                state.location_name = target_location_name
                delta.location_changed_to = target_location_name
                events.append(
                    TurnSystemEvent(
                        code="auto_move_location_for_attack",
                        message=f"Automatisch zu {target_location_name} bewegt, um {target} zu erreichen.",
                    )
                )

            if target_distance_band in {"near", "far", "unreachable"}:
                if target_zone_id:
                    current_zone_id = (state.scene_zone_id or "").strip()
                    if current_zone_id != target_zone_id:
                        state.scene_zone_id = target_zone_id
                        if target_zone_name:
                            state.scene_zone_name = target_zone_name
                        delta.scene_zone_changed_to_id = target_zone_id
                        if target_zone_name:
                            delta.scene_zone_changed_to_name = target_zone_name
                        events.append(
                            TurnSystemEvent(
                                code="auto_approach_for_attack",
                                message=f"Du naeherst dich {target} an ({target_zone_name or target_zone_id}).",
                            )
                        )
                else:
                    events.append(
                        TurnSystemEvent(
                            code="attack_out_of_range",
                            message=f"{target} ist ausser Reichweite fuer einen Nahkampfangriff.",
                            severity="warning",
                        )
                    )
                    return False
        elif attack_mode == "ranged":
            if target_distance_band == "unreachable":
                events.append(
                    TurnSystemEvent(
                        code="ranged_attack_out_of_range",
                        message=f"{target} ist ausser Reichweite fuer einen Fernkampfangriff.",
                        severity="warning",
                    )
                )
                return False

        base_damage = max(1, int(state.attributes.strength / 3))
        stamina_cost = 1
        if state.resources.stamina < stamina_cost:
            events.append(TurnSystemEvent(code="attack_no_stamina", message="Nicht genug Ausdauer fuer Angriff.", severity="warning"))
            return False
        state.resources.stamina = max(0, state.resources.stamina - stamina_cost)
        delta.stamina_delta -= stamina_cost
        relationship_change = {"npc": target, "standing_delta": -5}
        if target_id:
            relationship_change["npc_id"] = target_id
        delta.relationship_changes.append(relationship_change)
        events.append(
            TurnSystemEvent(
                code="attack_resolved",
                message=(
                    f"{'Fernkampf' if attack_mode == 'ranged' else 'Nahkampf'} gegen {target} ausgefuehrt "
                    f"(MVP-Schaden: {base_damage})."
                ),
            )
        )
        return True

    def _apply_use_item(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        inventory: list[InventoryItemInstance],
        delta: StateDelta,
        events: list[TurnSystemEvent],
    ) -> bool:
        target_ref = (action.item_ref or action.target_ref or "").strip()
        if not target_ref:
            events.append(TurnSystemEvent(code="use_item_missing_ref", message="Kein Item fuer Benutzung angegeben.", severity="warning"))
            return False

        item = self._find_item(inventory, target_ref)
        if item is None or item.quantity <= 0:
            events.append(TurnSystemEvent(code="use_item_not_found", message=f"Item nicht verfuegbar: {target_ref}", severity="warning"))
            return False

        if not any(mode in item.use_modes for mode in (ItemUseMode.use, ItemUseMode.consume, ItemUseMode.equip)):
            events.append(TurnSystemEvent(code="use_item_not_usable", message=f"{item.name} ist nicht benutzbar.", severity="warning"))
            return False

        hp_heal = 0
        for effect in item.effects:
            if effect.effect_type == "heal" and (effect.stat or "hp") == "hp":
                hp_heal += int(effect.amount or 0)

        if hp_heal > 0:
            new_hp = min(state.resources.max_hp, state.resources.hp + hp_heal)
            actual_delta = new_hp - state.resources.hp
            state.resources.hp = new_hp
            delta.hp_delta += actual_delta
            events.append(TurnSystemEvent(code="item_heal_applied", message=f"{item.name} stellt {actual_delta} HP wieder her."))
        else:
            events.append(TurnSystemEvent(code="item_used", message=f"{item.name} wurde verwendet."))

        if item.quantity > 0 and (ItemUseMode.consume in item.use_modes or ItemUseMode.use in item.use_modes):
            item.quantity -= 1
            delta.inventory_consumed.append({"item_id": item.inventory_item_id, "name": item.name, "quantity": 1})

        return True

    def _apply_skill_check(
        self,
        action: TurnIntentAction,
        state: CharacterState,
        events: list[TurnSystemEvent],
    ) -> bool:
        skill = str(action.parameters.get("skill") or "general")
        difficulty = int(action.parameters.get("dc") or 10)
        score = int(state.attributes.intelligence / 2) + 5
        success = score >= difficulty
        events.append(
            TurnSystemEvent(
                code="skill_check_success" if success else "skill_check_fail",
                message=f"Skill-Check ({skill}) {'bestanden' if success else 'fehlgeschlagen'} (score={score}, dc={difficulty}).",
                severity="info" if success else "warning",
            )
        )
        return success

    @staticmethod
    def _find_item(inventory: list[InventoryItemInstance], ref: str) -> InventoryItemInstance | None:
        needle = ref.strip().lower()
        for item in inventory:
            if item.inventory_item_id.lower() == needle or item.item_def_id.lower() == needle or item.name.lower() == needle:
                return item
        return None
