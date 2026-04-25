#!/usr/bin/env bash
# Runs each helper subcommand against the current real upstream data
# and prints the metadata array + slice-file sizes for each entry.
# Use this when modifying helpers to sanity-check that slices look right.
set -euo pipefail

HELPERS=".claude/skills/hydrate-ledger/helpers.py"
PYTHON="${PYTHON:-.venv/bin/python}"

for sub in append-kills append-sessions append-chapters append-npcs append-characters \
           refresh-chapters refresh-npcs refresh-characters refresh-road-ahead refresh-intro-epithet; do
    echo "=== $sub ==="
    out=$("$PYTHON" "$HELPERS" "$sub")
    echo "$out" | python3 -m json.tool
    # Print slice file sizes (pipe JSON via stdin to avoid quoting issues)
    echo "$out" | python3 -c "
import json, os, sys
data = json.load(sys.stdin)
for s in data['slices']:
    if os.path.exists(s['path']):
        print(f\"  {s['key']}: {os.path.getsize(s['path'])} bytes\")
    else:
        print(f\"  {s['key']}: <path missing>\")
"
    echo
done
