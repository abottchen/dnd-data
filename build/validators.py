"""validators.py — authored-store validation.

ValidationError plus every validate_* check. Each validator compares upstream
data (party/session-log) against the authored prose store and returns a list of
ValidationError; a non-empty list gates the render in build/render.py.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

KIND_MISSING = "MISSING"
KIND_MALFORMED = "MALFORMED"
KIND_ORPHAN = "ORPHAN"

@dataclass
class ValidationError:
    kind: str
    kind_type: str
    key: tuple
    field: str | None = None

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
REQUIRED_SITE_FIELDS = ("intro_epithet", "page_title", "page_subtitle", "footnote", "gm", "road_ahead")

# Reject if still present in authored/site.json after the migration to a build-computed value.
DEAD_SITE_FIELDS = ("intro_meta",)

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
    subclass_by_id = {m["id"]: (m.get("subclass") or "").strip()
                      for m in party.get("members", [])}
    by_id = {a["id"]: a for a in authored}
    for cid in expected:
        a = by_id.get(cid)
        if a is None:
            errors.append(ValidationError(KIND_MISSING, "characters", (cid,)))
            continue
        required = REQUIRED_CHAR_FIELDS
        # The sworn-path creed is required only where there is a sworn path to
        # gloss — i.e. the member carries a subclass on their sheet.
        if subclass_by_id.get(cid):
            required = required + ("sworn_creed",)
        for f in required:
            if _missing_or_blank(a, f):
                errors.append(ValidationError(KIND_MALFORMED, "characters", (cid,), field=f))
    for cid in by_id:
        if cid not in expected:
            errors.append(ValidationError(KIND_ORPHAN, "characters", (cid,)))
    return errors

def validate_portraits(party: dict, images_dir: Path) -> list[ValidationError]:
    """Each non-GM party member's `image` must resolve to a file in site/images/."""
    errors: list[ValidationError] = []
    for member in party.get("members", []):
        if member.get("id") == "gm":
            continue
        image = member.get("image")
        if not image:
            continue
        if not (images_dir / image).exists():
            errors.append(ValidationError(
                KIND_MISSING, "portraits", (member["id"],),
                field=f"image '{image}' not found in site/images/ — add the portrait file",
            ))
    return errors

def validate_map(images_dir: Path, filename: str = "chult-map.jpg") -> list[ValidationError]:
    """The player-map derivative must exist in site/images/ (see build/mapimage.py)."""
    if (images_dir / filename).exists():
        return []
    return [ValidationError(
        KIND_MISSING, "map", (filename,),
        field=f"'{filename}' not found in site/images/ — run "
              f"`python -m build map` to build it from data/chult-player-map.jpg",
    )]

def validate_dice_player_mapping(unmapped_players: list[str]) -> list[ValidationError]:
    """Each upstream dice-roll player name must resolve to a slug via build/dice-players.json."""
    errors: list[ValidationError] = []
    for upstream in unmapped_players:
        errors.append(ValidationError(
            KIND_MISSING, "dice_player_map", (upstream,),
            field='no entry in build/dice-players.json matches this upstream player — '
                  'add a "<first-name-or-handle>": "<character-slug>" entry',
        ))
    return errors

def validate_site(site: dict, latest_session: int) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for f in REQUIRED_SITE_FIELDS:
        if _missing_or_blank(site, f):
            errors.append(ValidationError(KIND_MALFORMED, "site", ("singleton",), field=f))
    rts = site.get("refreshed_through_session")
    # Reject bools (which are ints in Python) and any non-int / out-of-range value.
    if not isinstance(rts, int) or isinstance(rts, bool) or rts < 0 or rts > latest_session:
        errors.append(ValidationError(KIND_MALFORMED, "site", ("singleton",), field="refreshed_through_session"))
    for f in DEAD_SITE_FIELDS:
        if f in site:
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

def validate_distinction_uniqueness(authored: list) -> list[ValidationError]:
    """Distinction titles AND the underlying mechanical basis atom must be
    unique across the party — no two PCs crowned on the same fact."""
    errors: list[ValidationError] = []
    seen_title: dict[str, str] = {}
    seen_atom: dict[str, str] = {}
    for a in authored:
        t = a.get("distinction_title", "").strip().lower()
        if t:
            if t in seen_title:
                errors.append(ValidationError(
                    KIND_MALFORMED, "characters", (a["id"],),
                    field=f"distinction_title duplicates '{seen_title[t]}'"))
            else:
                seen_title[t] = a["id"]
        basis = a.get("distinction_basis") or {}
        if basis.get("kind") == "mechanical":
            atom = basis.get("atom")
            if atom:
                if atom in seen_atom:
                    errors.append(ValidationError(
                        KIND_MALFORMED, "characters", (a["id"],),
                        field=f"distinction_basis atom '{atom}' duplicates '{seen_atom[atom]}'"))
                else:
                    seen_atom[atom] = a["id"]
    return errors


def validate_distinction_basis(authored: list, fact_pack: dict) -> list[ValidationError]:
    """A mechanical distinction_basis must match the recomputed fact pack.
    Narrative bases record provenance only and are not fact-checked. A missing
    basis is tolerated (pre-migration entries)."""
    errors: list[ValidationError] = []
    for a in authored:
        basis = a.get("distinction_basis")
        if not basis:
            continue
        if basis.get("kind") != "mechanical":
            continue
        atom = basis.get("atom")
        atoms = fact_pack.get(a["id"], {})
        if atom not in atoms:
            errors.append(ValidationError(
                KIND_MALFORMED, "characters", (a["id"],),
                field=f"distinction_basis unknown atom '{atom}'"))
            continue
        if atoms[atom] != basis.get("value"):
            errors.append(ValidationError(
                KIND_MALFORMED, "characters", (a["id"],),
                field=(f"distinction_basis '{atom}' claims {basis.get('value')!r} "
                       f"but fact pack has {atoms[atom]!r}")))
    return errors
