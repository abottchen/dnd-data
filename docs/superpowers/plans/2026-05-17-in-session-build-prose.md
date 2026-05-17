# In-session build prose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `claude -p` subprocess authoring with a three-step flow — `python -m build prepare` writes a run directory of pending slices, a `/build-prose` skill walks that directory and writes results, `python -m build apply` validates results and renders the site.

**Architecture:** The current `build/__main__.py` is split front/back. The front half becomes `build/prepare.py` — it gathers slices via the existing `build/slices.py` builders and writes them to `build/.run/<timestamp>/` along with a manifest and frozen prompt/schema copies. The back half becomes `build/apply_cli.py` — it reads results, validates with `jsonschema`, applies via the existing `build/apply.py` functions, bumps the marker, and runs `render.py`. A new `.claude/skills/build-prose/SKILL.md` is the loop driver. `build/invoke.py` and `build/build_loop.py` are removed.

**Tech Stack:** Python 3, `jsonschema` (already in requirements.txt), pytest, existing `build/` package structure, Claude Code skill format.

**Reference spec:** `docs/superpowers/specs/2026-05-17-in-session-build-prose-design.md`

---

## File Structure

**New files:**
- `build/registry.py` — single source of truth mapping transformer name → (slice_builder, apply_fn, pass_name). Used by both prepare and apply so the two stay in sync.
- `build/prepare.py` — slice gathering and run-dir population. Pure function `prepare(args) -> Path` plus a thin CLI shim.
- `build/apply_cli.py` — manifest-driven apply + render. Pure function `apply_run(run_dir, *, skip_render) -> int` plus a CLI shim.
- `.claude/skills/build-prose/SKILL.md` — the procedural skill that drives authoring inside a Claude Code session.
- `tests/test_prepare.py` — unit tests for prepare.
- `tests/test_apply_cli.py` — unit tests for apply_cli.

**Modified files:**
- `build/__main__.py` — replaced with subcommand dispatch (`prepare`, `apply`, no-arg convenience).
- `build/paths.py` — `temp_dir()` is replaced by `run_dir(run_id)` rooted at `build/.run/`; legacy env var renamed.
- `.gitignore` — add `build/.run/`.

**Removed files (final task):**
- `build/invoke.py`
- `build/build_loop.py`
- `tests/test_invoke.py` (the frontmatter-parsing tests move to `tests/test_prepare.py` because `prepare` re-uses that parser).

---

## Manifest schema (referenced by multiple tasks)

`build/.run/<run_id>/manifest.json`:

```json
{
  "run_id": "2026-05-17T14-32-08",
  "marker": 8,
  "latest": 9,
  "force_refresh": false,
  "keep_temp": false,
  "slices": [
    {
      "transformer": "append-kills",
      "pass": "append",
      "key": "2026-04-30",
      "stem": "append-kills__2026-04-30",
      "model": "sonnet",
      "pending": "pending/append-kills__2026-04-30.json",
      "result": "results/append-kills__2026-04-30.json",
      "prompt_body": "prompts/append-kills.md",
      "schema": "prompts/append-kills.schema.json"
    }
  ]
}
```

`key` keeps its JSON-native type (int for session ids, str everywhere else). `stem` is the on-disk filename root after sanitizing: `re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{transformer}__{key}")`.

---

## Task 1: Transformer registry

**Files:**
- Create: `build/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
"""Tests for the transformer registry — the single source of truth that
wires transformer names to slice builders and apply functions."""
from build import registry, slices, apply


def test_registry_lists_every_transformer():
    names = {entry.name for entry in registry.ALL}
    assert names == {
        "refresh-known-npcs",
        "append-kills", "append-sessions", "append-chapters",
        "append-npcs", "append-characters",
        "refresh-chapters", "refresh-npcs", "refresh-characters",
        "refresh-road-ahead", "refresh-intro-epithet",
        "refresh-archetype-inscription",
    }


def test_registry_pass_assignment():
    by_name = {e.name: e for e in registry.ALL}
    assert by_name["refresh-known-npcs"].pass_name == "discovery"
    assert by_name["append-kills"].pass_name == "append"
    assert by_name["refresh-chapters"].pass_name == "refresh"


def test_registry_slice_and_apply_callables_wire_through():
    by_name = {e.name: e for e in registry.ALL}
    assert by_name["append-kills"].slice_builder is slices.append_kills
    assert by_name["append-kills"].apply_fn is apply.apply_append_kills
    assert by_name["refresh-known-npcs"].slice_builder is slices.refresh_known_npcs
    assert by_name["refresh-known-npcs"].apply_fn is apply.apply_refresh_known_npcs


def test_lookup_by_name():
    entry = registry.by_name("append-kills")
    assert entry.name == "append-kills"
    assert entry.pass_name == "append"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'build.registry'`.

- [ ] **Step 3: Write the registry**

Create `build/registry.py`:

```python
"""Single source of truth for transformer wiring.

Each transformer is described once: the prompt name (matches
.claude/prompts/<name>.md), the pass it belongs to, the slice builder that
emits its slices, and the apply function that absorbs its results.

`prepare.py` iterates ALL to gather slices. `apply_cli.py` looks entries up
by name to dispatch the right apply function. Keeping the wiring here means
the two scripts cannot drift out of sync.
"""
from dataclasses import dataclass
from typing import Callable

from . import apply, slices


@dataclass(frozen=True)
class Transformer:
    name: str
    pass_name: str  # "discovery" | "append" | "refresh"
    slice_builder: Callable
    apply_fn: Callable


ALL: tuple[Transformer, ...] = (
    Transformer("refresh-known-npcs", "discovery",
                slices.refresh_known_npcs, apply.apply_refresh_known_npcs),

    Transformer("append-kills", "append",
                slices.append_kills, apply.apply_append_kills),
    Transformer("append-sessions", "append",
                slices.append_sessions, apply.apply_append_sessions),
    Transformer("append-chapters", "append",
                slices.append_chapters, apply.apply_append_chapters),
    Transformer("append-npcs", "append",
                slices.append_npcs, apply.apply_append_npcs),
    Transformer("append-characters", "append",
                slices.append_characters, apply.apply_append_characters),

    Transformer("refresh-chapters", "refresh",
                slices.refresh_chapters, apply.apply_refresh_chapters),
    Transformer("refresh-npcs", "refresh",
                slices.refresh_npcs, apply.apply_refresh_npcs),
    Transformer("refresh-characters", "refresh",
                slices.refresh_characters, apply.apply_refresh_characters),
    Transformer("refresh-road-ahead", "refresh",
                slices.refresh_road_ahead, apply.apply_refresh_road_ahead),
    Transformer("refresh-intro-epithet", "refresh",
                slices.refresh_intro_epithet, apply.apply_refresh_intro_epithet),
    Transformer("refresh-archetype-inscription", "refresh",
                slices.refresh_archetype_inscription,
                apply.apply_refresh_archetype_inscription),
)

_BY_NAME = {t.name: t for t in ALL}


def by_name(name: str) -> Transformer:
    """Look up a transformer by name. Raises KeyError if missing."""
    return _BY_NAME[name]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add build/registry.py tests/test_registry.py
git commit -m "Add transformer registry as single source of truth"
```

---

## Task 2: Run directory paths

**Files:**
- Modify: `build/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_paths.py`:

```python
"""Tests for build/paths.py run-dir resolution."""
import os
from pathlib import Path

from build import paths


def test_run_dir_default_path(monkeypatch, tmp_path):
    """Without override, run_dir(run_id) anchors at REPO_ROOT/build/.run/."""
    monkeypatch.delenv("BUILD_RUN_ROOT", raising=False)
    p = paths.run_dir("2026-05-17T14-32-08")
    assert p == paths.REPO_ROOT / "build" / ".run" / "2026-05-17T14-32-08"
    assert p.exists()
    assert p.is_dir()


def test_run_dir_env_override(monkeypatch, tmp_path):
    """BUILD_RUN_ROOT relocates the root of all run dirs (for tests)."""
    monkeypatch.setenv("BUILD_RUN_ROOT", str(tmp_path))
    p = paths.run_dir("custom-id")
    assert p == tmp_path / "custom-id"
    assert p.exists()


def test_new_run_id_is_iso_timestamp(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILD_RUN_ROOT", str(tmp_path))
    run_id = paths.new_run_id()
    # ISO-ish: 4-digit year then dashes, T, dashes (no colons for fs safety).
    assert len(run_id) == 19
    assert run_id[4] == "-"
    assert run_id[10] == "T"


def test_run_root_returns_repo_default(monkeypatch):
    monkeypatch.delenv("BUILD_RUN_ROOT", raising=False)
    assert paths.run_root() == paths.REPO_ROOT / "build" / ".run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_paths.py -v`
Expected: FAIL (no `run_dir` / `new_run_id` / `run_root` attribute on `paths`).

- [ ] **Step 3: Update build/paths.py**

Replace the file contents:

```python
"""Path resolution for the build package.

Every path resolves from REPO_ROOT (the repo this package lives in). Test
isolation overrides via env vars: BUILD_DATA_DIR, BUILD_AUTHORED_DIR,
BUILD_RUN_ROOT.
"""
import datetime as _dt
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / ".claude" / "prompts"


def data_dir() -> Path:
    return Path(os.environ.get("BUILD_DATA_DIR", REPO_ROOT / "data"))


def authored_dir() -> Path:
    return Path(os.environ.get("BUILD_AUTHORED_DIR", REPO_ROOT / "build" / "authored"))


def run_root() -> Path:
    """Parent of all run dirs. Override via BUILD_RUN_ROOT."""
    override = os.environ.get("BUILD_RUN_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT / "build" / ".run"


def run_dir(run_id: str) -> Path:
    """Return (and create) the directory for one build run."""
    p = run_root() / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_run_id() -> str:
    """Filesystem-safe ISO-ish timestamp: 2026-05-17T14-32-08 (no colons)."""
    now = _dt.datetime.now().replace(microsecond=0)
    return now.isoformat().replace(":", "-")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_paths.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Update .gitignore**

Append to `.gitignore` (under the Python build artifacts block):

```
# Build run staging dirs
build/.run/
```

- [ ] **Step 6: Commit**

```bash
git add build/paths.py tests/test_paths.py .gitignore
git commit -m "Replace temp_dir with run_dir/run_root rooted at build/.run/"
```

---

## Task 3: Frontmatter parser moves into prepare

**Files:**
- Create: `build/prepare.py` (stub for this task — only the helper)
- Create: `tests/test_prepare.py`

This task only lands the frontmatter parser inside `prepare.py` so we can delete `build/invoke.py` later without losing the function. We keep `build/invoke.py` in place for now (the legacy build still uses it).

- [ ] **Step 1: Write the failing test**

Create `tests/test_prepare.py`:

```python
"""Tests for build/prepare.py — slice gathering and run-dir population."""
import json
from pathlib import Path

import pytest

from build import prepare


# -- Frontmatter parser (moved from build/invoke.py) ------------------------

def test_parse_frontmatter_no_marker_returns_text_unchanged():
    fm, body = prepare.parse_frontmatter("no marker here\nbody body")
    assert fm == {}
    assert body == "no marker here\nbody body"


def test_parse_frontmatter_key_value_pairs():
    fm, body = prepare.parse_frontmatter("---\nmodel: opus\n---\nbody\n")
    assert fm == {"model": "opus"}
    assert body == "body\n"


def test_parse_frontmatter_empty_block():
    fm, body = prepare.parse_frontmatter("---\n---\nbody\n")
    assert fm == {}
    assert body == "body\n"


def test_parse_frontmatter_crlf_tolerated():
    fm, body = prepare.parse_frontmatter("---\r\nmodel: sonnet\r\n---\r\nbody\r\n")
    assert fm == {"model": "sonnet"}


def test_parse_frontmatter_unclosed_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nmodel: opus\nbody but no close")


def test_parse_frontmatter_malformed_line_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nthis has no colon\n---\nbody")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_prepare.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build.prepare'`.

- [ ] **Step 3: Create build/prepare.py with the frontmatter parser**

Create `build/prepare.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_prepare.py -v`
Expected: PASS (6 frontmatter tests).

- [ ] **Step 5: Commit**

```bash
git add build/prepare.py tests/test_prepare.py
git commit -m "Land prepare module with relocated frontmatter parser"
```

---

## Task 4: prepare gathers slices and writes the run dir

**Files:**
- Modify: `build/prepare.py`
- Modify: `tests/test_prepare.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_prepare.py`:

```python
# -- Slice gathering + run-dir population -----------------------------------

import shutil
import pytest

from build import prepare, render, store, inventory
from build.paths import REPO_ROOT

FIXTURES = REPO_ROOT / "tests/fixtures"


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    """Stage a fixture data dir, authored dir, and isolated run root."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    (data_dir / "dice").mkdir()
    shutil.copy(FIXTURES / "sample_dicex_rolls.json",
                data_dir / "dice" / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    run_root = tmp_path / "runs"
    run_root.mkdir()

    monkeypatch.setenv("BUILD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(authored_dir))
    monkeypatch.setenv("BUILD_RUN_ROOT", str(run_root))
    return tmp_path


def test_prepare_creates_manifest_and_pending_files(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())

    # Manifest has expected top-level shape.
    assert "run_id" in manifest
    assert "marker" in manifest
    assert "latest" in manifest
    assert isinstance(manifest["slices"], list)
    assert len(manifest["slices"]) > 0

    # Every slice has a pending file on disk.
    for entry in manifest["slices"]:
        assert (run_dir / entry["pending"]).exists()
        assert (run_dir / entry["prompt_body"]).exists()
        assert (run_dir / entry["schema"]).exists()


def test_prepare_skips_refresh_pass_when_marker_current(run_env, monkeypatch):
    # Bump marker to latest so no refresh slices are produced.
    data = render.load_data(REPO_ROOT / "tests/fixtures")  # type: ignore[arg-type]
    # Easier: load via env-resolved authored dir and bump in place.
    from build.store import load_authored, bump_marker
    authored = load_authored()
    latest = max(e["session"] for e in authored["sessions"]) if authored["sessions"] else 0
    # Use render.load_data via the env override instead.
    import os
    data = render.load_data(os.environ["BUILD_DATA_DIR"])
    latest = len(data["session_log"]["entries"])
    bump_marker(authored, latest)

    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    refresh_slices = [s for s in manifest["slices"] if s["pass"] in ("discovery", "refresh")]
    assert refresh_slices == []


def test_prepare_includes_refresh_under_force(run_env):
    # Marker is whatever fixture says; force_refresh should add refresh slices.
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert any(s["pass"] == "refresh" for s in manifest["slices"])


def test_prepare_no_refresh_excludes_refresh_slices(run_env):
    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert not any(s["pass"] in ("discovery", "refresh") for s in manifest["slices"])


def test_prepare_stem_sanitization(run_env):
    """Stems must be filesystem-safe."""
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        # Stem matches pending filename root.
        assert entry["pending"] == f"pending/{entry['stem']}.json"
        # Only safe characters.
        assert all(c.isalnum() or c in "._-" for c in entry["stem"])


def test_prepare_model_from_prompt_frontmatter(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    models = {s["model"] for s in manifest["slices"]}
    # All entries should declare a model (default "sonnet" if absent).
    assert all(m for m in models)


def test_prepare_writes_keep_marker_when_keep_temp(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=True)
    assert (run_dir / ".keep").exists()


def test_prepare_no_keep_marker_by_default(run_env):
    run_dir = prepare.run(no_refresh=False, force_refresh=False, keep_temp=False)
    assert not (run_dir / ".keep").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_prepare.py -v`
Expected: FAIL — `prepare.run` does not exist.

- [ ] **Step 3: Implement prepare.run**

Append to `build/prepare.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_prepare.py -v`
Expected: PASS (all prepare tests, including the 6 frontmatter ones from Task 3).

- [ ] **Step 5: Commit**

```bash
git add build/prepare.py tests/test_prepare.py
git commit -m "prepare: gather slices and write run dir with manifest"
```

---

## Task 5: apply_cli reads results, validates, applies, renders

**Files:**
- Create: `build/apply_cli.py`
- Create: `tests/test_apply_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_apply_cli.py`:

```python
"""Tests for build/apply_cli.py — manifest-driven result application."""
import json
import shutil
from pathlib import Path

import pytest

from build import apply_cli, prepare, store
from build.paths import REPO_ROOT

FIXTURES = REPO_ROOT / "tests/fixtures"


@pytest.fixture
def staged_run(tmp_path, monkeypatch):
    """Run prepare against the fixtures to produce a real run dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    (data_dir / "dice").mkdir()
    shutil.copy(FIXTURES / "sample_dicex_rolls.json",
                data_dir / "dice" / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    run_root = tmp_path / "runs"
    run_root.mkdir()
    monkeypatch.setenv("BUILD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(authored_dir))
    monkeypatch.setenv("BUILD_RUN_ROOT", str(run_root))

    run_dir = prepare.run(no_refresh=True, force_refresh=False, keep_temp=False)
    return run_dir, authored_dir


def _write_result(run_dir: Path, entry: dict, payload: dict) -> None:
    """Helper: write the JSON result for one manifest entry."""
    (run_dir / entry["result"]).write_text(json.dumps(payload, indent=2))


def test_apply_missing_results_reports_pending(staged_run):
    run_dir, _ = staged_run
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert summary["pending"]  # at least one slice without a result
    assert summary["applied"] == []
    assert summary["render_ok"] is None  # render was skipped


def test_apply_validates_schema_and_rejects_malformed(staged_run):
    run_dir, _ = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    # Pick the first append-sessions slice — its schema requires a "fields"
    # object. Write something that fails validation.
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    _write_result(run_dir, target, {"bogus": "not the right shape"})

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    rejected = run_dir / "results" / "rejected"
    assert (rejected / f"{target['stem']}.json").exists()
    assert (rejected / f"{target['stem']}.error.json").exists()
    assert target["stem"] in {p["stem"] for p in summary["rejected"]}


def test_apply_applies_valid_results_and_persists_authored(staged_run):
    """Write a schema-valid append-sessions result and confirm the authored
    store gains the session entry after apply."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    slice_data = json.loads((run_dir / target["pending"]).read_text())

    _write_result(run_dir, target, {
        "fields": {
            "title": "Test Title",
            "summary": "A short summary of this session.",
            "silent_roll": []
        }
    })

    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert target["stem"] in {a["stem"] for a in summary["applied"]}

    sessions = json.loads((authored_dir / "sessions.json").read_text())
    matching = [s for s in sessions if s["session"] == slice_data["session"]]
    assert matching
    assert matching[0]["title"] == "Test Title"


def test_apply_is_idempotent_on_rerun(staged_run):
    """A second apply pass with the same result file should not double-apply."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    target = next(s for s in manifest["slices"] if s["transformer"] == "append-sessions")
    slice_data = json.loads((run_dir / target["pending"]).read_text())

    _write_result(run_dir, target, {
        "fields": {
            "title": "Idempotent",
            "summary": "Once.",
            "silent_roll": []
        }
    })

    apply_cli.apply_run(run_dir, skip_render=True)
    apply_cli.apply_run(run_dir, skip_render=True)

    sessions = json.loads((authored_dir / "sessions.json").read_text())
    matching = [s for s in sessions if s["session"] == slice_data["session"]]
    assert len(matching) == 1  # not duplicated by the second apply
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_apply_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build.apply_cli'`.

- [ ] **Step 3: Create build/apply_cli.py**

```python
"""Build orchestrator — apply half.

Reads results staged by the `/build-prose` skill, validates each against the
matching schema, applies via build.apply.apply_*, persists the authored
store, bumps the marker on full refresh-pass success, and runs
build/render.py.

Idempotency: a result that has already been applied moves out of `results/`
into `results/applied/`. Re-running apply on the same run dir reapplies
nothing that was applied before.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema

from . import inventory, registry, render, store
from .paths import REPO_ROOT, data_dir


def _load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text())


def _load_schema(run_dir: Path, entry: dict) -> dict:
    return json.loads((run_dir / entry["schema"]).read_text())


def _move(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def _run_render() -> dict:
    """Invoke build/render.py as a subprocess; return its status dict."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "build" / "render.py")],
        capture_output=True, text=True,
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def apply_run(run_dir: Path, *, skip_render: bool) -> dict:
    """Apply every present result in run_dir; return a summary dict.

    Summary keys:
      - applied: list of {transformer, key, stem}
      - rejected: list of {transformer, key, stem, reason}
      - pending: list of {transformer, key, stem} (no result file yet)
      - marker_old, marker_new
      - render_ok: bool | None (None when skip_render)
    """
    manifest = _load_manifest(run_dir)
    # Always load fresh state from disk; authored may have been edited between
    # prepare and apply (deliberate user intervention).
    data = render.load_data(str(data_dir()))
    authored = store.load_authored()
    inv_bundle = inventory.load(REPO_ROOT, party=data["party"])
    authored["inventory_by_id"] = inv_bundle["by_id"]
    authored["pronouns_by_id"] = render.load_character_pronouns()

    applied: list = []
    rejected: list = []
    pending: list = []
    refresh_total = sum(1 for s in manifest["slices"] if s["pass"] == "refresh")
    refresh_applied = 0

    rejected_dir = run_dir / "results" / "rejected"
    applied_dir = run_dir / "results" / "applied"

    for entry in manifest["slices"]:
        result_path = run_dir / entry["result"]
        if not result_path.exists():
            pending.append({"transformer": entry["transformer"],
                            "key": entry["key"], "stem": entry["stem"]})
            continue

        # Idempotency: if we previously moved a result to applied/, count it
        # toward refresh totals but do not re-apply.
        previously_applied = (applied_dir / f"{entry['stem']}.json").exists()
        if previously_applied and not result_path.exists():
            if entry["pass"] == "refresh":
                refresh_applied += 1
            continue

        # Validate against the snapshotted schema.
        try:
            output = json.loads(result_path.read_text())
            jsonschema.validate(output, _load_schema(run_dir, entry))
        except (json.JSONDecodeError, jsonschema.ValidationError) as e:
            err = {"transformer": entry["transformer"], "key": entry["key"],
                   "stem": entry["stem"], "reason": str(e)[:500]}
            rejected.append(err)
            (rejected_dir).mkdir(parents=True, exist_ok=True)
            _move(result_path, rejected_dir / f"{entry['stem']}.json")
            (rejected_dir / f"{entry['stem']}.error.json").write_text(
                json.dumps(err, indent=2)
            )
            continue

        # Apply.
        slice_data = json.loads((run_dir / entry["pending"]).read_text())
        fn = registry.by_name(entry["transformer"]).apply_fn
        fn(authored, entry["key"], slice_data, output)
        applied.append({"transformer": entry["transformer"],
                        "key": entry["key"], "stem": entry["stem"]})
        if entry["pass"] == "refresh":
            refresh_applied += 1

        # Move the result into applied/ so a second apply_run is a no-op.
        _move(result_path, applied_dir / f"{entry['stem']}.json")

    # Persist authored after the pass.
    if applied:
        store.persist(authored)

    marker_old = manifest["marker"]
    marker_new = marker_old
    # Bump marker only if every refresh slice in the manifest has now been
    # applied (no rejections, no still-pending).
    if refresh_total > 0 and refresh_applied == refresh_total and not rejected:
        store.bump_marker(authored, manifest["latest"])
        marker_new = manifest["latest"]

    render_ok: bool | None = None
    if not skip_render and not pending and not rejected:
        rr = _run_render()
        render_ok = rr["ok"]
        if not render_ok:
            # Surface to the caller; do not clean up.
            print(rr["stderr"][:2000], file=sys.stderr)

    return {
        "applied": applied,
        "rejected": rejected,
        "pending": pending,
        "marker_old": marker_old,
        "marker_new": marker_new,
        "render_ok": render_ok,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_apply_cli.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add build/apply_cli.py tests/test_apply_cli.py
git commit -m "apply_cli: validate results, apply, persist, render"
```

---

## Task 6: __main__ becomes a subcommand dispatcher

**Files:**
- Modify: `build/__main__.py`
- Modify: `tests/test_prepare.py` (one additional CLI integration check)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare.py`:

```python
# -- CLI dispatch ------------------------------------------------------------

def test_main_prepare_subcommand_creates_run_dir(run_env, capsys):
    from build.__main__ import main
    rc = main(["prepare", "--no-refresh"])
    assert rc == 0
    captured = capsys.readouterr()
    # main should print the run dir path so the user can pass it to the skill.
    assert "build/.run" in captured.out or "runs/" in captured.out


def test_main_apply_subcommand_requires_path(run_env, capsys):
    from build.__main__ import main
    rc = main(["apply"])
    assert rc != 0  # parser should reject missing positional
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_prepare.py -v -k "main_"`
Expected: FAIL — current `__main__.main` has no subcommands.

- [ ] **Step 3: Replace build/__main__.py**

```python
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

    args = parser.parse_args(argv)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_prepare.py tests/test_apply_cli.py tests/test_registry.py tests/test_paths.py -v`
Expected: PASS (all tests across the new modules).

- [ ] **Step 5: Smoke check that __main__ still imports**

Run: `.venv/bin/python -c "import build.__main__; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add build/__main__.py tests/test_prepare.py
git commit -m "Rewrite __main__ as prepare/apply subcommand dispatcher"
```

---

## Task 7: The /build-prose skill

**Files:**
- Create: `.claude/skills/build-prose/SKILL.md`

This is content, not code. There are no unit tests; verification is the end-to-end smoke run in Task 8.

- [ ] **Step 1: Create the skill file**

Create `.claude/skills/build-prose/SKILL.md`:

```markdown
---
name: build-prose
description: Drive a dnd-data build run by walking the pending/ slice queue in a run directory produced by `python -m build prepare`. Use when the user says "build prose", "drive a build", "/build-prose", or supplies a path under build/.run/. Dispatches one sub-agent per pending slice, each writing a JSON result file; does not touch build/authored/ directly.
---

# build-prose

You are the loop driver for the dnd-data build's authoring step. The deterministic Python around you has already done the slicing and will do the applying. Your single job: for every pending slice in the supplied run directory, dispatch a sub-agent that reads the slice and the prompt, produces JSON conforming to the schema, and writes it to `results/<stem>.json`.

## Inputs

The user invokes you with a path to a run directory, e.g.:
- `/build-prose build/.run/2026-05-17T14-32-08`
- `/build-prose` (no arg) — pick the alphabetically maximal subdirectory of `build/.run/`.

A valid run directory contains `manifest.json`, `pending/`, `results/`, `done/`, and `prompts/`.

## Procedure

1. Read `<run-dir>/manifest.json`.
2. Filter `slices` to entries whose `pending/<stem>.json` still exists (i.e. not yet authored).
3. Dispatch sub-agents in batches of up to 5 in a single message:
   - `subagent_type: "general-purpose"`
   - `model`: the entry's `model` field (`sonnet` or `opus`).
   - **Prompt body** (substitute the bracketed fields):

         You are acting as the [transformer] transformer. Read these
         two files only:

         - prompt body: <run-dir>/[prompt_body]
         - schema: <run-dir>/[schema]

         The slice input is:

         <inline the entire contents of <run-dir>/[pending]>

         Produce a single JSON object that conforms to the schema. Do
         not include any prose, markdown, or commentary — only the
         JSON document. Write it to:

         <run-dir>/[result]

         Do not edit any other file. Do not run any other tool besides
         Read (on the two paths above) and Write (on the result path).
4. After every sub-agent in the batch returns, check `results/<stem>.json`:
   - If the file exists and parses as JSON, move `pending/<stem>.json` to `done/<stem>.json`.
   - If not, leave the pending file in place and log the slice in `<run-dir>/failures.json` (append, not overwrite).
5. Repeat batches until `pending/` only contains slices that have failed at least once. Do not retry inside the same skill run — the user gets to decide whether to edit the slice or prompt first.
6. Print a one-line summary per slice (applied / failed) and the next-step command:
   ```
   python -m build apply <run-dir>
   ```

## Constraints

- Never modify `build/authored/*.json`. The apply step does that.
- Never modify files under `<run-dir>/prompts/`. They are the frozen reference.
- Never run `build/render.py`. The apply step does that.
- If `manifest.json` is missing, print an error and exit.
- If the run dir has no pending slices, print `nothing to do` and exit.

## Failure handling

If a sub-agent returns nothing or returns invalid JSON, do not write a placeholder result. Leave the pending file in place. The next `python -m build apply <run-dir>` will report it as pending; the user can fix the prompt or slice and re-run `/build-prose`.

A second `/build-prose <run-dir>` call is safe to run — it skips slices already moved to `done/` and retries anything still in `pending/`.
```

- [ ] **Step 2: Smoke check the YAML frontmatter parses**

Run: `.venv/bin/python -c "
import re, sys
text = open('.claude/skills/build-prose/SKILL.md').read()
assert text.startswith('---\n')
m = re.match(r'---\n(.*?)\n---\n', text, re.DOTALL)
assert m, 'frontmatter not closed'
print('ok')
"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/build-prose/SKILL.md
git commit -m "Add build-prose skill to drive the slice queue in-session"
```

---

## Task 8: End-to-end smoke + remove legacy code

**Files:**
- Delete: `build/invoke.py`
- Delete: `build/build_loop.py`
- Delete: `tests/test_invoke.py`
- Verify: full test suite, real build dry-run

- [ ] **Step 1: Run the full suite against current state**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS, including the new modules. Note the green baseline before deleting anything.

- [ ] **Step 2: Confirm nothing imports the legacy modules**

Run: `grep -rn "build.invoke\|build.build_loop\|from .invoke\|from .build_loop" build/ tests/`
Expected: no output (no remaining importers).

If output appears, stop and refactor the importer before continuing. The previous tasks should have left zero references, but verify.

- [ ] **Step 3: Delete the legacy modules**

```bash
git rm build/invoke.py build/build_loop.py tests/test_invoke.py
```

- [ ] **Step 4: Re-run the suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Dry-run prepare against the real repo**

Run: `.venv/bin/python -m build prepare --no-refresh`
Expected: prints a path like `build/.run/2026-05-17T...`. That directory exists, contains `manifest.json` and a `pending/` subdir.

Inspect: `ls $(ls -td build/.run/*/ | head -1)` — should list `manifest.json`, `pending/`, `results/`, `done/`, `prompts/`.

- [ ] **Step 6: Clean up the smoke run dir**

```bash
rm -rf build/.run
```

- [ ] **Step 7: Update CLAUDE.md to reflect the new flow**

In `CLAUDE.md`, replace the two paragraphs under `## Build & deploy` describing the build flow. New text:

```markdown
## Build & deploy

Building is a three-step flow:

1. `.venv/bin/python -m build prepare` gathers any pending slices into
   `build/.run/<timestamp>/` (manifest, pending slices, frozen prompts).
2. In a Claude Code session, run `/build-prose build/.run/<timestamp>/` —
   the skill dispatches one sub-agent per pending slice, each writing a
   JSON result file.
3. `.venv/bin/python -m build apply build/.run/<timestamp>/` validates
   each result against its schema, applies it to `build/authored/*.json`,
   bumps the marker on full refresh-pass success, and runs `build/render.py`.

A bare `python -m build` is the same as `prepare`; it prints the skill
command to run next and exits.

Validation gates the render: any `MISSING` or `MALFORMED` authored entry
causes `render.py` to exit 1. Fix the authored entry and re-run apply.

CLI flags:
- `prepare --no-refresh` — skip the discovery and refresh passes.
- `prepare --force-refresh` — run them even when the marker is current.
- `prepare --keep-temp` — preserve the run dir on success.
- `apply --skip-render` — apply results but don't rebuild the site.

To publish: pull `main`, run the three-step build, commit `site/index.html`
and `build/authored/*.json`, push.
```

Also update the `## Orchestration` and "Per-slice invocation pattern" sections to reflect that authoring runs in-session via the skill rather than via `claude -p`. Reuse the same three-step language. Remove the `--max-budget-usd`, `--disallowedTools`, `--permission-mode plan` paragraph.

- [ ] **Step 8: Commit**

```bash
git add build/ tests/ CLAUDE.md
git commit -m "Remove legacy claude -p orchestrator; document three-step build"
```

---

## Self-Review

**Spec coverage:**
- `prepare` subcommand → Task 4 + Task 6.
- Run-dir layout (pending/results/done/prompts/manifest.json) → Task 4.
- Frozen prompt + schema snapshots → Task 4 (`_prompt_meta`).
- Skill that drives sub-agents → Task 7.
- `apply` validates and rejects → Task 5.
- Idempotent re-apply → Task 5 (moves results to `applied/`).
- Marker bump on full refresh success → Task 5.
- Render gated by validation → Task 5 (only runs when no pending + no rejected).
- `.gitignore` for `build/.run/` → Task 2.
- Legacy modules removed → Task 8.
- CLI flags `--no-refresh`, `--force-refresh`, `--keep-temp`, `--skip-render` → Tasks 4 / 5 / 6.

**Placeholder scan:** No "TBD" / "TODO" / "fill in" markers. Every code step shows full code; every test step shows the assertions.

**Type consistency:** `apply_cli.apply_run` signature is `(run_dir: Path, *, skip_render: bool) -> dict` — used identically in Tasks 5 and 6. `prepare.run` signature is `(*, no_refresh, force_refresh, keep_temp) -> Path` — used identically in Tasks 4 and 6. The `Transformer` dataclass fields match across Tasks 1, 4, and 5. Manifest field names (`stem`, `pending`, `result`, `prompt_body`, `schema`, `pass`, `key`, `model`, `transformer`) are identical everywhere they appear.

**One spec gap I noticed and added in:** the spec mentions a `failures.json` log in the run dir for skill failures; that's covered in Task 7's procedure step 4. The spec also mentions `apply-errors.json`; the implementation in Task 5 writes per-rejected-result `<stem>.error.json` files instead, which is functionally equivalent and easier to read.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-in-session-build-prose.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
