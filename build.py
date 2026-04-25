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
