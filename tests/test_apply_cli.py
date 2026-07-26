"""Tests for build/apply_cli.py — manifest-driven result application."""
import json
import shutil
from pathlib import Path

import pytest

from build import apply_cli, prepare, store


@pytest.fixture
def staged_run(staged_env):
    """Thin wrapper over staged_env: run prepare against the fixtures to
    produce a real run dir. Returns (run_dir, authored_dir)."""
    authored_dir = staged_env / "authored"
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    return run_dir, authored_dir


@pytest.fixture
def staged_refresh_run(staged_env):
    """Like staged_run, but with the refresh pass forced on so refresh slices
    (e.g. refresh-road-ahead) exist in the manifest."""
    authored_dir = staged_env / "authored"
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    return run_dir, authored_dir


def _write_result(run_dir: Path, entry: dict, payload: dict) -> None:
    """Helper: write the JSON result for one manifest entry."""
    (run_dir / entry["result"]).write_text(json.dumps(payload, indent=2))


def _valid_payload_for(entry: dict, run_dir: Path) -> dict:
    """Build a minimal schema-valid result payload for a manifest entry,
    switching on its transformer. Covers the append transformers emitted by
    the staged_run fixture (no_refresh=True keeps it to append-only)."""
    transformer = entry["transformer"]
    if transformer == "append-kills":
        return {"fields": {}, "reason": "test fixture"}
    if transformer == "append-sessions":
        return {
            "fields": {
                "title": "Test Title",
                "summary": "A short summary of this session.",
                "silent_roll": [],
            },
            "reason": "test fixture",
        }
    if transformer == "append-chapters":
        return {
            "fields": {
                "title": "Test Chapter",
                "epigraph": "A test epigraph.",
            },
            "reason": "test fixture",
        }
    if transformer == "append-npcs":
        return {
            "fields": {
                "epithet": "the Tested",
                "allegiance": None,
            },
            "reason": "test fixture",
        }
    if transformer == "append-characters":
        return {"fields": {}, "reason": "test fixture"}
    raise NotImplementedError(
        f"_valid_payload_for has no builder for transformer {transformer!r}")


def test_apply_missing_results_reports_pending(staged_run):
    run_dir, _ = staged_run
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert summary["pending"]  # at least one slice without a result
    assert summary["applied"] == []
    assert summary["render_ok"] is None  # render was skipped


def test_apply_validates_schema_and_rejects_malformed(staged_run):
    run_dir, _ = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    # Pick the first append-sessions slice — its schema requires a "fields"
    # object. Write something that fails validation.
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    _write_result(run_dir, target, {"bogus": "not the right shape"})

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    rejected = run_dir / "results" / "rejected"
    assert (rejected / f"{target['stem']}.json").exists()
    assert (rejected / f"{target['stem']}.error.json").exists()
    assert target["stem"] in {p["stem"] for p in summary["rejected"]}


def test_apply_applies_valid_results_and_persists_authored(staged_run):
    """Write a schema-valid append-sessions result and confirm the authored
    store gains the session entry after apply."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    slice_data = json.loads((run_dir / target["pending"]).read_text())

    _write_result(run_dir, target, {
        "fields": {
            "title": "Test Title",
            "summary": "A short summary of this session.",
            "silent_roll": []
        },
        "reason": "test fixture"
    })

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert target["stem"] in {a["stem"] for a in summary["applied"]}

    sessions = json.loads((authored_dir / "sessions.json").read_text())
    matching = [s for s in sessions if s["session"] == slice_data["session"]]
    assert matching
    assert matching[0]["title"] == "Test Title"


def test_apply_is_idempotent_on_rerun(staged_run):
    """A second apply pass with the same result file should not double-apply."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    slice_data = json.loads((run_dir / target["pending"]).read_text())

    _write_result(run_dir, target, {
        "fields": {
            "title": "Idempotent",
            "summary": "Once.",
            "silent_roll": []
        },
        "reason": "test fixture"
    })

    apply_cli.apply_run(run_dir, skip_render=True)
    apply_cli.apply_run(run_dir, skip_render=True)

    sessions = json.loads((authored_dir / "sessions.json").read_text())
    matching = [s for s in sessions if s["session"] == slice_data["session"]]
    assert len(matching) == 1  # not duplicated by the second apply


def test_apply_reads_slice_from_done_when_skill_moved_it(staged_run):
    """The /build-prose skill moves authored slices from pending/ to done/.
    apply_cli must still find the slice in that case."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    slice_data = json.loads((run_dir / target["pending"]).read_text())

    _write_result(run_dir, target, {
        "fields": {
            "title": "Moved-to-done Title",
            "summary": "Slice was relocated by the skill.",
            "silent_roll": []
        },
        "reason": "test fixture"
    })

    # Simulate the build-prose skill moving the slice after authoring.
    done_dir = run_dir / "done"
    done_dir.mkdir(exist_ok=True)
    shutil.move(str(run_dir / target["pending"]),
                str(done_dir / f"{target['stem']}.json"))

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert target["stem"] in {a["stem"] for a in summary["applied"]}
    sessions = json.loads((authored_dir / "sessions.json").read_text())
    matching = [s for s in sessions if s["session"] == slice_data["session"]]
    assert matching and matching[0]["title"] == "Moved-to-done Title"


def test_apply_failure_in_apply_fn_rejects_slice_and_continues(staged_run):
    """A schema-valid result that the apply function refuses (e.g. unknown
    kill key) should be rejected, not abort the run."""
    run_dir, _ = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-kills")

    # Schema-valid (matches append-kills.schema.json) but kill_key references
    # nothing in the slice's kills array.
    (run_dir / target["result"]).write_text(json.dumps({
        "fields": {
            "nonexistent__1970-01-01__nothing__nothing": {
                "verse": "x",
                "annotation": "y"
            }
        },
        "reason": "test"
    }))

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert target["stem"] in {r["stem"] for r in summary["rejected"]}
    rejected_dir = run_dir / "results" / "rejected"
    assert (rejected_dir / f"{target['stem']}.json").exists()
    assert (rejected_dir / f"{target['stem']}.error.json").exists()


def test_failed_apply_leaves_no_partial_mutation(staged_run):
    """append-kills applies per-entry in a loop; a bad key mid-batch must not
    leave earlier entries appended when the slice is recorded rejected."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = next(s for s in manifest["slices"]
                 if s["transformer"] == "append-kills")
    slice_data = json.loads((run_dir / entry["pending"]).read_text())
    k = slice_data["kills"][0]
    good_key = f"{k['character']}__{k['date']}__{k['creature']}__{k['method']}"
    _write_result(run_dir, entry, {
        "fields": {
            good_key: {"verse": "A verse.", "annotation": "an annotation"},
            "nobody__2099-01-01__Nothing__nothing": {"verse": "x", "annotation": "y"},
        },
        "reason": "test",
    })

    # Also write a valid result for another slice so this run has at least
    # one successful apply — otherwise apply_run's `if applied: persist()`
    # gate never fires and kills.json would trivially stay untouched
    # regardless of whether the mid-loop mutation leaked, masking the bug.
    sessions_entry = next(s for s in manifest["slices"]
                          if s["transformer"] == "append-sessions")
    _write_result(run_dir, sessions_entry, {
        "fields": {
            "title": "Unrelated Session",
            "summary": "A session applied successfully in the same run.",
            "silent_roll": [],
        },
        "reason": "test",
    })

    before = json.loads((authored_dir / "kills.json").read_text())
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert any(r["stem"] == entry["stem"] for r in summary["rejected"])
    assert any(a["stem"] == sessions_entry["stem"] for a in summary["applied"])
    after = json.loads((authored_dir / "kills.json").read_text())
    assert after == before  # no partial append persisted


def test_apply_surfaces_road_ahead_graduations(staged_refresh_run):
    run_dir, authored_dir = staged_refresh_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = next(s for s in manifest["slices"]
                 if s["transformer"] == "refresh-road-ahead")
    _write_result(run_dir, entry, {
        "decision": "rewrite",
        "fields": {"known": [], "was_known":
                   [{"name": "Azlund's offer", "gloss": "answered"}],
                   "direction": "north"},
        "reason": "test",
    })
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert summary["graduated"] == ["Azlund's offer"]


def test_fully_successful_apply_prunes_run_dir(staged_run):
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert not summary["rejected"] and not summary["pending"]
    assert not run_dir.exists()


def test_keep_marker_preserves_run_dir(staged_run):
    run_dir, authored_dir = staged_run
    (run_dir / ".keep").write_text("")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    apply_cli.apply_run(run_dir, skip_render=True)
    assert run_dir.exists()


def test_missing_slice_file_is_rejected_not_crash(staged_run):
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = manifest["slices"][0]
    _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    (run_dir / entry["pending"]).unlink()          # simulate manual cleanup
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert any(r["stem"] == entry["stem"] and "slice file missing" in r["reason"]
               for r in summary["rejected"])


def _fill_all_results(run_dir: Path) -> None:
    """Write a schema-valid result for every slice so apply reaches the render."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))


def test_apply_run_prepares_the_map_before_rendering(staged_run, monkeypatch):
    run_dir, _ = staged_run
    _fill_all_results(run_dir)

    order = []
    monkeypatch.setattr(apply_cli.mapimage, "prepare_map",
                        lambda: (order.append("map"),
                                 {"status": "skipped", "src_bytes": 10, "out_bytes": 5})[1])
    monkeypatch.setattr(apply_cli, "_run_render",
                        lambda: (order.append("render"), {"ok": True, "stderr": ""})[1])

    summary = apply_cli.apply_run(run_dir, skip_render=False)

    assert order == ["map", "render"]
    assert summary["map"]["status"] == "skipped"


def test_apply_run_skips_the_map_when_the_render_is_skipped(staged_run, monkeypatch):
    run_dir, _ = staged_run
    _fill_all_results(run_dir)

    def _boom():
        raise AssertionError("the map must not be built when the render is skipped")

    monkeypatch.setattr(apply_cli.mapimage, "prepare_map", _boom)

    summary = apply_cli.apply_run(run_dir, skip_render=True)

    assert summary["map"] is None
