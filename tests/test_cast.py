"""Dramatis Personae: which sessions an NPC appears in, and the cast plate
the GM tab renders from that (see docs/superpowers/specs/2026-10-26-npc-circles-design.md)."""
from build.compute import CAST_PRESENT_WINDOW, compute_cast, npc_sessions

LOG = {"entries": [
    {"session": 1, "text": "- River led them down to where the river bent"},
    {"session": 2, "text": "- the river ran high; no guide to be had"},
    {"session": 3, "text": "- Faroul argued; Gondolo said nothing"},
    {"session": 4, "text": "- moved to where the honeyman said the site was"},
    {"session": 5, "text": "- Gondolo returned alone"},
]}


def test_npc_sessions_matches_whole_word_case_sensitive():
    # "the river bent" / "the river ran" must not count as the guide River.
    assert npc_sessions("River", LOG) == [1]


def test_npc_sessions_matches_either_half_of_a_paired_name():
    assert npc_sessions("Faroul & Gondolo", LOG) == [3, 5]


def test_npc_sessions_falls_back_to_case_insensitive_when_exact_name_never_appears():
    assert npc_sessions("The Honeyman", LOG) == [4]


def test_npc_sessions_ignores_leading_the():
    log = {"entries": [{"session": 7, "text": "- paid the Honeyman's price"}]}
    assert npc_sessions("The Honeyman", log) == [7]


def test_npc_sessions_empty_when_never_mentioned():
    assert npc_sessions("Volo", LOG) == []


# -- the cast plate ----------------------------------------------------------

REGISTRY = [
    {"key": "companions", "title": "The Companions", "billing": "principal"},
    {"key": "guides", "title": "The Guides"},
    {"key": "port-nyanzaru", "title": "The People of Port Nyanzaru"},
    {"key": "fort-beluarian", "title": "Fort Beluarian"},
    {"key": "racers", "title": "The Dinosaur Racers", "billing": "aside"},
]

NPCS = [
    {"name": "Artus Cimber", "epithet": "who hid his name", "circle": "companions"},
    {"name": "Dragonbait", "epithet": "saurial of many scents", "circle": "companions"},
    {"name": "Musharib", "epithet": "a guide", "circle": "guides"},
    {"name": "Shago", "epithet": "a guide out of the fort", "circle": "guides"},
    {"name": "Salida", "epithet": "a guide, the naga's creature", "circle": "guides"},
    {"name": "Wren", "epithet": "keeps a journal", "circle": "port-nyanzaru"},
    {"name": "Grandfather Zitembe", "epithet": "of the temple", "circle": "port-nyanzaru"},
    {"name": "Liara Portyr", "epithet": "commander of the fort", "circle": "fort-beluarian"},
    {"name": "Tiryki", "epithet": "a racer", "circle": "racers"},
    {"name": "Volo", "epithet": "chronicler", "circle": None},
    {"name": "Nava", "epithet": "a dryad"},   # pre-migration: no field
]

ROAD = {"entries": [
    {"session": 1, "text": "- Artus Cimber and Dragonbait sailed; Musharib and Salida hired; "
                           "Grandfather Zitembe blessed them; Liara Portyr signed the charter"},
    {"session": 2, "text": "- Shago waited at the fort"},
    {"session": 3, "text": "- Volo sold them a book"},
    {"session": 4, "text": "- Wren opened the journal; Tiryki raced"},
    {"session": 5, "text": "- Shago led; Wren wrote; Tiryki lost"},
    {"session": 6, "text": "- Musharib resigned his post; Tiryki raced again"},
]}


def _cast(window=2):
    return compute_cast(NPCS, ROAD, REGISTRY, window=window)


def _block(key, window=2):
    cast = _cast(window)
    return next(c for c in cast["live"] + cast["dormant"] if c["key"] == key)


def _names(entries):
    return [e["name"] for e in entries]


def test_default_window_is_three_sessions():
    assert CAST_PRESENT_WINDOW == 3


def test_compute_cast_files_each_npc_under_its_circle():
    guides = _block("guides")
    assert _names(guides["present"] + guides["rollcall"]) == ["Musharib", "Shago", "Salida"]
    assert guides["total"] == 3


def test_compute_cast_present_members_get_entries_and_the_rest_fold():
    # window=2 on a six-session log: sessions 5 and 6 are the present road.
    guides = _block("guides")
    assert _names(guides["present"]) == ["Musharib", "Shago"]
    assert _names(guides["rollcall"]) == ["Salida"]


def test_compute_cast_principals_are_live_and_never_fold():
    # Nobody in The Companions has been named since session 1, yet the block
    # is live with every member in full: the story's poles stay in view.
    companions = _block("companions")
    assert companions in _cast()["live"]
    assert _names(companions["present"]) == ["Artus Cimber", "Dragonbait"]
    assert companions["rollcall"] == []
    assert companions["billing"] == "principal"


def test_compute_cast_splits_live_from_dormant_and_orders_by_tier_then_recency():
    cast = _cast()
    # principals, then ordinary circles by last mention, then asides.
    assert [c["key"] for c in cast["live"]] == ["companions", "guides", "port-nyanzaru", "racers"]
    # nobody named lately: dormant, same order, the catch-all always last.
    assert [c["key"] for c in cast["dormant"]] == ["fort-beluarian", "road"]
    assert cast["dormant"][-1]["catch_all"] is True
    assert _block("racers")["billing"] == "aside"
    assert _block("guides")["billing"] is None


def test_compute_cast_breaks_recency_ties_by_how_many_sessions_name_the_circle():
    registry = [{"key": "a", "title": "A"}, {"key": "b", "title": "B"}]
    npcs = [{"name": "Ann", "epithet": "x", "circle": "a"},
            {"name": "Bob", "epithet": "x", "circle": "b"}]
    log = {"entries": [{"session": 1, "text": "- Bob"}, {"session": 2, "text": "- Bob"},
                       {"session": 3, "text": "- Ann and Bob"}]}
    cast = compute_cast(npcs, log, registry, window=1)
    assert [c["key"] for c in cast["live"]] == ["b", "a"]


def test_compute_cast_catch_all_holds_the_ungrouped_and_the_unmigrated():
    road = _block("road")
    assert road["title"] == "Met Along the Road"
    assert _names(road["rollcall"]) == ["Volo", "Nava"]       # Nava never named: last


def test_compute_cast_fold_label_reports_last_session_seen():
    assert _block("guides")["last_seen_label"] == "I"        # Salida, session 1
    assert _block("road")["last_seen_label"] == "III"        # Volo; Nava never seen
    assert _block("guides", window=6)["last_seen_label"] == ""   # nobody left folded


def test_compute_cast_ignores_unknown_keys_without_failing():
    npcs = [{"name": "Volo", "epithet": "x", "circle": "nope"}]
    cast = compute_cast(npcs, ROAD, REGISTRY, window=2)
    assert [c["key"] for c in cast["live"] + cast["dormant"]] == ["road"]


def test_compute_cast_entries_carry_a_slug_for_anchors():
    assert _block("port-nyanzaru")["rollcall"][0]["slug"] == "grandfather-zitembe"
