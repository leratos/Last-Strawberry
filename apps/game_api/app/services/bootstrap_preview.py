from __future__ import annotations

from ls_shared_schemas.character import CharacterAttributes, CharacterTemplateSeed, WorldCharacterSeed
from ls_shared_schemas.inventory import InventoryItemInstance, ItemEffect, ItemUseMode
from ls_shared_schemas.npc_memory import NPCProfile
from ls_shared_schemas.world import WorldBootstrapRequest, WorldBootstrapResult, WorldSeed

from apps.game_api.app.services.urban_occult_basis import (
    get_urban_occult_preset,
    should_use_urban_occult_preset,
)


def build_world_bootstrap_preview(request: WorldBootstrapRequest) -> WorldBootstrapResult:
    use_urban_occult = should_use_urban_occult_preset(request.world_description, request.character_description, request.tone)
    preset = get_urban_occult_preset() if use_urban_occult else None

    template = CharacterTemplateSeed(
        template_name="Template aus Beschreibung",
        archetype="binder_initiate" if use_urban_occult else "wanderer",
        background=request.character_description[:400],
        attributes=CharacterAttributes(strength=10, dexterity=11, intelligence=12, charisma=10),
    )
    character_seed = WorldCharacterSeed(
        display_name="Neuer Abenteurer",
        motivation=(
            "Die Lage verstehen, den Vorfall einordnen und verlaessliche Verbuendete finden."
            if use_urban_occult
            else "Die Lage verstehen und erste Verbuendete finden."
        ),
        template=template,
        starter_location_name="Marktplatz",
    )
    starter_inventory = [
        InventoryItemInstance(
            inventory_item_id="inv-starter-heal-1",
            item_def_id="starter_healing_draught",
            name="Starter-Heiltrank",
            category="consumable",
            description="Ein kleiner Trank zur Wundversorgung.",
            quantity=1,
            use_modes=[ItemUseMode.inspect, ItemUseMode.use, ItemUseMode.consume],
            effects=[ItemEffect(effect_type="heal", stat="hp", amount=4)],
        )
    ]
    starter_npcs = [
        NPCProfile(
            npc_id="npc-market-guide",
            name="Mira",
            role="healer",
            faction="aegis_archiv" if use_urban_occult else "locals",
            location_name="Marktplatz",
            scene_zone_id="zone-market-stalls",
            scene_zone_name="Marktstaende",
            personality_tags=["ruhig", "beobachtend", "hilfsbereit"],
            stats={"trust_seed": 10, "competence": 12},
        )
    ]
    if use_urban_occult:
        starter_npcs.append(
            NPCProfile(
                npc_id="npc-circle-binder",
                name="Kael",
                role="beschwoerer",
                faction="binder_konklave",
                location_name="Marktplatz",
                scene_zone_id="zone-fountain-ring",
                scene_zone_name="Brunnenplatz",
                personality_tags=["kontrolliert", "verschwiegen", "angespannt"],
                stats={"trust_seed": 4, "competence": 14},
            )
        )

    world_name = "Vorgeschlagene Welt"
    start_hook = "Ein lokaler Konflikt zwingt dich, schnell Position zu beziehen."
    factions = ["Stadtrat", "Haendlerbund", "Schattennetz"]
    open_threads = ["Wer kontrolliert die Schmuggelroute?", "Wem kann man trauen?"]
    initial_narrative = (
        "Du kommst auf dem Marktplatz an, waehrend ein Streit zwischen Haendlern und Stadtwache eskaliert. "
        "Mehrere Blicke richten sich auf dich, als waerst du genau zur richtigen - oder falschen - Zeit erschienen."
    )
    player_orientation = [
        "Du befindest dich auf dem Marktplatz.",
        "Ein lokaler Konflikt ist bereits im Gange.",
        "Mira (Heilerin) scheint eine moegliche Ansprechpartnerin zu sein.",
    ]

    if preset is not None:
        world_name = "Vorgeschlagene Welt - Urban Occult"
        start_hook = preset.start_hook
        factions = list(preset.factions)
        open_threads = list(preset.open_threads)
        initial_narrative = preset.initial_narrative
        player_orientation = [
            *preset.player_orientation,
            "Mira (Heilerin) arbeitet fuer das Aegis-Archiv und beobachtet die Lage.",
            "Kael (Binder) koennte mehr ueber das gestoerte Ritual wissen.",
            f"Glossar-Hinweis: {', '.join(preset.glossary_terms)}.",
        ]

    world_seed = WorldSeed(
        world_id="preview-world-seed",
        name=world_name,
        summary=request.world_description[:600],
        start_location_name="Marktplatz",
        start_hook=start_hook,
        factions=factions,
        open_threads=open_threads,
        starter_npcs=starter_npcs,
        suggested_character_template=template,
        created_character_seed=character_seed,
        starter_inventory=starter_inventory,
    )
    return WorldBootstrapResult(
        world_seed=world_seed,
        initial_narrative=initial_narrative,
        player_orientation=player_orientation,
    )
