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


def apply_append_kills(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Each entry in output['fields'] keys by <char>__<date>__<creature>__<method>;
    we look the kill up in the slice's kills array (using render.kill_key for
    case-insensitive matching of creature/method) to recover the canonical row."""
    by_normalized = {
        render.kill_key(k["character"], k["date"], k["creature"], k["method"]): k
        for k in slice_data["kills"]
    }
    for kk_str, vals in output["fields"].items():
        parts = kk_str.split("__", 3)
        if len(parts) != 4:
            raise ValueError(f"malformed kill key from model: {kk_str!r}")
        char, date, creature, method = parts
        normalized = render.kill_key(char, date, creature, method)
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


def apply_append_sessions(authored: dict, key, slice_data: dict, output: dict) -> None:
    fields = output["fields"]
    authored["sessions"].append({
        "session": slice_data["session"],
        "date": slice_data["real_date"],
        "title": fields["title"],
        "summary": fields["summary"],
        "silent_roll": fields.get("silent_roll", []),
    })


def apply_append_chapters(authored: dict, key, slice_data: dict, output: dict) -> None:
    fields = output["fields"]
    authored["chapters"].append({
        "id": int(key),
        "starts_at_session": slice_data["starts_at_session"],
        "title": fields["title"],
        "epigraph": fields["epigraph"],
    })


def apply_append_npcs(authored: dict, key, slice_data: dict, output: dict) -> None:
    """`key` is the upstream-derived NPC name; we use it verbatim rather than
    trusting the model's echoed `name`, so casing/whitespace drift in the
    structured output cannot create duplicate authored entries."""
    fields = output["fields"]
    authored["npcs"].append({
        "name": key,
        "epithet": fields["epithet"],
        "allegiance": fields.get("allegiance"),
    })


def apply_append_characters(authored: dict, key, slice_data: dict, output: dict) -> None:
    """One slice for the whole batch; output['fields'] is keyed by PC id."""
    for pc_id, bundle in output["fields"].items():
        authored["characters"].append({
            "id": pc_id,
            "epithet": bundle["epithet"],
            "reliquary_header": bundle["reliquary_header"],
            "constellation_epithet": bundle["constellation_epithet"],
            "distinction_title": bundle["distinction_title"],
            "distinction_subtitle": bundle["distinction_subtitle"],
            "distinction_detail": bundle["distinction_detail"],
        })


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
            n["epithet"] = fields["epithet"]
            n["allegiance"] = fields["allegiance"]
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


def apply_refresh_known_npcs(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    authored["site"]["known_npcs"] = list(fields["known_npcs"])
