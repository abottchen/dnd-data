"""Dramatis Personae: which sessions an NPC appears in, and the circle plate
the GM tab renders from that (see docs/superpowers/specs/2026-10-26-npc-circles-design.md)."""
from build.compute import compute_cast, npc_sessions

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


# -- the circle plate --------------------------------------------------------

REGISTRY = [
    {"key": "guides", "title": "The Guides", "kind": "company"},
    {"key": "fort-beluarian", "title": "Fort Beluarian", "kind": "company"},
    {"key": "port-nyanzaru", "title": "The People of Port Nyanzaru", "kind": "company"},
    {"key": "harpers", "title": "The Harpers", "kind": "faction"},
    {"key": "zhentarim", "title": "The Zhentarim", "kind": "faction"},
]

NPCS = [
    {"name": "Musharib", "allegiance": "with", "epithet": "a guide", "circles": ["guides"]},
    {"name": "Shago", "allegiance": "with", "epithet": "a guide out of the fort", "circles": ["guides", "fort-beluarian"]},
    {"name": "Salida", "allegiance": "against", "epithet": "a guide, the naga's creature", "circles": ["guides"]},
    {"name": "Wren", "allegiance": "with", "epithet": "keeps a journal", "circles": ["port-nyanzaru", "harpers"]},
    {"name": "Grandfather Zitembe", "allegiance": "with", "epithet": "of the temple", "circles": ["port-nyanzaru"]},
    {"name": "Volo", "allegiance": "with", "epithet": "chronicler", "circles": []},
    {"name": "Nava", "allegiance": None, "epithet": "a dryad"},   # pre-backfill: no field
]

ROAD = {"entries": [
    {"session": 1, "text": "- Musharib and Salida hired; Grandfather Zitembe blessed them"},
    {"session": 2, "text": "- Shago waited at the fort"},
    {"session": 3, "text": "- Volo sold them a book"},
    {"session": 4, "text": "- Wren opened the journal"},
    {"session": 5, "text": "- Shago led; Wren wrote"},
    {"session": 6, "text": "- Musharib resigned his post"},
]}


def _cast(window=2):
    return compute_cast(NPCS, ROAD, REGISTRY, window=window)


def _circle(key, window=2):
    return next(c for c in _cast(window)["circles"] if c["key"] == key)


def _names(entries):
    return [e["name"] for e in entries]


def test_compute_cast_files_each_npc_under_its_first_company():
    assert _names(_circle("guides")["present"] + _circle("guides")["rollcall"]) == ["Musharib", "Shago", "Salida"]
    # A faction is never a circle block on the page.
    assert "harpers" not in [c["key"] for c in _cast()["circles"]]


def test_compute_cast_present_members_get_entries_and_the_rest_the_roll_call():
    # window=2 on a six-session log: sessions 5 and 6 are the present road.
    guides = _circle("guides")
    assert _names(guides["present"]) == ["Musharib", "Shago"]
    assert _names(guides["rollcall"]) == ["Salida"]


def test_compute_cast_second_company_is_a_cross_reference_in_its_roll_call():
    fort = _circle("fort-beluarian")
    assert fort["present"] == []
    assert [(e["name"], e["ref"]) for e in fort["rollcall"]] == [("Shago", True)]
    shago = _circle("guides")["present"][1]
    assert shago["ref"] is False
    assert [a["key"] for a in shago["also"]] == ["fort-beluarian"]


def test_compute_cast_count_includes_cross_references():
    assert _circle("fort-beluarian")["total"] == 1
    assert _circle("guides")["total"] == 3


def test_compute_cast_factions_become_marks_on_the_entry():
    wren = _circle("port-nyanzaru")["present"][0]
    assert wren["name"] == "Wren"
    assert [f["title"] for f in wren["factions"]] == ["The Harpers"]
    assert _circle("port-nyanzaru")["rollcall"][0]["factions"] == []


def test_compute_cast_orders_circles_by_recency_with_the_catch_all_last():
    # guides last named vi; port and fort both v, port first met i, fort ii.
    assert [c["key"] for c in _cast()["circles"]] == ["guides", "port-nyanzaru", "fort-beluarian", "road"]
    assert _cast()["circles"][-1]["catch_all"] is True


def test_compute_cast_catch_all_holds_the_ungrouped_and_the_unmigrated():
    road = _circle("road")
    assert _names(road["rollcall"]) == ["Volo", "Nava"]       # Nava never named: last


def test_compute_cast_roll_call_label_reports_last_session_seen():
    assert _circle("guides")["last_seen_label"] == "I"        # Salida, session 1
    assert _circle("road")["last_seen_label"] == "III"        # Volo; Nava never seen
    assert _circle("guides", window=6)["last_seen_label"] == ""   # nobody left in the roll call


def test_compute_cast_ignores_unknown_keys_without_failing():
    npcs = [{"name": "Volo", "allegiance": "with", "epithet": "x", "circles": ["nope", "harpers"]}]
    cast = compute_cast(npcs, ROAD, REGISTRY, window=2)
    assert [c["key"] for c in cast["circles"]] == ["road"]
    assert [f["key"] for f in cast["circles"][0]["rollcall"][0]["factions"]] == ["harpers"]


def test_compute_cast_legend_lists_only_factions_with_bearers():
    assert [f["key"] for f in _cast()["factions"]] == ["harpers"]


def test_compute_cast_entries_carry_a_slug_for_anchors():
    assert _circle("port-nyanzaru")["rollcall"][0]["slug"] == "grandfather-zitembe"
