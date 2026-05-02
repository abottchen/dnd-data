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
import json
from pathlib import Path
from typing import Optional

from build.render import _load_dice_player_map, _resolve_dice_player


def load(repo_root: Path, party: Optional[dict] = None) -> dict:
    """Load the latest inventory snapshot under <repo_root>/data and shape
    it for the renderer. Returns an empty bundle if no snapshot is found.

    `party` may be supplied by the caller (e.g. compute_all, which
    already scrubs member ids to slugs); when omitted, the function
    reads party.json from the same data directory and wraps the bare
    list. Tests override the data dir via BUILD_DATA_DIR.
    """
    from build.paths import data_dir

    d = data_dir()
    snapshot = _resolve_snapshot_path(d)
    if snapshot is None:
        return {"by_id": {}, "company_strip": []}

    raw = json.loads(snapshot.read_text())
    if party is None:
        party_path = d / "party.json"
        party_raw = json.loads(party_path.read_text()) if party_path.exists() else []
        party = party_raw if isinstance(party_raw, dict) else {"members": party_raw}

    mapping = _load_dice_player_map()
    parsed = _parse_inventories(raw, mapping)
    return _build_bundle(parsed, party)


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


def _assign_archetypes(
    chars: dict[str, dict],
    slate: tuple[dict, ...] = ARCHETYPE_SLATE,
) -> dict[str, str]:
    """Assign each character at most one archetype slug.

    Algorithm:
      1. Score every (character, archetype) pair.
      2. For each archetype, find the leader and the lead size (leader
         minus runner-up; or leader minus 0 when the field is one wide).
         Discard archetypes where lead < min_lead OR leader's score == 0.
      3. Iterate: each unassigned character collects every archetype
         they currently lead. They keep the one with the largest lead
         (slate-order tiebreak). Surrendered archetypes recompute their
         leader against remaining (unassigned + still-eligible) chars and
         re-enter the pool.
      4. Repeat step 3 until stable.

    Returns: {char_slug: archetype_slug}. Characters without any winning
    archetype are simply absent from the dict.
    """
    candidate_pool: dict[str, list[tuple[str, float]]] = {}
    slate_by_slug = {a["slug"]: a for a in slate}
    slate_order = [a["slug"] for a in slate]

    for arc in slate:
        scored = sorted(
            ((cs, arc["score"](cd["items"], cd["member"])) for cs, cd in chars.items()),
            key=lambda p: -p[1],
        )
        candidate_pool[arc["slug"]] = scored

    def lead(scored: list[tuple[str, float]]) -> float:
        if not scored:
            return 0.0
        if len(scored) == 1:
            return scored[0][1]
        return scored[0][1] - scored[1][1]

    assigned: dict[str, str] = {}
    claimed_archetypes: set[str] = set()
    changed = True
    while changed:
        changed = False
        wins_by_char: dict[str, list[tuple[str, float]]] = {}
        for arc_slug, scored in candidate_pool.items():
            if arc_slug in claimed_archetypes:
                continue
            scored_live = [(cs, sc) for cs, sc in scored if cs not in assigned]
            if not scored_live:
                continue
            min_lead = slate_by_slug[arc_slug]["min_lead"]
            ld = lead(scored_live)
            top_char, top_score = scored_live[0]
            if top_score <= 0 or ld < min_lead:
                continue
            wins_by_char.setdefault(top_char, []).append((arc_slug, ld))

        for cs, wins in wins_by_char.items():
            if not wins:
                continue
            wins.sort(key=lambda p: (-p[1], slate_order.index(p[0])))
            keeper = wins[0][0]
            assigned[cs] = keeper
            claimed_archetypes.add(keeper)
            changed = True

    return assigned


def _shortname(name: str) -> str:
    """First whitespace-split token. 'Lilac Mist' -> 'Lilac'."""
    return (name or "").split()[0] if name else ""


def _build_bundle(parsed: dict[str, dict], party: dict) -> dict:
    """Combine parsed inventories with party members.

    Returns:
      {
        "by_id": {<slug>: {rack, spotlight, manifest, total_weight,
                          capacity, breakdown, archetype, item_count}, ...},
        "company_strip": [{slug, shortname, status,
                           total_weight, capacity, breakdown}, ...],
      }

    Status is "ok" when the character has parsed inventory data, or
    "awaiting_manifest" when they don't (Anton/Lilac before their data
    arrives).
    """
    members_by_id = {m["id"]: m for m in party.get("members", [])
                     if m.get("id") != "gm"}

    by_id: dict[str, dict] = {}
    chars_for_assignment: dict[str, dict] = {}
    for slug, inv in parsed.items():
        member = members_by_id.get(slug)
        if member is None:
            continue
        items = inv["items"]
        rack, spotlight, manifest = _classify(items)
        capacity = _carrying_capacity(member)
        total_weight = _total_weight(items)
        by_id[slug] = {
            "rack": rack,
            "spotlight": spotlight,
            "manifest": manifest,
            "total_weight": total_weight,
            "capacity": capacity,
            "breakdown": _zone_breakdown(rack, spotlight, manifest),
            "item_count": sum((it.get("count") or 1) for it in items),
            "archetype": None,
        }
        chars_for_assignment[slug] = {"items": items, "member": member}

    assignments = _assign_archetypes(chars_for_assignment, ARCHETYPE_SLATE)
    for slug, arc_slug in assignments.items():
        by_id[slug]["archetype"] = arc_slug

    strip: list[dict] = []
    for member in party.get("members", []):
        slug = member.get("id")
        if slug == "gm":
            continue
        rec = by_id.get(slug)
        if rec is None:
            strip.append({
                "slug": slug,
                "shortname": _shortname(member.get("name", "")),
                "status": "awaiting_manifest",
                "total_weight": 0,
                "capacity": _carrying_capacity(member),
                "breakdown": {"rack": 0, "spotlight": 0, "manifest": 0},
            })
        else:
            strip.append({
                "slug": slug,
                "shortname": _shortname(member.get("name", "")),
                "status": "ok",
                "total_weight": rec["total_weight"],
                "capacity": rec["capacity"],
                "breakdown": rec["breakdown"],
            })

    return {"by_id": by_id, "company_strip": strip}


def math_inscription(rec: dict, ranks: dict[str, int]) -> str:
    """Generate a deterministic stats-line tooltip for a character record.

    `rec` is a single entry from inventory_by_id (with `archetype`,
    `total_weight`, `item_count`, etc.). `ranks` maps archetype slug to
    the holder's rank (1 = winner). When the holder is rank 1, append
    "most in the party" to anchor the framing.
    """
    arc = rec.get("archetype")
    if not arc:
        return ""
    weight = rec.get("total_weight", 0)
    n = rec.get("item_count", 0)
    is_winner = ranks.get(arc) == 1
    suffix = " — most in the party" if is_winner else ""
    if arc == "featherfoot":
        cap = rec.get("capacity", 0) or 1
        pct = round(weight / cap * 100)
        return f"Carries {weight:g} lb of {cap} ({pct}% of capacity){suffix}."
    return f"Carries {weight:g} lb across {n} items{suffix}."


def resolve_inscription(
    rec: dict,
    authored: dict | None,
    ranks: dict[str, int],
) -> str:
    """Pick the right tooltip text for a character's archetype badge.

    Use the authored inscription when:
      - `authored` is a dict with both `archetype` and `inscription`,
      - and `authored["archetype"]` matches the current math pick.

    Otherwise, fall back to math_inscription. Returns "" when there is no
    current archetype (the badge will not render).
    """
    if not rec.get("archetype"):
        return ""
    if (
        isinstance(authored, dict)
        and authored.get("archetype") == rec["archetype"]
        and isinstance(authored.get("inscription"), str)
        and authored["inscription"].strip()
    ):
        return authored["inscription"]
    return math_inscription(rec, ranks)
