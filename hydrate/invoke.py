"""claude -p invocation for hydrate.

For each transformer, reads .claude/prompts/<name>.md (frontmatter + body)
and .claude/prompts/<name>.schema.json. Pipes the slice JSON to claude via
stdin. Returns the structured_output dict (schema-validated by the harness).
"""
import json
import re
import subprocess
from pathlib import Path

from .paths import PROMPTS_DIR

DISALLOWED_TOOLS = (
    "Bash Read Write Edit Glob Grep LS WebFetch WebSearch "
    "Task TodoWrite NotebookEdit NotebookRead ExitPlanMode"
)
PERMISSION_MODE = "plan"
MAX_BUDGET_USD = "1.00"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class TransformerError(RuntimeError):
    """Raised when claude -p returns an error or an invalid response."""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse single-level YAML-like frontmatter (`key: value` per line) from a
    prompt file. Returns (frontmatter_dict, body_text)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, m.group(2)


def call_transformer(name: str, slice_data: dict, run_dir: Path) -> dict:
    """Invoke the named transformer. Returns the structured_output dict.

    `name` is the prompt file stem (e.g. "append-kills"). `run_dir` is the
    per-run temp directory used for debug artifacts (slice + body file).
    Slice and body are persisted there so failures can be inspected by the
    user.
    """
    prompt_path = PROMPTS_DIR / f"{name}.md"
    schema_path = PROMPTS_DIR / f"{name}.schema.json"
    if not prompt_path.exists():
        raise TransformerError(f"prompt file missing: {prompt_path}")
    if not schema_path.exists():
        raise TransformerError(f"schema file missing: {schema_path}")

    fm, body = _parse_frontmatter(prompt_path.read_text())
    model = fm.get("model", "sonnet")

    body_path = run_dir / f"{name}.body.md"
    body_path.write_text(body)
    slice_path = run_dir / f"{name}.slice.json"
    slice_str = json.dumps(slice_data, indent=2)
    slice_path.write_text(slice_str)

    schema_str = json.dumps(json.loads(schema_path.read_text()), separators=(",", ":"))

    cmd = [
        "claude", "-p",
        "--model", model,
        "--system-prompt-file", str(body_path),
        "--json-schema", schema_str,
        "--output-format", "json",
        "--max-budget-usd", MAX_BUDGET_USD,
        "--disallowedTools", DISALLOWED_TOOLS,
        "--permission-mode", PERMISSION_MODE,
    ]
    result = subprocess.run(cmd, input=slice_str, capture_output=True, text=True)
    if result.returncode != 0:
        raise TransformerError(
            f"claude -p exited {result.returncode} for {name}\n"
            f"stderr: {result.stderr[:1500]}\n"
            f"slice preserved at: {slice_path}"
        )

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise TransformerError(
            f"non-JSON stdout from claude -p ({name}): {e}\n"
            f"raw: {result.stdout[:500]}"
        ) from e

    if parsed.get("is_error"):
        raise TransformerError(
            f"claude -p reported error for {name}: {parsed.get('result', '')[:500]}"
        )

    so = parsed.get("structured_output")
    if so is None:
        raise TransformerError(
            f"null structured_output for {name} — schema validation likely failed.\n"
            f"raw result: {parsed.get('result', '')[:500]}\n"
            f"slice preserved at: {slice_path}"
        )
    return so
