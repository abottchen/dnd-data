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


# -- Earlier visits ---------------------------------------------------------

def test_seen_before_cuts_dm_notes_and_later_sessions():
    entries = [
        {"session": 1, "text": "- Arrived in Mbala (DM Note: the king was Kwalu)\n- Ate."},
        {"session": 2, "text": "- Mbala [secret] again"},
        {"session": 3, "text": "- Mbala later"},
    ]
    out = reference.seen_before(entries, 3, ["Mbala"])
    assert out == [{"session": 1, "line": "Arrived in Mbala"},
                   {"session": 2, "line": "Mbala  again"}]


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
    assert set(ref) == {"party_sheets", "places", "creatures", "seen_before"}
    assert [p["name"] for p in ref["places"]] == ["Mbala"]


def test_build_reference_without_module_text(staged_env, monkeypatch, tmp_path):
    """No dnd-toa link: the writer gets no places and the build still runs."""
    monkeypatch.setenv("BUILD_TOA_ADVENTURE", str(tmp_path / "missing.json"))
    reference._adventure_sections.cache_clear()
    data = render.load_data(staged_env / "data")
    ref = reference.build_reference(data, 2, "Mbala", [], fluff={}, skip=frozenset(),
                                    stat_blocks=frozenset())
    assert ref["places"] == [] and ref["seen_before"] == []
    reference._adventure_sections.cache_clear()
