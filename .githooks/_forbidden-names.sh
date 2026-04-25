#!/usr/bin/env bash
# Helper: print the regex that pre-commit, commit-msg, and pre-push hooks
# use to detect player real names in commits.
#
# The signal we want to block is "<player first name> <Capitalized word>" —
# i.e. a full real name. The first names of the players currently at the
# table are baked in below; bare first names are allowed (they already
# appear unavoidably in CLAUDE.md, test fixtures, etc.). When a new player
# joins the table, add their first name to the alternation.

# Word-boundary on each side, alternation of first names, one-or-more
# whitespace, then a Capitalized token (the suspected last name).
echo "\\b(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z][a-zA-Z'-]+\\b"
