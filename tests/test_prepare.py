"""Tests for build/prepare.py — slice gathering and run-dir population."""
import json
import os
from pathlib import Path

import pytest

from build import prepare, render


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
def run_env(staged_env):
    """Thin wrapper over staged_env: stage a fixture data dir, authored dir,
    and isolated run root. Returns tmp_path."""
    return staged_env


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


def test_prepare_records_verify_prompt_for_append_sessions(run_env):
    """append-sessions pairs an independent verify pass. When it emits a slice,
    prepare must freeze the verify prompt + schema and record them in the
    manifest's `verify` map so /build-prose can dispatch the verifier in the
    same run (same-build fact-check)."""
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert "append-sessions" in manifest["verify"], manifest["verify"]
    vm = manifest["verify"]["append-sessions"]
    assert (run_dir / vm["prompt_body"]).exists()
    assert (run_dir / vm["schema"]).exists()
    assert vm["model"] in {"sonnet", "opus"}


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
    # All entries should declare a known model (default "sonnet" if absent).
    assert models <= {"sonnet", "opus", "fable"}


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


def test_prepare_records_edit_prompt_for_append_sessions(run_env):
    """append-sessions also pairs an editor pass (a reader's critique the author
    revises against, before the fact verifier runs). When it emits a slice,
    prepare must freeze the edit prompt + schema and record them in the
    manifest's `edit` map so /build-prose can drive the critique/revise loop."""
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert "append-sessions" in manifest["edit"], manifest.get("edit")
    em = manifest["edit"]["append-sessions"]
    assert (run_dir / em["prompt_body"]).exists()
    assert (run_dir / em["schema"]).exists()
    assert em["model"] in {"sonnet", "opus", "fable"}
    assert em["max_rounds"] >= 1


# -- Prompt includes + chronicle context ------------------------------------

def test_expand_includes_inlines_shared_prompt_text(tmp_path):
    """`{{include: name.md}}` on a line of its own becomes that file's body,
    with the included file's own frontmatter stripped."""
    (tmp_path / "publisher-notes.md").write_text("---\nmodel: opus\n---\n> the note\n")
    body = "head\n{{include: publisher-notes.md}}\ntail\n"
    out = prepare.expand_includes(body, prompts_dir=tmp_path)
    assert out == "head\n> the note\ntail\n"


def test_expand_includes_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare.expand_includes("{{include: nope.md}}", prompts_dir=tmp_path)


def test_expand_includes_missing_publisher_notes_names_it_as_local(tmp_path):
    """publisher-notes.md is gitignored, so a fresh clone lacks it. prepare
    stops and says which file and why, rather than building without it."""
    with pytest.raises(FileNotFoundError, match="local and gitignored"):
        prepare.expand_includes("{{include: publisher-notes.md}}", prompts_dir=tmp_path)


def test_prepare_freezes_the_stand_in_for_the_publishers_notes(run_env):
    """The publisher's notes exist only on the publisher's machine, so the
    suite points prepare at its own prompts dir (BUILD_PROMPTS_DIR) carrying a
    stand-in. The frozen writer prompt must come from there, not from the
    repo's .claude/prompts/, or every prepare.run fails on a fresh clone."""
    stand_in = (Path(os.environ["BUILD_PROMPTS_DIR"]) / "publisher-notes.md").read_text()
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    writer = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    assert stand_in.strip() in (run_dir / writer["prompt_body"]).read_text()


def test_prepare_freezes_prompts_with_includes_expanded(run_env):
    """The frozen writer and editor prompts carry the publisher's notes
    inline, so the run dir records exactly what the agents read."""
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    frozen = {(run_dir / s["prompt_body"]).read_text() for s in manifest["slices"]}
    frozen.add((run_dir / manifest["edit"]["append-sessions"]["prompt_body"]).read_text())
    assert not any("{{include:" in t for t in frozen)


def test_prepare_writes_chronicle_context_for_session_slices(run_env):
    """The editor's first read is pages only, so the chronicle goes in a file
    of its own that the skill hands over before the slice."""
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    sess = [s for s in manifest["slices"] if s["transformer"] == "append-sessions"]
    assert sess and all("chronicle" in s for s in sess)
    for s in sess:
        pages = json.loads((run_dir / s["chronicle"]).read_text())
        assert isinstance(pages, list) and all({"session", "title", "text"} <= set(p) for p in pages)
    others = [s for s in manifest["slices"] if s["transformer"] != "append-sessions"]
    assert not any("chronicle" in s for s in others)


def test_prepare_records_plan_prompt_for_append_sessions(run_env):
    """append-sessions is planned before it is written: the planner's output
    is shown to the publisher for sign-off, and the approved plan is an input
    to the writer and the editor. prepare freezes the plan prompt + schema and
    records them in the manifest's `plan` map."""
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert "append-sessions" in manifest["plan"], manifest.get("plan")
    pm = manifest["plan"]["append-sessions"]
    assert (run_dir / pm["prompt_body"]).exists()
    assert (run_dir / pm["schema"]).exists()
    assert pm["model"] in {"sonnet", "opus", "fable"}
    assert "{{include:" not in (run_dir / pm["prompt_body"]).read_text()
