from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class UrbanOccultPreset:
    preset_id: str
    display_name: str
    factions: tuple[str, ...]
    open_threads: tuple[str, ...]
    start_hook: str
    initial_narrative: str
    player_orientation: tuple[str, ...]
    glossary_terms: tuple[str, ...]


URBAN_OCCULT_BINDER_CHAMPION_PRESET = UrbanOccultPreset(
    preset_id="urban_occult_binder_champion_v1",
    display_name="Urban Occult - Binder/Champion Conflict",
    factions=(
        "Binder-Konklave",
        "Aegis-Archiv",
        "Nachtgericht",
    ),
    open_threads=(
        "Wer bricht den Geheimhaltungskodex in der Stadt?",
        "Welcher Binder bereitet ein illegales Champion-Ritual vor?",
        "Welche Fraktion kontrolliert die Reliktlieferungen?",
    ),
    start_hook=(
        "Ein verdecktes Ritual geraet aus dem Takt, und mehrere Fraktionen versuchen gleichzeitig, "
        "den Vorfall zu vertuschen oder auszunutzen."
    ),
    initial_narrative=(
        "Du erreichst den Marktplatz von Fuyora, als ein Stromausfall Teile des Viertels lahmlegt. "
        "Zwischen flackernden Lampen und hektischen Passanten registrierst du Spuren eines "
        "fehlgeschlagenen Binder-Rituals. Mehrere Beobachter mustern dich, als haetten sie auf "
        "genau diesen Moment gewartet."
    ),
    player_orientation=(
        "Die Stadt wirkt modern, doch im Verborgenen operieren Binder, Champions und Reliktjaeger.",
        "Magische Zwischenfaelle muessen vor der Oeffentlichkeit verborgen bleiben.",
        "Fraktionen beobachten den Vorfall bereits und suchen Verbuendete.",
    ),
    glossary_terms=(
        "Binder",
        "Champion",
        "Relikt",
        "Siegelkreis",
        "Geheimhaltungskodex",
    ),
)


ROLE_ALIASES_BY_CANONICAL: dict[str, tuple[str, ...]] = {
    "heiler": ("heiler", "heilerin", "healer", "medicus"),
    "krieger": ("krieger", "warrior", "fighter", "schwertkaempfer", "schwertkämpfer"),
    "tank": ("tank", "guardian", "vanguard", "schildtraeger", "schildträger"),
    "haendler": ("haendler", "händler", "merchant", "trader", "kaufmann", "verkaeufer"),
    "magier": ("magier", "mage", "wizard", "zauberer", "hexer"),
    "beschwoerer": ("beschwoerer", "beschwörer", "summoner", "conjurer", "binder"),
    "wache": ("wache", "guard", "waechter", "wächter", "executor"),
    "priester": ("priester", "priest", "exorzist", "exorcist"),
    "ritter": ("ritter", "knight"),
}

ROLE_CANONICAL_BY_ALIAS: dict[str, str] = {}
for canonical_role, aliases in ROLE_ALIASES_BY_CANONICAL.items():
    for alias in aliases:
        ROLE_CANONICAL_BY_ALIAS[alias] = canonical_role


_URBAN_OCCULT_KEYWORDS = (
    "magie",
    "magier",
    "ritual",
    "beschwoer",
    "beschwör",
    "geheimhaltung",
    "fraktion",
    "kirche",
    "relikt",
    "gral",
    "champion",
    "binder",
    "mana",
)

_ROLE_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_äöüÄÖÜß]+")
_LEADING_ARTICLE_PATTERN = re.compile(
    r"^(der|die|das|dem|den|des|ein|eine|einer|einem|einen)\s+",
    flags=re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value or "").strip()


def _ascii_fold(value: str) -> str:
    normalized = _normalize_text(value).lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    return normalized


def should_use_urban_occult_preset(*texts: str) -> bool:
    haystack = " ".join(_ascii_fold(text) for text in texts if text)
    return any(keyword in haystack for keyword in _URBAN_OCCULT_KEYWORDS)


def get_urban_occult_preset() -> UrbanOccultPreset:
    return URBAN_OCCULT_BINDER_CHAMPION_PRESET


def infer_canonical_role_from_text(text: str) -> str | None:
    candidate = _normalize_text(text)
    if not candidate:
        return None

    candidate = _LEADING_ARTICLE_PATTERN.sub("", candidate)
    folded = _ascii_fold(candidate)

    if folded in ROLE_CANONICAL_BY_ALIAS:
        return ROLE_CANONICAL_BY_ALIAS[folded]

    for token in _ROLE_TOKEN_PATTERN.findall(folded):
        if token in ROLE_CANONICAL_BY_ALIAS:
            return ROLE_CANONICAL_BY_ALIAS[token]

    return None

