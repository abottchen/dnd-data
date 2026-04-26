"""Tests for hydrate.apply — the functions that mutate the in-memory authored
store from a transformer's structured_output. These tests use synthetic
authored / slice / output dicts; no subprocess, no fixtures on disk."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hydrate import apply  # noqa: E402


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
    }, "reason": "test"}
    apply.apply_append_npcs(authored, key="Azlund",
                            slice_data=slice_data, output=output)
    assert authored["npcs"] == [{
        "name": "Azlund",
        "epithet": "the merchant who brokers what others would not",
        "allegiance": "with",
    }]


def test_append_npcs_tolerates_null_allegiance():
    authored = {"npcs": []}
    output = {"fields": {"epithet": "ambiguous", "allegiance": None},
              "reason": "test"}
    apply.apply_append_npcs(authored, key="Stranger",
                            slice_data={"name": "Stranger", "mentions": []},
                            output=output)
    assert authored["npcs"][0]["allegiance"] is None


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
