"""Tests for the XP-threshold helpers and compute_ascent geometry."""
from build import render


def test_level_for_xp_boundaries():
    assert render._level_for_xp(0) == 1
    assert render._level_for_xp(299) == 1
    assert render._level_for_xp(300) == 2
    assert render._level_for_xp(899) == 2
    assert render._level_for_xp(900) == 3      # party sits exactly here
    assert render._level_for_xp(2699) == 3
    assert render._level_for_xp(2700) == 4


def test_next_threshold():
    assert render._next_threshold(2) == 900
    assert render._next_threshold(3) == 2700
    assert render._next_threshold(20) is None  # capped


import json
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures" / "sample_xp_log.json"


def _load_fixture():
    return json.loads(FIX.read_text())


def test_compute_ascent_none_when_empty():
    assert render.compute_ascent({"entries": []}) is None
    assert render.compute_ascent(None) is None


def test_compute_ascent_cumulative_and_summary():
    a = render.compute_ascent(_load_fixture())
    # 7 nodes: a ground node at 0 plus 6 deeds
    assert len(a["nodes"]) == 7
    assert a["nodes"][0]["total"] == 0
    assert a["nodes"][0]["type"] is None
    assert [n["total"] for n in a["nodes"]] == [0, 300, 390, 610, 685, 775, 900]
    assert a["total"] == 900
    assert a["level_num"] == 3
    assert a["level"] == "III"
    assert a["next_threshold"] == 2700
    assert a["to_next"] == 1800
    assert a["deeds"] == 6
    assert a["sessions"] == 4
    assert a["richest_xp"] == 300
    assert a["richest_title"] == "Reached Port Nyanzaru"


def test_compute_ascent_levelups_and_sources():
    a = render.compute_ascent(_load_fixture())
    ups = {n["total"]: n["up"] for n in a["nodes"] if n["up"]}
    assert ups == {300: "II", 900: "III"}      # the two threshold crossings
    src = {s["type"]: s["xp"] for s in a["sources"]}
    assert src == {"milestone": 425, "combat": 220, "quest": 90, "roleplay": 90, "discovery": 75}
    # ymax is the next threshold; thresholds within (0, ymax] are II, III, IV
    assert a["ymax"] == 2700
    assert [t["lvl"] for t in a["thresholds"]] == ["II", "III", "IV"]
    assert a["thresholds"][-1]["top"] is True


def test_compute_ascent_geometry_well_formed():
    a = render.compute_ascent(_load_fixture())
    assert a["line_d"].startswith("M ")
    assert a["area_d"].endswith(" Z")
    # every node x is inside the plot box, ascending left to right
    xs = [n["cx"] for n in a["nodes"]]
    assert xs == sorted(xs)
    assert a["plot_left"] <= xs[0] and xs[-1] <= a["plot_right"]
    # session ticks: one per distinct session (4), the s4 group is multi
    assert len(a["ticks"]) == 4
    assert a["ticks"][-1]["multi"] is True


def test_compute_ascent_at_max_level_has_no_next_threshold():
    # A party at level 20 (>= 355,000 XP) has no next threshold; the template
    # must guard on this (next_threshold None, to_next 0) and not crash.
    log = {"entries": [
        {"id": "x", "date": "2026-04-19", "sessionId": "s1",
         "title": "Apotheosis", "type": "milestone", "perPc": 355000},
    ]}
    a = render.compute_ascent(log)
    assert a["level_num"] == 20
    assert a["next_threshold"] is None
    assert a["to_next"] == 0
    assert a["ymax"] == a["total"]  # ceiling falls back to the current total
