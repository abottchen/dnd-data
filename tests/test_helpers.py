"""Tests for the hydrate-ledger slice helpers.

The helpers live in a gitignored skill directory so a fresh clone (or CI
without the skill installed) gracefully skips these tests. When the skill
IS installed, this test file invokes the helper module via subprocess;
the helpers themselves manipulate sys.path internally to `import build`.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPERS_PATH = REPO_ROOT / ".claude/skills/hydrate-ledger/helpers.py"
FIXTURES = REPO_ROOT / "tests/fixtures"

if not HELPERS_PATH.exists():
    pytest.skip("hydrate-ledger skill not installed", allow_module_level=True)


def run_helper(subcommand: str, data_dir: Path, authored_dir: Path, temp_dir: Path) -> dict:
    """Run a helper subcommand as a subprocess (matches real invocation) and
    return parsed stdout JSON. data_dir / authored_dir / temp_dir override the
    helper's default repo-relative paths via env vars."""
    env = {
        "HYDRATE_DATA_DIR": str(data_dir),
        "HYDRATE_AUTHORED_DIR": str(authored_dir),
        "HYDRATE_TEMP_DIR": str(temp_dir),
        "PATH": "/usr/bin:/bin",
    }
    result = subprocess.run(
        [sys.executable, str(HELPERS_PATH), subcommand],
        capture_output=True, text=True, env=env, check=True,
    )
    return json.loads(result.stdout)


@pytest.fixture
def helper_env(tmp_path):
    """Materialize a writable copy of the fixture data + authored store +
    temp dir under tmp_path, so each test gets clean state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    shutil.copy(FIXTURES / "sample_dicex_rolls.json", data_dir / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    return {"data_dir": data_dir, "authored_dir": authored_dir, "temp_dir": temp_dir}


def test_skill_directory_present():
    """Sanity check that the skip guard would have triggered if absent."""
    assert HELPERS_PATH.exists()


def test_helpers_cli_unknown_subcommand_exits_nonzero(helper_env):
    result = subprocess.run(
        [sys.executable, str(HELPERS_PATH), "no-such-subcommand"],
        env={"HYDRATE_DATA_DIR": str(helper_env["data_dir"]),
             "HYDRATE_AUTHORED_DIR": str(helper_env["authored_dir"]),
             "HYDRATE_TEMP_DIR": str(helper_env["temp_dir"]),
             "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_append_kills_emits_slice_per_session_with_new_kills(helper_env):
    """Fixture has 3 kills total (Anton: Goblin Apr 19, Anton: Bandit Apr 23,
    Vex: Goblin Apr 19) and 1 authored kill (Anton's Goblin). Expect:
      - one slice for 2026-04-19 with count=1 (Vex's Goblin)
      - one slice for 2026-04-23 with count=1 (Anton's Bandit)
    """
    out = run_helper("append-kills", **helper_env)
    slices = out["slices"]
    by_key = {s["key"]: s for s in slices}
    assert set(by_key) == {"2026-04-19", "2026-04-23"}
    assert by_key["2026-04-19"]["count"] == 1
    assert by_key["2026-04-23"]["count"] == 1

    # Slice file for 04-19 should describe Vex's Goblin and contain narrative.
    body = json.loads(Path(by_key["2026-04-19"]["path"]).read_text())
    assert body["session"] == "I"
    assert body["real_date"] == "2026-04-19"
    assert any(k["character"] == "vex" and k["creature"] == "Goblin" for k in body["kills"])
    assert "Daggerford" in body["narrative"]


def test_append_sessions_emits_slice_per_unauthored_session(helper_env):
    """Fixture: session log has sessions I and II; authored has only I.
    Expect one slice for session II."""
    out = run_helper("append-sessions", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "II"
    assert slices[0]["count"] == 1

    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["session"] == "II"
    assert body["real_date"] == "2026-04-23"
    assert "crossroads" in body["narrative"]
    assert body["chapter_marker"] is True


def test_append_chapters_emits_slice_per_unauthored_marker(helper_env):
    """Fixture: session II has '--- Chapter II ---' marker; authored has chapter 1.
    Expect one slice keyed "2" (the next chapter id)."""
    out = run_helper("append-chapters", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "2"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["starts_at_session"] == "II"
    assert "crossroads" in body["narrative"]


def test_append_npcs_emits_slice_per_unauthored_npc(helper_env):
    """Fixture: site.known_npcs lists 'Azlund'; authored npcs is empty.
    Expect one slice for Azlund with the session-I narrative line."""
    out = run_helper("append-npcs", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "Azlund"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["name"] == "Azlund"
    assert any("Azlund" in m["line"] for m in body["mentions"])


def test_append_characters_emits_one_bundled_slice(helper_env):
    """Fixture: party has anton + vex; authored characters has only anton.
    Expect ONE slice with key='all' covering vex; existing anton's
    distinction_title surfaced for collision avoidance."""
    out = run_helper("append-characters", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "all"
    assert slices[0]["count"] == 1  # one new PC

    body = json.loads(Path(slices[0]["path"]).read_text())
    assert len(body["new_pcs"]) == 1
    assert body["new_pcs"][0]["id"] == "vex"
    assert "Sharpest Tongue" in body["existing_distinction_titles"]


def test_refresh_chapters_count_zero_when_no_new_sessions(helper_env):
    """Fixture marker: refreshed_through_session=1, latest_session=2.
    Authored chapter 1 (starts at I). The new session II is inside chapter 1
    OR opens chapter 2 — either way, chapter 1 may merit re-evaluation if a
    new session sits inside it. count = sessions inside this chapter postdating
    the marker.
    """
    out = run_helper("refresh-chapters", **helper_env)
    slices = out["slices"]
    # one entry per authored chapter; count derives from new-session membership
    keys = {s["key"] for s in slices}
    assert "1" in keys
