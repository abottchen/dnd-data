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

from . import inventory, registry, render, store
from .paths import (PROMPTS_DIR, REPO_ROOT, authored_dir, data_dir,
                    new_run_id, run_dir)

_STEM_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _stem(transformer: str, key) -> str:
    return _STEM_SAFE.sub("-", f"{transformer}__{key}")


def _prompt_meta(name: str, frozen_prompts_dir: Path) -> dict:
    """Copy prompt + schema into the run dir and return manifest fields."""
    prompt_src = PROMPTS_DIR / f"{name}.md"
    schema_src = PROMPTS_DIR / f"{name}.schema.json"
    if not prompt_src.exists():
        raise FileNotFoundError(f"prompt missing: {prompt_src}")
    if not schema_src.exists():
        raise FileNotFoundError(f"schema missing: {schema_src}")

    fm, body = parse_frontmatter(prompt_src.read_text())
    body_path = frozen_prompts_dir / f"{name}.md"
    body_path.write_text(body)
    schema_path = frozen_prompts_dir / f"{name}.schema.json"
    shutil.copy(schema_src, schema_path)
    return {
        "model": fm.get("model", "sonnet"),
        "prompt_body_rel": f"prompts/{name}.md",
        "schema_rel": f"prompts/{name}.schema.json",
    }


def run(*, no_refresh: bool, force_refresh: bool, keep_temp: bool) -> Path:
    """Gather all pending slices, write them to a new run directory.

    Returns the run-dir path. Skill `/build-prose` consumes it.
    """
    data = render.load_data(str(data_dir()))
    authored = store.load_authored()
    latest = len(data["session_log"]["entries"])
    marker = authored["site"].get("refreshed_through_session", 0)

    # Inventory + pronoun side channels (mirror current __main__.py wiring).
    inv_bundle = inventory.load(REPO_ROOT, party=data["party"])
    authored["inventory_by_id"] = inv_bundle["by_id"]
    authored["pronouns_by_id"] = render.load_character_pronouns()
    # Side channel for marker-aware refresh builders (e.g. refresh_npcs): under
    # --force-refresh they must re-evaluate the whole roster, not just entities
    # touched by sessions past the marker.
    authored["force_refresh"] = force_refresh

    refresh_gate = not no_refresh and (latest > marker or force_refresh)

    run_id = new_run_id()
    rdir = run_dir(run_id)
    (rdir / "pending").mkdir(exist_ok=True)
    (rdir / "results").mkdir(exist_ok=True)
    (rdir / "done").mkdir(exist_ok=True)
    frozen_prompts = rdir / "prompts"
    frozen_prompts.mkdir(exist_ok=True)

    if keep_temp:
        (rdir / ".keep").write_text("")

    # Map prompt name → cached meta so we copy each prompt once even when
    # a transformer emits many slices.
    prompt_cache: dict = {}

    slices_out: list = []
    for entry in registry.ALL:
        if entry.pass_name in ("discovery", "refresh") and not refresh_gate:
            continue
        for key, slice_data in entry.slice_builder(data, authored):
            if entry.name not in prompt_cache:
                prompt_cache[entry.name] = _prompt_meta(entry.name, frozen_prompts)
            meta = prompt_cache[entry.name]
            stem = _stem(entry.name, key)
            pending_rel = f"pending/{stem}.json"
            result_rel = f"results/{stem}.json"
            (rdir / pending_rel).write_text(
                json.dumps(slice_data, indent=2, ensure_ascii=False) + "\n"
            )
            slices_out.append({
                "transformer": entry.name,
                "pass": entry.pass_name,
                "key": key,
                "stem": stem,
                "model": meta["model"],
                "pending": pending_rel,
                "result": result_rel,
                "prompt_body": meta["prompt_body_rel"],
                "schema": meta["schema_rel"],
            })

    manifest = {
        "run_id": run_id,
        "marker": marker,
        "latest": latest,
        "force_refresh": force_refresh,
        "keep_temp": keep_temp,
        "no_refresh": no_refresh,
        "slices": slices_out,
    }
    (rdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    return rdir


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
