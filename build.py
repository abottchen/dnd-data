#!/usr/bin/env python3
"""build.py — render index.html from data + authored store + templates.

Exit codes:
  0  render succeeded
  1  validation errors; nothing written
  2  internal error (template syntax, file read failure, bestiary miss)
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

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

def load_data(data_dir: Path) -> dict:
    """Load upstream data files. Returns dict with party, dice_rolls, session_log."""
    data_dir = Path(data_dir)
    with (data_dir / "party.json").open() as f:
        party = json.load(f)
    with (data_dir / "session-log.json").open() as f:
        session_log = json.load(f)

    dice_paths = sorted(data_dir.glob("dicex-rolls-*.json"))
    dice_rolls = [json.loads(p.read_text()) for p in dice_paths]

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
    return 0

if __name__ == "__main__":
    sys.exit(main())
