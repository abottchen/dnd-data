"""Slice builders for hydrate.

Each builder takes (data, authored) and returns a list of (key, slice_data)
tuples. The orchestrator iterates and dispatches the matching transformer for
each slice.

Mirrors the slicing logic that lived in `helpers.py` under the retired
hydrate-ledger skill. Per the project rule that build.py and hydrate code
mirror patterns rather than extract a shared module, this file imports a few
named helpers from `build` (the authoritative computation source) but does
not factor a third common module.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parents[1] / "build"
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))
import build  # noqa: E402


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
    auth_keys = {build.kill_key(k["character"], k["date"], k["creature"], k["method"])
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
            kk = build.kill_key(char, k["date"], k["creature"], k["method"])
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
    expected = build.collect_npcs_from_log(data["session_log"], authored["site"])
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
        })
    if not new_pcs:
        return []

    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    return [("all", {
        "new_pcs": new_pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
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
    out = []
    for npc in authored["npcs"]:
        name = npc["name"]
        all_mentions = []
        for entry in data["session_log"]["entries"]:
            if not mentions(name, entry.get("text", "")):
                continue
            all_mentions.append({"session": entry.get("session"), "line": entry.get("text", "")})
        out.append((name, {
            "name": name,
            "mentions": all_mentions,
            "existing": {"epithet": npc["epithet"], "allegiance": npc.get("allegiance")},
        }))
    return out


def refresh_characters(data: dict, authored: dict) -> list[tuple]:
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
        })
    if not pcs:
        return []
    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    existing = {c["id"]: c for c in authored["characters"]}
    return [("all", {
        "pcs": pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
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
