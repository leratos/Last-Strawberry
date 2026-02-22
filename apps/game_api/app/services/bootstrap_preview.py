from __future__ import annotations

from ls_shared_schemas.character import CharacterAttributes, CharacterTemplateSeed, WorldCharacterSeed
from ls_shared_schemas.inventory import InventoryItemInstance, ItemEffect, ItemUseMode
from ls_shared_schemas.npc_memory import NPCProfile
from ls_shared_schemas.world import WorldBootstrapRequest, WorldBootstrapResult, WorldSeed


def build_world_bootstrap_preview(request: WorldBootstrapRequest) -> WorldBootstrapResult:
    template = CharacterTemplateSeed(
        template_name="Template aus Beschreibung",
        archetype="wanderer",
        background=request.character_description[:400],
        attributes=CharacterAttributes(strength=10, dexterity=11, intelligence=12, charisma=10),
    )
    character_seed = WorldCharacterSeed(
        display_name="Neuer Abenteurer",
        motivation="Die Lage verstehen und erste Verbuendete finden.",
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
            faction="locals",
            location_name="Marktplatz",
            scene_zone_id="zone-market-stalls",
            scene_zone_name="Marktstaende",
            personality_tags=["ruhig", "beobachtend", "hilfsbereit"],
            stats={"trust_seed": 10, "competence": 12},
        )
    ]
    world_seed = WorldSeed(
        world_id="preview-world-seed",
        name="Vorgeschlagene Welt",
        summary=request.world_description[:600],
        start_location_name="Marktplatz",
        start_hook="Ein lokaler Konflikt zwingt dich, schnell Position zu beziehen.",
        factions=["Stadtrat", "Haendlerbund", "Schattennetz"],
        open_threads=["Wer kontrolliert die Schmuggelroute?", "Wem kann man trauen?"],
        starter_npcs=starter_npcs,
        suggested_character_template=template,
        created_character_seed=character_seed,
        starter_inventory=starter_inventory,
    )
    return WorldBootstrapResult(
        world_seed=world_seed,
        initial_narrative=(
            "Du kommst auf dem Marktplatz an, waehrend ein Streit zwischen Haendlern und Stadtwache eskaliert. "
            "Mehrere Blicke richten sich auf dich, als waerst du genau zur richtigen - oder falschen - Zeit erschienen."
        ),
        player_orientation=[
            "Du befindest dich auf dem Marktplatz.",
            "Ein lokaler Konflikt ist bereits im Gange.",
            "Mira (Heilerin) scheint eine moegliche Ansprechpartnerin zu sein.",
        ],
    )
