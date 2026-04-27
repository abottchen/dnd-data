"""Tests for build slice builders (replaces the retired test_helpers.py).

Slice builders are pure functions of (data, authored) — no subprocess needed.
Each test materializes the fixture data + authored store under tmp_path and
calls the builder directly.
"""
import json
import shutil
from pathlib import Path

import pytest

from build import render, slices, store

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests/fixtures"


@pytest.fixture
def slice_env(tmp_path, monkeypatch):
    """Materialize a writable copy of fixture data + authored store under
    tmp_path. Returns (data_dict, authored_dict). BUILD_AUTHORED_DIR is
    monkeypatched so store.load_authored() points at the fixture copy."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    shutil.copy(FIXTURES / "sample_dicex_rolls.json", data_dir / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(authored_dir))

    data = render.load_data(data_dir)
    authored = store.load_authored()
    return {"data": data, "authored": authored, "authored_dir": authored_dir}


# -- Append-pass coverage ----------------------------------------------------

def test_append_kills_emits_slice_per_session_with_new_kills(slice_env):
    """Fixture has 3 kills (Anton: Goblin Apr 19, Anton: Bandit Apr 23,
    Vex: Goblin Apr 19) and 1 authored kill (Anton's Goblin). Expect:
      - one slice for 2026-04-19 with Vex's Goblin
      - one slice for 2026-04-23 with Anton's Bandit
    """
    out = slices.append_kills(slice_env["data"], slice_env["authored"])
    by_key = dict(out)
    assert set(by_key) == {"2026-04-19", "2026-04-23"}
    assert len(by_key["2026-04-19"]["kills"]) == 1
    assert len(by_key["2026-04-23"]["kills"]) == 1

    s = by_key["2026-04-19"]
    assert s["session"] == 1
    assert s["real_date"] == "2026-04-19"
    assert any(k["character"] == "vex" and k["creature"] == "Goblin" for k in s["kills"])
    assert "Daggerford" in s["narrative"]


def test_append_sessions_emits_slice_per_unauthored_session(slice_env):
    out = slices.append_sessions(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == 2
    assert body["session"] == 2
    assert body["real_date"] == "2026-04-23"
    assert "crossroads" in body["narrative"]
    assert body["chapter_marker"] is True


def test_append_chapters_emits_slice_per_unauthored_marker(slice_env):
    out = slices.append_chapters(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "2"
    assert body["starts_at_session"] == 2
    assert "crossroads" in body["narrative"]


def test_append_npcs_emits_slice_per_unauthored_npc(slice_env):
    out = slices.append_npcs(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "Azlund"
    assert body["name"] == "Azlund"
    assert any("Azlund" in m["line"] for m in body["mentions"])


def test_append_characters_emits_one_bundled_slice(slice_env):
    out = slices.append_characters(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "all"
    assert len(body["new_pcs"]) == 1
    assert body["new_pcs"][0]["id"] == "vex"
    assert "Sharpest Tongue" in body["existing_distinction_titles"]


# -- Refresh-pass coverage ---------------------------------------------------

def test_refresh_chapters_returns_slice_per_authored_chapter(slice_env):
    out = slices.refresh_chapters(slice_env["data"], slice_env["authored"])
    by_key = dict(out)
    assert set(by_key) == {"1"}
    assert by_key["1"]["existing"]["title"]


def test_refresh_characters_emits_one_bundle_slice(slice_env):
    out = slices.refresh_characters(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "all"
    assert any(c["id"] == "anton" for c in body["pcs"])
    assert "trials_per_char" in body
    assert "fortune_by_char" in body
    assert "existing" in body


def test_refresh_npcs_with_authored_npc(slice_env):
    """Add 'Azlund' to authored npcs; refresh-npcs should emit a slice for it
    with the full mention history."""
    npcs_path = slice_env["authored_dir"] / "npcs.json"
    npcs_path.write_text(json.dumps([
        {"name": "Azlund", "allegiance": "with",
         "epithet": "the merchant who brokers what others would not"}
    ]))
    authored = store.load_authored()
    out = slices.refresh_npcs(slice_env["data"], authored)
    by_key = dict(out)
    assert "Azlund" in by_key
    assert any("Azlund" in m["line"] for m in by_key["Azlund"]["mentions"])
    assert by_key["Azlund"]["existing"]["allegiance"] == "with"


def test_refresh_road_ahead_emits_singleton(slice_env):
    out = slices.refresh_road_ahead(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "all"
    assert "new_sessions" in body
    assert "existing" in body
    assert "Azlund's offer" in {e["name"] for e in body["existing"]["known"]}


def test_refresh_intro_epithet_emits_singleton(slice_env):
    out = slices.refresh_intro_epithet(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "all"
    assert "new_sessions" in body
    assert "road_ahead_known" in body
    assert body["existing"] == "A small ledger."


def test_refresh_known_npcs_emits_singleton(slice_env):
    out = slices.refresh_known_npcs(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, body = out[0]
    assert key == "all"
    assert "sessions" in body
    assert body["existing"] == ["Azlund"]


def test_refresh_known_npcs_passes_full_session_history(slice_env):
    """Discovery is name-extraction, not new-evidence evaluation: every
    session entry is passed regardless of refreshed_through_session."""
    out = slices.refresh_known_npcs(slice_env["data"], slice_env["authored"])
    _, body = out[0]
    total = len(slice_env["data"]["session_log"]["entries"])
    assert len(body["sessions"]) == total


def test_refresh_known_npcs_tolerates_missing_known_npcs_field(slice_env):
    """Cold-start friendly: site.json without `known_npcs` yields existing=[]."""
    authored = dict(slice_env["authored"])
    authored["site"] = {**authored["site"]}
    authored["site"].pop("known_npcs", None)
    out = slices.refresh_known_npcs(slice_env["data"], authored)
    _, body = out[0]
    assert body["existing"] == []


# -- Cold-start coverage -----------------------------------------------------

@pytest.mark.parametrize("builder_name", [
    "append_kills",
    "append_sessions",
    "append_chapters",
    "append_npcs",
    "append_characters",
])
def test_append_builders_tolerate_empty_authored(slice_env, builder_name, tmp_path, monkeypatch):
    """Cold start: an empty authored dir (no JSON files yet) yields empty
    containers from store.load_authored. Append builders must run cleanly,
    treating the authored store as empty rather than crashing."""
    empty_authored = tmp_path / "empty-authored"
    empty_authored.mkdir()
    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(empty_authored))
    authored = store.load_authored()
    builder = getattr(slices, builder_name)
    out = builder(slice_env["data"], authored)
    assert isinstance(out, list)
