"""Tests for build.apply — the functions that mutate the in-memory authored
store from a transformer's structured_output. These tests use synthetic
authored / slice / output dicts; no subprocess, no fixtures on disk."""
import pytest

from build import apply


# -- apply_append_kills ------------------------------------------------------

def test_append_kills_round_trips_canonical_row_via_kill_key():
    """The model returns keys in arbitrary casing; the apply step must look
    them up via build.kill_key (case-insensitive on creature/method) so the
    canonical character/date/creature/method from the slice are written."""
    slice_data = {"kills": [
        {"character": "anton", "date": "2026-04-19",
         "creature": "Goblin", "method": "Vicious Mockery"},
    ]}
    output = {"fields": {
        # Note: model emitted lowercased creature + different-cased method.
        "anton__2026-04-19__goblin__VICIOUS MOCKERY": {
            "verse": "A goblin, undone by a whisper.",
            "annotation": "Vicious Mockery · words alone.",
        },
    }, "reason": "test"}
    authored = {"kills": []}
    apply.apply_append_kills(authored, key=None, slice_data=slice_data, output=output)
    assert len(authored["kills"]) == 1
    row = authored["kills"][0]
    # Canonical casing recovered from the slice, not the model's key.
    assert row["creature"] == "Goblin"
    assert row["method"] == "Vicious Mockery"
    assert row["verse"].startswith("A goblin")


def test_append_kills_raises_when_model_returns_unknown_key():
    slice_data = {"kills": [
        {"character": "anton", "date": "2026-04-19",
         "creature": "Goblin", "method": "Vicious Mockery"},
    ]}
    output = {"fields": {
        "anton__2026-04-19__bandit__shortbow": {
            "verse": "x", "annotation": "y",
        },
    }, "reason": "test"}
    authored = {"kills": []}
    with pytest.raises(ValueError, match="not in slice"):
        apply.apply_append_kills(authored, key=None, slice_data=slice_data, output=output)


def test_append_kills_raises_on_malformed_key():
    slice_data = {"kills": []}
    output = {"fields": {"too__few__parts": {"verse": "x", "annotation": "y"}},
              "reason": "test"}
    with pytest.raises(ValueError, match="malformed kill key"):
        apply.apply_append_kills({"kills": []}, key=None,
                                 slice_data=slice_data, output=output)


def test_append_kills_rejects_existing_key():
    authored = {"kills": [{"character": "vex", "date": "2026-04-19",
                           "creature": "Goblin", "method": "shortbow",
                           "verse": "v", "annotation": "a"}]}
    slice_data = {"kills": [{"character": "vex", "date": "2026-04-19",
                             "creature": "Goblin", "method": "shortbow"}]}
    output = {"fields": {"vex__2026-04-19__Goblin__shortbow":
                         {"verse": "v2", "annotation": "a2"}}}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_kills(authored, "2026-04-19", slice_data, output)


def test_append_kills_rejects_duplicate_within_batch():
    """Two raw keys in one output batch that normalize to the same kill
    (model casing drift) must not both pass the guard — the second raises
    and no duplicate row lands in authored."""
    authored = {"kills": []}
    slice_data = {"kills": [{"character": "vex", "date": "2026-04-19",
                             "creature": "Goblin", "method": "shortbow"}]}
    output = {"fields": {
        "vex__2026-04-19__Goblin__shortbow": {"verse": "v1", "annotation": "a1"},
        "vex__2026-04-19__goblin__SHORTBOW": {"verse": "v2", "annotation": "a2"},
    }}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_kills(authored, "2026-04-19", slice_data, output)
    assert len(authored["kills"]) <= 1


# -- apply_append_npcs -------------------------------------------------------

def test_append_npcs_uses_slice_key_not_model_output():
    """Regression: even if the model echoes back a corrupted name (whitespace
    drift, casing change), the authored entry must use the canonical name
    that the orchestrator passed in as the slice key."""
    authored = {"npcs": []}
    slice_data = {"name": "Azlund", "mentions": []}
    output = {"fields": {
        "epithet": "the merchant who brokers what others would not",
        "allegiance": "with",
        "circles": [],
    }, "reason": "test"}
    apply.apply_append_npcs(authored, key="Azlund",
                            slice_data=slice_data, output=output)
    assert authored["npcs"] == [{
        "name": "Azlund",
        "epithet": "the merchant who brokers what others would not",
        "allegiance": "with",
        "circles": [],
    }]


def test_append_npcs_tolerates_null_allegiance():
    authored = {"npcs": []}
    output = {"fields": {"epithet": "ambiguous", "allegiance": None, "circles": []},
              "reason": "test"}
    apply.apply_append_npcs(authored, key="Stranger",
                            slice_data={"name": "Stranger", "mentions": []},
                            output=output)
    assert authored["npcs"][0]["allegiance"] is None


def test_append_npcs_rejects_existing_name():
    authored = {"npcs": [{"name": "Azlund", "epithet": "e", "allegiance": "with"}]}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_npcs(authored, "Azlund", {"name": "Azlund"},
                                {"fields": {"epithet": "x", "allegiance": "with",
                                            "circles": []}})


# -- apply_refresh_chapters --------------------------------------------------

def test_refresh_chapters_no_change_is_noop():
    authored = {"chapters": [
        {"id": 1, "starts_at_session": 1, "title": "Old", "epigraph": "Old line."}
    ]}
    output = {"decision": "no_change", "fields": None, "reason": "still good"}
    apply.apply_refresh_chapters(authored, key="1", slice_data={}, output=output)
    assert authored["chapters"][0]["title"] == "Old"


def test_refresh_chapters_rewrite_updates_title_and_epigraph():
    authored = {"chapters": [
        {"id": 1, "starts_at_session": 1, "title": "Old", "epigraph": "Old line."}
    ]}
    output = {"decision": "rewrite",
              "fields": {"title": "New", "epigraph": "New line."},
              "reason": "data shifted"}
    apply.apply_refresh_chapters(authored, key="1", slice_data={}, output=output)
    assert authored["chapters"][0]["title"] == "New"
    assert authored["chapters"][0]["epigraph"] == "New line."


def test_refresh_chapters_raises_when_chapter_not_in_authored():
    authored = {"chapters": [
        {"id": 1, "starts_at_session": 1, "title": "x", "epigraph": "y"}
    ]}
    output = {"decision": "rewrite",
              "fields": {"title": "n", "epigraph": "m"},
              "reason": ""}
    with pytest.raises(ValueError, match="chapter 99"):
        apply.apply_refresh_chapters(authored, key="99",
                                     slice_data={}, output=output)


def test_append_chapters_rejects_existing_id_or_start():
    authored = {"chapters": [{"id": 1, "starts_at_session": 1,
                              "title": "t", "epigraph": "e"}]}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_chapters(authored, "1", {"starts_at_session": 9},
                                    {"fields": {"title": "x", "epigraph": "y"}})
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_chapters(authored, "2", {"starts_at_session": 1},
                                    {"fields": {"title": "x", "epigraph": "y"}})


# -- apply_refresh_road_ahead ------------------------------------------------

def test_refresh_road_ahead_no_change_returns_empty_graduations():
    authored = {"site": {"road_ahead": {
        "known": [{"name": "A", "gloss": "g1"}],
        "was_known": [],
        "direction": "south",
    }}}
    output = {"decision": "no_change", "fields": None, "reason": ""}
    grads = apply.apply_refresh_road_ahead(authored, key="all",
                                           slice_data={}, output=output)
    assert grads == {"graduated": []}


def test_refresh_road_ahead_graduations_diff_detects_moved_threads():
    """Entries that disappear from `known` between old and new state are
    reported as graduations, regardless of whether the new state put them in
    was_known. The orchestrator surfaces this list in the run report."""
    authored = {"site": {"road_ahead": {
        "known": [
            {"name": "A", "gloss": "g1"},
            {"name": "B", "gloss": "g2"},
        ],
        "was_known": [],
        "direction": "south",
    }}}
    output = {"decision": "rewrite", "fields": {
        "known": [{"name": "B", "gloss": "g2 sharpened"}],
        "was_known": [{"name": "A", "gloss": "g1, resolved"}],
        "direction": "south",
    }, "reason": "A resolved"}
    grads = apply.apply_refresh_road_ahead(authored, key="all",
                                           slice_data={}, output=output)
    assert grads == {"graduated": ["A"]}
    assert authored["site"]["road_ahead"]["known"] == [
        {"name": "B", "gloss": "g2 sharpened"}
    ]
    assert authored["site"]["road_ahead"]["was_known"] == [
        {"name": "A", "gloss": "g1, resolved"}
    ]


def test_refresh_road_ahead_no_graduations_when_known_unchanged():
    authored = {"site": {"road_ahead": {
        "known": [{"name": "A", "gloss": "g1"}],
        "was_known": [],
        "direction": "south",
    }}}
    # Direction-only rewrite keeps `known` the same.
    output = {"decision": "rewrite", "fields": {
        "known": [{"name": "A", "gloss": "g1"}],
        "was_known": [],
        "direction": "north",
    }, "reason": "campaign turned"}
    grads = apply.apply_refresh_road_ahead(authored, key="all",
                                           slice_data={}, output=output)
    assert grads == {"graduated": []}
    assert authored["site"]["road_ahead"]["direction"] == "north"


# -- apply_refresh_intro_epithet ---------------------------------------------

def test_refresh_intro_epithet_no_change_is_noop():
    authored = {"site": {"intro_epithet": "A small ledger."}}
    output = {"decision": "no_change", "fields": None, "reason": ""}
    apply.apply_refresh_intro_epithet(authored, key="all",
                                      slice_data={}, output=output)
    assert authored["site"]["intro_epithet"] == "A small ledger."


def test_refresh_intro_epithet_rewrite_replaces_string():
    authored = {"site": {"intro_epithet": "A small ledger."}}
    output = {"decision": "rewrite",
              "fields": {"intro_epithet": "A larger ledger, lately."},
              "reason": "more sessions"}
    apply.apply_refresh_intro_epithet(authored, key="all",
                                      slice_data={}, output=output)
    assert authored["site"]["intro_epithet"] == "A larger ledger, lately."


# -- apply_refresh_known_npcs ------------------------------------------------

def test_refresh_known_npcs_no_change_is_noop():
    authored = {"site": {"known_npcs": ["Azlund", "Tessa"]}}
    output = {"decision": "no_change", "fields": None, "reason": ""}
    apply.apply_refresh_known_npcs(authored, key="all",
                                   slice_data={}, output=output)
    assert authored["site"]["known_npcs"] == ["Azlund", "Tessa"]


def test_refresh_known_npcs_rewrite_replaces_list():
    authored = {"site": {"known_npcs": ["Azlund", "Tessa"]}}
    output = {"decision": "rewrite",
              "fields": {"known_npcs": ["Azlund", "Tessa", "Lilac Mist"]},
              "reason": "session 6 introduced Lilac Mist"}
    apply.apply_refresh_known_npcs(authored, key="all",
                                   slice_data={}, output=output)
    assert authored["site"]["known_npcs"] == ["Azlund", "Tessa", "Lilac Mist"]


def test_refresh_known_npcs_rewrite_preserves_order():
    """Apply is a verbatim replace — order from the model output is honored."""
    authored = {"site": {"known_npcs": ["A"]}}
    output = {"decision": "rewrite",
              "fields": {"known_npcs": ["A", "B", "C"]},
              "reason": ""}
    apply.apply_refresh_known_npcs(authored, key="all",
                                   slice_data={}, output=output)
    assert authored["site"]["known_npcs"] == ["A", "B", "C"]


# -- NPC circles (append + refresh) ------------------------------------------

_REGISTRY = [
    {"key": "guides", "title": "The Guides", "kind": "company"},
    {"key": "port-nyanzaru", "title": "The People of Port Nyanzaru", "kind": "company"},
    {"key": "harpers", "title": "The Harpers", "kind": "faction"},
]


def _npc_output(circles, **over):
    fields = {"epithet": "e", "allegiance": "with", "circles": circles}
    fields.update(over)
    return {"fields": fields, "reason": "test"}


def test_append_npcs_writes_circles():
    authored = {"npcs": [], "site": {"circles": _REGISTRY}}
    apply.apply_append_npcs(authored, "Wren", {"name": "Wren", "mentions": []},
                            _npc_output(["port-nyanzaru", "harpers"]))
    assert authored["npcs"][0]["circles"] == ["port-nyanzaru", "harpers"]


def test_append_npcs_orders_companies_before_factions():
    """The contract is companies first (home circle first), then factions.
    Apply normalises model output that lists a faction ahead of a company,
    keeping the relative order within each kind."""
    authored = {"npcs": [], "site": {"circles": _REGISTRY}}
    apply.apply_append_npcs(authored, "Wren", {"name": "Wren", "mentions": []},
                            _npc_output(["harpers", "port-nyanzaru", "guides"]))
    assert authored["npcs"][0]["circles"] == ["port-nyanzaru", "guides", "harpers"]


def test_append_npcs_rejects_unknown_circle_key():
    authored = {"npcs": [], "site": {"circles": _REGISTRY}}
    with pytest.raises(ValueError, match="unknown circle"):
        apply.apply_append_npcs(authored, "Wren", {"name": "Wren", "mentions": []},
                                _npc_output(["port-nyanzaru", "obanashi"]))
    assert authored["npcs"] == []


def test_append_npcs_rejects_circles_when_registry_absent():
    """No registry means no valid keys: a non-empty list cannot be honoured."""
    authored = {"npcs": [], "site": {}}
    with pytest.raises(ValueError, match="unknown circle"):
        apply.apply_append_npcs(authored, "Wren", {"name": "Wren", "mentions": []},
                                _npc_output(["harpers"]))


def test_append_npcs_empty_circles_ok_without_registry():
    authored = {"npcs": []}
    apply.apply_append_npcs(authored, "Volo", {"name": "Volo", "mentions": []},
                            _npc_output([]))
    assert authored["npcs"][0]["circles"] == []


def test_refresh_npcs_rewrite_writes_circles():
    authored = {"npcs": [{"name": "Shago", "epithet": "e", "allegiance": "with",
                          "circles": []}],
                "site": {"circles": _REGISTRY}}
    output = {"decision": "rewrite", "reason": "joined the guides",
              "fields": {"epithet": "e2", "allegiance": "with", "circles": ["guides"]}}
    apply.apply_refresh_npcs(authored, "Shago", {}, output)
    assert authored["npcs"][0]["circles"] == ["guides"]
    assert authored["npcs"][0]["epithet"] == "e2"


def test_refresh_npcs_rewrite_orders_companies_before_factions():
    authored = {"npcs": [{"name": "Wren", "epithet": "e", "allegiance": "with",
                          "circles": []}],
                "site": {"circles": _REGISTRY}}
    output = {"decision": "rewrite", "reason": "r",
              "fields": {"epithet": "e", "allegiance": "with",
                         "circles": ["harpers", "port-nyanzaru"]}}
    apply.apply_refresh_npcs(authored, "Wren", {}, output)
    assert authored["npcs"][0]["circles"] == ["port-nyanzaru", "harpers"]


def test_refresh_npcs_rewrite_rejects_unknown_circle_key():
    authored = {"npcs": [{"name": "Shago", "epithet": "e", "allegiance": "with",
                          "circles": ["guides"]}],
                "site": {"circles": _REGISTRY}}
    output = {"decision": "rewrite", "reason": "r",
              "fields": {"epithet": "e2", "allegiance": "with", "circles": ["nope"]}}
    with pytest.raises(ValueError, match="unknown circle"):
        apply.apply_refresh_npcs(authored, "Shago", {}, output)
    # Nothing moved: the entry keeps its old prose and circles.
    assert authored["npcs"][0] == {"name": "Shago", "epithet": "e",
                                   "allegiance": "with", "circles": ["guides"]}


def test_refresh_npcs_no_change_leaves_circles():
    authored = {"npcs": [{"name": "Shago", "epithet": "e", "allegiance": "with",
                          "circles": ["guides"]}],
                "site": {"circles": _REGISTRY}}
    apply.apply_refresh_npcs(authored, "Shago", {},
                             {"decision": "no_change", "fields": None, "reason": ""})
    assert authored["npcs"][0]["circles"] == ["guides"]


def test_refresh_known_npcs_merges_circle_additions_append_only():
    """New circles are appended; a proposal whose key already exists is
    skipped (the pipeline never renames or removes a published circle)."""
    authored = {"site": {"known_npcs": ["A"],
                         "circles": [{"key": "guides", "title": "The Guides",
                                      "kind": "company"}]}}
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["A", "Xhosala"],
        "circles": [
            {"key": "guides", "title": "Renamed Guides", "kind": "company"},
            {"key": "obanashi", "title": "The Obanashi", "kind": "company"},
        ],
    }}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored["site"]["known_npcs"] == ["A", "Xhosala"]
    assert authored["site"]["circles"] == [
        {"key": "guides", "title": "The Guides", "kind": "company"},
        {"key": "obanashi", "title": "The Obanashi", "kind": "company"},
    ]


def test_refresh_known_npcs_rewrite_without_circles_keeps_registry():
    reg = [{"key": "guides", "title": "The Guides", "kind": "company"}]
    authored = {"site": {"known_npcs": ["A"], "circles": list(reg)}}
    output = {"decision": "rewrite", "reason": "r",
              "fields": {"known_npcs": ["A", "B"]}}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored["site"]["circles"] == reg


def test_refresh_known_npcs_creates_registry_when_absent():
    authored = {"site": {"known_npcs": ["A"]}}
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["A"],
        "circles": [{"key": "obanashi", "title": "The Obanashi", "kind": "company"}],
    }}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored["site"]["circles"] == [
        {"key": "obanashi", "title": "The Obanashi", "kind": "company"}]


def test_refresh_known_npcs_no_change_leaves_registry():
    reg = [{"key": "guides", "title": "The Guides", "kind": "company"}]
    authored = {"site": {"known_npcs": ["A"], "circles": list(reg)}}
    apply.apply_refresh_known_npcs(authored, "all", {},
                                   {"decision": "no_change", "fields": None, "reason": ""})
    assert authored["site"]["circles"] == reg


def _store_for_discovery():
    return {
        "site": {
            "known_npcs": ["Artus Cimber", "Xhosala"],
            "circles": [
                {"key": "horizon", "title": "The Horizon", "kind": "company"},
                {"key": "harpers", "title": "The Harpers", "kind": "faction"},
            ],
        },
        "npcs": [
            {"name": "Artus Cimber", "epithet": "e", "allegiance": "with",
             "circles": ["horizon"]},
            {"name": "Xhosala", "epithet": "e", "allegiance": "with", "circles": []},
        ],
    }


def test_refresh_known_npcs_places_existing_members_in_new_circle():
    """The per-NPC slices in the same run were prepared before this result
    existed, so a new circle's already-authored members are filed here, or
    the circle would sit memberless (and fail validation) until a hand edit.
    Placement keeps companies ahead of factions."""
    authored = _store_for_discovery()
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["Artus Cimber", "Xhosala"],
        "circles": [
            {"key": "obanashi", "title": "The Obanashi", "kind": "company",
             "members": ["Xhosala", "Artus Cimber"]},
            {"key": "ytepka-society", "title": "The Ytepka Society", "kind": "faction",
             "members": ["Xhosala"]},
        ],
    }}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    by_name = {n["name"]: n for n in authored["npcs"]}
    assert by_name["Xhosala"]["circles"] == ["obanashi", "ytepka-society"]
    assert by_name["Artus Cimber"]["circles"] == ["horizon", "obanashi"]
    assert [c["key"] for c in authored["site"]["circles"]] == [
        "horizon", "harpers", "obanashi", "ytepka-society"]
    # The stored registry entry carries only the registry fields.
    assert authored["site"]["circles"][2] == {
        "key": "obanashi", "title": "The Obanashi", "kind": "company"}


def test_refresh_known_npcs_defers_members_not_yet_authored():
    """A member who is in known_npcs but has no authored entry yet is filed
    when append-npcs authors them (their slice will carry the new circle)."""
    authored = _store_for_discovery()
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["Artus Cimber", "Xhosala", "Wainrath"],
        "circles": [{"key": "tamalka", "title": "Tamalka", "kind": "company",
                     "members": ["Wainrath", "Xhosala"]}],
    }}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored["site"]["known_npcs"][-1] == "Wainrath"
    assert authored["site"]["circles"][-1]["key"] == "tamalka"
    by_name = {n["name"]: n for n in authored["npcs"]}
    assert by_name["Xhosala"]["circles"] == ["tamalka"]
    assert "Wainrath" not in by_name


def test_refresh_known_npcs_rejects_member_outside_known_npcs():
    """A member name that is neither an existing nor a newly added known NPC
    is a typo or an invention; the whole result is refused, unapplied."""
    authored = _store_for_discovery()
    before = {"site": dict(authored["site"]), "npcs": [dict(n) for n in authored["npcs"]]}
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["Artus Cimber", "Xhosala", "Wainrath"],
        "circles": [{"key": "obanashi", "title": "The Obanashi", "kind": "company",
                     "members": ["Xhosala", "Xosala"]}],
    }}
    with pytest.raises(ValueError, match="not a known NPC"):
        apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored == before


def test_refresh_known_npcs_existing_key_is_skipped_with_its_members():
    """Append-only means an existing circle is never touched by discovery,
    not even to add members: that is refresh-npcs' job."""
    authored = _store_for_discovery()
    output = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["Artus Cimber", "Xhosala"],
        "circles": [{"key": "horizon", "title": "The Horizon, renamed",
                     "kind": "company", "members": ["Xhosala"]}],
    }}
    apply.apply_refresh_known_npcs(authored, "all", {}, output)
    assert authored["site"]["circles"][0]["title"] == "The Horizon"
    assert authored["npcs"][1]["circles"] == []


# -- apply_refresh_ascent_read -----------------------------------------------

def test_apply_refresh_ascent_read_rewrite():
    authored = {"site": {"ascent_read": "old"}}
    apply.apply_refresh_ascent_read(
        authored, "all", {}, {"decision": "rewrite",
                              "fields": {"ascent_read": "new line"}, "reason": "x"})
    assert authored["site"]["ascent_read"] == "new line"


def test_apply_refresh_ascent_read_no_change():
    authored = {"site": {"ascent_read": "old"}}
    apply.apply_refresh_ascent_read(
        authored, "all", {}, {"decision": "no_change", "fields": None, "reason": "x"})
    assert authored["site"]["ascent_read"] == "old"


# -- distinction_basis persistence -------------------------------------------

def test_apply_refresh_characters_persists_basis():
    authored = {"characters": [{"id": "a", "epithet": "x", "reliquary_header": "h",
                "constellation_epithet": "c", "distinction_title": "old",
                "distinction_subtitle": "s", "distinction_detail": "d"}]}
    output = {"decision": "rewrite", "fields": {"a": {
        "epithet": "x2", "constellation_epithet": "c2",
        "distinction_title": "Luckiest Hand", "distinction_subtitle": "s2",
        "distinction_detail": "<b>4.1</b> average",
        "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}}}}
    apply.apply_refresh_characters(authored, "all", {}, output)
    c = authored["characters"][0]
    assert c["distinction_title"] == "Luckiest Hand"
    assert c["distinction_basis"] == {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}

def test_apply_append_characters_persists_basis():
    authored = {"characters": []}
    output = {"fields": {"a": {
        "epithet": "e", "reliquary_header": "r", "constellation_epithet": "c",
        "distinction_title": "t", "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "narrative", "sessions": [3], "note": "n"}}}}
    apply.apply_append_characters(authored, "all", {}, output)
    assert authored["characters"][0]["distinction_basis"]["kind"] == "narrative"


def test_append_characters_rejects_existing_id():
    authored = {"characters": [{"id": "vex"}]}
    output = {"fields": {"vex": {"epithet": "e", "reliquary_header": "r",
                                 "constellation_epithet": "c",
                                 "distinction_title": "t", "distinction_subtitle": "s",
                                 "distinction_detail": "d", "distinction_basis": {}}}}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_characters(authored, "all", {}, output)
