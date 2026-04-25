#!/usr/bin/env python3
"""build.py — render index.html from data + authored store + templates.

Exit codes:
  0  render succeeded
  1  validation errors; nothing written
  2  internal error (template syntax, file read failure, bestiary miss)
"""
from __future__ import annotations
import argparse
import functools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent

KIND_MISSING = "MISSING"
KIND_MALFORMED = "MALFORMED"
KIND_ORPHAN = "ORPHAN"

class ValidationError:
    def __init__(self, kind: str, kind_type: str, key: tuple, field: str | None = None):
        self.kind = kind
        self.kind_type = kind_type
        self.key = key
        self.field = field

    def __str__(self) -> str:
        key_str = "(" + ", ".join(str(k) for k in self.key) + ")"
        if self.kind == KIND_MALFORMED:
            return f"{self.kind} {self.kind_type} {key_str} field={self.field}"
        return f"{self.kind} {self.kind_type} {key_str}"

def kill_key(character: str, date: str, creature: str, method: str) -> tuple:
    """Normalize a kill key. Case-folded creature/method; date and char as-is."""
    return (character, date, creature.casefold(), method.casefold())

REQUIRED_KILL_FIELDS = ("verse", "annotation")

def validate_kills(party: dict, authored: list) -> list[ValidationError]:
    errors: list[ValidationError] = []
    expected_keys: dict[tuple, dict] = {}
    for member in party.get("members", []):
        char_id = member["id"]
        for k in member.get("kills", []):
            key = kill_key(char_id, k["date"], k["creature"], k["method"])
            expected_keys[key] = k

    by_key: dict[tuple, dict] = {}
    for entry in authored:
        key = kill_key(entry["character"], entry["date"], entry["creature"], entry["method"])
        by_key[key] = entry

    # MISSING + MALFORMED
    for key, _kill in expected_keys.items():
        entry = by_key.get(key)
        if entry is None:
            errors.append(ValidationError(KIND_MISSING, "kills", key))
            continue
        for f in REQUIRED_KILL_FIELDS:
            v = entry.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                errors.append(ValidationError(KIND_MALFORMED, "kills", key, field=f))

    # ORPHAN
    for key in by_key:
        if key not in expected_keys:
            errors.append(ValidationError(KIND_ORPHAN, "kills", key))

    return errors

REQUIRED_SESSION_FIELDS = ("title", "summary", "silent_roll")
REQUIRED_CHAPTER_FIELDS = ("title", "epigraph")
REQUIRED_NPC_FIELDS = ("epithet",)
REQUIRED_CHAR_FIELDS = ("reliquary_header", "constellation_epithet")
REQUIRED_SITE_FIELDS = ("intro_epithet", "intro_meta", "page_title", "page_subtitle")

def _missing_or_blank(entry: dict, field: str) -> bool:
    v = entry.get(field)
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, list) and len(v) == 0:
        return True
    return False

def validate_sessions(session_log: dict, authored: list) -> list[ValidationError]:
    errors: list[ValidationError] = []
    expected = {e["session"]: e for e in session_log.get("entries", [])}
    by_key = {a["session"]: a for a in authored}
    for sess_id in expected:
        a = by_key.get(sess_id)
        if a is None:
            errors.append(ValidationError(KIND_MISSING, "sessions", (sess_id,)))
            continue
        for f in REQUIRED_SESSION_FIELDS:
            if _missing_or_blank(a, f):
                errors.append(ValidationError(KIND_MALFORMED, "sessions", (sess_id,), field=f))
    for sess_id in by_key:
        if sess_id not in expected:
            errors.append(ValidationError(KIND_ORPHAN, "sessions", (sess_id,)))
    return errors

def validate_chapters(session_log: dict, authored: list) -> list[ValidationError]:
    """Each chapter_marker session opens a chapter that needs authored content.
    The first session implicitly opens a chapter even without an explicit marker."""
    errors: list[ValidationError] = []
    chapter_sessions = [e["session"] for e in session_log.get("entries", []) if e.get("chapter_marker")]
    by_starts = {a["starts_at_session"]: a for a in authored if "starts_at_session" in a}
    if session_log.get("entries"):
        first = session_log["entries"][0]["session"]
        if first not in by_starts and first not in chapter_sessions:
            chapter_sessions = [first] + chapter_sessions
    for s in chapter_sessions:
        a = by_starts.get(s)
        if a is None:
            errors.append(ValidationError(KIND_MISSING, "chapters", (s,)))
            continue
        for f in REQUIRED_CHAPTER_FIELDS:
            if _missing_or_blank(a, f):
                errors.append(ValidationError(KIND_MALFORMED, "chapters", (s,), field=f))
    for s in by_starts:
        if s not in chapter_sessions:
            errors.append(ValidationError(KIND_ORPHAN, "chapters", (s,)))
    return errors

def validate_npcs(npcs_in_log: list, authored: list) -> list[ValidationError]:
    errors: list[ValidationError] = []
    expected = set(npcs_in_log)
    by_name = {a["name"]: a for a in authored}
    for n in expected:
        a = by_name.get(n)
        if a is None:
            errors.append(ValidationError(KIND_MISSING, "npcs", (n,)))
            continue
        for f in REQUIRED_NPC_FIELDS:
            if _missing_or_blank(a, f):
                errors.append(ValidationError(KIND_MALFORMED, "npcs", (n,), field=f))
    for n in by_name:
        if n not in expected:
            errors.append(ValidationError(KIND_ORPHAN, "npcs", (n,)))
    return errors

def validate_characters(party: dict, authored: list) -> list[ValidationError]:
    errors: list[ValidationError] = []
    expected = {m["id"] for m in party.get("members", [])}
    by_id = {a["id"]: a for a in authored}
    for cid in expected:
        a = by_id.get(cid)
        if a is None:
            errors.append(ValidationError(KIND_MISSING, "characters", (cid,)))
            continue
        for f in REQUIRED_CHAR_FIELDS:
            if _missing_or_blank(a, f):
                errors.append(ValidationError(KIND_MALFORMED, "characters", (cid,), field=f))
    for cid in by_id:
        if cid not in expected:
            errors.append(ValidationError(KIND_ORPHAN, "characters", (cid,)))
    return errors

def validate_site(site: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for f in REQUIRED_SITE_FIELDS:
        if _missing_or_blank(site, f):
            errors.append(ValidationError(KIND_MALFORMED, "site", ("singleton",), field=f))
    return errors

def collect_npcs_from_log(session_log: dict, site: dict) -> list[str]:
    """Return the canonical list of NPC names whose epithets must be authored.
    Priority: per-entry `npcs` field; fallback: site.known_npcs allowlist.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for entry in session_log.get("entries", []):
        for n in entry.get("npcs", []):
            if n not in seen_set:
                seen.append(n)
                seen_set.add(n)
    if not seen:
        for n in site.get("known_npcs", []):
            if n not in seen_set:
                seen.append(n)
                seen_set.add(n)
    return seen

BESTIARY_GLOB = ".claude/ext/5etools-src/data/bestiary/bestiary-*.json"

# Source priority: XMM (5e 2024 Monster Manual) first, then originals, then minor.
_BESTIARY_SOURCE_PRIORITY = ["XMM", "MM", "MPMM", "VRGR", "FTD", "MTF", "VGM", "ToA"]

@functools.lru_cache(maxsize=1)
def _load_bestiary() -> dict[str, dict]:
    """Return name (lowercased) -> best entry across all bestiary files."""
    import glob as _glob
    by_name: dict[str, dict] = {}
    files = sorted(_glob.glob(str(REPO_ROOT / BESTIARY_GLOB)))
    if not files:
        return by_name

    def priority(src: str) -> int:
        try:
            return _BESTIARY_SOURCE_PRIORITY.index(src)
        except ValueError:
            return len(_BESTIARY_SOURCE_PRIORITY)

    for fpath in files:
        with open(fpath) as f:
            content = json.load(f)
        for m in content.get("monster", []):
            name = m.get("name", "")
            if not name:
                continue
            key = name.casefold()
            existing = by_name.get(key)
            if existing is None or priority(m.get("source", "")) < priority(existing.get("source", "")):
                # Normalize type to a string (it can be "humanoid" or {"type": "humanoid", "tags": [...]}).
                t = m.get("type", "")
                if isinstance(t, dict):
                    t = t.get("type", "")
                by_name[key] = {
                    "name": name,
                    "type": t,
                    "cr": m.get("cr"),
                    "source": m.get("source", ""),
                }
    return by_name

@functools.lru_cache(maxsize=2048)
def bestiary_lookup(creature: str) -> Optional[dict]:
    """Return {name, type, cr, source} for a creature, or None."""
    return _load_bestiary().get(creature.casefold())

def validate_all(data: dict, authored: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_kills(data["party"], authored["kills"]))
    errors.extend(validate_sessions(data["session_log"], authored["sessions"]))
    errors.extend(validate_chapters(data["session_log"], authored["chapters"]))
    npcs = collect_npcs_from_log(data["session_log"], authored["site"])
    errors.extend(validate_npcs(npcs, authored["npcs"]))
    errors.extend(validate_characters(data["party"], authored["characters"]))
    errors.extend(validate_site(authored["site"]))
    return errors

def load_data(data_dir: Path) -> dict:
    """Load upstream data files. Returns dict with party, dice_rolls, session_log."""
    data_dir = Path(data_dir)
    with (data_dir / "party.json").open() as f:
        party = json.load(f)
    with (data_dir / "session-log.json").open() as f:
        session_log = json.load(f)

    dice_paths = sorted(data_dir.glob("dicex-rolls-*.json"))
    dice_rolls = [json.loads(p.read_text()) for p in dice_paths]

    # Normalize party: upstream may emit a bare list; wrap it for downstream validators.
    if isinstance(party, list):
        party = {"members": party}

    # Scrub real-name data from party members at the edge.
    # Upstream `id` may embed a real player first name (e.g. "simon-fighter"); the site slug
    # is derivable from the character `name` field's first word, lowercased. `player` carries
    # the real first name and must never reach downstream code, the authored store, or git.
    scrubbed_members = []
    for m in party.get("members", []):
        m = dict(m)
        if m.get("name"):
            m["id"] = m["name"].split()[0].lower()
        m.pop("player", None)
        scrubbed_members.append(m)
    party = dict(party)
    party["members"] = scrubbed_members

    # Normalize session-log: upstream uses "id" and "realDate"; validators expect "session" and "date".
    normalized_entries = []
    for e in session_log.get("entries", []):
        ne = dict(e)
        if "session" not in ne and "id" in ne:
            ne["session"] = ne["id"]
        if "date" not in ne and "realDate" in ne:
            ne["date"] = ne["realDate"]
        normalized_entries.append(ne)
    session_log = dict(session_log)
    session_log["entries"] = normalized_entries

    return {
        "party": party,
        "dice_rolls": dice_rolls,  # list of file contents (each itself a list)
        "session_log": session_log,
    }

def load_authored(repo_root: Path) -> dict:
    """Load authored/*.json. Missing files become empty defaults so build can report MISSING errors."""
    auth_dir = Path(repo_root) / "authored"
    def read_or(default, name):
        p = auth_dir / name
        return json.loads(p.read_text()) if p.exists() else default
    return {
        "kills": read_or([], "kills.json"),
        "sessions": read_or([], "sessions.json"),
        "chapters": read_or([], "chapters.json"),
        "npcs": read_or([], "npcs.json"),
        "characters": read_or([], "characters.json"),
        "site": read_or({}, "site.json"),
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Render index.html.")
    parser.add_argument("--data-dir", default=str(REPO_ROOT),
                        help="Directory containing party.json etc.")
    parser.add_argument("--out", default=str(REPO_ROOT / "index.html"),
                        help="Output HTML path.")
    parser.add_argument("--strict", action="store_true",
                        help="Abort on any validation error (default: True).")
    args = parser.parse_args()

    print(f"build.py: starting (data_dir={args.data_dir})")
    data = load_data(Path(args.data_dir))
    authored = load_authored(REPO_ROOT)
    party_count = len(data['party']) if isinstance(data['party'], list) else len(data['party'].get('members', []))
    session_count = len(data['session_log'].get('entries', []))
    dice_count = sum(len(r) for r in data['dice_rolls'])
    print(f"build.py: loaded {party_count} party members, "
          f"{dice_count} dice events, "
          f"{session_count} session entries")
    print(f"build.py: authored kills={len(authored['kills'])} sessions={len(authored['sessions'])} "
          f"npcs={len(authored['npcs'])} chapters={len(authored['chapters'])}")
    errors = validate_all(data, authored)
    if errors:
        print(f"build.py: {len(errors)} validation error(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("build.py: validation passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
