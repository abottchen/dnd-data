"""Landing-hero + Chronicle-archive compute helpers.

Covers compute_latest / compute_recent / compute_gauge / compute_road_ahead_digest
and their wiring into compute_all's context.
"""
from pathlib import Path

import pytest

from build.compute import (
    compute_ascent,
    compute_gauge,
    compute_latest,
    compute_recent,
    compute_road_ahead_digest,
)


def _chron(chapters):
    return {"chapters": chapters, "rail": []}


def _session(sid, title, kills=0):
    return {
        "id": sid, "label": "S", "title": title, "summary": f"sum-{sid}",
        "silent_roll": [], "iu_date": "12 Eleasis", "real_date_label": "13 JUL 2026",
        "kills_count": kills, "kill_pips": [{"creature": "x"}] * kills,
    }


# ── compute_latest ───────────────────────────────────────────────────────────

def test_latest_is_last_session_of_last_chapter():
    ch = compute_latest(_chron([
        {"label": "I", "title": "Ch One", "sessions": [_session(1, "a")]},
        {"label": "II", "title": "Ch Two", "sessions": [_session(2, "b"), _session(3, "c", kills=2)]},
    ]))
    assert ch["chapter_label"] == "II"
    assert ch["chapter_title"] == "Ch Two"
    assert ch["session_id"] == 3
    assert ch["title"] == "c"
    assert ch["summary"] == "sum-3"
    assert ch["kills_count"] == 2


def test_latest_none_when_no_sessions():
    assert compute_latest(_chron([])) is None
    assert compute_latest(_chron([{"label": "I", "title": "x", "sessions": []}])) is None


# ── compute_recent ───────────────────────────────────────────────────────────

def test_recent_excludes_latest_most_recent_first():
    rec = compute_recent(_chron([
        {"label": "I", "title": "c", "sessions": [_session(1, "a"), _session(2, "b"), _session(3, "c")]},
    ]), n=2)
    assert [r["id"] for r in rec] == [2, 1]
    assert rec[0]["title"] == "b"


def test_recent_handles_single_session():
    assert compute_recent(_chron([{"label": "I", "title": "x", "sessions": [_session(1, "a")]}])) == []


# ── compute_gauge ────────────────────────────────────────────────────────────

def test_gauge_none_without_xp():
    assert compute_gauge(None) is None
    assert compute_gauge(compute_ascent({"entries": []})) is None


def test_gauge_frames_climb_below_next_level():
    xp = {"entries": [
        {"date": "2026-03-15", "perPc": 300, "type": "combat", "title": "t1", "sessionId": "1"},
        {"date": "2026-04-01", "perPc": 400, "type": "quest", "title": "t2", "sessionId": "2"},
    ]}
    a = compute_ascent(xp)
    g = compute_gauge(a)
    # current point sits BELOW the next-level (goal) line → larger y in SVG coords
    assert g["last_cy"] > g["goal_y"]
    assert g["level"] == a["level"]
    assert g["next_level"] == "III"  # 700 XP → level II, next is III
    assert g["total_fmt"] == f'{a["total"]:,}'
    assert g["next_fmt"] == f'{a["next_threshold"]:,}'
    assert g["at_summit"] is False
    # viewBox spans from just above the goal line down to the baseline
    assert g["view_y"] < g["goal_y"] < g["view_y"] + g["view_h"]


# ── compute_road_ahead_digest ────────────────────────────────────────────────

def test_road_digest_caps_and_counts_overflow():
    ra = {"direction": "south to Shilku",
          "known": [{"name": f"n{i}", "gloss": "g"} for i in range(8)]}
    d = compute_road_ahead_digest(ra, n=5)
    assert d["direction"] == "south to Shilku"
    assert len(d["known"]) == 5
    assert d["more_count"] == 3


def test_road_digest_handles_missing():
    assert compute_road_ahead_digest(None) == {"direction": "", "known": [], "more_count": 0}


# ── compute_all wiring (integration; skips if gitignored data/ is absent) ─────

def test_compute_all_exposes_landing_keys():
    root = Path(__file__).resolve().parent.parent
    if not (root / "data" / "party.json").exists():
        pytest.skip("data/ not present (gitignored)")
    from build.render import load_data, load_authored
    from build.compute import compute_all

    data = load_data(root / "data")
    authored = load_authored(root / "build")
    ctx = compute_all(data, authored)
    assert {"latest", "recent", "gauge", "road_ahead_digest"} <= ctx.keys()
    assert ctx["latest"]["session_id"] >= 1
    assert isinstance(ctx["recent"], list)
