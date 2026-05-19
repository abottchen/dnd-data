"""Tests for build/apply_cli.py — manifest-driven result application."""
import json
import shutil
from pathlib import Path

import pytest

from build import apply_cli, prepare, store
from build.paths import REPO_ROOT

FIXTURES = REPO_ROOT / "tests/fixtures"


@pytest.fixture
def staged_run(tmp_path, monkeypatch):
    """Run prepare against the fixtures to produce a real run dir."""
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

    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    return run_dir, authored_dir


def _write_result(run_dir: Path, entry: dict, payload: dict) -> None:
    """Helper: write the JSON result for one manifest entry."""
    (run_dir / entry["result"]).write_text(json.dumps(payload, indent=2))


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
