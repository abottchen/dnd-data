"""Build orchestrator — prepare half.

Loads upstream data + authored state, computes the set of slices that need
authoring across discovery/append/refresh passes, and writes them to a per-run
directory along with a manifest and frozen copies of the prompt body + schema
for each transformer. The skill `/build-prose` consumes that directory.
"""
import json
import re
import shutil
from pathlib import Path


class FrontmatterError(ValueError):
    """Raised when a prompt's YAML-like frontmatter is malformed."""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse single-level `key: value` frontmatter from a prompt file.

    - No leading `---\\n` → returns ({}, text) unchanged.
    - Leading `---` with no matching closing `---` → FrontmatterError.
    - Non-empty, non-comment line without ':' inside the block → FrontmatterError.
    CRLF line endings are tolerated (normalized to LF before parsing).
    """
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, text
    rest = normalized[len("---\n"):]
    if rest.startswith("---\n"):
        fm_text, body = "", rest[len("---\n"):]
    elif (end_idx := rest.find("\n---\n")) != -1:
        fm_text, body = rest[:end_idx], rest[end_idx + len("\n---\n"):]
    elif rest.endswith("\n---"):
        fm_text, body = rest[:-len("\n---")], ""
    else:
        raise FrontmatterError(
            "frontmatter started with '---' but no closing '---' found"
        )

    fm: dict = {}
    for raw_line in fm_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise FrontmatterError(f"malformed frontmatter line (no ':'): {raw_line!r}")
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body
