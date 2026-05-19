"""Tests for build/prepare.py — slice gathering and run-dir population."""
import json
import os
import shutil
from pathlib import Path

import pytest

from build import prepare, render
from build.paths import REPO_ROOT

FIXTURES = REPO_ROOT / "tests/fixtures"


# -- Frontmatter parser (moved from build/invoke.py) ------------------------

def test_parse_frontmatter_no_marker_returns_text_unchanged():
    fm, body = prepare.parse_frontmatter("no marker here\nbody body")
    assert fm == {}
    assert body == "no marker here\nbody body"


def test_parse_frontmatter_key_value_pairs():
    fm, body = prepare.parse_frontmatter("---\nmodel: opus\n---\nbody\n")
    assert fm == {"model": "opus"}
    assert body == "body\n"


def test_parse_frontmatter_empty_block():
    fm, body = prepare.parse_frontmatter("---\n---\nbody\n")
    assert fm == {}
    assert body == "body\n"


def test_parse_frontmatter_crlf_tolerated():
    fm, body = prepare.parse_frontmatter("---\r\nmodel: sonnet\r\n---\r\nbody\r\n")
    assert fm == {"model": "sonnet"}


def test_parse_frontmatter_unclosed_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nmodel: opus\nbody but no close")


def test_parse_frontmatter_malformed_line_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nthis has no colon\n---\nbody")


# -- Slice gathering + run-dir population -----------------------------------


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    """Stage a fixture data dir, authored dir, and isolated run root."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    (data_dir / "dice").mkdir()
    shutil.copy(FIXTURES / "sample_dicex_rolls.json",
                data_dir / "dice" / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    run_root = tmp_path / "runs"
    run_root.mkdir()

    monkeypatch.setenv("BUILD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(authored_dir))
    monkeypatch.setenv("BUILD_RUN_ROOT", str(run_root))
    return tmp_path


def test_prepare_creates_manifest_and_pending_files(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    # Manifest has expected top-level shape.
    assert "run_id" in manifest
    assert "marker" in manifest
    assert "latest" in manifest
    assert isinstance(manifest["slices"], list)
    assert len(manifest["slices"]) > 0

    # Every slice has a pending file on disk.
    for entry in manifest["slices"]:
        assert (run_dir / entry["pending"]).exists()
        assert (run_dir / entry["prompt_body"]).exists()
        assert (run_dir / entry["schema"]).exists()


def test_prepare_skips_refresh_pass_when_marker_current(run_env, monkeypatch):
    # Bump marker to latest so no refresh slices are produced.
    from build.store import load_authored, bump_marker
    authored = load_authored()
    data = render.load_data(os.environ["BUILD_DATA_DIR"])
    latest = len(data["session_log"]["entries"])
    bump_marker(authored, latest)

    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    refresh_slices = [s for s in manifest["slices"] if s["pass"] in ("discovery", "refresh")]
    assert refresh_slices == []


def test_prepare_includes_refresh_under_force(run_env):
    # Marker is whatever fixture says; force_refresh should add refresh slices.
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert any(s["pass"] == "refresh" for s in manifest["slices"])


def test_prepare_no_refresh_excludes_refresh_slices(run_env):
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert not any(s["pass"] in ("discovery", "refresh") for s in manifest["slices"])


def test_prepare_stem_sanitization(run_env):
    """Stems must be filesystem-safe."""
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        # Stem matches pending filename root.
        assert entry["pending"] == f"pending/{entry['stem']}.json"
        # Only safe characters.
        assert all(c.isalnum() or c in "._-" for c in entry["stem"])


def test_prepare_model_from_prompt_frontmatter(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    models = {s["model"] for s in manifest["slices"]}
    # All entries should declare a model (default "sonnet" if absent).
    assert all(m for m in models)


def test_prepare_writes_keep_marker_when_keep_temp(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=True)
    assert (run_dir / ".keep").exists()


def test_prepare_no_keep_marker_by_default(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    assert not (run_dir / ".keep").exists()


# -- CLI dispatch ------------------------------------------------------------

def test_main_prepare_subcommand_creates_run_dir(run_env, capsys):
    from build.__main__ import main
    rc = main(["prepare", "--no-refresh"])
    assert rc == 0
    captured = capsys.readouterr()
    # main should print the run dir path so the user can pass it to the skill.
    assert "build/.run" in captured.out or "runs/" in captured.out


def test_main_apply_subcommand_requires_path(run_env, capsys):
    from build.__main__ import main
    rc = main(["apply"])
    assert rc != 0  # parser should reject missing positional
