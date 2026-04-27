"""Build orchestrator entry point.

Run with: `python -m build` (or `.venv/bin/python -m build`).

Workflow:
  1. Load upstream data + authored state.
  2. Append pass: invoke each append-* transformer for any unauthored entities.
  3. Refresh pass (only if latest_session > marker): invoke each refresh-*.
  4. Persist authored store. Bump marker on full refresh-pass success.
  5. Run render.py. (Targeted MISSING/MALFORMED retry — TODO.)
  6. Print end-of-run report.

The temp directory is removed on full success and preserved on partial
failure so the user can inspect slice / body / stderr artifacts. Pass
`--keep-temp` to preserve it on success too.
"""
import argparse
import concurrent.futures
import shutil
import sys
from pathlib import Path

from . import apply, render, slices, store
from .build_loop import run_render
from .invoke import TransformerError, call_transformer
from .paths import data_dir, temp_dir

DEFAULT_CONCURRENCY = 5


DISCOVERY_PASS = [
    ("refresh-known-npcs", slices.refresh_known_npcs, apply.apply_refresh_known_npcs),
]

APPEND_PASS = [
    ("append-kills", slices.append_kills, apply.apply_append_kills),
    ("append-sessions", slices.append_sessions, apply.apply_append_sessions),
    ("append-chapters", slices.append_chapters, apply.apply_append_chapters),
    ("append-npcs", slices.append_npcs, apply.apply_append_npcs),
    ("append-characters", slices.append_characters, apply.apply_append_characters),
]

REFRESH_PASS = [
    ("refresh-chapters", slices.refresh_chapters, apply.apply_refresh_chapters),
    ("refresh-npcs", slices.refresh_npcs, apply.apply_refresh_npcs),
    ("refresh-characters", slices.refresh_characters, apply.apply_refresh_characters),
    ("refresh-road-ahead", slices.refresh_road_ahead, apply.apply_refresh_road_ahead),
    ("refresh-intro-epithet", slices.refresh_intro_epithet, apply.apply_refresh_intro_epithet),
]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _run_pass(pass_name: str, transformers, data, authored, run_dir: Path, concurrency: int):
    """Run a pass with bounded parallelism.

    Slice gathering is sequential (cheap, no I/O). Transformer calls are
    dispatched to a thread pool (subprocess.run releases the GIL during the
    network/CLI wait). Applies happen on the main thread as futures complete,
    so authored-store mutations are serialized.

    Returns (per_category_results, full_success).
    """
    work_items: list[tuple] = []
    for name, build_slices, apply_fn in transformers:
        for key, slice_data in build_slices(data, authored):
            work_items.append((name, key, slice_data, apply_fn))

    if not work_items:
        return {}, True

    _log(f"  dispatching {len(work_items)} transformer call(s) (concurrency={concurrency})")

    results_by_id: dict = {}
    full_success = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_meta = {
            executor.submit(call_transformer, name, slice_data, run_dir):
                (name, key, slice_data, apply_fn)
            for (name, key, slice_data, apply_fn) in work_items
        }
        for future in concurrent.futures.as_completed(future_to_meta):
            name, key, slice_data, apply_fn = future_to_meta[future]
            try:
                output = future.result()
            except TransformerError as e:
                _log(f"  [{name}:{key}] FAILED: {e}")
                full_success = False
                continue
            _log(f"  [{name}:{key}] {output.get('decision', 'ok')}")

            if name == "refresh-road-ahead":
                grads = apply_fn(authored, key, slice_data, output)
                results_by_id[(name, key)] = (output.get("decision"), output.get("reason", ""), grads)
            else:
                apply_fn(authored, key, slice_data, output)
                results_by_id[(name, key)] = (output.get("decision"), output.get("reason", ""), None)

    # Reorganize by category, preserving submission order for stable reports.
    results: dict = {}
    for name, key, _slice, _apply in work_items:
        ident = (name, key)
        if ident in results_by_id:
            decision, reason, grads = results_by_id[ident]
            results.setdefault(name, []).append((key, decision, reason, grads))
    return results, full_success


def _print_report(*, discovery_results, append_results, refresh_results,
                  marker_old, marker_new,
                  render_result, run_dir: Path, full_success: bool, temp_kept: bool):
    _log("\n" + "=" * 60)
    _log("BUILD RUN REPORT")
    _log("=" * 60)

    if discovery_results:
        _log("\nDiscovery decisions:")
        for category, items in discovery_results.items():
            _log(f"  {category}:")
            for key, decision, reason, _grads in items:
                _log(f"    {key}: {decision} — {reason}")

    if append_results:
        _log("\nAppend additions:")
        for category, items in append_results.items():
            _log(f"  {category}:")
            for key, _decision, reason, _grads in items:
                _log(f"    {key}: {reason}")
    else:
        _log("\nAppend additions: (none)")

    if refresh_results:
        _log("\nRefresh decisions:")
        graduations: list[str] = []
        for category, items in refresh_results.items():
            _log(f"  {category}:")
            for key, decision, reason, grads in items:
                _log(f"    {key}: {decision} — {reason}")
                if grads and grads.get("graduated"):
                    graduations.extend(grads["graduated"])
        if graduations:
            _log(f"\nGraduations (known → was_known): {sorted(set(graduations))}")
    else:
        _log("\nRefresh decisions: (no refresh pass run or no items)")

    if marker_new == marker_old:
        _log(f"\nMarker: unchanged at {marker_old}")
    else:
        _log(f"\nMarker: {marker_old} → {marker_new}")

    _log(f"\nRender: {'OK' if render_result['ok'] else 'FAILED (returncode=' + str(render_result['returncode']) + ')'}")
    if not render_result["ok"]:
        _log("--- render stderr ---")
        _log(render_result["stderr"][:2000])

    if temp_kept:
        _log(f"\nTemp dir: {run_dir} (preserved; rm -rf when done)")
    else:
        _log(f"\nTemp dir: {run_dir} (removed)")
    _log(f"Overall: {'SUCCESS' if full_success and render_result['ok'] else 'PARTIAL/FAILED'}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build")
    parser.add_argument(
        "--skip-render", action="store_true",
        help="Skip running render.py at the end (useful for iteration).",
    )
    parser.add_argument(
        "--no-refresh", action="store_true",
        help="Skip the discovery and refresh passes even if the marker is behind.",
    )
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Run the discovery and refresh passes even if the marker is up to date.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Max parallel `claude -p` calls per pass (default: {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--keep-temp", action="store_true",
        help="Preserve the per-run temp dir even on full success "
             "(default: remove on success, preserve on partial failure).",
    )
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")

    data = render.load_data(str(data_dir()))
    authored = store.load_authored()
    latest = len(data["session_log"]["entries"])
    marker = authored["site"].get("refreshed_through_session", 0)

    run_dir = temp_dir()
    _log(f"build run temp dir: {run_dir}")
    _log(f"latest_session={latest}, marker={marker}")

    # --- Discovery pass ---
    # Runs before append so newly discovered NPC names flow into append-npcs
    # on the same build. Gated on latest > marker (no work to do otherwise),
    # bypassed by --force-refresh.
    discovery_results: dict = {}
    discovery_ok = True
    refresh_gate = not args.no_refresh and (latest > marker or args.force_refresh)
    if refresh_gate:
        _log("\n--- discovery pass ---")
        discovery_results, discovery_ok = _run_pass("discovery", DISCOVERY_PASS, data, authored, run_dir, args.concurrency)
        store.persist(authored)

    # --- Append pass ---
    _log("\n--- append pass ---")
    append_results, append_ok = _run_pass("append", APPEND_PASS, data, authored, run_dir, args.concurrency)
    store.persist(authored)

    # --- Refresh pass ---
    refresh_results: dict = {}
    refresh_ok = True
    marker_new = marker
    if refresh_gate:
        _log("\n--- refresh pass ---")
        refresh_results, refresh_ok = _run_pass("refresh", REFRESH_PASS, data, authored, run_dir, args.concurrency)
        store.persist(authored)
        if refresh_ok:
            store.bump_marker(authored, latest)
            marker_new = latest
    else:
        if args.no_refresh:
            _log("\nrefresh pass skipped (--no-refresh)")
        else:
            _log("\nrefresh pass skipped (marker up to date)")

    # --- Render ---
    if args.skip_render:
        _log("\nrender step skipped (--skip-render)")
        render_result = {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
    else:
        _log("\n--- running render.py ---")
        render_result = run_render()

    full_success = discovery_ok and append_ok and refresh_ok and render_result["ok"]

    # Clean up the temp dir on full success unless --keep-temp.
    # On partial failure we always preserve it so the user can inspect
    # the slice / body / stderr artifacts.
    temp_kept = args.keep_temp or not full_success
    if not temp_kept:
        shutil.rmtree(run_dir, ignore_errors=True)

    _print_report(
        discovery_results=discovery_results,
        append_results=append_results,
        refresh_results=refresh_results,
        marker_old=marker,
        marker_new=marker_new,
        render_result=render_result,
        run_dir=run_dir,
        full_success=full_success,
        temp_kept=temp_kept,
    )

    return 0 if full_success else 1


if __name__ == "__main__":
    sys.exit(main())
