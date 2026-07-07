"""bestiary.py — 5etools bestiary lookup + XP/CR tables.

Reads the local 5etools bestiary source data (via the BESTIARY_GLOB under
.claude/ext/) to resolve a creature name to its type, CR, source, and token
URL, and owns the CR→XP table used by the trial/fortune computes.
"""
from __future__ import annotations
import functools
import json
from typing import Optional

from .paths import REPO_ROOT

BESTIARY_GLOB = ".claude/ext/5etools-src/data/bestiary/bestiary-*.json"

# Source priority: XMM (5e 2024 Monster Manual) first, then originals, then minor.
_BESTIARY_SOURCE_PRIORITY = ["XMM", "MM", "MPMM", "VRGR", "FTD", "MTF", "VGM", "ToA"]

TOKEN_URL_BASE = "https://5e.tools/img/bestiary/tokens"

def _name_to_token_name(name: str) -> str:
    """Mirror 5etools js/parser.js Parser.nameToTokenName: NFD normalize, strip
    combining marks, replace Æ/æ → AE/ae, drop double quotes. Caller URL-encodes."""
    import unicodedata
    out = unicodedata.normalize("NFD", name)
    out = "".join(c for c in out if not unicodedata.combining(c))
    out = out.replace("Æ", "AE").replace("æ", "ae").replace('"', "")
    return out

def _creature_token_url(entry: dict) -> Optional[str]:
    """Return the 5e.tools token URL for a bestiary entry, or None when the
    entry has no token. Mirrors Renderer.monster.getTokenUrl in render.js."""
    if not entry.get("hasToken"):
        return None
    from urllib.parse import quote
    tok = entry.get("token") or {}
    source = tok.get("source") or entry.get("source", "")
    name = tok.get("name") or entry.get("name", "")
    if not source or not name:
        return None
    return f"{TOKEN_URL_BASE}/{source}/{quote(_name_to_token_name(name))}.webp"

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
                entry = {
                    "name": name,
                    "type": t,
                    "cr": m.get("cr"),
                    "source": m.get("source", ""),
                    "hasToken": bool(m.get("hasToken")),
                    "token": m.get("token"),
                }
                entry["token_url"] = _creature_token_url(entry)
                by_name[key] = entry
    return by_name

# Homebrew/named NPCs that run on a standard stat block. Maps the NPC's
# display name -> the 5etools creature whose type, CR, source, and token should
# stand in for them (e.g. the Camp Vengeance scout "Wulf Rygor" is a Scout).
# The NPC's own name is preserved on lookup; only the mechanical fields are
# borrowed, so the bestiary and chronicle still read "Wulf Rygor". This mirrors
# the in-data reskin convention (e.g. recording a "yellow musk guard" kill under
# its real "Yellow Musk Zombie" stat block) for cases where the fiction name
# must survive on the page.
CUSTOM_NPC_STATBLOCKS = {
    "Wulf Rygor": "Scout",
    "Queen Grabstab": "Goblin Boss",
}

# Explicit pip-icon overrides for named NPCs. Maps display name -> an image URL
# (e.g. adventure art). Used only for the kill pip, where it takes precedence
# over any stat-block token. An entry here does NOT by itself enter the creature
# into the "Kinds Slain" tally or grant CR/XP — that requires a real bestiary
# name or a CUSTOM_NPC_STATBLOCKS entry. Queen Grabstab has both: she borrows the
# Goblin Boss stat block (above) for the bestiary/XP, but keeps her own portrait
# on the pip via this table.
CUSTOM_CREATURE_TOKENS = {
    "Queen Grabstab": "https://5e.tools/img/adventure/ToA/048-0322.webp",
}

@functools.lru_cache(maxsize=2048)
def bestiary_lookup(creature: str) -> Optional[dict]:
    """Return {name, type, cr, source, hasToken, token, token_url} for a creature, or None.

    Falls back to CUSTOM_NPC_STATBLOCKS for named NPCs that borrow a standard
    stat block; the returned entry keeps the NPC's display name."""
    by_name = _load_bestiary()
    entry = by_name.get(creature.casefold())
    if entry is not None:
        return entry
    statblock = CUSTOM_NPC_STATBLOCKS.get(creature)
    if statblock:
        base = by_name.get(statblock.casefold())
        if base is not None:
            aliased = dict(base)
            aliased["name"] = creature
            return aliased
    return None

XP_BY_CR = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100,
    "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800,
    "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
    "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000,
}

def xp_for_cr(cr) -> int:
    """Lookup XP. Accepts strings, ints, or 5etools-style {"cr": "1/4"} dicts."""
    if isinstance(cr, dict):
        cr = cr.get("cr")
    return XP_BY_CR.get(str(cr), 0)

def _kill_cr(kill_creature: str) -> str:
    info = bestiary_lookup(kill_creature)
    if not info:
        return "0"
    cr = info["cr"]
    if isinstance(cr, dict):
        cr = cr.get("cr")
    return str(cr)

def _kill_xp(kill_creature: str) -> int:
    return xp_for_cr(_kill_cr(kill_creature))
