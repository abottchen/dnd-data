#!/usr/bin/env python3
"""Write a chapter from build/.chronicle/session-N/story.md into build/authored/sessions.json.

Conversion rules, matching the published entries:
  * title      = the `# ` line
  * an italic header and `---` rule after the title, if present, are dropped
  * `## I. Title` becomes the plain line `I. Title`, its own paragraph
  * `*emphasis*` markers are stripped
  * paragraphs are joined with one blank line; `*V.G.*` becomes `V.G.`
  * silent_roll = []

Usage:
  story2entry.py STORY.md --session N --date YYYY-MM-DD [--dry-run] [--authored PATH]
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[4]
DEFAULT_AUTHORED = REPO_ROOT / "build" / "authored" / "sessions.json"


def convert(md: str) -> tuple[str, str]:
    lines = md.split("\n")
    i = 0
    while i < len(lines) and not lines[i].startswith("# "):
        i += 1
    if i == len(lines):
        sys.exit("story2entry: no '# Title' line")
    title = lines[i][2:].strip()
    # Older drafts carried an italic header and a `---` rule after the title; skip them if present.
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or lines[j].strip() == "---" or re.fullmatch(r"\*[^*]+\*", lines[j].strip())):
        j += 1
    j -= 1
    paras: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            paras.append(" ".join(cur))
            cur.clear()

    for line in lines[j + 1:]:
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("## "):
            flush()
            paras.append(s[3:].strip())
        else:
            cur.append(s)
    flush()
    text = "\n\n".join(paras)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    if "*" in text:
        sys.exit("story2entry: stray '*' left after stripping emphasis")
    return title, text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", type=Path)
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--date", required=True, help="real date, YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="print the entry; do not write")
    ap.add_argument("--authored", type=Path, default=DEFAULT_AUTHORED)
    args = ap.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        sys.exit("story2entry: --date must be YYYY-MM-DD")
    title, summary = convert(args.story.read_text(encoding="utf-8"))
    entry = {"session": args.session, "date": args.date, "title": title, "summary": summary, "silent_roll": []}

    if args.dry_run:
        json.dump(entry, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    sessions = json.loads(args.authored.read_text(encoding="utf-8"))
    replaced = False
    for k, e in enumerate(sessions):
        if e.get("session") == args.session:
            sessions[k] = entry
            replaced = True
    if not replaced:
        sessions.append(entry)
    args.authored.write_text(json.dumps(sessions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verb = "replaced" if replaced else "appended"
    print(f"story2entry: {verb} session {args.session} in {args.authored} "
          f"({len(summary)} chars, {summary.count(chr(10)+chr(10))+1} paragraphs)")
    print("next: .venv/bin/python build/render.py")


if __name__ == "__main__":
    main()
