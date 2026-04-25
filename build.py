#!/usr/bin/env python3
"""build.py — render index.html from data + authored store + templates.

Exit codes:
  0  render succeeded
  1  validation errors; nothing written
  2  internal error (template syntax, file read failure, bestiary miss)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

def main() -> int:
    parser = argparse.ArgumentParser(description="Render index.html.")
    parser.add_argument("--data-dir", default=str(REPO_ROOT),
                        help="Directory containing party.json etc.")
    parser.add_argument("--out", default=str(REPO_ROOT / "index.html"),
                        help="Output HTML path.")
    parser.add_argument("--strict", action="store_true",
                        help="Abort on any validation error (default: True).")
    args = parser.parse_args()

    print(f"build.py: starting (data_dir={args.data_dir})")
    # placeholder pipeline; later tasks fill this in
    print("build.py: ok (skeleton)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
