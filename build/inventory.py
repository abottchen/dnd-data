"""Load and shape the upstream inventory snapshot for the renderer.

Mirrors the dice-data integration: the latest obr-inv-backup-*.json under
data/ is read, upstream player names are resolved through the existing
build/dice-players.json substring map (so real surnames never reach the
template), items are classified into three Pack-section zones (Rack,
Spotlight, Manifest), totals are computed against 15×STR carrying
capacity, and 16 archetypes are scored to pick one badge per character.

This module is render-only. The single place a model contributes is the
tooltip inscription on each archetype badge — that's authored elsewhere
(refresh-archetype-inscription transformer + characters.json) and read
back at render time.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from build.render import _resolve_dice_player


def load(repo_root: Path) -> dict:
    """Return an inventory bundle keyed for the renderer.

    Shape:
      {
        "by_id": {"<slug>": CharacterInventory, ...},
        "company_strip": [StripEntry, ...],
      }

    Empty bundle if no snapshot file is present — the renderer treats
    this as "every character awaiting manifest" rather than failing.
    """
    return {"by_id": {}, "company_strip": []}


SNAPSHOT_GLOB = "obr-inv-backup-*.json"


def _resolve_snapshot_path(data_dir: Path) -> Optional[Path]:
    """Pick the lexicographically maximal matching file. The upstream
    timestamp format (ISO with T-separator and Z suffix) sorts as text
    in the same order as time, so a string max equals the time max."""
    matches = sorted(data_dir.glob(SNAPSHOT_GLOB))
    return matches[-1] if matches else None


def _parse_inventories(raw: dict, mapping: dict[str, str]) -> dict[str, dict]:
    """Resolve each inventory's upstream `name` to a site slug, drop GM,
    discard the upstream name (which can carry real surnames), and return
    a slug-keyed dict of {items: [...]} payloads.

    Items are passed through verbatim; classification happens later. Null
    weights are kept as null here and normalized to 0 inside the totals
    step — keeping null lets later inspection see that the data was null
    upstream rather than zero by intent.
    """
    out: dict[str, dict] = {}
    for inv in raw.get("inventories", {}).values():
        name = inv.get("name", "")
        if name == "GM":
            continue
        slug = _resolve_dice_player(name, mapping)
        if slug is None:
            continue
        out[slug] = {"items": list(inv.get("items", []))}
    return out


RACK_CATEGORIES = frozenset({"Weapon", "Armor", "Ammunition"})
SPOTLIGHT_CATEGORIES = frozenset({"Wondrous Item", "Spellcasting Focus"})
SPOTLIGHT_CAP = 3

_RARITY_ORDER = {
    "legendary": 0, "very rare": 1, "rare": 2, "uncommon": 3,
    "common": 4,
}


def _classify(items: list[dict]) -> tuple[list, list, list]:
    """Partition items into (rack, spotlight, manifest) zones.

    Rack: weapons, armor, ammunition.
    Spotlight: items with rarity != "common" OR a wondrous/focus category.
      Capped at SPOTLIGHT_CAP, ranked by rarity (legendary first), with
      spillover landing in Manifest.
    Manifest: everything else (and spotlight spillover).
    """
    rack: list[dict] = []
    candidates_for_spotlight: list[dict] = []
    rest: list[dict] = []

    for it in items:
        cat = it.get("category", "")
        rarity = (it.get("rarity") or "common").lower()
        if cat in RACK_CATEGORIES:
            rack.append(it)
        elif cat in SPOTLIGHT_CATEGORIES or rarity != "common":
            candidates_for_spotlight.append(it)
        else:
            rest.append(it)

    candidates_for_spotlight.sort(
        key=lambda it: _RARITY_ORDER.get((it.get("rarity") or "common").lower(), 99)
    )
    spotlight = candidates_for_spotlight[:SPOTLIGHT_CAP]
    spillover = candidates_for_spotlight[SPOTLIGHT_CAP:]

    return rack, spotlight, rest + spillover


def _total_weight(items: list[dict]) -> float:
    """Sum of weight×count, treating null weight as 0."""
    total = 0.0
    for it in items:
        w = it.get("weight")
        if w is None:
            w = 0
        c = it.get("count") or 1
        total += w * c
    return total


def _carrying_capacity(member: dict) -> int:
    """5e 2024 carrying capacity (15 × STR), in pounds."""
    return 15 * int(member.get("abilities", {}).get("str", 0))


def _zone_breakdown(rack: list, spotlight: list, manifest: list) -> dict[str, float]:
    return {
        "rack": _total_weight(rack),
        "spotlight": _total_weight(spotlight),
        "manifest": _total_weight(manifest),
    }


# --- Archetype scoring ------------------------------------------------------
# Each scorer takes (items, member) and returns a numeric score. Higher is
# stronger except for Featherfoot, which is scored separately because it
# needs the carrying capacity from `member`.

def _name_lower(it: dict) -> str:
    return (it.get("name") or "").lower()


def _matches_any(it: dict, keywords: tuple[str, ...]) -> bool:
    name = _name_lower(it)
    return any(kw in name for kw in keywords)


def _sum_count_where(items: list[dict], predicate) -> int:
    return sum((it.get("count") or 1) for it in items if predicate(it))


def score_pack_mule(items: list[dict], member: dict) -> float:
    return _total_weight(items)


def score_armorer(items: list[dict], member: dict) -> float:
    return sum(
        (it.get("weight") or 0) * (it.get("count") or 1)
        for it in items
        if it.get("category") in ("Weapon", "Armor")
    )


def score_glaive_hand(items: list[dict], member: dict) -> int:
    return len({it["id"] for it in items if it.get("category") == "Weapon"})


def score_quiver(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: it.get("category") == "Ammunition")


def score_curio_keeper(items: list[dict], member: dict) -> int:
    def is_curio(it: dict) -> bool:
        rarity = (it.get("rarity") or "common").lower()
        return rarity != "common" or it.get("category") == "Wondrous Item"
    return _sum_count_where(items, is_curio)


_SCHOLAR_KW = ("book", "parchment", "ink", "scroll", "spellbook")
_NATURALIST_KW = ("druidic", "mistletoe", "yew", "totem", "natural")
_TONGUES_KW = ("sending stone", "message", "speaking", "whisper")


def score_scholar(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _SCHOLAR_KW))


def score_naturalist(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _NATURALIST_KW))


def score_tongues(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _TONGUES_KW))


_LAMPLIGHTER_KW = ("oil", "torch", "lantern", "candle", "tinderbox", "lamp")
_PATHFINDER_KW = ("rope", "crowbar", "grapple", "piton", "spike", "climber")
_CELLARER_KW = ("ration", "waterskin", "mess kit", "trail", "wineskin")
_TRAPPER_KW = ("caltrop", "trap", "snare", "hunter's trap")
_COSTUME_KW = ("costume", "disguise", "perfume", "fine clothes", "noble")


def score_lamplighter(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _LAMPLIGHTER_KW))


def score_pathfinder(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _PATHFINDER_KW))


def score_apothecary(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: it.get("category") == "Consumable")


def score_cellarer(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _CELLARER_KW))


def score_trapper(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _TRAPPER_KW))


def score_costume_master(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _COSTUME_KW))


def score_quartermaster(items: list[dict], member: dict) -> int:
    return len({it["id"] for it in items})


def score_featherfoot(items: list[dict], member: dict) -> float:
    """Inverted carry-ratio utilization. Higher = more decisively unburdened.

    Score = 100 - utilization%, where utilization = total / capacity * 100.
    A character with no capacity (STR 0) is unscorable — return 0.
    """
    cap = _carrying_capacity(member)
    if cap <= 0:
        return 0.0
    weight = _total_weight(items)
    util_pct = weight / cap * 100
    return 100.0 - util_pct


# Listed in priority order — used as the tiebreaker when a character has two
# archetype wins with equal lead. Pack-Mule resolves before Armorer, etc.
ARCHETYPE_SLATE: tuple[dict, ...] = (
    {"slug": "pack-mule",       "label": "THE PACK-MULE",       "score": score_pack_mule,       "min_lead": 0},
    {"slug": "armorer",         "label": "THE ARMORER",         "score": score_armorer,         "min_lead": 0},
    {"slug": "glaive-hand",     "label": "THE GLAIVE-HAND",     "score": score_glaive_hand,     "min_lead": 0},
    {"slug": "quiver",          "label": "THE QUIVER",          "score": score_quiver,          "min_lead": 0},
    {"slug": "curio-keeper",    "label": "THE CURIO-KEEPER",    "score": score_curio_keeper,    "min_lead": 0},
    {"slug": "naturalist",      "label": "THE NATURALIST",      "score": score_naturalist,      "min_lead": 0},
    {"slug": "scholar",         "label": "THE SCHOLAR",         "score": score_scholar,         "min_lead": 0},
    {"slug": "tongues",         "label": "THE TONGUES",         "score": score_tongues,         "min_lead": 0},
    {"slug": "lamplighter",     "label": "THE LAMPLIGHTER",     "score": score_lamplighter,     "min_lead": 0},
    {"slug": "pathfinder",      "label": "THE PATHFINDER",      "score": score_pathfinder,      "min_lead": 0},
    {"slug": "apothecary",      "label": "THE APOTHECARY",      "score": score_apothecary,      "min_lead": 0},
    {"slug": "cellarer",        "label": "THE CELLARER",        "score": score_cellarer,        "min_lead": 0},
    {"slug": "trapper",         "label": "THE TRAPPER",         "score": score_trapper,         "min_lead": 0},
    {"slug": "costume-master",  "label": "THE COSTUME-MASTER",  "score": score_costume_master,  "min_lead": 0},
    {"slug": "quartermaster",   "label": "THE QUARTERMASTER",   "score": score_quartermaster,   "min_lead": 0},
    # Featherfoot needs a meaningful gap to feel earned (5 percentage-point
    # difference in inverted utilization).
    {"slug": "featherfoot",     "label": "THE FEATHERFOOT",     "score": score_featherfoot,     "min_lead": 5},
)
