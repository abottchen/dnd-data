"""Apply transformer returns to the in-memory authored store.

Each apply function mutates `authored` in place. Persistence is the
orchestrator's responsibility (see store.persist).

Signature: apply_*(authored, key, slice_data, output) -> None | dict
- `authored` — the in-memory authored store dict.
- `key` — the slice key (date / session id / npc name / etc.).
- `slice_data` — the original slice that was sent to the transformer.
- `output` — the schema-validated structured_output dict from claude -p.

`apply_refresh_road_ahead` returns a graduations dict so the orchestrator can
include it in the end-of-run report; the others return None.
"""
from . import render


def _circle_kinds(authored: dict) -> dict:
    """key -> kind for every circle in the registry (site.circles)."""
    site = authored.get("site") or {}
    return {c["key"]: c.get("kind") for c in (site.get("circles") or [])}


def _resolve_circles(authored: dict, circles: list) -> list:
    """Check an NPC's circle keys against the registry and put companies
    ahead of factions (stable within each kind), so the first entry is the
    home circle whatever order the model listed them in. An unknown key
    raises ValueError: the result is rejected rather than landing a dangling
    key that validate_circles would fail the render on."""
    kinds = _circle_kinds(authored)
    unknown = [k for k in circles if k not in kinds]
    if unknown:
        raise ValueError("unknown circle key(s): " + ", ".join(repr(k) for k in unknown))
    return ([k for k in circles if kinds[k] != "faction"]
            + [k for k in circles if kinds[k] == "faction"])


def apply_append_kills(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Each entry in output['fields'] keys by <char>__<date>__<creature>__<method>;
    we look the kill up in the slice's kills array (using render.kill_key for
    case-insensitive matching of creature/method) to recover the canonical row."""
    by_normalized = {
        render.kill_key(k["character"], k["date"], k["creature"], k["method"]): k
        for k in slice_data["kills"]
    }
    existing = {
        render.kill_key(a["character"], a["date"], a["creature"], a["method"])
        for a in authored["kills"]
    }
    for kk_str, vals in output["fields"].items():
        parts = kk_str.split("__", 3)
        if len(parts) != 4:
            raise ValueError(f"malformed kill key from model: {kk_str!r}")
        char, date, creature, method = parts
        normalized = render.kill_key(char, date, creature, method)
        if normalized in existing:
            raise ValueError(f"kill already authored: {kk_str!r}")
        kill = by_normalized.get(normalized)
        if kill is None:
            raise ValueError(f"kill key not in slice: {kk_str!r}")
        authored["kills"].append({
            "character": kill["character"],
            "date": kill["date"],
            "creature": kill["creature"],
            "method": kill["method"],
            "verse": vals["verse"],
            "annotation": vals["annotation"],
        })
        existing.add(normalized)


def apply_append_chapters(authored: dict, key, slice_data: dict, output: dict) -> None:
    chapter_id = int(key)
    if any(c["id"] == chapter_id for c in authored["chapters"]):
        raise ValueError(f"chapter id {chapter_id} already authored")
    if any(c["starts_at_session"] == slice_data["starts_at_session"]
           for c in authored["chapters"]):
        raise ValueError(
            f"chapter starting at session {slice_data['starts_at_session']} already authored")
    fields = output["fields"]
    authored["chapters"].append({
        "id": chapter_id,
        "starts_at_session": slice_data["starts_at_session"],
        "title": fields["title"],
        "epigraph": fields["epigraph"],
    })


def apply_append_npcs(authored: dict, key, slice_data: dict, output: dict) -> None:
    """`key` is the upstream-derived NPC name; we use it verbatim rather than
    trusting the model's echoed `name`, so casing/whitespace drift in the
    structured output cannot create duplicate authored entries."""
    if any(n["name"] == key for n in authored["npcs"]):
        raise ValueError(f"npc {key!r} already authored")
    fields = output["fields"]
    circles = _resolve_circles(authored, list(fields["circles"]))
    authored["npcs"].append({
        "name": key,
        "epithet": fields["epithet"],
        "allegiance": fields.get("allegiance"),
        "circles": circles,
    })


def apply_append_characters(authored: dict, key, slice_data: dict, output: dict) -> None:
    """One slice for the whole batch; output['fields'] is keyed by PC id."""
    for pc_id, bundle in output["fields"].items():
        if any(c["id"] == pc_id for c in authored["characters"]):
            raise ValueError(f"character {pc_id!r} already authored")
        authored["characters"].append({
            "id": pc_id,
            "epithet": bundle["epithet"],
            "reliquary_header": bundle["reliquary_header"],
            "constellation_epithet": bundle["constellation_epithet"],
            "distinction_title": bundle["distinction_title"],
            "distinction_subtitle": bundle["distinction_subtitle"],
            "distinction_detail": bundle["distinction_detail"],
            "distinction_basis": bundle["distinction_basis"],
        })


def apply_append_sworn(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Write characters[<id>].sworn_creed. `key` is the character id, used
    verbatim so casing drift in the echoed output can't miss the entry."""
    fields = output["fields"]
    for c in authored["characters"]:
        if c["id"] == key:
            c["sworn_creed"] = fields["sworn_creed"]
            return
    raise ValueError(f"character {key!r} not found in authored store")


def apply_refresh_chapters(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    chapter_id = int(key)
    for c in authored["chapters"]:
        if c["id"] == chapter_id:
            c["title"] = fields["title"]
            c["epigraph"] = fields["epigraph"]
            return
    raise ValueError(f"chapter {chapter_id} not found in authored store")


def apply_refresh_npcs(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    name = key
    for n in authored["npcs"]:
        if n["name"] == name:
            # Resolve before touching the entry so a bad key leaves it intact.
            circles = _resolve_circles(authored, list(fields["circles"]))
            n["epithet"] = fields["epithet"]
            n["allegiance"] = fields["allegiance"]
            n["circles"] = circles
            return
    raise ValueError(f"npc {name!r} not found in authored store")


def apply_refresh_characters(authored: dict, key, slice_data: dict, output: dict) -> None:
    """5-field rewrite per PC; reliquary_header is locked and never returned.
    Only PCs present in output['fields'] are rewritten."""
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    by_id = {c["id"]: c for c in authored["characters"]}
    for pc_id, bundle in fields.items():
        c = by_id.get(pc_id)
        if c is None:
            raise ValueError(f"pc {pc_id!r} not found in authored store")
        c["epithet"] = bundle["epithet"]
        c["constellation_epithet"] = bundle["constellation_epithet"]
        c["distinction_title"] = bundle["distinction_title"]
        c["distinction_subtitle"] = bundle["distinction_subtitle"]
        c["distinction_detail"] = bundle["distinction_detail"]
        c["distinction_basis"] = bundle["distinction_basis"]


def apply_refresh_road_ahead(authored: dict, key, slice_data: dict, output: dict) -> dict:
    """Returns {graduated: [names...]} — entries that moved known → was_known
    in this rewrite. Empty list on no_change or no graduations."""
    if output["decision"] == "no_change":
        return {"graduated": []}
    fields = output["fields"] or {}
    old_known_names = {e["name"] for e in authored["site"]["road_ahead"]["known"]}
    authored["site"]["road_ahead"] = {
        "known": fields["known"],
        "was_known": fields["was_known"],
        "direction": fields["direction"],
    }
    new_known_names = {e["name"] for e in fields["known"]}
    return {"graduated": sorted(old_known_names - new_known_names)}


def apply_refresh_intro_epithet(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    authored["site"]["intro_epithet"] = fields["intro_epithet"]


def apply_refresh_ascent_read(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    authored["site"]["ascent_read"] = fields["ascent_read"]


def apply_refresh_known_npcs(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Replace `site.known_npcs` and merge any proposed circles into the
    registry (`site.circles`), append-only: a proposal whose key already
    exists is skipped whole, members included, because the pipeline never
    renames, removes, or re-populates a published circle.

    Each accepted circle's `members` who already have an authored entry are
    filed under it here. The per-NPC slices of this same run were prepared
    before this result existed, so nothing else would place them and the
    circle would sit memberless, which validate_circles fails the render on.
    Members not yet authored are left to append-npcs, whose next slice will
    carry the new circle. A member outside the (new) known_npcs list is a
    typo or an invention: the whole result is refused before any mutation.
    """
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    site = authored["site"]
    known = list(fields["known_npcs"])
    known_set = set(known)
    present = {c["key"] for c in (site.get("circles") or [])}
    accepted = []
    for c in fields.get("circles") or []:
        if c["key"] in present:
            continue
        for m in c.get("members", []):
            if m not in known_set:
                raise ValueError(
                    f"circle {c['key']!r} names member {m!r}, which is not a known NPC")
        accepted.append(c)
        present.add(c["key"])

    site["known_npcs"] = known
    if not accepted:
        return
    registry = site.setdefault("circles", [])
    npcs_by_name = {n["name"]: n for n in authored.get("npcs", [])}
    for c in accepted:
        registry.append({"key": c["key"], "title": c["title"], "kind": c["kind"]})
        for m in c.get("members", []):
            npc = npcs_by_name.get(m)
            if npc is None:
                continue
            circles = list(npc.get("circles", []))
            if c["key"] not in circles:
                circles.append(c["key"])
            npc["circles"] = _resolve_circles(authored, circles)


def apply_refresh_archetype_inscription(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Write characters[<id>].archetype_badge = {archetype, inscription}.

    On `no_change`, leaves any existing badge untouched. On `rewrite`,
    sets the badge to the slice's archetype slug + the model's
    inscription. Raises ValueError if the character id is not present in
    the authored store.
    """
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    char_id = slice_data["character"]["id"]
    arc_slug = slice_data["archetype"]["slug"]
    for c in authored["characters"]:
        if c["id"] == char_id:
            c["archetype_badge"] = {
                "archetype": arc_slug,
                "inscription": fields["inscription"],
            }
            return
    raise ValueError(f"character {char_id!r} not found in authored store")
