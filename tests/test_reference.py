"""Tests for build/reference.py — the record handed to the session writer."""
import pytest

from build import reference, render


# -- 5etools text ------------------------------------------------------------

def test_untag_resolves_nested_tags():
    assert reference.untag("{@creature Nanny Pu'pu|ToA} and {@dice 2d6}") == "Nanny Pu'pu and 2d6"
    assert reference.untag("{@b {@i deep}}") == "deep"


MINI_ADVENTURE = {"data": [
    {"type": "section", "name": "Foreword", "entries": [
        {"type": "entries", "name": "Death Curse", "entries": ["How to run the curse."]},
    ]},
    {"type": "section", "name": "The Land", "entries": [
        {"type": "entries", "name": "Mbala", "entries": [
            {"type": "insetReadaloud", "entries": ["A plateau rises above heaps of boulders."]},
            "The path winds up the cliff face.",
            {"type": "entries", "name": "Nanny Pu'pu", "entries": [
                "The only structure still intact is a lone hut.",
                {"type": "table", "colLabels": ["d6"], "rows": [["secret"]]},
            ]},
            {"type": "entries", "name": "Treasure", "entries": ["A sack in a cistern."]},
        ]},
        {"type": "entries", "name": "Guides", "entries": ["Hire one in port."]},
        {"type": "entries", "name": "Orolunga", "entries": ["A ziggurat of four tiers."]},
    ]},
]}


def test_walk_sections_flattens_with_headings_and_readaloud():
    secs = {s["name"]: s for s in reference.walk_sections(MINI_ADVENTURE)}
    mb = secs["Mbala"]
    assert mb["path"] == ["The Land", "Mbala"]
    assert "> A plateau rises" in mb["text"]          # read-aloud marked
    assert "## Nanny Pu'pu" in mb["text"]             # subsection heading kept
    assert "lone hut" in mb["text"]                   # subsection text folded in
    assert "secret" not in mb["text"]                 # tables dropped


def test_match_places_is_case_sensitive_and_folds_nested_hits():
    secs = reference.walk_sections(MINI_ADVENTURE)
    log = "They hired guides and climbed to Mbala to see Nanny Pu'pu about the Death Curse."
    hits = reference.match_places(log, secs, people=frozenset())
    names = [h["name"] for h in hits]
    # Nanny folded into Mbala; "guides" does not match Guides; the foreword's
    # Death Curse section is not a place.
    assert names == ["Mbala"]
    assert hits[0]["where"] == "The Land > Mbala"


def test_match_places_skips_sections_named_for_people():
    secs = reference.walk_sections(MINI_ADVENTURE)
    log = "Nanny Pu'pu waited."
    assert reference.match_places(log, secs, people=frozenset({"nanny pu'pu"})) == []
    assert [h["name"] for h in reference.match_places(log, secs, people=frozenset())] == ["Nanny Pu'pu"]


def test_match_places_skips_generic_sections_and_whole_chapters():
    secs = reference.walk_sections(MINI_ADVENTURE)
    log = "They found Treasure in The Land near Orolunga."
    hits = reference.match_places(log, secs, max_section_chars=60, people=frozenset())
    # "Treasure" is generic; "The Land" is the chapter and over the size cap;
    # Orolunga is small enough to keep.
    assert [h["name"] for h in hits] == ["Orolunga"]


# -- Creatures --------------------------------------------------------------

FLUFF = {
    "flesh golem": "Flesh golems are roughly human-shaped collections of body parts.",
    "green hag": "Green hags use illusions to cloak themselves in unassuming forms.",
    "wolf": "A wolf.",
    "winter wolf": "Winter wolves are horse-size predators.",
    "salida": "Salida is a yuan-ti spy.",
    "guard": "A guard.",
    "ghost": "A ghost is the soul of a once-living creature.",
}


FLUFF["giants"] = "Giants are a family of huge folk."
STAT_BLOCKS = frozenset(k for k in FLUFF if k != "giants")


def test_creature_lore_from_kills_and_log_without_named_or_generic():
    log = "A guard watched as three giants and two winter wolves passed. Salida led them."
    kills = [{"character": "chumble", "creature": "Flesh Golem", "method": "Eldritch Blast"}]
    lore = reference.creature_lore(log, kills, fluff=FLUFF, skip=frozenset({"salida"}),
                                   stat_blocks=STAT_BLOCKS)
    # winter wolves matched by plural and wolf folded into it; guard is generic;
    # salida is a person; "Giants" is a family, not a stat block.
    assert set(lore) == {"Flesh Golem", "Winter Wolf"}


def test_creature_lore_ignores_creatures_named_only_in_dm_notes():
    """A creature the DM's notes name is one the company has not met. The
    note's text may sit outside the parentheses: `(DM note) a ghost waits`."""
    dm_only = "Camped by the river. (DM note) a ghost waits in the temple\n[winter wolves next week]"
    assert reference.creature_lore(dm_only, [], fluff=FLUFF, skip=frozenset(),
                                   stat_blocks=STAT_BLOCKS) == {}
    lore = reference.creature_lore("A ghost rose from the pool.", [], fluff=FLUFF,
                                   skip=frozenset(), stat_blocks=STAT_BLOCKS)
    assert set(lore) == {"Ghost"}


# -- Earlier logs -----------------------------------------------------------

def test_earlier_logs_keeps_every_earlier_session_and_cuts_dm_notes():
    """What the company has seen and heard: every earlier session's log, the
    player-facing lines only. A DM note is cut to the end of its line whether
    its text sits inside the parentheses or after them, and a line that was
    nothing but a note is dropped."""
    entries = [
        {"session": 1, "text": "- Arrived in Mbala (DM Note: the king was Kwalu)\n- Ate.\n  - (DM note) she would have seen Mesika"},
        {"session": 2, "text": "- Mbala [secret] again"},
        {"session": 3, "text": "- Mbala later"},
    ]
    out = reference.earlier_logs(entries, 3)
    assert out == [{"session": 1, "text": "- Arrived in Mbala\n- Ate."},
                   {"session": 2, "text": "- Mbala  again"}]
    assert reference.earlier_logs(entries, 1) == []


def test_player_text_cuts_dm_note_blocks_under_a_header():
    """A `DM notes:` or `(DM notes)` line opens a block of notes, each line
    unmarked, that runs to the next `<br />` separator or the end of the
    entry. The log has both: one at the top of an entry, one at its end."""
    text = ("(DM notes)\n\n- Double-check Vex's languages\n\n  - Common, Draconic\n\n<br />\n\n"
            "1 Eleint\n\n- Resting for the night\n\n"
            "DM notes:\n\n- I forgot the emeralds\n- Need to give Mesika a way in\n\n<br />\n\n<br />\n")
    out = reference.player_text(text)
    assert "languages" not in out and "Draconic" not in out
    assert "emeralds" not in out and "Mesika" not in out
    assert "1 Eleint" in out and "- Resting for the night" in out


# -- Party sheets + assembly -------------------------------------------------

def test_party_sheets_and_build_reference(staged_env):
    data = render.load_data(staged_env / "data")
    sheets = reference.party_sheets(data)
    assert {s["name"] for s in sheets} == {m["name"] for m in data["party"]["members"]}
    assert all({"species", "class", "features", "feats", "attacks"} <= set(s) for s in sheets)

    secs = reference.walk_sections(MINI_ADVENTURE)
    ref = reference.build_reference(data, 2, "They reached Mbala.", [],
                                    sections=secs, fluff=FLUFF, skip=frozenset(),
                                    stat_blocks=STAT_BLOCKS)
    assert set(ref) == {"party_sheets", "places", "creatures", "earlier_logs"}
    assert [p["name"] for p in ref["places"]] == ["Mbala"]
    assert [e["session"] for e in ref["earlier_logs"]] == [1]


def test_build_reference_without_module_text(staged_env, monkeypatch, tmp_path):
    """No dnd-toa link: the writer gets no places and the build still runs."""
    monkeypatch.setenv("BUILD_TOA_ADVENTURE", str(tmp_path / "missing.json"))
    reference._adventure_sections.cache_clear()
    data = render.load_data(staged_env / "data")
    ref = reference.build_reference(data, 2, "Mbala", [], fluff={}, skip=frozenset(),
                                    stat_blocks=frozenset())
    assert ref["places"] == [] and ref["creatures"] == {}
    assert [e["session"] for e in ref["earlier_logs"]] == [1]
    reference._adventure_sections.cache_clear()


# -- Markdown modules (the Lost City of Mezro transcription) ----------------

MINI_MARKDOWN = """# Lost City of Mezro — Full Transcription

## Contents

| Section | Page |
|---|---|

# Chapter 1: The Runestone Guide

## Page 10

_[Printed page 9]_

## The Village of Tamalka

Smoke rises over the huts.

### 1. Village Entrance

***Pit.*** A pit beyond the archway.

## Page 11

### 2. The Grounds

Bodies near the huts.

## The Tunnel Maze

Dark passages under the shrines.

### Talking with Wainrath

He tells them everything.

## The Seething Halls

Once a temple of the rising sun.

### 1. The Capricious Guardian

A dryad, Nava, waits at the door.

## Fate of the Obanashi

Where the clan went.
"""


def test_walk_markdown_sections_nests_by_heading_and_skips_page_markers():
    secs = {s["name"]: s for s in reference.walk_markdown_sections(MINI_MARKDOWN)}
    assert "Page 10" not in secs and "Page 11" not in secs
    village = secs["The Village of Tamalka"]
    assert village["path"] == ["Chapter 1: The Runestone Guide", "The Village of Tamalka"]
    assert "Smoke rises" in village["text"]
    assert "## 1. Village Entrance" in village["text"]      # subsection heading kept
    assert "Pit. A pit beyond the archway." in village["text"]  # emphasis marks stripped
    assert "## 2. The Grounds" in village["text"]           # a page marker does not break nesting
    assert "Printed page" not in village["text"]            # bracketed transcription notes dropped
    assert secs["Contents"]["text"] == ""                   # tables dropped
    assert secs["1. Village Entrance"]["depth"] == 3
    assert secs["The Tunnel Maze"]["path"] == ["Chapter 1: The Runestone Guide", "The Tunnel Maze"]


def test_match_places_matches_of_name_sections_near_the_top_only():
    secs = reference.walk_markdown_sections(MINI_MARKDOWN)
    log = "Arrived in Tamalka Village to find it attacked. Went in looking for Wainrath."
    hits = reference.match_places(log, secs, people=frozenset())
    # "The Village of Tamalka" matches on Tamalka and folds its subsections;
    # "Talking with Wainrath" is deep and not "of <Name>", so Wainrath in the
    # log does not hand over the conversation script.
    assert [h["name"] for h in hits] == ["The Village of Tamalka"]
    assert "## 1. Village Entrance" in hits[0]["text"]


def test_match_places_tolerates_the_article_the_plural_and_of_the():
    """The log says "the Seething Hall"; the book's heading is "The Seething
    Halls". A section is reached by its name without its article and in the
    singular, and "Fate of the Obanashi" by the name after "of the"."""
    secs = reference.walk_markdown_sections(MINI_MARKDOWN)
    log = "Arrived at the Seething Hall. The Obanashi have not been seen for some time."
    hits = reference.match_places(log, secs, people=frozenset())
    assert [h["name"] for h in hits] == ["The Seething Halls", "Fate of the Obanashi"]
    assert "## 1. The Capricious Guardian" in hits[0]["text"]


def test_match_places_ignores_places_named_only_in_dm_notes():
    secs = reference.walk_sections(MINI_ADVENTURE)
    assert reference.match_places("Camped. (DM note: next stop is Mbala)", secs, people=frozenset()) == []
    assert reference.match_places("Camped.\n- (DM note) next stop is Mbala", secs, people=frozenset()) == []
    assert reference.match_places("Camped. [Mbala next]", secs, people=frozenset()) == []
    assert [h["name"] for h in reference.match_places("Climbed to Mbala.", secs, people=frozenset())] == ["Mbala"]
