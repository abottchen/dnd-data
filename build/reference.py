"""reference.py — the record behind a session, gathered for the chronicle writer.

The session log says what happened. It does not say what a flesh golem is,
what Grieg's nose can do, or what the hut at Mbala is made of. Those facts
live in party.json, the 5etools bestiary, and the module text linked in from
the dnd-toa repo. This module collects the ones relevant to one session so
the writer works from the record instead of paraphrasing the log.

Everything here is selection, not judgment. The module text carries things
the company never learned, and the writer's brief holds it to what the
players have: see .claude/prompts/append-sessions.md.
"""
from __future__ import annotations

import functools
import glob as _glob
import html
import json
import re
import sys

from .paths import REPO_ROOT, toa_adventure_path, toa_docs_glob

BESTIARY_GLOB = ".claude/ext/5etools-src/data/bestiary/bestiary-*.json"
FLUFF_GLOB = ".claude/ext/5etools-src/data/bestiary/fluff-bestiary-*.json"
_FLUFF_SOURCE_PRIORITY = ["XMM", "MM", "MPMM", "ToA", "VGM", "MTF"]

# Section names that are structure, not places: matching "Treasure" against a
# log that mentions treasure would pull in every treasure block in the book.
_GENERIC_SECTIONS = {
    "Treasure", "Development", "Developments", "Features", "Conclusion",
    "Introduction", "Overview", "Tactics", "Exploration", "Encounters",
    "Random Encounters", "Areas", "General Features", "Adventure Hooks",
}
# Stat blocks named after ordinary words. "guard" in a log line is not a
# request for the Guard's bestiary entry.
_GENERIC_CREATURES = {
    "guard", "scout", "noble", "commoner", "cultist", "spy", "thug", "priest",
    "knight", "veteran", "mage", "acolyte", "bandit", "berserker", "druid",
    "gladiator", "hunter", "warrior", "tribal warrior", "archer", "assassin",
    "swarm", "bat", "cat", "dog", "rat", "frog", "ape", "hawk", "boar", "deer",
}

# Parts of the book that are about running it, not about a place the company
# can stand in. A log that says "death curse" is not asking for the foreword.
_EXCLUDED_PATH_PARTS = {
    "Foreword", "Running the Adventure", "Conclusion", "Credits",
    # The markdown transcriptions' front matter: the who's-who, the blurbs
    # that summarize the whole trilogy, the transcriber's own notes.
    "Contents", "Table of Contents", "About this transcription",
    "Dramatis Personae", "Product Summary", "Series Overview",
}

# Markdown module text is read by heading. Page markers are the
# transcription's structure, not the book's, and never open a section.
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_PAGE = re.compile(r"^Page \d+$")
_MD_EMPHASIS = re.compile(r"\*{1,3}|(?<!\w)_{1,2}|_{1,2}(?!\w)")
# A top-level place named "<Something> of <Name>" is reached by its name
# alone: a log that says Tamalka wants "The Village of Tamalka".
_OF_NAME = re.compile(r"\bof ([A-Z][\w'-]{3,})$")
_DM_NOTE = re.compile(r"\(DM [Nn]ote[^)]*\)")
_BRACKETED = re.compile(r"\[[^\]]*\]")

_SECTION_TYPES = ("section", "entries", "inset", "insetReadaloud")
_TAG = re.compile(r"\{@\w+ ([^{}|]*)(?:\|[^{}]*)?\}")
_HTML = re.compile(r"<[^>]+>")
_NOTABLE_GEAR = re.compile(
    r"\+\d|\bRing\b|\bRod\b|Gauntlet|Focus|Monkey|Sprig|Token|Amulet|Cloak|"
    r"\bWand\b|Staff of|Ubtao", re.I)


def untag(s: str) -> str:
    """`{@creature Nanny Pu'pu|ToA}` → `Nanny Pu'pu`, repeated until no tag is
    left, so nested tags resolve too."""
    prev = None
    while prev != s:
        prev, s = s, _TAG.sub(r"\1", s)
    return s


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _HTML.sub(" ", html.unescape(s or ""))).strip()


def _word(name: str, *, flags: int = 0, plural: bool = False) -> re.Pattern:
    """A whole-word match for a name, tolerant of the apostrophes and spaces
    in "Nanny Pu'pu" and "Port Nyanzaru". With `plural`, "winter wolf" also
    matches "winter wolves" and "flesh golem" matches "flesh golems"."""
    pat = re.escape(name)
    if plural:
        alts = [pat + r"(?:s|es)?"]
        if name.endswith("f"):
            alts.append(re.escape(name[:-1]) + "ves")
        elif name.endswith("fe"):
            alts.append(re.escape(name[:-2]) + "ves")
        pat = "(?:" + "|".join(alts) + ")"
    return re.compile(r"(?<!\w)" + pat + r"(?!\w)", flags)


# -- Party sheets -----------------------------------------------------------

def party_sheets(data: dict) -> list[dict]:
    """What each member is and can do, compact enough to hand a writer: the
    feats and features by name with a line of what they do, attacks and
    spells by name, and only the gear a story would notice."""
    out = []
    for m in data["party"]["members"]:
        spells = m.get("spells") or {}
        prepared = spells.get("prepared") if isinstance(spells, dict) else None
        out.append({
            "name": m.get("name"),
            "species": m.get("race"),
            "class": m.get("class"),
            "subclass": m.get("subclass"),
            "background": m.get("background"),
            "attacks": [a.get("name") for a in m.get("attacks", []) if a.get("name")],
            "features": [{"name": f.get("name"), "what": _strip_html(f.get("description", ""))[:240]}
                         for f in m.get("features", []) if f.get("name")],
            "feats": [{"name": f.get("name"), "what": _strip_html(f.get("description", ""))[:240]}
                      for f in m.get("feats", []) if f.get("name")],
            "cantrips": list(spells.get("cantrips", [])) if isinstance(spells, dict) else [],
            "spells": [s.get("name") for s in prepared if s.get("name")] if isinstance(prepared, list) else [],
            "notable_gear": [e for e in m.get("equipment", []) if _NOTABLE_GEAR.search(e)],
        })
    return out


# -- Module text ------------------------------------------------------------

def _flatten(node, out: list, readaloud: bool = False) -> None:
    """Render a 5etools entries tree to plain lines. Read-aloud boxes are
    prefixed `> `, subsection names become `## ` headings, tables are
    dropped (they are DM machinery, never description)."""
    if isinstance(node, str):
        out.append(("> " if readaloud else "") + untag(node))
        return
    if isinstance(node, list):
        for x in node:
            _flatten(x, out, readaloud)
        return
    if not isinstance(node, dict):
        return
    t = node.get("type")
    if t == "table":
        return
    ra = readaloud or t == "insetReadaloud"
    if t == "item":
        body: list = []
        _flatten(node.get("entry", node.get("entries", [])), body, ra)
        name = node.get("name")
        out.append((f"{untag(name)}: " if name else "") + " ".join(body))
        return
    if node.get("name") and t in _SECTION_TYPES:
        out.append(f"## {untag(node['name'])}")
    for k in ("entries", "items", "entry"):
        if k in node:
            _flatten(node[k], out, ra)


def walk_sections(adventure: dict | list) -> list[dict]:
    """Every named node in a 5etools adventure → {name, path, depth, text},
    where text is the node's whole content, subsections included."""
    out: list[dict] = []

    def rec(node, path: list):
        if isinstance(node, dict):
            name = node.get("name")
            if name and node.get("type") in _SECTION_TYPES:
                buf: list = []
                _flatten(node.get("entries", []), buf)
                path = path + [untag(name)]
                out.append({"name": path[-1], "path": path, "depth": len(path),
                            "text": "\n".join(buf).strip()})
            for k in ("entries", "items", "entry"):
                v = node.get(k)
                if isinstance(v, (list, dict)):
                    rec(v, path)
        elif isinstance(node, list):
            for x in node:
                rec(x, path)

    rec(adventure.get("data", adventure) if isinstance(adventure, dict) else adventure, [])
    return out


def _md_line(raw: str) -> str | None:
    """One markdown line as plain text, or None for lines that are not the
    book's prose: table rows, rules, and the transcriber's bracketed notes
    (`_[Printed page 9]_`, map and illustration descriptions)."""
    s = raw.strip()
    if not s:
        return ""
    if s.startswith("|") or s.startswith("---") or s.startswith("_[") or s.startswith("["):
        return None
    if s.startswith(">"):
        s = "> " + s.lstrip("> ").strip()
    return html.unescape(_MD_EMPHASIS.sub("", s)).strip()


def walk_markdown_sections(text: str) -> list[dict]:
    """Every heading of a markdown module transcription → {name, path, depth,
    text}, the same shape `walk_sections` gives the 5etools JSON. Nesting
    follows heading level; a section's text is its whole content,
    subsections included, their headings kept as `## ` lines."""
    out: list[dict] = []
    stack: list[tuple[int, dict]] = []
    for raw in text.splitlines():
        m = _MD_HEADING.match(raw)
        if m:
            level, name = len(m.group(1)), m.group(2).strip()
            if _MD_PAGE.match(name):
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = [s[1]["name"] for s in stack] + [name]
            sec = {"name": name, "path": path, "depth": len(path), "lines": []}
            for _, anc in stack:
                anc["lines"].append(f"## {name}")
            stack.append((level, sec))
            out.append(sec)
            continue
        line = _md_line(raw)
        if line is None:
            continue
        for _, sec in stack:
            sec["lines"].append(line)
    return [{"name": s["name"], "path": s["path"], "depth": s["depth"],
             "text": re.sub(r"\n{3,}", "\n\n", "\n".join(s["lines"])).strip()}
            for s in out]


@functools.lru_cache(maxsize=1)
def _adventure_sections() -> tuple:
    """Every section of every module the writer may draw on: the Tomb of
    Annihilation JSON, then the markdown transcriptions beside it."""
    out: list[dict] = []
    p = toa_adventure_path()
    if p.exists():
        with open(p) as f:
            out.extend(walk_sections(json.load(f)))
    for fpath in sorted(_glob.glob(toa_docs_glob())):
        with open(fpath) as f:
            out.extend(walk_markdown_sections(f.read()))
    if not out:
        print(f"reference: no module text at {p}; the session writer gets none "
              "(link ../dnd-toa under .claude/ext/, see .claude/ext/README.md)",
              file=sys.stderr)
    return tuple(out)


def _names_place(section: dict, narrative: str) -> bool:
    """Does the log name this section? By its whole name, as written; or,
    for a section near the top of its chapter named "<Something> of <Name>",
    by that name alone."""
    if _word(section["name"]).search(narrative):
        return True
    m = _OF_NAME.search(section["name"])
    return bool(m and section["depth"] <= 2 and _word(m.group(1)).search(narrative))


def match_places(narrative: str, sections, *, limit: int = 6,
                 max_section_chars: int = 14000,
                 people: frozenset | None = None) -> list[dict]:
    """Sections whose name appears in this session's log, as written (case
    matters: `Guides` must not match a log that says guides). A section
    nested inside another match is folded into its parent. Whole chapters are
    skipped: a log that says Port Nyanzaru wants the district, not the book.
    Sections named for a person (an NPC stat block) are skipped too: those
    are biographies, and who someone secretly is comes from the log or not
    at all."""
    people = _named_creatures() if people is None else people
    # A place the log names only inside a DM note is not one the company
    # went to.
    narrative = _BRACKETED.sub("", _DM_NOTE.sub("", narrative))
    hits = [s for s in sections
            if s["name"] not in _GENERIC_SECTIONS and len(s["name"]) >= 4
            and s["name"][0].isupper() and s["name"].casefold() not in people
            and not any(p in _EXCLUDED_PATH_PARTS or p.startswith("Appendix") for p in s["path"])
            and _names_place(s, narrative)
            and len(s["text"]) <= max_section_chars]
    paths = {tuple(h["path"]) for h in hits}
    keep = [h for h in hits
            if not any(tuple(h["path"][:i]) in paths for i in range(1, len(h["path"])))]
    keep.sort(key=lambda h: (h["depth"], -len(h["text"])))
    return [{"name": h["name"], "where": " > ".join(h["path"]), "text": h["text"]}
            for h in keep[:limit]]


# -- Creatures --------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _bestiary_names() -> tuple[frozenset, frozenset]:
    """(every stat block name, the ones that are people). Salida, Shago and
    Artus Cimber are stat blocks too, and their fluff is who they secretly
    are, so the people never go to the writer as lore."""
    every, people = set(), set()
    for fpath in _glob.glob(str(REPO_ROOT / BESTIARY_GLOB)):
        with open(fpath) as f:
            for m in json.load(f).get("monster", []):
                if not m.get("name"):
                    continue
                every.add(m["name"].casefold())
                if m.get("isNamedCreature"):
                    people.add(m["name"].casefold())
    return frozenset(every), frozenset(people)


def _named_creatures() -> frozenset:
    return _bestiary_names()[1]


@functools.lru_cache(maxsize=1)
def _load_fluff() -> dict:
    """creature name (casefolded) → its descriptive text, best source first."""
    def prio(src: str) -> int:
        try:
            return _FLUFF_SOURCE_PRIORITY.index(src)
        except ValueError:
            return len(_FLUFF_SOURCE_PRIORITY)
    best: dict = {}
    for fpath in _glob.glob(str(REPO_ROOT / FLUFF_GLOB)):
        with open(fpath) as f:
            content = json.load(f)
        for m in content.get("monsterFluff", []):
            name = m.get("name")
            if not name:
                continue
            buf: list = []
            _flatten(m.get("entries", []), buf)
            text = " ".join(p for p in buf if len(p) > 40 and not p.startswith("## "))
            if not text:
                continue
            key = name.casefold()
            p = prio(m.get("source", ""))
            if key not in best or p < best[key][0]:
                best[key] = (p, text)
    return {k: v[1] for k, v in best.items()}


def creature_lore(narrative: str, kills: list, *, fluff: dict | None = None,
                  skip: frozenset | None = None, stat_blocks: frozenset | None = None,
                  limit: int = 10, max_chars: int = 1000) -> dict:
    """What the bestiary says about each creature this session met: every
    killed creature, plus any stat block whose name appears in the log,
    singular or plural. A name contained in a longer match is dropped (Wolf
    inside Winter Wolf), and fluff for a family of creatures ("Giants") is
    not a stat block and never matches."""
    fluff = _load_fluff() if fluff is None else fluff
    skip = _named_creatures() if skip is None else skip
    stat_blocks = _bestiary_names()[0] if stat_blocks is None else stat_blocks
    found = {k["creature"].casefold() for k in kills if k.get("creature")}
    for key in fluff:
        if (len(key) >= 4 and key not in _GENERIC_CREATURES and key in stat_blocks
                and _word(key, flags=re.I, plural=True).search(narrative)):
            found.add(key)
    found = {k for k in found if k not in skip and k in fluff}
    found = {k for k in found if not any(k != o and k in o for o in found)}
    out = {}
    for key in sorted(found)[:limit]:
        out[key.title()] = fluff[key][:max_chars]
    return out


# -- Earlier visits ---------------------------------------------------------

def seen_before(entries: list, sid, place_names: list) -> list[dict]:
    """Player-facing log lines from earlier sessions that mention a place this
    session visits. DM notes and bracketed asides are cut from the line."""
    if not place_names:
        return []
    pats = [_word(n) for n in place_names]
    out = []
    for e in entries:
        esid = e.get("session")
        if esid is None or sid is None or esid >= sid:
            continue
        text = e.get("text", "")
        if isinstance(text, list):
            text = "\n".join(text)
        for raw in text.split("\n"):
            line = re.sub(r"\(DM [Nn]ote[^)]*\)", "", raw)
            line = re.sub(r"\[[^\]]*\]", "", line)
            line = re.sub(r"^[\s\-*]+", "", line).strip()
            if line and any(p.search(line) for p in pats):
                out.append({"session": esid, "line": line})
    return out


# -- Assembly ---------------------------------------------------------------

def build_reference(data: dict, sid, narrative: str, kills: list, *,
                    sections=None, fluff: dict | None = None,
                    skip: frozenset | None = None,
                    stat_blocks: frozenset | None = None) -> dict:
    """The reference block for one append-sessions slice. `sections`, `fluff`,
    `skip` and `stat_blocks` exist for tests; the build reads the linked
    module text and the bestiary."""
    sections = _adventure_sections() if sections is None else sections
    places = match_places(narrative, sections, people=skip)
    return {
        "party_sheets": party_sheets(data),
        "places": places,
        "creatures": creature_lore(narrative, kills, fluff=fluff, skip=skip,
                                   stat_blocks=stat_blocks),
        "seen_before": seen_before(data["session_log"]["entries"], sid,
                                   [p["name"] for p in places]),
    }
