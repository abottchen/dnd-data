#!/usr/bin/env bash
# Helper: print a regex alternation of forbidden names from the gitignored
# dice-players.json. Empty output means "no enforcement" (file or list missing).
# Sourced by pre-commit, commit-msg, and pre-push hooks.

source_file=".claude/skills/hydrate-ledger/dice-players.json"
[ -f "$source_file" ] || { echo ""; exit 0; }

python3 - "$source_file" <<'PY'
import json, re, sys
try:
    data = json.load(open(sys.argv[1]))
    names = data.get("forbidden_in_commits", []) or []
    print("|".join(re.escape(n) for n in names if isinstance(n, str) and n))
except Exception:
    print("")
PY
