"""Build orchestrator entry point.

Three CLI forms:
  python -m build prepare [--no-refresh] [--force-refresh] [--keep-temp]
      Gather pending slices, write a per-run directory under build/.run/,
      print the path. Authoring happens out-of-band via the /build-prose
      skill in a Claude Code session.

  python -m build apply <run-dir> [--skip-render]
      Validate every result file in <run-dir>, apply it to the authored
      store, bump the marker on full refresh-pass success, run render.py.

  python -m build       (convenience)
      Same as `prepare`, then prints the skill command to run next.
"""
import argparse
import sys
from pathlib import Path

from . import apply_cli, prepare


def _cmd_prepare(args) -> int:
    run_dir = prepare.run(
        no_refresh=args.no_refresh,
        force_refresh=args.force_refresh,
        keep_temp=args.keep_temp,
    )
    print(str(run_dir))
    print(
        f"\nNext: in Claude Code, run `/build-prose {run_dir}`, then\n"
        f"  python -m build apply {run_dir}",
        file=sys.stderr,
    )
    return 0


def _cmd_apply(args) -> int:
    run_dir = Path(args.run_dir)
    if not (run_dir / "manifest.json").exists():
        print(f"no manifest.json in {run_dir}", file=sys.stderr)
        return 2
    summary = apply_cli.apply_run(run_dir, skip_render=args.skip_render)

    print(f"applied: {len(summary['applied'])}", file=sys.stderr)
    print(f"rejected: {len(summary['rejected'])}", file=sys.stderr)
    print(f"pending: {len(summary['pending'])}", file=sys.stderr)
    if summary["marker_new"] != summary["marker_old"]:
        print(f"marker: {summary['marker_old']} → {summary['marker_new']}", file=sys.stderr)
    if summary["render_ok"] is True:
        print("render: OK", file=sys.stderr)
    elif summary["render_ok"] is False:
        print("render: FAILED", file=sys.stderr)
    else:
        print("render: skipped", file=sys.stderr)

    if summary["rejected"] or summary["pending"]:
        return 1
    if summary["render_ok"] is False:
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build")
    sub = parser.add_subparsers(dest="cmd")

    p_prep = sub.add_parser("prepare", help="Stage pending slices.")
    p_prep.add_argument("--no-refresh", action="store_true")
    p_prep.add_argument("--force-refresh", action="store_true")
    p_prep.add_argument("--keep-temp", action="store_true")

    p_apply = sub.add_parser("apply", help="Apply results and render.")
    p_apply.add_argument("run_dir")
    p_apply.add_argument("--skip-render", action="store_true")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if args.cmd is None:
        # Bare `python -m build` → prepare with defaults.
        ns = argparse.Namespace(no_refresh=False, force_refresh=False, keep_temp=False)
        return _cmd_prepare(ns)
    if args.cmd == "prepare":
        return _cmd_prepare(args)
    if args.cmd == "apply":
        return _cmd_apply(args)
    parser.error(f"unknown subcommand: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
