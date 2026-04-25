#!/usr/bin/env python3
"""Slice helpers for the hydrate-ledger skill.

Each subcommand introspects upstream + authored state with no parameters,
writes per-entity slice JSON to a temp dir, and prints metadata to stdout.

Test override env vars:
  HYDRATE_DATA_DIR     — directory containing party.json / session-log.json / dicex-rolls-*.json
  HYDRATE_AUTHORED_DIR — directory containing kills.json / sessions.json / ... / site.json
  HYDRATE_TEMP_DIR     — directory to write slice files into (default: tempfile.mkdtemp)
"""
import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
import build  # noqa: E402


def _data_dir() -> Path:
    return Path(os.environ.get("HYDRATE_DATA_DIR", REPO_ROOT))


def _authored_dir() -> Path:
    return Path(os.environ.get("HYDRATE_AUTHORED_DIR", REPO_ROOT / "authored"))


def _temp_dir() -> Path:
    override = os.environ.get("HYDRATE_TEMP_DIR")
    if override:
        return Path(override)
    return Path(tempfile.mkdtemp(prefix="hydrate-"))


def _load_authored() -> dict:
    """Load all authored/*.json files, keyed by stem (kills, sessions, ...).

    site.json is loaded as a dict; the rest are lists.
    """
    auth_dir = _authored_dir()
    out = {}
    for stem in ("kills", "sessions", "chapters", "npcs", "characters"):
        out[stem] = json.loads((auth_dir / f"{stem}.json").read_text())
    out["site"] = json.loads((auth_dir / "site.json").read_text())
    return out


def _emit(slices: list[dict]) -> None:
    """Print metadata to stdout as a single JSON line."""
    print(json.dumps({"slices": slices}))


def _iu_date(entry: dict) -> str:
    """Format an in-universe date from a session-log entry. Returns empty
    string if no iu_* fields are populated; handles partial data gracefully."""
    parts = [str(entry.get(k, "")).strip() for k in ("iu_day", "iu_month", "iu_year")]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return " ".join(parts) + " DR"


NAME_STOP_TOKENS = frozenset({"the", "a", "an", "of", "and", "or"})
NAME_LEADING_ARTICLE = re.compile(r"^(?:The|A|An)\s+", re.IGNORECASE)
NAME_ALIAS_SPLIT = re.compile(r",?\s+called\s+", re.IGNORECASE)


def _name_forms(name: str) -> list[str]:
    """Return search forms for an NPC name: canonical, leading-article-stripped,
    sub-names from ', called ' aliases, and individual non-stop-word tokens of
    each multi-token sub-name. Single-token names yield only themselves.

    Example: "Corwin, called Artus Cimber" yields
        {"Corwin, called Artus Cimber", "Corwin", "Artus Cimber", "Artus", "Cimber"}.
    """
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


def _mentions(name: str, text: str) -> bool:
    """Word-boundary, case-insensitive match across all search forms of `name`.
    Forms include the canonical name, the leading-article-stripped variant,
    sub-names from ', called ' aliases, and individual proper-noun tokens.
    The \\b boundary guards against substring false positives."""
    for form in _name_forms(name):
        if re.search(r"\b" + re.escape(form) + r"\b", text, re.IGNORECASE):
            return True
    return False


def _session_index(roman: str, session_log: dict) -> int | None:
    """Return the 1-based ordinal of a session id within the log."""
    for i, e in enumerate(session_log["entries"], start=1):
        if e.get("session") == roman:
            return i
    return None


def _chapter_session_ids(chapter_id: int, chapters: list, session_log: dict) -> list[str]:
    """Return ordered list of session ids that belong to the given chapter.

    Returns empty list if the chapter's starts_at_session is not yet in the log.
    Other chapters with unresolvable starts are ignored when computing the next
    chapter boundary."""
    chapters = sorted(chapters, key=lambda c: c["id"])
    chapter = next(c for c in chapters if c["id"] == chapter_id)
    chapter_start_idx = _session_index(chapter["starts_at_session"], session_log)
    if chapter_start_idx is None:
        return []
    next_start_indices = []
    for c in chapters:
        if c["id"] == chapter_id:
            continue
        idx = _session_index(c["starts_at_session"], session_log)
        if idx is not None and idx > chapter_start_idx:
            next_start_indices.append(idx)
    chapter_end_idx = (min(next_start_indices) - 1) if next_start_indices else len(session_log["entries"])
    return [e["session"] for e in session_log["entries"][chapter_start_idx - 1:chapter_end_idx]]


def cmd_append_kills() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_keys = {build.kill_key(k["character"], k["date"], k["creature"], k["method"])
                 for k in authored["kills"]}

    # First-seen wins on the rare same-date case (a long Saturday spanning two
    # sessions): the earlier session in log order owns the date's kill narrative.
    sessions_by_date: dict[str, dict] = {}
    for e in data["session_log"]["entries"]:
        sessions_by_date.setdefault(e["date"], e)
    new_by_date: dict[str, list[dict]] = defaultdict(list)
    for member in data["party"]["members"]:
        char = member["id"]
        for k in member.get("kills", []):
            key = build.kill_key(char, k["date"], k["creature"], k["method"])
            if key in auth_keys:
                continue
            new_by_date[k["date"]].append({
                "character": char,
                "creature": k["creature"],
                "method": k["method"],
                "date": k["date"],
            })

    temp = _temp_dir()
    slices = []
    for date in sorted(new_by_date.keys()):
        kills = new_by_date[date]
        session = sessions_by_date.get(date)
        if session is None:
            continue
        slice_data = {
            "session": session.get("session"),
            "iu_date": _iu_date(session),
            "real_date": date,
            "narrative": session.get("text", ""),
            "kills": kills,
        }
        path = temp / f"append_kills_{date}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": date, "path": str(path), "count": len(kills)})

    _emit(slices)
    return 0


def cmd_append_sessions() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_sessions = {s["session"] for s in authored["sessions"]}

    temp = _temp_dir()
    slices = []
    for entry in data["session_log"]["entries"]:
        sid = entry.get("session")
        if sid in auth_sessions:
            continue
        slice_data = {
            "session": sid,
            "real_date": entry.get("date"),
            "iu_date": _iu_date(entry),
            "narrative": entry.get("text", ""),
            "chapter_marker": entry.get("chapter_marker", False),
        }
        path = temp / f"append_sessions_{sid}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": sid, "path": str(path), "count": 1})

    _emit(slices)
    return 0


def cmd_append_chapters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_chapter_starts = {c["starts_at_session"] for c in authored["chapters"]}
    next_id = max((c["id"] for c in authored["chapters"]), default=0) + 1

    entries = data["session_log"]["entries"]
    by_session = {e.get("session"): e for e in entries}
    chapter_session_ids = [e.get("session") for e in entries if e.get("chapter_marker")]
    if entries:
        first = entries[0].get("session")
        if first not in chapter_session_ids:
            chapter_session_ids = [first] + chapter_session_ids

    temp = _temp_dir()
    slices = []
    for sid in chapter_session_ids:
        if sid in auth_chapter_starts:
            continue
        entry = by_session.get(sid, {})
        slice_data = {
            "starts_at_session": sid,
            "real_date": entry.get("date"),
            "narrative": entry.get("text", ""),
        }
        key = str(next_id)
        path = temp / f"append_chapters_{key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": key, "path": str(path), "count": 1})
        next_id += 1

    _emit(slices)
    return 0


def cmd_append_npcs() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_names = {n["name"] for n in authored["npcs"]}
    expected = build.collect_npcs_from_log(data["session_log"], authored["site"])
    missing = [name for name in expected if name not in auth_names]

    # Group mentions per NPC across all sessions.
    mentions_by_npc: dict[str, list[dict]] = {name: [] for name in missing}
    for entry in data["session_log"]["entries"]:
        text = entry.get("text", "")
        for name in missing:
            if _mentions(name, text):
                mentions_by_npc[name].append({"session": entry.get("session"), "line": text})

    temp = _temp_dir()
    slices = []
    for name in missing:
        slice_data = {"name": name, "mentions": mentions_by_npc[name]}
        safe_key = name.replace(" ", "_").replace("/", "_")
        path = temp / f"append_npcs_{safe_key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": name, "path": str(path), "count": len(mentions_by_npc[name])})

    _emit(slices)
    return 0


def cmd_append_characters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_ids = {c["id"] for c in authored["characters"]}

    new_pcs = []
    for member in data["party"]["members"]:
        cid = member["id"]
        if cid in auth_ids:
            continue
        new_pcs.append({
            "id": cid,
            "name": member.get("name"),
            "race": member.get("race"),
            "class": member.get("class"),
            "kills": member.get("kills", []),
        })

    if not new_pcs:
        _emit([])
        return 0

    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }

    temp = _temp_dir()
    body = {
        "new_pcs": new_pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
        "existing_distinction_titles": [c["distinction_title"] for c in authored["characters"]],
    }
    path = temp / "append_characters_all.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_pcs)}])
    return 0


def cmd_refresh_chapters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    temp = _temp_dir()
    slices = []
    for chapter in authored["chapters"]:
        sids = _chapter_session_ids(chapter["id"], authored["chapters"], data["session_log"])
        new_sids = [s for s in sids if (_session_index(s, data["session_log"]) or 0) > marker]
        sessions_in_chapter = [
            e for e in data["session_log"]["entries"] if e.get("session") in sids
        ]
        slice_data = {
            "chapter_id": chapter["id"],
            "starts_at_session": chapter["starts_at_session"],
            "sessions": sessions_in_chapter,
            "existing": {"title": chapter["title"], "epigraph": chapter["epigraph"]},
        }
        key = str(chapter["id"])
        path = temp / f"refresh_chapters_{key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": key, "path": str(path), "count": len(new_sids)})

    _emit(slices)
    return 0


def cmd_refresh_npcs() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    temp = _temp_dir()
    slices = []
    for npc in authored["npcs"]:
        name = npc["name"]
        all_mentions = []
        new_mentions = 0
        for entry in data["session_log"]["entries"]:
            if not _mentions(name, entry.get("text", "")):
                continue
            sid_idx = _session_index(entry.get("session"), data["session_log"]) or 0
            mention = {"session": entry.get("session"), "line": entry.get("text", "")}
            all_mentions.append(mention)
            if sid_idx > marker:
                new_mentions += 1
        slice_data = {
            "name": name,
            "mentions": all_mentions,
            "existing": {"epithet": npc["epithet"], "allegiance": npc.get("allegiance")},
        }
        safe_key = name.replace(" ", "_").replace("/", "_")
        path = temp / f"refresh_npcs_{safe_key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": name, "path": str(path), "count": new_mentions})

    _emit(slices)
    return 0


def cmd_refresh_characters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
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
        _emit([])
        return 0

    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    existing = {c["id"]: c for c in authored["characters"]}

    body = {
        "pcs": pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
        "existing": existing,
    }
    temp = _temp_dir()
    path = temp / "refresh_characters_all.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(pcs)}])
    return 0


def cmd_refresh_road_ahead() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1)
        if i > marker
    ]
    body = {
        "new_sessions": new_sessions,
        "existing": authored["site"]["road_ahead"],
    }
    temp = _temp_dir()
    path = temp / "refresh_road_ahead.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_sessions)}])
    return 0


def cmd_refresh_intro_epithet() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1)
        if i > marker
    ]
    body = {
        "new_sessions": new_sessions,
        "road_ahead_known": authored["site"]["road_ahead"]["known"],
        "existing": authored["site"]["intro_epithet"],
    }
    temp = _temp_dir()
    path = temp / "refresh_intro_epithet.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_sessions)}])
    return 0


SUBCOMMANDS: dict[str, Callable[[], int]] = {
    "append-kills": cmd_append_kills,
    "append-sessions": cmd_append_sessions,
    "append-chapters": cmd_append_chapters,
    "append-npcs": cmd_append_npcs,
    "append-characters": cmd_append_characters,
    "refresh-chapters": cmd_refresh_chapters,
    "refresh-npcs": cmd_refresh_npcs,
    "refresh-characters": cmd_refresh_characters,
    "refresh-road-ahead": cmd_refresh_road_ahead,
    "refresh-intro-epithet": cmd_refresh_intro_epithet,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hydrate-ledger slice helpers")
    parser.add_argument("subcommand", choices=sorted(SUBCOMMANDS.keys()))
    args = parser.parse_args(argv)
    return SUBCOMMANDS[args.subcommand]()


if __name__ == "__main__":
    sys.exit(main())
