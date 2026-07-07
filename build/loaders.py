"""loaders.py — source-data / authored-store / dice-map loading.

Reusable loading primitives shared by the renderer (build/render.py) and the
orchestrator slice builders: authored-prose loading, PC pronoun map, and the
dice-player substring map (with its privacy-preserving longest-first resolve).
The top-level load_data orchestration lives in build/render.py, which imports
these primitives.
"""
from __future__ import annotations
import json
from pathlib import Path

from .paths import REPO_ROOT

BUILD_DIR = REPO_ROOT / "build"

DICE_PLAYER_MAP_PATH = BUILD_DIR / "dice-players.json"
CHARACTER_PRONOUNS_PATH = BUILD_DIR / "character-pronouns.json"


def _mdy_to_iso(mdy: str) -> str:
    """'03/15/2026' -> '2026-03-15'. Returns input unchanged if it doesn't match."""
    parts = mdy.split("/")
    if len(parts) != 3:
        return mdy
    m, d, y = parts
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return mdy

def _has_chapter_marker(text: str) -> bool:
    """Detect an explicit chapter boundary marker authored in a session log entry."""
    if not text:
        return False
    low = text.lower()
    return ("--- chapter" in low) or ("chapter " in low and " begins" in low)


def load_character_pronouns() -> dict[str, str]:
    """Read the PC pronoun map (character slug -> short form like 'he/him').
    Empty dict if the file is missing; callers (the character-touching slice
    builders in build/slices.py) treat a missing entry as no signal."""
    path = CHARACTER_PRONOUNS_PATH
    if not path.exists():
        return {}
    try:
        content = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    m = content.get("pronouns", {})
    return {k: v for k, v in m.items() if isinstance(k, str) and isinstance(v, str)}


def load_dice_player_map() -> dict[str, str]:
    """Read the dice-players mapping (substring pattern -> site slug).
    Empty dict if the file is missing; callers must surface unmapped players as errors.
    Keys are first-name or handle substrings; the upstream player name from the dice
    JSON resolves via `_resolve_dice_player` (longest-pattern-first substring match)
    so the file never has to record full real names."""
    path = DICE_PLAYER_MAP_PATH
    if not path.exists():
        return {}
    try:
        content = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    m = content.get("mapping", {})
    return {k: v for k, v in m.items() if isinstance(k, str) and isinstance(v, str)}


def resolve_dice_player(upstream_name: str, mapping: dict[str, str]) -> str | None:
    """Resolve an upstream dice-roll player name to a site slug via longest-first
    substring match. Longest-first guards against pattern collisions if two
    overlapping keys ever coexist (a longer specific key shadows a shorter prefix)."""
    for pattern in sorted(mapping, key=len, reverse=True):
        if pattern and pattern in upstream_name:
            return mapping[pattern]
    return None

def load_authored(build_dir: Path) -> dict:
    """Load <build_dir>/authored/*.json. Missing files become empty defaults so build can report MISSING errors."""
    auth_dir = Path(build_dir) / "authored"
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
