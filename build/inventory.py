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
