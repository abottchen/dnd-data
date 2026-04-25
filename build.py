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
from statistics import pstdev
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
REQUIRED_CHAR_FIELDS = ("epithet", "reliquary_header", "constellation_epithet",
                         "distinction_title", "distinction_subtitle", "distinction_detail")
REQUIRED_SITE_FIELDS = ("intro_epithet", "intro_meta", "page_title", "page_subtitle")

# Fields that are list-typed and legitimately may be empty lists (not MALFORMED).
_LIST_EMPTY_OK = frozenset({"silent_roll"})

def _missing_or_blank(entry: dict, field: str) -> bool:
    v = entry.get(field)
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, list) and len(v) == 0 and field not in _LIST_EMPTY_OK:
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
        if first not in chapter_sessions:
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

@functools.lru_cache(maxsize=2048)
def bestiary_lookup(creature: str) -> Optional[dict]:
    """Return {name, type, cr, source, hasToken, token, token_url} for a creature, or None."""
    return _load_bestiary().get(creature.casefold())

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

def compute_trials(party: dict) -> dict:
    """Return per-character trials dict + party-wide aggregates needed by templates."""
    members = party.get("members", [])
    per_char: dict[str, dict] = {}

    for m in members:
        cid = m["id"]
        kills = m.get("kills", [])
        xp = sum(_kill_xp(k["creature"]) for k in kills)
        kill_count = len(kills)

        # Means of Ending: most common method; tiebreak highest CR; then alphabetical.
        method_counter = Counter(k["method"] for k in kills)
        if method_counter:
            top_n = method_counter.most_common(1)[0][1]
            tied = [m_ for m_, n in method_counter.items() if n == top_n]
            if len(tied) == 1:
                means = tied[0]
            else:
                # Tiebreak by max CR among kills using that method
                def max_cr_for_method(method):
                    crs = [_kill_cr(k["creature"]) for k in kills if k["method"] == method]
                    return max((XP_BY_CR.get(c, 0) for c in crs), default=0)
                tied.sort(key=lambda mm: (-max_cr_for_method(mm), mm.lower()))
                means = tied[0]
            means_n = top_n
        else:
            means = "—"
            means_n = 0

        # Kinds Slain: distinct creature types
        type_counter: Counter = Counter()
        for k in kills:
            info = bestiary_lookup(k["creature"])
            if info:
                type_counter[info["type"]] += 1
        kinds = sorted(type_counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))

        per_char[cid] = {
            "xp": xp,
            "kill_count": kill_count,
            "means": means,
            "means_n": means_n,
            "kinds": [{"type": t, "count": c} for t, c in kinds],
            "kinds_count": len(kinds),
        }

    party_xp = sum(c["xp"] for c in per_char.values())
    party_kills = sum(c["kill_count"] for c in per_char.values())

    for cid, c in per_char.items():
        c["xp_pct"] = round(c["xp"] / party_xp * 100) if party_xp else 0
        c["kill_pct"] = round(c["kill_count"] / party_kills * 100) if party_kills else 0

    return {
        "per_char": per_char,
        "party_xp": party_xp,
        "party_kills": party_kills,
    }

def _short_date(iso_date: str) -> str:
    """'2026-04-23' -> '23 APR 2026'."""
    from datetime import date
    d = date.fromisoformat(iso_date)
    return d.strftime("%d %b %Y").upper()

def compute_sessions_chart(party: dict) -> dict:
    """Bars + tooltip-ready KILLS_BY_CHAR_SESSION map."""
    members = party.get("members", [])

    # Distinct sorted session dates across the party
    all_dates = sorted({k["date"] for m in members for k in m.get("kills", [])})

    # Per-char per-date counts
    per_char_per_date: dict[str, dict[str, list[dict]]] = {}
    for m in members:
        cid = m["id"]
        bucket: dict[str, list[dict]] = {d: [] for d in all_dates}
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"]) or {}
            bucket[k["date"]].append({
                "creature": k["creature"],
                "method": k["method"],
                "token_url": info.get("token_url"),
            })
        per_char_per_date[cid] = bucket

    # Party max per (char,session) count
    party_max = max(
        (len(per_char_per_date[m["id"]][d]) for m in members for d in all_dates),
        default=0,
    )
    scale = max(party_max, 3)

    per_char_bars: dict[str, list[dict]] = {}
    for m in members:
        cid = m["id"]
        bars = []
        for d in all_dates:
            kl = per_char_per_date[cid][d]
            n = len(kl)
            bars.append({
                "date": d,
                "label": _short_date(d),
                "count": n,
                "height_pct": round(n / scale * 100),
                "zero": n == 0,
                "kills": kl,
            })
        per_char_bars[cid] = bars

    return {
        "sessions": [{"date": d, "label": _short_date(d)} for d in all_dates],
        "per_char": per_char_bars,
        "party_max": party_max,
        "scale": scale,
    }

def compute_fortune(events: list) -> dict:
    """Compute fortune stats for one character from their flattened roll events.

    events: list of {"rolls": [die...], "total": N, "notation": str, "date": "YYYY-MM-DD"}.
    Each die is {"type": "d20"/"d6"/..., "value": N, "dropped"?: bool, "isExplosion"?: bool}.
    """
    physical_d20s: list[int] = []
    kept_d20s: list[int] = []
    heaviest = {"total": 0, "notation": ""}

    for ev in events:
        for d in ev.get("rolls", []):
            if d.get("type") == "d20":
                v = int(d["value"])
                physical_d20s.append(v)
                if not d.get("dropped"):
                    kept_d20s.append(v)
        # Heaviest blow: pure damage rolls only. Excludes any event containing a d20
        # (attack rolls, saves, ability checks) or a d100 (percentile rolls in this
        # dice system pair d100 with a d10 for the units digit, so the d10 alone
        # is not a damage signal).
        types_in_event = {d.get("type") for d in ev.get("rolls", [])}
        is_damage = (not (types_in_event & {"d20", "d100"})
                     and bool(types_in_event - {"mod"}))
        if is_damage and ev.get("total", 0) > heaviest["total"]:
            heaviest = {"total": ev["total"], "notation": ev.get("notation", "")}

    avg = round(sum(kept_d20s) / len(kept_d20s), 1) if kept_d20s else 0.0
    sd = round(pstdev(kept_d20s), 1) if len(kept_d20s) >= 2 else 0.0

    return {
        "rolls_total": len(events),
        "physical_d20s_count": len(physical_d20s),
        "kept_d20s_count": len(kept_d20s),
        "avg": avg,
        "sd": sd,
        "crits": sum(1 for v in kept_d20s if v == 20),
        "fumbles": sum(1 for v in kept_d20s if v == 1),
        "heaviest": heaviest,
        "physical_d20s": physical_d20s,  # for histogram
        "events": events,                # for Other Dice and tooltips
    }

def compute_d20_histogram(physical_d20s: list[int], party_max: int) -> list[dict]:
    counts = Counter(physical_d20s)
    scale = max(party_max, 3)
    bars = []
    for v in range(1, 21):
        n = counts.get(v, 0)
        bars.append({
            "value": v,
            "count": n,
            "height_pct": round(n / scale * 100) if scale else 0,
            "zero": n == 0,
        })
    return bars

def compute_party_d20_max(all_physicals_by_player: dict[str, list[int]]) -> int:
    """Per-value max across the party (incl. GM)."""
    party_max = 0
    for v in range(1, 21):
        s = sum(physicals.count(v) for physicals in all_physicals_by_player.values())
        if s > party_max:
            party_max = s
    return party_max

def compute_patron_die(fortune_by_char: dict, party: dict) -> list[dict]:
    """Party-wide d20 histogram, excluding the GM."""
    physicals: list[int] = []
    for m in party.get("members", []):
        if m["id"] == "gm":
            continue
        physicals.extend(fortune_by_char[m["id"]]["physical_d20s"])
    counts = Counter(physicals)
    party_max = max((counts.get(v, 0) for v in range(1, 21)), default=0)
    return compute_d20_histogram(physicals, party_max=party_max)

def compute_other_dice(events: list) -> list[dict]:
    """Per-die-type rows: d4..d12+, with dot positions and avg/best."""
    by_die: dict[str, list[dict]] = {}
    for ev in events:
        date = ev.get("date", "")
        # Percentile rolls in this dice system pair a d100 with a d10 for the
        # units digit. Drop the units d10 so it doesn't pollute the d10 row.
        types_in_event = {d.get("type") for d in ev.get("rolls", [])}
        skip_units_d10 = "d100" in types_in_event
        for d in ev.get("rolls", []):
            t = d.get("type")
            if t in (None, "d20", "d100", "mod"):
                continue
            if t == "d10" and skip_units_d10:
                continue
            if d.get("dropped"):
                continue
            v = int(d["value"])
            face = int(t.lstrip("d"))
            # d10 quirk: source stores 10 as value: 0
            if face == 10 and v == 0:
                v = 10
            by_die.setdefault(t, []).append({"value": v, "face": face, "date": date})

    rows = []
    for die_type in sorted(by_die.keys(), key=lambda x: int(x.lstrip("d"))):
        entries = by_die[die_type]
        values = [e["value"] for e in entries]
        face = entries[0]["face"]
        N = len(values)
        if N == 1:
            xs = [189]
        else:
            xs = [round(24 + i / (N - 1) * 330) for i in range(N)]
        ys = [round(56 - (v - 1) / (face - 1) * 52) for v in values]
        rows.append({
            "die": die_type,
            "count": N,
            "avg": round(sum(values) / N, 1),
            "best": max(values),
            "dots": [{"x": x, "y": y, "value": v, "date": e["date"]}
                     for x, y, v, e in zip(xs, ys, values, entries)],
        })
    return rows

SKILL_DISPLAY = {
    "acrobatics": "Acrobatics",
    "animalHandling": "Animal Handling",
    "arcana": "Arcana",
    "athletics": "Athletics",
    "deception": "Deception",
    "history": "History",
    "insight": "Insight",
    "intimidation": "Intimidation",
    "investigation": "Investigation",
    "medicine": "Medicine",
    "nature": "Nature",
    "perception": "Perception",
    "performance": "Performance",
    "persuasion": "Persuasion",
    "religion": "Religion",
    "sleightOfHand": "Sleight of Hand",
    "stealth": "Stealth",
    "survival": "Survival",
}

_PROF_RANK = {"expertise": 3, "full": 2, "half": 1, "none": 0}

def compute_best_skill(member: dict) -> dict | None:
    """Return {'name': 'Persuasion', 'mod': 5} for the member's strongest skill.
    Tie-break: higher proficiency rank, then alphabetical skill key."""
    skills = member.get("skills") or {}
    if not skills:
        return None
    def sort_key(item):
        key, info = item
        return (info.get("mod", 0),
                _PROF_RANK.get(info.get("prof", "none"), 0),
                -ord(key[0]) if key else 0)
    best_key, best = max(skills.items(), key=sort_key)
    return {
        "name": SKILL_DISPLAY.get(best_key, best_key),
        "mod": best.get("mod", 0),
    }

def compute_constellation(party: dict, fortune_by_char: dict, trials: dict) -> dict:
    """Position each (non-GM) character by (xp, total rolls). Excludes GM."""
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    party_max_xp = max((trials["per_char"][m["id"]]["xp"] for m in members), default=0)
    party_max_rolls = max(
        (fortune_by_char[m["id"]]["rolls_total"] for m in members), default=0
    )

    stars = []
    for m in members:
        cid = m["id"]
        xp = trials["per_char"][cid]["xp"]
        rolls = fortune_by_char[cid]["rolls_total"]
        left = round(xp / party_max_xp * 92 + 4) if party_max_xp else 4
        top = round(96 - rolls / party_max_rolls * 92) if party_max_rolls else 96
        stars.append({"id": cid, "left_pct": left, "top_pct": top})

    return {
        "stars": stars,
        "party_max_xp": party_max_xp,
        "party_max_rolls": party_max_rolls,
        "mid_xp": (party_max_xp + 1) // 2,
        "mid_rolls": (party_max_rolls + 1) // 2,
    }

def compute_bestiary(party: dict) -> list[dict]:
    """Group every kill by creature type, then by creature name within type."""
    by_type: dict[str, dict[str, int]] = {}
    token_by_name: dict[str, Optional[str]] = {}
    for m in party.get("members", []):
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"])
            if not info:
                continue
            t = info["type"]
            n = info["name"]
            by_type.setdefault(t, {}).setdefault(n, 0)
            by_type[t][n] += 1
            token_by_name.setdefault(n, info.get("token_url"))

    groups = []
    for t in by_type.keys():
        creatures = sorted(by_type[t].items(), key=lambda kv: (-kv[1], kv[0].lower()))
        groups.append({
            "type": t,
            "total": sum(c for _, c in creatures),
            "creatures": [{"name": n, "count": c, "token_url": token_by_name.get(n)}
                          for n, c in creatures],
        })
    groups.sort(key=lambda g: (-g["total"], g["type"].lower()))
    return groups

def compute_company_ledger(party: dict, dice_files: list, session_log: dict, trials: dict, fortune_by_char: dict) -> dict:
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    total_xp = sum(trials["per_char"][m["id"]]["xp"] for m in members)
    total_kills = sum(trials["per_char"][m["id"]]["kill_count"] for m in members)
    total_rolls = sum(fortune_by_char[m["id"]]["rolls_total"] for m in members)
    total_d20s = sum(fortune_by_char[m["id"]]["kept_d20s_count"] for m in members)
    sessions_kept = len(session_log.get("entries", []))

    return {
        "total_xp": total_xp,
        "total_kills": total_kills,
        "total_rolls": total_rolls,
        "total_d20s": total_d20s,
        "sessions_kept": sessions_kept,
    }

FORGOTTEN_REALMS_MONTHS = [
    "Hammer", "Alturiak", "Ches", "Tarsakh", "Mirtul", "Kythorn",
    "Flamerule", "Eleasis", "Eleint", "Marpenoth", "Uktar", "Nightal",
]

def compute_chronicle(session_log: dict, sessions_authored: list, chapters_authored: list, party: dict) -> dict:
    entries = session_log.get("entries", [])
    auth_session_by_id = {a["session"]: a for a in sessions_authored}
    chapter_by_starts = {a["starts_at_session"]: a for a in chapters_authored if "starts_at_session" in a}

    # Determine chapter spans: every chapter_marker opens a chapter; first session implicitly opens one.
    chapter_starts: list[str] = []
    for e in entries:
        if not chapter_starts or e.get("chapter_marker"):
            chapter_starts.append(e["session"])

    # Map each session to its chapter's starting session
    session_to_chapter: dict[str, str] = {}
    current = None
    for e in entries:
        if e["session"] in chapter_starts:
            current = e["session"]
        session_to_chapter[e["session"]] = current

    # Per-date -> [kill record] for portrait tallies + pip data. Each record carries
    # the killer (id/name/image) and the creature so chronicle pips can render
    # creature tokens with a tooltip naming the killer + method.
    party_kills_by_date: dict[str, list[dict]] = {}
    for m in party.get("members", []):
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"]) or {}
            party_kills_by_date.setdefault(k["date"], []).append({
                "killer_id": m["id"],
                "killer_name": m.get("name", m["id"]).split()[0],
                "killer_image": m.get("image", ""),
                "creature": k["creature"],
                "method": k["method"],
                "date": k["date"],
                "date_label": _short_date(k["date"]),
                "token_url": info.get("token_url"),
            })

    chapters = []
    for idx, start_id in enumerate(chapter_starts, start=1):
        ch = chapter_by_starts.get(start_id, {})
        sess_in_chapter = [e for e in entries if session_to_chapter[e["session"]] == start_id]
        # Flatten chapter-level kill records in chronological session order.
        chapter_kill_pips: list[dict] = []
        for e in sess_in_chapter:
            chapter_kill_pips.extend(party_kills_by_date.get(e["date"], []))

        chapters.append({
            "label": _to_roman(idx),
            "title": ch.get("title", ""),
            "epigraph": ch.get("epigraph", ""),
            "starts_at": start_id,
            "session_count": len(sess_in_chapter),
            "kill_count": len(chapter_kill_pips),
            "kill_pips": chapter_kill_pips,
            "sessions": [_render_session(e, auth_session_by_id, party_kills_by_date)
                         for e in sess_in_chapter],
        })

    # Regnal rail: (year, month) -> session count, ordered by Forgotten Realms month order.
    months_by_year: dict[str, dict[str, int]] = {}
    for e in entries:
        iu_m = e.get("iu_month") or "Kythorn"
        iu_y = str(e.get("iu_year") or "1494")
        year = f"{iu_y} DR" if not iu_y.endswith("DR") else iu_y
        months_by_year.setdefault(year, {})
        months_by_year[year][iu_m] = months_by_year[year].get(iu_m, 0) + 1
    rail = []
    for year, ms in months_by_year.items():
        ordered = [m for m in FORGOTTEN_REALMS_MONTHS if m in ms]
        for m in ordered:
            rail.append({"month": m, "year": year, "count": ms[m]})

    return {"chapters": chapters, "rail": rail}

def _render_session(entry: dict, auth_by_id: dict, kills_by_date: dict) -> dict:
    sess_id = entry["session"]
    auth = auth_by_id.get(sess_id, {})
    kills = kills_by_date.get(entry["date"], [])
    iu_day = entry.get("iu_day", "")
    iu_month = entry.get("iu_month", "Kythorn")
    return {
        "id": sess_id,
        "title": auth.get("title", ""),
        "summary": auth.get("summary", ""),
        "silent_roll": auth.get("silent_roll", []),
        "real_date": entry["date"],
        "real_date_label": _short_date(entry["date"]),
        "iu_date": f"{iu_day} {iu_month}".strip(),
        "kills_count": len(kills),
        "kill_pips": kills,
    }

def compute_distinctions(party: dict, characters_authored: list) -> list[dict]:
    """Pair each non-GM character with their authored distinction crown."""
    by_id = {a["id"]: a for a in characters_authored}
    rows = []
    for m in party.get("members", []):
        if m["id"] == "gm":
            continue
        a = by_id.get(m["id"], {})
        rows.append({
            "id": m["id"],
            "name": m["id"].title(),
            "title": a.get("distinction_title", ""),
            "subtitle": a.get("distinction_subtitle", ""),
            "detail": a.get("distinction_detail", ""),
        })
    return rows

def validate_distinction_uniqueness(authored: list) -> list[ValidationError]:
    """Distinction titles must be unique across the party."""
    errors: list[ValidationError] = []
    seen: dict[str, str] = {}
    for a in authored:
        t = a.get("distinction_title", "").strip().lower()
        if not t:
            continue
        if t in seen:
            errors.append(ValidationError(
                KIND_MALFORMED, "characters", (a["id"],),
                field=f"distinction_title duplicates '{seen[t]}'"
            ))
        else:
            seen[t] = a["id"]
    return errors

def validate_all(data: dict, authored: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_kills(data["party"], authored["kills"]))
    errors.extend(validate_sessions(data["session_log"], authored["sessions"]))
    errors.extend(validate_chapters(data["session_log"], authored["chapters"]))
    npcs = collect_npcs_from_log(data["session_log"], authored["site"])
    errors.extend(validate_npcs(npcs, authored["npcs"]))
    errors.extend(validate_characters(data["party"], authored["characters"]))
    errors.extend(validate_distinction_uniqueness(authored["characters"]))
    errors.extend(validate_site(authored["site"]))
    return errors

_ROMAN_PAIRS = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
                (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]

def _to_roman(n: int) -> str:
    out = ""
    for val, s in _ROMAN_PAIRS:
        while n >= val:
            out += s
            n -= val
    return out

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

def load_data(data_dir: Path) -> dict:
    """Load upstream data files. Returns dict with party, dice_rolls, session_log."""
    data_dir = Path(data_dir)
    with (data_dir / "party.json").open() as f:
        party = json.load(f)
    with (data_dir / "session-log.json").open() as f:
        session_log = json.load(f)

    dice_paths = sorted(data_dir.glob("dicex-rolls-*.json"))
    dice_rolls = [json.loads(p.read_text()) for p in dice_paths]

    # Build rolls_by_slug from dice files by mapping real-name players to site slugs.
    # Upstream shape: {"players": {uuid: {"name": str, "rolls": [event]}}, "exportedAt": str}.
    # Each event has: {"dice": [die...], "total": N, "notation": str, "timestamp": str}.
    # We normalize dice->rolls (to match compute_fortune's expected shape) and extract a date.
    dice_player_map = _load_dice_player_map()
    unmapped_players: set[str] = set()
    rolls_by_slug: dict[str, list[dict]] = {}
    for f in dice_rolls:
        if not isinstance(f, dict) or "players" not in f:
            continue
        for uuid, pdata in f.get("players", {}).items():
            if not isinstance(pdata, dict):
                continue
            upstream_name = pdata.get("name", "")
            slug = dice_player_map.get(upstream_name)
            if slug is None:
                unmapped_players.add(upstream_name)
                continue
            for ev in pdata.get("rolls", []):
                ev2 = dict(ev)
                ev2["rolls"] = ev2.pop("dice", [])
                ts = ev2.get("timestamp", "")
                ev2["date"] = ts[:10] if ts else ""
                rolls_by_slug.setdefault(slug, []).append(ev2)

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

    # Normalize session-log entries to the shape downstream expects:
    #   session: Roman numeral from upstream `day` (1 -> I, 2 -> II, ...).
    #   date: ISO YYYY-MM-DD from upstream `realDate` MM/DD/YYYY.
    #   iu_day, iu_month, iu_year: snake-case from camelCase iuDay/iuMonth/iuYear.
    #   chapter_marker: True when the upstream `text` contains an explicit chapter
    #     boundary marker authored by the user (e.g. "--- Chapter II ---" or
    #     "Chapter II begins."). First session implicitly opens Chapter I.
    # Session I lacks in-universe date fields upstream; they get backfilled here,
    # per the design rule: never edit upstream data, fill the gap at render time.
    normalized_entries = []
    for e in session_log.get("entries", []):
        ne = dict(e)
        if "session" not in ne and "day" in ne:
            try:
                ne["session"] = _to_roman(int(ne["day"]))
            except (ValueError, TypeError):
                ne["session"] = str(ne["day"])
        if "date" not in ne and "realDate" in ne:
            ne["date"] = _mdy_to_iso(ne["realDate"])
        for camel, snake in (("iuDay", "iu_day"), ("iuMonth", "iu_month"), ("iuYear", "iu_year")):
            if camel in ne and snake not in ne:
                ne[snake] = ne[camel]
        # Backfill Session I's in-universe date (absent upstream).
        if ne.get("session") == "I":
            ne.setdefault("iu_day", "1")
            ne.setdefault("iu_month", "Kythorn")
            ne.setdefault("iu_year", "1494")
        text = ne.get("text", "")
        if _has_chapter_marker(text):
            ne["chapter_marker"] = True
        normalized_entries.append(ne)
    session_log = dict(session_log)
    session_log["entries"] = normalized_entries

    return {
        "party": party,
        "dice_rolls": dice_rolls,  # raw file contents; downstream should prefer rolls_by_slug
        "rolls_by_slug": rolls_by_slug,
        "unmapped_players": sorted(unmapped_players),
        "session_log": session_log,
    }

DICE_PLAYER_MAP_PATH = Path(".claude/skills/hydrate-ledger/dice-players.json")

def _load_dice_player_map() -> dict[str, str]:
    """Read the gitignored dice-players mapping (real-name/handle -> site slug).
    Empty dict if the file is missing; callers must surface unmapped players as errors."""
    path = REPO_ROOT / DICE_PLAYER_MAP_PATH
    if not path.exists():
        return {}
    try:
        content = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    m = content.get("mapping", {})
    return {k: v for k, v in m.items() if isinstance(k, str) and isinstance(v, str)}

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

def compute_all(data: dict, authored: dict) -> dict:
    party = data["party"]
    session_log = data["session_log"]
    rolls_by_slug = data.get("rolls_by_slug", {})

    trials = compute_trials(party)
    fortune_ids = [m["id"] for m in party.get("members", [])] + ["gm"]
    fortune_by_char = {cid: compute_fortune(rolls_by_slug.get(cid, []))
                       for cid in fortune_ids}
    sessions_chart = compute_sessions_chart(party)

    # Histograms
    all_physicals_by_player = {cid: f["physical_d20s"] for cid, f in fortune_by_char.items()}
    party_max = compute_party_d20_max(all_physicals_by_player)
    histograms = {cid: compute_d20_histogram(f["physical_d20s"], party_max)
                  for cid, f in fortune_by_char.items()}
    other_dice = {cid: compute_other_dice(f["events"]) for cid, f in fortune_by_char.items()}

    constellation = compute_constellation(party, fortune_by_char, trials)
    bestiary = compute_bestiary(party)
    chronicle = compute_chronicle(session_log, authored["sessions"], authored["chapters"], party)
    ledger = compute_company_ledger(party, data.get("dice_rolls", []), session_log, trials, fortune_by_char)
    distinctions = compute_distinctions(party, authored["characters"])
    patron = compute_patron_die(fortune_by_char, party)
    best_skill_by_id = {m["id"]: compute_best_skill(m) for m in party.get("members", [])}

    char_auth_by_id = {a["id"]: a for a in authored["characters"]}

    return {
        "site": authored["site"],
        "party": party,
        "characters_authored": char_auth_by_id,
        "kills_authored_by_key": {
            kill_key(k["character"], k["date"], k["creature"], k["method"]): k
            for k in authored["kills"]
        },
        "trials": trials,
        "fortune": fortune_by_char,
        "sessions_chart": sessions_chart,
        "histograms": histograms,
        "other_dice": other_dice,
        "constellation": constellation,
        "bestiary": bestiary,
        "chronicle": chronicle,
        "ledger": ledger,
        "distinctions": distinctions,
        "patron_die": patron,
        "best_skill_by_id": best_skill_by_id,
        "npcs_by_allegiance": _split_npcs(authored["npcs"]),
    }

def _split_npcs(npcs: list) -> dict:
    return {
        "with": [n for n in npcs if n.get("allegiance") == "with"],
        "against": [n for n in npcs if n.get("allegiance") == "against"],
    }

def compute_cr_label(creature: str) -> str:
    info = bestiary_lookup(creature)
    if not info:
        return "?"
    cr = info["cr"]
    if isinstance(cr, dict):
        cr = cr.get("cr")
    cr = str(cr)
    return {"1/8": "&frac18;", "1/4": "&frac14;", "1/2": "&frac12;"}.get(cr, cr)

def render_page(context: dict, templates_dir: Path, out_path: Path) -> None:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.filters["short_date"] = _short_date
    env.filters["roman"] = _to_roman
    env.filters["cr_label"] = compute_cr_label
    template = env.get_template("base.html")
    html = template.render(**context)
    out_path.write_text(html)

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

    templates_dir = REPO_ROOT / "templates"
    base_template = templates_dir / "base.html"
    if not base_template.exists():
        print(f"build.py: no templates/base.html yet; skipping render (compute only). "
              f"Create templates first (plan tasks 18-24).")
        return 0

    try:
        context = compute_all(data, authored)
        render_page(context, templates_dir, Path(args.out))
    except Exception as e:
        print(f"build.py: render failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"build.py: rendered {args.out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
