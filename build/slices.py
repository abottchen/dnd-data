"""Slice builders for the build orchestrator.

Each builder takes (data, authored) and returns a list of (key, slice_data)
tuples. The orchestrator iterates and dispatches the matching transformer for
each slice.

Mirrors the slicing logic that lived in `helpers.py` under the retired
hydrate-ledger skill. Per the project rule that render.py and orchestrator
code mirror patterns rather than extract a shared module, this file imports
a few named helpers from `render` (the authoritative computation source)
but does not factor a third common module.
"""
import re
from collections import defaultdict

from . import render


def _character_context(data: dict, authored: dict) -> tuple[dict, dict, list]:
    """Returns (fact_pack, had_new_activity, session_text) for the character
    authoring slices. had_new_activity[pc] is True if the PC made a kill or
    cast a die in a session newer than the refresh marker. session_text is the
    new sessions' narrative (for the narrative-tiebreak path)."""
    trials = render.compute_trials(data["party"])
    fortune = {
        m["id"]: render.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    constellation = render.compute_constellation(data["party"], fortune, trials)
    fact_pack = render.compute_fact_pack(
        data["party"], trials, fortune, constellation, data["session_log"])

    marker = authored["site"].get("refreshed_through_session", 0)
    entries = data["session_log"]["entries"]
    new_dates = {e["date"] for i, e in enumerate(entries, start=1) if i > marker}
    session_text = [
        {"session": e.get("session"), "date": e.get("date"), "text": e.get("text", "")}
        for i, e in enumerate(entries, start=1) if i > marker
    ]

    had_new_activity = {}
    for m in data["party"]["members"]:
        cid = m["id"]
        killed = any(k["date"] in new_dates for k in m.get("kills", []))
        rolled = any(ev.get("date") in new_dates
                     for ev in data["rolls_by_slug"].get(cid, []))
        had_new_activity[cid] = bool(killed or rolled)
    return fact_pack, had_new_activity, session_text


def iu_date(entry: dict) -> str:
    parts = [str(entry.get(k, "")).strip() for k in ("iu_day", "iu_month", "iu_year")]
    parts = [p for p in parts if p]
    return " ".join(parts) + " DR" if parts else ""


# -- NPC name matching -------------------------------------------------------
# Word-boundary, case-insensitive match across multiple search forms of a
# canonical NPC name: the canonical, leading-article-stripped, sub-names from
# ", called " aliases, and individual proper-noun tokens.

NAME_STOP_TOKENS = frozenset({"the", "a", "an", "of", "and", "or"})
NAME_LEADING_ARTICLE = re.compile(r"^(?:The|A|An)\s+", re.IGNORECASE)
NAME_ALIAS_SPLIT = re.compile(r",?\s+called\s+", re.IGNORECASE)


def name_forms(name: str) -> list[str]:
    forms: set[str] = {name}
    forms.add(NAME_LEADING_ARTICLE.sub("", name))
    for part in NAME_ALIAS_SPLIT.split(name):
        part = part.strip()
        if not part:
            continue
        forms.add(part)
        forms.add(NAME_LEADING_ARTICLE.sub("", part))
        tokens = part.split()
        if len(tokens) > 1:
            for tok in tokens:
                if tok.lower().rstrip(",.;:") not in NAME_STOP_TOKENS:
                    forms.add(tok)
    return [f for f in forms if f.strip()]


def mentions(name: str, text: str) -> bool:
    for form in name_forms(name):
        if re.search(r"\b" + re.escape(form) + r"\b", text, re.IGNORECASE):
            return True
    return False


def session_index(sid: int, session_log: dict) -> int | None:
    for i, e in enumerate(session_log["entries"], start=1):
        if e.get("session") == sid:
            return i
    return None


def chapter_session_ids(chapter_id: int, chapters: list, session_log: dict) -> list[int]:
    chapters = sorted(chapters, key=lambda c: c["id"])
    chapter = next(c for c in chapters if c["id"] == chapter_id)
    chapter_start_idx = session_index(chapter["starts_at_session"], session_log)
    if chapter_start_idx is None:
        return []
    next_start_indices = []
    for c in chapters:
        if c["id"] == chapter_id:
            continue
        idx = session_index(c["starts_at_session"], session_log)
        if idx is not None and idx > chapter_start_idx:
            next_start_indices.append(idx)
    chapter_end_idx = (min(next_start_indices) - 1) if next_start_indices else len(session_log["entries"])
    return [e["session"] for e in session_log["entries"][chapter_start_idx - 1:chapter_end_idx]]


# -- Append slice builders ---------------------------------------------------

def append_kills(data: dict, authored: dict) -> list[tuple]:
    auth_keys = {render.kill_key(k["character"], k["date"], k["creature"], k["method"])
                 for k in authored["kills"]}

    # First-seen wins on the rare same-date case (a long Saturday spanning two
    # sessions): the earlier session in log order owns the date's kill narrative.
    sessions_by_date: dict = {}
    for e in data["session_log"]["entries"]:
        sessions_by_date.setdefault(e["date"], e)

    new_by_date: dict = defaultdict(list)
    for member in data["party"]["members"]:
        char = member["id"]
        for k in member.get("kills", []):
            kk = render.kill_key(char, k["date"], k["creature"], k["method"])
            if kk in auth_keys:
                continue
            new_by_date[k["date"]].append({
                "character": char,
                "creature": k["creature"],
                "method": k["method"],
                "date": k["date"],
            })

    out = []
    for date in sorted(new_by_date.keys()):
        kills = new_by_date[date]
        session = sessions_by_date.get(date)
        if session is None:
            continue
        out.append((date, {
            "session": session.get("session"),
            "iu_date": iu_date(session),
            "real_date": date,
            "narrative": session.get("text", ""),
            "kills": kills,
        }))
    return out


def append_sessions(data: dict, authored: dict) -> list[tuple]:
    auth_sessions = {s["session"] for s in authored["sessions"]}
    out = []
    for entry in data["session_log"]["entries"]:
        sid = entry.get("session")
        if sid in auth_sessions:
            continue
        out.append((sid, {
            "session": sid,
            "real_date": entry.get("date"),
            "iu_date": iu_date(entry),
            "narrative": entry.get("text", ""),
            "chapter_marker": entry.get("chapter_marker", False),
        }))
    return out


def append_chapters(data: dict, authored: dict) -> list[tuple]:
    auth_starts = {c["starts_at_session"] for c in authored["chapters"]}
    next_id = max((c["id"] for c in authored["chapters"]), default=0) + 1

    entries = data["session_log"]["entries"]
    by_session = {e.get("session"): e for e in entries}
    chapter_sids = [e.get("session") for e in entries if e.get("chapter_marker")]
    if entries:
        first = entries[0].get("session")
        if first not in chapter_sids:
            chapter_sids = [first] + chapter_sids

    out = []
    for sid in chapter_sids:
        if sid in auth_starts:
            continue
        entry = by_session.get(sid, {})
        out.append((str(next_id), {
            "starts_at_session": sid,
            "real_date": entry.get("date"),
            "narrative": entry.get("text", ""),
        }))
        next_id += 1
    return out


def append_npcs(data: dict, authored: dict) -> list[tuple]:
    auth_names = {n["name"] for n in authored["npcs"]}
    expected = render.collect_npcs_from_log(data["session_log"], authored["site"])
    missing = [n for n in expected if n not in auth_names]
    out = []
    for name in missing:
        npc_mentions = []
        for entry in data["session_log"]["entries"]:
            text = entry.get("text", "")
            if mentions(name, text):
                npc_mentions.append({"session": entry.get("session"), "line": text})
        out.append((name, {"name": name, "mentions": npc_mentions}))
    return out


def append_characters(data: dict, authored: dict) -> list[tuple]:
    auth_ids = {c["id"] for c in authored["characters"]}
    pronouns_by_id = authored.get("pronouns_by_id", {})
    new_pcs = []
    for member in data["party"]["members"]:
        if member["id"] in auth_ids:
            continue
        new_pcs.append({
            "id": member["id"],
            "name": member.get("name"),
            "race": member.get("race"),
            "class": member.get("class"),
            "kills": member.get("kills", []),
            "pronouns": pronouns_by_id.get(member["id"], ""),
        })
    if not new_pcs:
        return []

    fact_pack, had_new_activity, session_text = _character_context(data, authored)
    return [("all", {
        "new_pcs": new_pcs,
        "fact_pack": fact_pack,
        "had_new_activity": had_new_activity,
        "session_text": session_text,
        "existing_distinction_titles": [c["distinction_title"] for c in authored["characters"]],
    })]


# -- Refresh slice builders --------------------------------------------------

def refresh_chapters(data: dict, authored: dict) -> list[tuple]:
    out = []
    for chapter in authored["chapters"]:
        sids = chapter_session_ids(chapter["id"], authored["chapters"], data["session_log"])
        sessions_in_chapter = [
            e for e in data["session_log"]["entries"] if e.get("session") in sids
        ]
        out.append((str(chapter["id"]), {
            "chapter_id": chapter["id"],
            "starts_at_session": chapter["starts_at_session"],
            "sessions": sessions_in_chapter,
            "existing": {"title": chapter["title"], "epigraph": chapter["epigraph"]},
        }))
    return out


def refresh_npcs(data: dict, authored: dict) -> list[tuple]:
    """One slice per authored NPC named in a session newer than the marker.

    An NPC's epithet is a pure function of its mention set, so an NPC whose
    mentions all fall in already-refreshed sessions would re-author to an
    identical epithet — re-dispatching it is wasted work. We gate emission on
    the marker the same way refresh_road_ahead / refresh_intro_epithet gate
    their evidence. Each emitted slice still carries the NPC's *full* mention
    history for context; only the decision to emit is marker-scoped.

    Under --force-refresh (signalled via the `force_refresh` side channel) the
    gate is lifted and the whole roster is re-evaluated.
    """
    marker = authored["site"].get("refreshed_through_session", 0)
    force = authored.get("force_refresh", False)
    new_session_ids = None if force else {
        entry.get("session")
        for i, entry in enumerate(data["session_log"]["entries"], start=1)
        if i > marker
    }

    out = []
    for npc in authored["npcs"]:
        name = npc["name"]
        all_mentions = []
        for entry in data["session_log"]["entries"]:
            if not mentions(name, entry.get("text", "")):
                continue
            all_mentions.append({"session": entry.get("session"), "line": entry.get("text", "")})
        if new_session_ids is not None and not any(
            m["session"] in new_session_ids for m in all_mentions
        ):
            continue
        out.append((name, {
            "name": name,
            "mentions": all_mentions,
            "existing": {"epithet": npc["epithet"], "allegiance": npc.get("allegiance")},
        }))
    return out


def refresh_characters(data: dict, authored: dict) -> list[tuple]:
    pronouns_by_id = authored.get("pronouns_by_id", {})
    pcs = []
    for member in data["party"]["members"]:
        if not any(c["id"] == member["id"] for c in authored["characters"]):
            continue
        pcs.append({
            "id": member["id"],
            "name": member.get("name"),
            "race": member.get("race"),
            "class": member.get("class"),
            "kills": member.get("kills", []),
            "pronouns": pronouns_by_id.get(member["id"], ""),
        })
    if not pcs:
        return []
    fact_pack, had_new_activity, session_text = _character_context(data, authored)
    existing = {c["id"]: c for c in authored["characters"]}
    return [("all", {
        "pcs": pcs,
        "fact_pack": fact_pack,
        "had_new_activity": had_new_activity,
        "session_text": session_text,
        "existing": existing,
    })]


def refresh_road_ahead(data: dict, authored: dict) -> list[tuple]:
    marker = authored["site"].get("refreshed_through_session", 0)
    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1) if i > marker
    ]
    return [("all", {
        "new_sessions": new_sessions,
        "existing": authored["site"]["road_ahead"],
    })]


def refresh_intro_epithet(data: dict, authored: dict) -> list[tuple]:
    marker = authored["site"].get("refreshed_through_session", 0)
    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1) if i > marker
    ]
    return [("all", {
        "new_sessions": new_sessions,
        "road_ahead_known": authored["site"]["road_ahead"]["known"],
        "existing": authored["site"]["intro_epithet"],
    })]


def refresh_ascent_read(data: dict, authored: dict) -> list[tuple]:
    """One slice carrying the new sessions, the current XP-by-type composition,
    and the existing one-line 'character read' for the prompt to weigh."""
    marker = authored["site"].get("refreshed_through_session", 0)
    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1) if i > marker
    ]
    by_type: dict[str, int] = defaultdict(int)
    for e in (data.get("xp_log") or {}).get("entries", []):
        by_type[e.get("type") or "other"] += int(e.get("perPc", 0))
    total = sum(by_type.values())
    composition = [
        {"type": t, "xp": x, "pct": round(x / total * 100) if total else 0}
        for t, x in sorted(by_type.items(), key=lambda kv: -kv[1])
    ]
    return [("all", {
        "new_sessions": new_sessions,
        "composition": composition,
        "existing": authored["site"].get("ascent_read", ""),
    })]


def refresh_known_npcs(data: dict, authored: dict) -> list[tuple]:
    """Discover NPC names from session text and append them to the canonical
    `site.known_npcs` list. Runs in the discovery pass before append-npcs so
    newly named NPCs flow into per-NPC epithet authoring on the same build.

    Unlike road-ahead / intro-epithet (which evaluate new evidence against
    existing belief), this task is name-extraction over the full corpus. We
    pass every session so the model can catch names missed in earlier runs;
    `existing` tells it which names are already covered.
    """
    return [("all", {
        "sessions": list(data["session_log"]["entries"]),
        "existing": list(authored["site"].get("known_npcs", [])),
    })]


# -- Refresh: archetype inscription ------------------------------------------

from build.inventory import archetype_match, ARCHETYPE_SLATE

_ARCHETYPE_LABELS = {a["slug"]: a["label"] for a in ARCHETYPE_SLATE}


def refresh_archetype_inscription(data: dict, authored: dict) -> list[tuple]:
    """One slice per character whose math archetype is set.

    `authored` is expected to carry an `inventory_by_id` field — the
    orchestrator wiring places it there before calling this builder.
    """
    inv_by_id = authored.get("inventory_by_id", {})
    pronouns_by_id = authored.get("pronouns_by_id", {})
    auth_by_id = {a["id"]: a for a in authored.get("characters", [])}
    out: list[tuple] = []
    for member in data["party"].get("members", []):
        cid = member.get("id")
        if cid == "gm":
            continue
        rec = inv_by_id.get(cid)
        if not rec or not rec.get("archetype"):
            continue
        arc_slug = rec["archetype"]
        all_items = (
            rec.get("rack", []) + rec.get("spotlight", []) + rec.get("manifest", [])
        )
        slice_items = [
            {
                "name": it.get("name"),
                "count": it.get("count", 1),
                "weight": it.get("weight"),
                "description": it.get("description", ""),
            }
            for it in archetype_match(arc_slug, all_items)
        ]
        existing = auth_by_id.get(cid, {}).get("archetype_badge")
        out.append((cid, {
            "character": {
                "id": cid,
                "name": member.get("name"),
                "race": member.get("race"),
                "class": member.get("class"),
                "background": member.get("background"),
                "epithet": auth_by_id.get(cid, {}).get("epithet", ""),
                "pronouns": pronouns_by_id.get(cid, ""),
            },
            "archetype": {
                "slug": arc_slug,
                "label": _ARCHETYPE_LABELS.get(arc_slug, arc_slug.upper()),
                "metric": arc_slug,
                "score": rec.get("total_weight", 0),
                "runner_up_score": 0,
                "lead": 0,
            },
            "items": slice_items,
            "existing": existing,
        }))
    return out
