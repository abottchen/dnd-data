"""Build orchestrator — apply half.

Reads results staged by the `/build-prose` skill, validates each against the
matching schema, applies via build.apply.apply_*, persists the authored
store, bumps the marker on full refresh-pass success, and runs
build/render.py.

Idempotency: a result that has already been applied moves out of `results/`
into `results/applied/`. Re-running apply on the same run dir reapplies
nothing that was applied before.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema

from . import inventory, registry, render, store
from .paths import REPO_ROOT, data_dir


def _load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text())


def _load_schema(run_dir: Path, entry: dict) -> dict:
    return json.loads((run_dir / entry["schema"]).read_text())


def _load_slice(run_dir: Path, entry: dict) -> dict:
    """Read a slice's input JSON. The /build-prose skill moves authored slices
    from pending/ to done/ for its own re-run idempotency, so look in both."""
    pending_path = run_dir / entry["pending"]
    if pending_path.exists():
        return json.loads(pending_path.read_text())
    done_path = run_dir / "done" / f"{entry['stem']}.json"
    return json.loads(done_path.read_text())


def _move(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def _run_render() -> dict:
    """Invoke build/render.py as a subprocess; return its status dict."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "build" / "render.py")],
        capture_output=True, text=True,
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def _record_rejection(
    rejected: list,
    rejected_dir: Path,
    entry: dict,
    result_path: Path,
    reason: str,
) -> None:
    """Append to rejected list, move the result file, and write error sidecar."""
    err = {"transformer": entry["transformer"], "key": entry["key"],
           "stem": entry["stem"], "reason": reason[:500]}
    rejected.append(err)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    _move(result_path, rejected_dir / f"{entry['stem']}.json")
    (rejected_dir / f"{entry['stem']}.error.json").write_text(
        json.dumps(err, indent=2)
    )


def apply_run(run_dir: Path, *, skip_render: bool) -> dict:
    """Apply every present result in run_dir; return a summary dict.

    Summary keys:
      - applied: list of {transformer, key, stem}
      - rejected: list of {transformer, key, stem, reason}
      - pending: list of {transformer, key, stem} (no result file yet)
      - marker_old, marker_new
      - render_ok: bool | None (None when skip_render)
    """
    manifest = _load_manifest(run_dir)
    # Always load fresh state from disk; authored may have been edited between
    # prepare and apply (deliberate user intervention).
    data = render.load_data(str(data_dir()))
    authored = store.load_authored()
    inv_bundle = inventory.load(REPO_ROOT, party=data["party"])
    authored["inventory_by_id"] = inv_bundle["by_id"]
    authored["pronouns_by_id"] = render.load_character_pronouns()

    applied: list = []
    rejected: list = []
    pending: list = []
    refresh_total = sum(1 for s in manifest["slices"] if s["pass"] == "refresh")
    refresh_applied = 0

    rejected_dir = run_dir / "results" / "rejected"
    applied_dir = run_dir / "results" / "applied"

    for entry in manifest["slices"]:
        result_path = run_dir / entry["result"]

        # Idempotency: if we previously moved a result to applied/, count it
        # toward refresh totals but do not re-apply.
        previously_applied = (applied_dir / f"{entry['stem']}.json").exists()
        if previously_applied:
            if entry["pass"] == "refresh":
                refresh_applied += 1
            continue

        if not result_path.exists():
            pending.append({"transformer": entry["transformer"],
                            "key": entry["key"], "stem": entry["stem"]})
            continue

        # Validate against the snapshotted schema.
        try:
            output = json.loads(result_path.read_text())
            jsonschema.validate(output, _load_schema(run_dir, entry))
        except (json.JSONDecodeError, jsonschema.ValidationError,
                jsonschema.SchemaError) as e:
            _record_rejection(rejected, rejected_dir, entry, result_path, str(e))
            continue

        # Apply.
        slice_data = _load_slice(run_dir, entry)
        fn = registry.by_name(entry["transformer"]).apply_fn
        try:
            fn(authored, entry["key"], slice_data, output)
        except (ValueError, KeyError) as e:
            _record_rejection(rejected, rejected_dir, entry, result_path,
                              f"apply failed: {e}")
            continue

        applied.append({"transformer": entry["transformer"],
                        "key": entry["key"], "stem": entry["stem"]})
        if entry["pass"] == "refresh":
            refresh_applied += 1

        # Move the result into applied/ so a second apply_run is a no-op.
        _move(result_path, applied_dir / f"{entry['stem']}.json")

    # Persist authored after the pass.
    if applied:
        store.persist(authored)

    marker_old = manifest["marker"]
    marker_new = marker_old
    # Bump marker only if every refresh slice in the manifest has now been
    # applied (no rejections, no still-pending).
    if refresh_total > 0 and refresh_applied == refresh_total and not rejected:
        store.bump_marker(authored, manifest["latest"])
        marker_new = manifest["latest"]

    render_ok: bool | None = None
    if not skip_render and not pending and not rejected:
        rr = _run_render()
        render_ok = rr["ok"]
        if not render_ok:
            # Surface to the caller; do not clean up.
            print(rr["stderr"][:2000], file=sys.stderr)

    return {
        "applied": applied,
        "rejected": rejected,
        "pending": pending,
        "marker_old": marker_old,
        "marker_new": marker_new,
        "render_ok": render_ok,
    }
