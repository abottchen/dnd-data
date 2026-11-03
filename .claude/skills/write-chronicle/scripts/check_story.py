#!/usr/bin/env python3
"""Mechanical checks on a chapter draft. Reports line: match for every hit; exit 1 if any.

Checks: em-dashes, digits other than the allowed years, player first names (from the
git hook's regex), game-mechanics vocabulary, modern idiom, table idiom inside quotes,
quote framing, decoded Dragonbait scents, party members reduced to "somebody", and
unbalanced quotation marks.

Usage: check_story.py STORY.md [--years 1385,1494]
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[4]
HOOK = REPO_ROOT / ".githooks" / "_forbidden-names.sh"

GAME_TERMS = r"\b(hit points?|armou?r class|saving throws?|concentration|necrotic|radiant damage|bonus action|initiative|d20|nat(ural)? 20|short rest|long rest|spell slots?|with advantage|disadvantage|attack rolls?|damage dice|a critical|crit)\b"
MODERN = r"\b(fast-forward|okay|OK|basically|literally|awesome)\b"
TABLE_IDIOM = r"\b(you folks|lean into|pretty good|kind of|sort of|I guess|I feel like|basically|actually|definitely|stuff|you know|like I said|gonna|wanna)\b"
FRAMING = r"\b(set (it |them |this )?down as (he|she|they) said|remembered (it|them) exactly|word for word|verbatim|exact words|I quote)\b"
SCENT = r"\b(honeysuckle|roses|wood smoke|baked bread|brimstone|ham|lemon)\b[^.]{0,60}\b(which is|anger|sadness|concern|devotion|worry|joy|tenderness|sorrow|frustration|has not (yet )?learned|what those mean)\b"
ANON = r"\b(somebody|someone|one of them|one of the company|a member of the company)\b[^.]{0,40}\b(asked|said|wondered|suggested|offered|pointed out|proposed)\b"


def first_names() -> str:
    if not HOOK.exists():
        return ""
    m = re.search(r"\\\\b\((.*?)\)\[\[:space:\]\]", HOOK.read_text())
    return m.group(1) if m else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", type=Path)
    ap.add_argument("--years", default="1385,1494", help="comma-separated digits allowed in the text")
    args = ap.parse_args()
    text = args.story.read_text(encoding="utf-8")
    lines = text.split("\n")
    allowed = set(args.years.split(","))
    hits: list[tuple[int, str, str]] = []

    def scan(label: str, pattern: str, flags: int = 0, quoted_only: bool = False) -> None:
        for n, line in enumerate(lines, 1):
            targets = re.findall(r'"[^"]*"', line) if quoted_only else [line]
            for t in targets:
                for m in re.finditer(pattern, t, flags):
                    a, b = max(0, m.start() - 30), min(len(t), m.end() + 30)
                    hits.append((n, label, t[a:b].strip()))

    scan("em-dash", "—")
    for n, line in enumerate(lines, 1):
        for d in re.findall(r"\d+", line):
            if d not in allowed:
                hits.append((n, "digits", d))
    names = first_names()
    if names:
        scan("real name", rf"\b({names})\b")
    scan("game term", GAME_TERMS, re.I)
    scan("modern idiom", MODERN)
    scan("table idiom in quote", TABLE_IDIOM, re.I, quoted_only=True)
    scan("quote framing", FRAMING, re.I)
    scan("decoded scent", SCENT, re.I)
    scan("anonymous party member", ANON, re.I)
    if text.count('"') % 2:
        hits.append((0, "quotes", "odd number of double quotes"))

    for n, label, snippet in hits:
        print(f"L{n}: [{label}] {snippet}")
    print(f"check_story: {len(hits)} finding(s), {len(text.split())} words")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
