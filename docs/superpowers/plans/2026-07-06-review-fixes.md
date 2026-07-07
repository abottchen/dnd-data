# Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every finding from the 2026-07-06 repo-wide design/code-quality review: correctness bugs, apply-pipeline atomicity, dead code, template/JS duplication, missing test coverage, CI gating, privacy-guard hygiene, and the render.py module split.

**Architecture:** The repo is a deterministic static-site build: `data/` + `build/authored/*.json` → `build/render.py` (validate → compute → Jinja2) → `site/index.html`, orchestrated by the `build` package (`prepare`/`apply`). Fixes are ordered: orchestrator correctness first, renderer bugs second, template/JS third, tests/CI/hygiene fourth, and the two large refactors (tooltip consolidation lands in phase 3; render.py split last) as behavior-preserving code motion.

**Tech Stack:** Python 3 (stdlib + jinja2 + jsonschema), pytest, Jinja2 templates, vanilla JS inline in `_script.html`, GitHub Actions.

## Global Constraints

- Commit messages: conventional-commit style, **never mention Claude/AI, no trailers of any kind (no Co-Authored-By)**.
- `.venv/bin/pytest tests/` must pass after every task (249 tests at start; count grows).
- After any task that touches render output, re-render and diff: `.venv/bin/python build/render.py && git diff --stat site/index.html`. Unless the task says otherwise, output must be identical (or the diff must be exactly what the task predicts).
- Renderer philosophy is locked: geometry/computation server-side, client JS only animates/positions/reveals — never recomputes data.
- Templates reference assets relative to `site/index.html` (`styles.css`, `images/...`).
- `data/` contents are gitignored and must never be committed; real player names must never appear in committed files or the rendered HTML.
- Env overrides for test isolation: `BUILD_DATA_DIR`, `BUILD_AUTHORED_DIR`, `BUILD_RUN_ROOT`.
- Run each task's commit from the repo root; hooks are active (`git config core.hooksPath .githooks`).

---

## Phase 1 — Orchestrator correctness

### Task 1: Session-ordinal invariant + `_new_entries()` helper

The refresh marker `site.refreshed_through_session` is compared against **positional** entry indices in five places in `build/slices.py`. This is only correct while entry N in the session log *is* session N. Make the invariant explicit (fail loudly in `load_data`) and single-source the marker gate.

**Files:**
- Modify: `build/render.py` (in `load_data`, right after the `normalized_entries` loop completes and before `session_log = dict(session_log)`)
- Modify: `build/slices.py` (add helper; use it in `_character_context`, `refresh_npcs`, `refresh_road_ahead`, `refresh_intro_epithet`, `refresh_ascent_read`)
- Test: `tests/test_loaders.py`, `tests/test_slices.py`

**Interfaces:**
- Produces: `slices._new_entries(data: dict, authored: dict) -> list[dict]` — session-log entries newer than the refresh marker, in log order.

- [ ] **Step 1: Write failing tests**

In `tests/test_loaders.py` (match existing test style — build a minimal data dir under `tmp_path` the way neighboring tests do; if they construct `session-log.json` inline, do the same):

```python
def test_load_data_rejects_out_of_order_session_ordinals(tmp_path):
    """The refresh marker is a positional count; entry i must be session i."""
    (tmp_path / "party.json").write_text("[]")
    (tmp_path / "dice").mkdir()
    log = {"entries": [
        {"day": "1", "realDate": "04/19/2026", "text": ""},
        {"day": "3", "realDate": "04/23/2026", "text": ""},   # gap: entry 2 is session 3
    ]}
    (tmp_path / "session-log.json").write_text(json.dumps(log))
    with pytest.raises(ValueError, match="session ordinal"):
        render.load_data(tmp_path)
```

In `tests/test_slices.py`:

```python
def test_new_entries_respects_marker(slice_env):
    data, authored = slice_env["data"], slice_env["authored"]
    authored["site"]["refreshed_through_session"] = 1
    new = slices._new_entries(data, authored)
    assert [e["session"] for e in new] == [
        e["session"] for e in data["session_log"]["entries"][1:]
    ]

def test_new_entries_empty_when_marker_current(slice_env):
    data, authored = slice_env["data"], slice_env["authored"]
    authored["site"]["refreshed_through_session"] = len(data["session_log"]["entries"])
    assert slices._new_entries(data, authored) == []
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_loaders.py tests/test_slices.py -k "ordinal or new_entries" -v` → FAIL (no `_new_entries`, no ValueError raised).

- [ ] **Step 3: Implement**

In `build/render.py`, after the `normalized_entries` loop:

```python
    # The refresh marker (site.refreshed_through_session) and every marker
    # gate in build/slices.py treat entry position as session id. That is
    # only sound while entry i IS session i — fail loudly if the log ever
    # gains an out-of-order / inserted entry so the assumption is revisited
    # deliberately instead of silently mis-scoping every refresh pass.
    for i, ne in enumerate(normalized_entries, start=1):
        if ne.get("session") != i:
            raise ValueError(
                f"session ordinal mismatch: entry {i} carries session "
                f"{ne.get('session')!r}; the refresh marker requires entry i == session i"
            )
```

In `build/slices.py`, add below `session_index`:

```python
def _new_entries(data: dict, authored: dict) -> list[dict]:
    """Session-log entries newer than the refresh marker, in log order.

    The marker is a positional count (entry i == session i; load_data
    enforces this), so 'newer' is simply position > marker.
    """
    marker = authored["site"].get("refreshed_through_session", 0)
    entries = data["session_log"]["entries"]
    return list(entries[marker:])
```

Replace the five inline `enumerate(entries, start=1) ... if i > marker` gates:
- `_character_context`: `new = _new_entries(data, authored)`; then `new_dates = {e["date"] for e in new}` and `session_text = [{"session": e.get("session"), "date": e.get("date"), "text": e.get("text", "")} for e in new]`. Delete the local `marker`/`entries` lines that only fed the old comprehensions.
- `refresh_npcs`: `new_session_ids = None if force else {e.get("session") for e in _new_entries(data, authored)}`. Delete the now-unused local `marker`.
- `refresh_road_ahead`, `refresh_intro_epithet`, `refresh_ascent_read`: `new_sessions = _new_entries(data, authored)`; delete the local `marker` lines.

- [ ] **Step 4: Run full suite** — `.venv/bin/pytest tests/ -v` → all pass.
- [ ] **Step 5: Commit** — `git add build/render.py build/slices.py tests/test_loaders.py tests/test_slices.py && git commit -m "fix(build): enforce session-ordinal invariant, single-source marker gate"`

---

### Task 2: Atomic apply + remove dead data loading in apply_cli

`apply_*` functions mutate the shared `authored` dict mid-loop; an exception leaves half-applied state that `store.persist` then writes to disk. Also, `apply_run` loads `data`, the inventory bundle, and pronouns that **no apply function reads** — dead weight coupling apply to `data/` being present.

**Files:**
- Modify: `build/apply_cli.py`
- Test: `tests/test_apply_cli.py`

**Interfaces:**
- Consumes: `registry.by_name(name).apply_fn(authored, key, slice_data, output)` (unchanged signature).
- Produces: `apply_run` unchanged externally, but a slice that fails mid-apply leaves `authored` exactly as before that slice.

- [ ] **Step 1: Write failing test** in `tests/test_apply_cli.py` (uses the existing `staged_run` fixture and `_write_result` helper):

```python
def test_failed_apply_leaves_no_partial_mutation(staged_run):
    """append-kills applies per-entry in a loop; a bad key mid-batch must not
    leave earlier entries appended when the slice is recorded rejected."""
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = next(s for s in manifest["slices"]
                 if s["transformer"] == "append-kills")
    slice_data = json.loads((run_dir / entry["pending"]).read_text())
    k = slice_data["kills"][0]
    good_key = f"{k['character']}__{k['date']}__{k['creature']}__{k['method']}"
    _write_result(run_dir, entry, {"fields": {
        good_key: {"verse": "A verse.", "annotation": "an annotation"},
        "nobody__2099-01-01__Nothing__nothing": {"verse": "x", "annotation": "y"},
    }})
    before = json.loads((authored_dir / "kills.json").read_text())
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert any(r["stem"] == entry["stem"] for r in summary["rejected"])
    after = json.loads((authored_dir / "kills.json").read_text())
    assert after == before  # no partial append persisted
```

Note: if the append-kills schema rejects the second key before apply runs, loosen the fake key to one that *passes* the schema pattern but is absent from the slice (read `run_dir/prompts/append-kills.schema.json` to confirm the shape). The point is to reach `apply_append_kills` and fail on the second entry.

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_apply_cli.py::test_failed_apply_leaves_no_partial_mutation -v` → FAIL (partial kill persisted).

- [ ] **Step 3: Implement** in `build/apply_cli.py`:

Add `import copy` to the imports. Delete these lines from `apply_run` (dead — no apply fn reads them):

```python
    data = render.load_data(str(data_dir()))
    ...
    inv_bundle = inventory.load(REPO_ROOT, party=data["party"])
    authored["inventory_by_id"] = inv_bundle["by_id"]
    authored["pronouns_by_id"] = render.load_character_pronouns()
```

Also remove the now-unused imports (`inventory`, `render` if nothing else uses it — `render` is still unused after this; keep only what's referenced) and `data_dir`/`REPO_ROOT` if unused (`REPO_ROOT` is still used by `_run_render`).

Replace the apply block with a trial-copy pattern:

```python
        # Apply against a scratch copy so a mid-loop failure inside an
        # apply fn cannot leave half-applied mutations in the store that
        # a later persist() would write to disk.
        slice_data = _load_slice(run_dir, entry)
        fn = registry.by_name(entry["transformer"]).apply_fn
        trial = copy.deepcopy(authored)
        try:
            fn(trial, entry["key"], slice_data, output)
        except (ValueError, KeyError) as e:
            _record_rejection(rejected, rejected_dir, entry, result_path,
                              f"apply failed: {e}")
            continue
        authored = trial
```

- [ ] **Step 4: Run** — `.venv/bin/pytest tests/test_apply_cli.py tests/test_apply.py -v` → all pass. Then full suite.
- [ ] **Step 5: Commit** — `git commit -am "fix(apply): make per-slice apply atomic; drop unused data/inventory loading"`

---

### Task 3: Duplicate-append guards in apply functions

Applying two independently-prepared run dirs currently duplicates every appended entry, and `append_chapters` bakes `next_id` at prepare time so a chapter added between prepare and apply collides ids. Reject appends whose key already exists.

**Files:**
- Modify: `build/apply.py` (`apply_append_kills`, `apply_append_sessions`, `apply_append_chapters`, `apply_append_npcs`, `apply_append_characters`)
- Test: `tests/test_apply.py`

- [ ] **Step 1: Write failing tests** in `tests/test_apply.py` (follow the file's existing construction style for `authored`/`slice_data`/`output` dicts):

```python
def test_append_sessions_rejects_existing_session():
    authored = {"sessions": [{"session": 2, "date": "2026-04-23",
                              "title": "t", "summary": "s", "silent_roll": []}]}
    slice_data = {"session": 2, "real_date": "2026-04-23"}
    output = {"fields": {"title": "new", "summary": "new", "silent_roll": []}}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_sessions(authored, 2, slice_data, output)

def test_append_npcs_rejects_existing_name():
    authored = {"npcs": [{"name": "Azlund", "epithet": "e", "allegiance": "with"}]}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_npcs(authored, "Azlund", {"name": "Azlund"},
                                {"fields": {"epithet": "x", "allegiance": "with"}})

def test_append_chapters_rejects_existing_id_or_start():
    authored = {"chapters": [{"id": 1, "starts_at_session": 1,
                              "title": "t", "epigraph": "e"}]}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_chapters(authored, "1", {"starts_at_session": 9},
                                    {"fields": {"title": "x", "epigraph": "y"}})
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_chapters(authored, "2", {"starts_at_session": 1},
                                    {"fields": {"title": "x", "epigraph": "y"}})

def test_append_kills_rejects_existing_key():
    authored = {"kills": [{"character": "vex", "date": "2026-04-19",
                           "creature": "Goblin", "method": "shortbow",
                           "verse": "v", "annotation": "a"}]}
    slice_data = {"kills": [{"character": "vex", "date": "2026-04-19",
                             "creature": "Goblin", "method": "shortbow"}]}
    output = {"fields": {"vex__2026-04-19__Goblin__shortbow":
                         {"verse": "v2", "annotation": "a2"}}}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_kills(authored, "2026-04-19", slice_data, output)

def test_append_characters_rejects_existing_id():
    authored = {"characters": [{"id": "vex"}]}
    output = {"fields": {"vex": {"epithet": "e", "reliquary_header": "r",
                                 "constellation_epithet": "c",
                                 "distinction_title": "t", "distinction_subtitle": "s",
                                 "distinction_detail": "d", "distinction_basis": {}}}}
    with pytest.raises(ValueError, match="already authored"):
        apply.apply_append_characters(authored, "all", {}, output)
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_apply.py -k rejects -v` → FAIL.

- [ ] **Step 3: Implement** in `build/apply.py`. At the top of each append fn, before any mutation (these run against the trial copy from Task 2, so raising is clean):

```python
# apply_append_kills — inside the loop, after computing `normalized`:
        existing = {
            render.kill_key(a["character"], a["date"], a["creature"], a["method"])
            for a in authored["kills"]
        }
        # (hoist this set-build above the loop, not per-iteration)
        if normalized in existing:
            raise ValueError(f"kill already authored: {kk_str!r}")

# apply_append_sessions — first line:
    if any(s["session"] == slice_data["session"] for s in authored["sessions"]):
        raise ValueError(f"session {slice_data['session']} already authored")

# apply_append_chapters — first lines:
    chapter_id = int(key)
    if any(c["id"] == chapter_id for c in authored["chapters"]):
        raise ValueError(f"chapter id {chapter_id} already authored")
    if any(c["starts_at_session"] == slice_data["starts_at_session"]
           for c in authored["chapters"]):
        raise ValueError(
            f"chapter starting at session {slice_data['starts_at_session']} already authored")

# apply_append_npcs — first line:
    if any(n["name"] == key for n in authored["npcs"]):
        raise ValueError(f"npc {key!r} already authored")

# apply_append_characters — inside the loop, before append:
        if any(c["id"] == pc_id for c in authored["characters"]):
            raise ValueError(f"character {pc_id!r} already authored")
```

Use `chapter_id` in the append (`"id": chapter_id`) instead of re-calling `int(key)`.

- [ ] **Step 4: Run full suite** → pass.
- [ ] **Step 5: Commit** — `git commit -am "fix(apply): reject appends whose key is already authored"`

---

### Task 4: Refresh schemas — `rewrite` requires non-null `fields`

All eight `refresh-*.schema.json` files type `fields` as `["object", "null"]` unconditionally, so `{"decision": "rewrite", "fields": null}` passes the validation gate and dies later as a cryptic `apply failed: 'epithet'`.

**Files:**
- Modify: all 8 files listed by `grep -l '"null"' .claude/prompts/refresh-*.schema.json` (`refresh-archetype-inscription`, `refresh-ascent-read`, `refresh-chapters`, `refresh-characters`, `refresh-intro-epithet`, `refresh-known-npcs`, `refresh-npcs`, `refresh-road-ahead`)
- Test: `tests/test_validator.py` (or a new `tests/test_schemas.py`)

- [ ] **Step 1: Write failing test** in a new `tests/test_schemas.py`:

```python
"""Refresh schemas must reject decision=rewrite with fields=null."""
import json
from pathlib import Path

import jsonschema
import pytest

PROMPTS = Path(__file__).resolve().parent.parent / ".claude" / "prompts"
REFRESH_SCHEMAS = sorted(PROMPTS.glob("refresh-*.schema.json"))


@pytest.mark.parametrize("schema_path", REFRESH_SCHEMAS, ids=lambda p: p.stem)
def test_rewrite_requires_fields_object(schema_path):
    schema = json.loads(schema_path.read_text())
    bad = {"decision": "rewrite", "fields": None, "reason": "r"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.parametrize("schema_path", REFRESH_SCHEMAS, ids=lambda p: p.stem)
def test_no_change_allows_null_fields(schema_path):
    schema = json.loads(schema_path.read_text())
    ok = {"decision": "no_change", "fields": None, "reason": "r"}
    jsonschema.validate(ok, schema)  # must not raise
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/pytest tests/test_schemas.py -v` → the `rewrite` half FAILS.

- [ ] **Step 3: Implement** — add to each of the 8 schemas, as a top-level key alongside `"properties"`:

```json
  "allOf": [
    {
      "if": {"properties": {"decision": {"const": "rewrite"}}},
      "then": {"properties": {"fields": {"type": "object"}}}
    }
  ]
```

(Do not change the existing `"fields": {"type": ["object", "null"], ...}` declaration — the conditional narrows it only when rewriting.)

- [ ] **Step 4: Run** — `.venv/bin/pytest tests/test_schemas.py tests/test_apply_cli.py -v` → pass.
- [ ] **Step 5: Commit** — `git add .claude/prompts tests/test_schemas.py && git commit -m "fix(schemas): rewrite decision requires non-null fields"`

---

### Task 5: Surface road-ahead graduations in the apply summary

`apply_refresh_road_ahead` returns `{"graduated": [...]}`; `apply_run` discards every return value, so the documented "end-of-run report" doesn't exist.

**Files:**
- Modify: `build/apply_cli.py`, `build/__main__.py`
- Test: `tests/test_apply_cli.py`

**Interfaces:**
- Produces: `apply_run` summary gains `"graduated": list[str]` (names that moved known → was_known this run; empty list otherwise).

- [ ] **Step 1: Write failing test** in `tests/test_apply_cli.py`. Use a `force_refresh` staged run so a road-ahead slice exists (mirror `staged_run` but call `prepare.run(no_refresh=False, force_refresh=True, keep_temp=False)`); write a result for the `refresh-road-ahead` entry:

```python
def test_apply_surfaces_road_ahead_graduations(staged_refresh_run):
    run_dir, authored_dir = staged_refresh_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = next(s for s in manifest["slices"]
                 if s["transformer"] == "refresh-road-ahead")
    _write_result(run_dir, entry, {
        "decision": "rewrite",
        "fields": {"known": [], "was_known":
                   [{"name": "Azlund's offer", "gloss": "answered"}],
                   "direction": "north"},
        "reason": "test",
    })
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert summary["graduated"] == ["Azlund's offer"]
```

Add the `staged_refresh_run` fixture next to `staged_run` (same body, `force_refresh=True, no_refresh=False`).

- [ ] **Step 2: Verify failure** — KeyError `graduated`.

- [ ] **Step 3: Implement** — in `apply_run`, initialize `graduated: list = []` beside `applied`; capture the return where `fn` is invoked (Task 2's block):

```python
        try:
            ret = fn(trial, entry["key"], slice_data, output)
        except (ValueError, KeyError) as e:
            ...
        authored = trial
        if isinstance(ret, dict):
            graduated.extend(ret.get("graduated", []))
```

Add `"graduated": graduated` to the returned summary and document it in the docstring's summary-keys list. In `build/__main__.py::_cmd_apply`, after the pending line:

```python
    if summary.get("graduated"):
        print("graduated (known → was_known): "
              + ", ".join(summary["graduated"]), file=sys.stderr)
```

- [ ] **Step 4: Run full suite** → pass.
- [ ] **Step 5: Commit** — `git commit -am "feat(apply): surface road-ahead graduations in the run summary"`

---

### Task 6: Run-dir pruning (honor `--keep-temp`) + `_load_slice` rejection

Nothing ever deletes run dirs (17 accumulated since May) even though `prepare` writes a `.keep` sentinel and CLAUDE.md implies pruning. Also `_load_slice` crashes the whole run on a hand-cleaned run dir.

**Files:**
- Modify: `build/apply_cli.py`
- Test: `tests/test_apply_cli.py`

- [ ] **Step 1: Write failing tests**:

```python
def test_fully_successful_apply_prunes_run_dir(staged_run):
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert not summary["rejected"] and not summary["pending"]
    assert not run_dir.exists()

def test_keep_marker_preserves_run_dir(staged_run):
    run_dir, authored_dir = staged_run
    (run_dir / ".keep").write_text("")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for entry in manifest["slices"]:
        _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    apply_cli.apply_run(run_dir, skip_render=True)
    assert run_dir.exists()

def test_missing_slice_file_is_rejected_not_crash(staged_run):
    run_dir, authored_dir = staged_run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    entry = manifest["slices"][0]
    _write_result(run_dir, entry, _valid_payload_for(entry, run_dir))
    (run_dir / entry["pending"]).unlink()          # simulate manual cleanup
    summary = apply_cli.apply_run(run_dir, skip_render=True)
    assert any(r["stem"] == entry["stem"] and "slice file missing" in r["reason"]
               for r in summary["rejected"])
```

For `_valid_payload_for`, check how existing tests in this file construct valid results (e.g. `test_apply_applies_valid_results` or the idempotency test around line 94) and reuse/extract that helper rather than inventing a new shape. If no such helper exists, write one that switches on `entry["transformer"]` for the transformers the fixture run emits (`no_refresh=True` keeps it to append transformers only), producing schema-valid minimal payloads.

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** in `apply_run`:

`_load_slice` hardening — wrap the apply block's slice load:

```python
        try:
            slice_data = _load_slice(run_dir, entry)
        except FileNotFoundError:
            _record_rejection(rejected, rejected_dir, entry, result_path,
                              "slice file missing from pending/ and done/")
            continue
```

(`_load_slice`'s `done_path` read raises `FileNotFoundError` naturally; no change needed there.)

Pruning — at the end of `apply_run`, just before `return`:

```python
    # A fully-successful run has nothing left to inspect: prune the run dir
    # unless the user pinned it with --keep-temp (the .keep sentinel).
    fully_ok = not rejected and not pending and render_ok is not False
    if fully_ok and not (run_dir / ".keep").exists():
        shutil.rmtree(run_dir, ignore_errors=True)
```

- [ ] **Step 4: Run full suite** → pass. Existing idempotency tests that re-apply the same run dir may need a `.keep` file added or reordering — adjust them to write `(run_dir / ".keep")` before the first apply, preserving what they test.
- [ ] **Step 5: Commit** — `git commit -am "feat(apply): prune run dir on full success, honor .keep; reject missing slice files"`

---

### Task 7: Inventory/slices hygiene sweep

Single-source the archetype keywords, harden `it["id"]` access, move the mid-file import, drop fabricated slice fields, warn on dropped kills, fix stale comments.

**Files:**
- Modify: `build/inventory.py`, `build/slices.py`, `build/prepare.py`, `build/__main__.py`, `.claude/prompts/refresh-archetype-inscription.md`
- Test: `tests/test_inventory.py`, `tests/test_slices.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_inventory.py
def test_scorers_and_archetype_match_share_keywords():
    """A keyword added to a scorer must also drive archetype_match filtering."""
    items = [{"id": "b1", "name": "Dusty Spellbook", "count": 1,
              "category": "Adventuring Gear", "weight": 1, "rarity": "common",
              "description": ""}]
    assert inventory.score_scholar(items, {}) == 1
    assert inventory.archetype_match("scholar", items) == items

def test_glaive_hand_and_quartermaster_tolerate_missing_id():
    items = [{"name": "Blade", "category": "Weapon", "count": 1}]
    assert inventory.score_glaive_hand(items, {}) == 0
    assert inventory.score_quartermaster(items, {}) == 0

# tests/test_slices.py
def test_archetype_slice_carries_no_fabricated_stats(slice_env):
    data, authored = slice_env["data"], slice_env["authored"]
    authored["inventory_by_id"] = {"vex": {
        "archetype": "scholar", "total_weight": 3.0,
        "rack": [], "spotlight": [],
        "manifest": [{"name": "Spellbook", "count": 1, "weight": 3,
                      "description": ""}],
    }}
    out = slices.refresh_archetype_inscription(data, authored)
    (_, s), = [t for t in out if t[0] == "vex"]
    assert set(s["archetype"]) == {"slug", "label", "score"}
```

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement**

`build/inventory.py`:
1. Move the `_KEYWORDS` dict from ~line 448 up to just above `score_scholar` (keep its comment). Delete `_SCHOLAR_KW`, `_NATURALIST_KW`, `_TONGUES_KW`, `_LAMPLIGHTER_KW`, `_PATHFINDER_KW`, `_CELLARER_KW`, `_TRAPPER_KW`, `_COSTUME_KW`. Each keyword scorer reads the shared map, e.g.:
   ```python
   def score_scholar(items: list[dict], member: dict) -> int:
       return _sum_count_where(items, lambda it: _matches_any(it, _KEYWORDS["scholar"]))
   ```
   (same pattern for naturalist, tongues, lamplighter, pathfinder, cellarer, trapper, costume_master).
2. `score_glaive_hand`: `return len({it.get("id") for it in items if it.get("category") == "Weapon" and it.get("id")})`. `score_quartermaster`: `return len({it.get("id") for it in items if it.get("id")})`.

`build/slices.py`:
3. Move `from build.inventory import archetype_match, ARCHETYPE_SLATE` (line ~431) to the top-of-file imports as `from .inventory import ARCHETYPE_SLATE, archetype_match`; move `_ARCHETYPE_LABELS = ...` up with the other module constants. Confirm no import cycle: `.venv/bin/python -c "import build.slices"`.
4. In `refresh_archetype_inscription`, shrink the archetype block to real data only:
   ```python
            "archetype": {
                "slug": arc_slug,
                "label": _ARCHETYPE_LABELS.get(arc_slug, arc_slug.upper()),
                "score": rec.get("total_weight", 0),
            },
   ```
5. In `append_kills`, replace the silent `continue` on a date with no session entry:
   ```python
        if session is None:
            print(f"append_kills: no session-log entry for kill date {date}; "
                  f"skipping {len(kills)} kill(s)", file=sys.stderr)
            continue
   ```
   (add `import sys` at top).

`.claude/prompts/refresh-archetype-inscription.md`:
6. Update the line documenting the archetype object (line ~11) to `` `archetype`: `{slug, label, score}` `` and remove any prose referencing `metric`, `runner_up_score`, or `lead` elsewhere in the file.

Stale comments:
7. `build/prepare.py` line ~55: change `# Inventory + pronoun side channels (mirror current __main__.py wiring).` to `# Inventory + pronoun side channels for slice builders. These ride inside the authored dict but are never persisted: store.persist writes only LIST_STEMS + site.`
8. `build/__main__.py`: delete the unreachable `parser.error(...)` / `return 2` tail of `main()` (every `cmd` value is handled above).

- [ ] **Step 4: Run full suite** → pass.
- [ ] **Step 5: Commit** — `git commit -am "refactor(inventory,slices): single-source archetype keywords, drop fabricated slice stats, hygiene"`

---

## Phase 2 — Renderer fixes

### Task 8: Fix `compute_best_skill` tiebreak

Docstring says "then alphabetical skill key"; the implementation uses `-ord(key[0])` (first character only, wrong direction guarantees nothing past char 1).

**Files:**
- Modify: `build/render.py` (`compute_best_skill`)
- Test: `tests/test_compute.py`

- [ ] **Step 1: Write failing test**

```python
def test_compute_best_skill_alphabetical_tiebreak_past_first_char():
    member = {"skills": {
        "athletics": {"mod": 3, "prof": "full"},
        "arcana":    {"mod": 3, "prof": "full"},
    }}
    assert render.compute_best_skill(member)["name"] == "Arcana"
```

- [ ] **Step 2: Verify failure** (with dict order `athletics` first, `max` keeps `athletics`).

- [ ] **Step 3: Implement**

```python
def compute_best_skill(member: dict) -> dict | None:
    """Return {'name': 'Persuasion', 'mod': 5} for the member's strongest skill.
    Tie-break: higher proficiency rank, then alphabetical skill key."""
    skills = member.get("skills") or {}
    if not skills:
        return None
    best_key, best = min(
        skills.items(),
        key=lambda item: (-item[1].get("mod", 0),
                          -_PROF_RANK.get(item[1].get("prof", "none"), 0),
                          item[0]),
    )
    return {"name": SKILL_DISPLAY.get(best_key, best_key), "mod": best.get("mod", 0)}
```

- [ ] **Step 4: Run** — suite passes; re-render (`.venv/bin/python build/render.py`) and `git diff site/index.html` — expect no diff unless a real tie existed (if it did, eyeball that the change is the alphabetical winner, keep it).
- [ ] **Step 5: Commit** — `git commit -am "fix(render): correct compute_best_skill alphabetical tiebreak"`

---

### Task 9: Join reliquary verses in Python (kill the template key rebuild)

`_reliquary.html` rebuilds kill keys with `| lower` while Python uses `.casefold()` — divergent for non-ASCII, and a mismatch is a render-time KeyError. Give the template pre-joined rows.

**Files:**
- Modify: `build/render.py` (`compute_all`), `build/templates/_reliquary.html`
- Test: `tests/test_compute.py`

**Interfaces:**
- Produces: context key `reliquary_by_id: dict[str, list[dict]]` — per member id, date-sorted rows `{date, date_label, creature, cr_label, verse, annotation}`. Context key `kills_authored_by_key` is REMOVED (template was its only consumer — verify with `grep -rn kills_authored_by_key build/ tests/`).

- [ ] **Step 1: Write failing test**

```python
def test_compute_reliquary_joins_authored_verse_casefolded():
    party = {"members": [{"id": "vex", "name": "Vex", "kills": [
        {"date": "2026-04-19", "creature": "Goblin", "method": "Shortbow"},
    ]}]}
    authored_kills = [{"character": "vex", "date": "2026-04-19",
                       "creature": "goblin", "method": "shortbow",
                       "verse": "A verse.", "annotation": "an annotation"}]
    rows = render.compute_reliquary(party, authored_kills)
    assert rows["vex"][0]["verse"] == "A verse."
    assert rows["vex"][0]["date_label"] == "19 APR 2026"
```

- [ ] **Step 2: Verify failure** (no `compute_reliquary`).

- [ ] **Step 3: Implement** in `build/render.py` (near `compute_cr_label`):

```python
def compute_reliquary(party: dict, authored_kills: list) -> dict[str, list[dict]]:
    """Per-member, date-sorted kill rows with their authored verse joined in.
    Joining here (via kill_key's casefold) keeps templates free of key
    reconstruction — the template-side `| lower` rebuild diverged from
    casefold on non-ASCII names."""
    by_key = {
        kill_key(k["character"], k["date"], k["creature"], k["method"]): k
        for k in authored_kills
    }
    out: dict[str, list[dict]] = {}
    for m in party.get("members", []):
        rows = []
        for k in sorted(m.get("kills", []), key=lambda k: k["date"]):
            auth = by_key.get(kill_key(m["id"], k["date"], k["creature"], k["method"]), {})
            rows.append({
                "date": k["date"],
                "date_label": _short_date(k["date"]),
                "creature": k["creature"],
                "cr_label": compute_cr_label(k["creature"]),
                "verse": auth.get("verse", ""),
                "annotation": auth.get("annotation", ""),
            })
        out[m["id"]] = rows
    return out
```

In `compute_all`: add `"reliquary_by_id": compute_reliquary(party, authored["kills"]),` and delete the `kills_authored_by_key` entry.

Rewrite `_reliquary.html` body:

```jinja
{% from "_macros.html" import section_head -%}
      <section class="reliquary" id="{{ member.id }}-reliquary">
        {%- set char_auth = characters_authored[member.id] %}
        {{ section_head("iii", "The Fallen", "Reliquary", char_auth.reliquary_header) }}
        <ul class="fallen">
          {%- for row in reliquary_by_id[member.id] %}
          <li>
            <div class="mark">&#10013;</div>
            <div class="verse">
              {{ row.verse | safe }}
              <span class="what">{{ row.annotation | safe }}</span>
            </div>
            <div class="when">{{ row.date_label }} &middot; CR {{ row.cr_label | safe }}</div>
          </li>
          {%- endfor %}
        </ul>
      </section>
```

(The old `first_name` set was unused — drop it.)

- [ ] **Step 4: Run suite; re-render; `git diff site/index.html`** → must be empty.
- [ ] **Step 5: Commit** — `git commit -am "fix(render): join reliquary verses server-side, drop template key rebuild"`

---

### Task 10: Emit `data-value` on roll dots; delete the JS geometry inversion

Python already computes each dot's value; the JS re-derives it by inverting chart geometry (`Math.round(1 + (56 - cy) / 52 * (max - 1))`) after regexing the die's face count from label text — the most fragile coupling in the repo.

**Files:**
- Modify: `build/templates/_fortune.html` (line ~59), `build/templates/_script.html` (other-dice IIFE, ~lines 249–315)

- [ ] **Step 1: Template** — in `_fortune.html`'s dot loop add the attribute:

```jinja
<circle class="roll-dot" data-date="{{ d.date }}" data-value="{{ d.value }}" cx="{{ d.x }}" cy="{{ d.y }}" ...>
```

- [ ] **Step 2: JS** — in the other-dice IIFE:
  - Keep `dieStr` (still used for the aria-label) but delete the `const m = dieStr.match(/d(\d+)/); if (!m) return; const max = parseInt(m[1], 10);` lines and the comment about the regex.
  - Replace `const cy = ...; const value = Math.round(1 + (56 - cy) / 52 * (max - 1));` with `const value = parseInt(dot.getAttribute('data-value'), 10);`.
  - Delete the now-unused `cy` read if nothing else uses it.

- [ ] **Step 3: Re-render and verify** — `.venv/bin/python build/render.py`; `git diff site/index.html` shows only added `data-value` attributes and the script change. Load the preview (`python3 -m http.server 8765 --bind 127.0.0.1 --directory site`) and hover an Other Dice dot: tooltip number equals the dot's `data-value`.
- [ ] **Step 4: Run suite** → pass.
- [ ] **Step 5: Commit** — `git commit -am "fix(fortune): emit dot values as data-value, drop JS geometry inversion"` (include `site/index.html`).

---

### Task 11: Renderer dead-code sweep + validation gaps + small fixes

One task, many mechanical edits; each is independent and the render diff verifies them together.

**Files:**
- Modify: `build/render.py`, `build/templates/base.html`, `build/templates/_gm.html`
- Test: `tests/test_compute.py`, `tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validator.py
def test_validate_site_requires_footnote_gm_road_ahead():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": 0}
    errors = render.validate_site(site, latest_session=0)
    fields = {e.field for e in errors}
    assert {"footnote", "gm", "road_ahead"} <= fields

# tests/test_compute.py
def test_short_date_fixed_english_months():
    assert render._short_date("2026-04-23") == "23 APR 2026"
    assert render._short_date("2026-12-01") == "01 DEC 2026"
```

- [ ] **Step 2: Verify failure** (site-fields test fails).

- [ ] **Step 3: Implement** in `build/render.py`:

1. **REQUIRED_SITE_FIELDS**: `REQUIRED_SITE_FIELDS = ("intro_epithet", "page_title", "page_subtitle", "footnote", "gm", "road_ahead")`. `_missing_or_blank` treats a present dict as fine (it only flags None/blank-str/empty-list), so `gm`/`road_ahead` dicts pass. Update any `test_validator.py` fixtures that now fail by adding the three fields (the fixture `sample_authored/site.json` already carries all three).
2. **Traceback in main()**:
   ```python
       except Exception as e:
           import traceback
           traceback.print_exc()
           print(f"render.py: render failed: {type(e).__name__}: {e}", file=sys.stderr)
           return 2
   ```
3. **Delete `--strict`** (the two `parser.add_argument` lines for it) — it is parsed and never read.
4. **Delete the `intro_meta` pipeline**: remove `compute_intro_meta`, `_count_word`, `NUMBER_WORDS`, and the `site["intro_meta"] = compute_intro_meta(session_log)` line in `compute_all`. Keep `DEAD_SITE_FIELDS = ("intro_meta",)` (it guards the *authored* store). Delete the `test_compute_intro_meta_*` tests and the `compute_intro_meta` import in `tests/test_compute.py`. Grep first: `grep -rn "intro_meta\|_count_word\|NUMBER_WORDS" build/ tests/ --include="*.py" --include="*.html"` — templates must show no hits.
5. **Drop `dice_files` param**: `def compute_company_ledger(party, session_log, trials, fortune_by_char)`; update the `compute_all` call site (remove `data.get("dice_rolls", [])`) and any test calls in `tests/test_compute.py`.
6. **`_short_date` month table**:
   ```python
   _MONTHS_ABBR = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

   def _short_date(iso_date: str) -> str:
       """'2026-04-23' -> '23 APR 2026'. Fixed English table — strftime('%b')
       is locale-dependent."""
       from datetime import date
       d = date.fromisoformat(iso_date)
       return f"{d.day:02d} {_MONTHS_ABBR[d.month - 1]} {d.year}"
   ```
7. **Rename** the local `max_cr_for_method` in `compute_trials` to `max_xp_for_method` (it maps CRs through `XP_BY_CR` — it returns XP).
8. **`ValidationError` as dataclass**:
   ```python
   from dataclasses import dataclass

   @dataclass
   class ValidationError:
       kind: str
       kind_type: str
       key: tuple
       field: str | None = None

       def __str__(self) -> str:
           key_str = "(" + ", ".join(str(k) for k in self.key) + ")"
           if self.kind == KIND_MALFORMED:
               return f"{self.kind} {self.kind_type} {key_str} field={self.field}"
           return f"{self.kind} {self.kind_type} {key_str}"
   ```
9. **Stale comment fixes**: `compute_sessions_chart` docstring → `"""Per-character kill bars per session date, with tooltip-ready kill lists."""`; the `main()` message `"Create templates first (plan tasks 18-24)."` → `"skipping render (compute only)."`.

In `build/templates/base.html`: replace the stale script comment (lines ~91–93) with:

```jinja
  {# The inline <script> below is the page's only client-side logic (tab
     switcher + all tooltip/animation IIFEs). Removing it breaks the page
     silently — see CLAUDE.md gotchas. #}
```

In `build/templates/_gm.html` line 4: `{%- set gm_fortune = fortune.get("gm") %}`.

- [ ] **Step 4: Run suite; re-render; diff** — `site/index.html` must be unchanged (intro_meta was rendered nowhere; verify the grep in step 3.4 before trusting this).
- [ ] **Step 5: Commit** — `git commit -am "refactor(render): dead-code sweep, site-field validation, locale-safe dates"`

---

### Task 12: Turn on Jinja autoescape

With `autoescape=False`, all ~25 `| safe` filters are no-ops and any field containing `<`/`&` corrupts markup silently — including OBR inventory descriptions (third-party input). The `| safe` markers are already mostly correct; flip the switch and fix the stragglers.

**Files:**
- Modify: `build/render.py` (`render_page`), templates as the diff demands
- Test: render-diff driven

- [ ] **Step 1: Flip** — `autoescape=True` in `render_page`.

- [ ] **Step 2: Re-render and diff** — `.venv/bin/python build/render.py && git diff site/index.html`. Triage every hunk:
  - Intentional entities now double-escaped (e.g. `&middot;` inside a **Python-computed string** rendered without `| safe`): either mark the expression `| safe` when the value is build-computed and trusted (e.g. `{{ row.cr_label | safe }}` — already safe-marked after Task 9), or better, change the Python to emit the literal character (`·` instead of `&middot;`) — prefer the literal-character fix wherever the value is plain text.
  - Literal entities typed **directly in template text** (`&#10013;`, `&mdash;`, `&middot;` between tags) are untouched by autoescape — no action.
  - Known hotspots to check by hand: `_character.html` (`skill_str | replace("-", "&minus;") | safe` — keep), `_abilities.html` (`mod_display | safe` — keep), `_fortune.html` (`&sigma;`/format strings), `_company.html` bestiary marks, `header_eyebrow` lines (plain text — fine), `data-inscription="{{ inscription }}"` (autoescape now escapes quotes — **good**, that's the fix working).
  - Goal state: the rendered HTML is byte-identical except where escaping is genuinely more correct (e.g. a quote inside a data attribute). Every surviving hunk must be explainable in one sentence.

- [ ] **Step 3: Add a regression test** in `tests/test_compute.py` or a new `tests/test_render_env.py`:

```python
def test_render_env_autoescapes(tmp_path):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "base.html").write_text("<p data-x=\"{{ v }}\">{{ v }}</p>")
    out = tmp_path / "out.html"
    render.render_page({"v": '<img onerror=x>"'}, tdir, out)
    html = out.read_text()
    assert "<img onerror" not in html
    assert "&lt;img" in html
```

- [ ] **Step 4: Run suite; preview the site locally and click through all tabs** (tab switcher, chronicle, pack tooltips) to confirm nothing renders as visible escaped markup.
- [ ] **Step 5: Commit** — `git commit -am "fix(render): enable Jinja autoescape"` (include `site/index.html` and template edits).

---

## Phase 3 — Templates and client JS

### Task 13: Consolidate tooltips on one shared module (fixes cross-widget flicker) + escape tooltip HTML

Eight IIFEs re-implement find-or-create tooltip + private `hideTimer` + positioning. Private timers cause a real bug: widget A's pending hide dismisses widget B's fresh tooltip. Tooltip HTML is built by string concatenation from data attributes — OBR item descriptions (third-party input) reach `innerHTML` unescaped.

**Files:**
- Modify: `build/templates/_script.html` (top-to-bottom), `site/styles.css` (three new tip classes)

**Interfaces:**
- Produces (JS, module scope in `_script.html`): `Tip.show(anchor, html, opts?)` where `opts = {wide?: bool, gloss?: bool}`; `Tip.hide()`; `Tip.cancelHide()`; `Tip.esc(s)`; `Tip.el` (the singleton div).

- [ ] **Step 1: Add the shared module** at the very top of `_script.html`, before the tab-switcher IIFE:

```js
    // Shared tooltip singleton. One element, ONE hide timer — per-widget
    // timers let widget A's pending hide dismiss the tooltip widget B just
    // showed when the pointer moves quickly between widgets.
    const Tip = (() => {
      const HIDE_DELAY_MS = 80;
      const el = document.createElement('div');
      el.className = 'dice-tooltip';
      document.body.appendChild(el);
      let hideTimer;
      const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => (
        {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
      function show(anchor, html, opts) {
        opts = opts || {};
        clearTimeout(hideTimer);
        el.className = 'dice-tooltip'
          + (opts.wide ? ' tip-wide' : '')
          + (opts.gloss ? ' tip-gloss' : '');
        el.innerHTML = html;
        el.classList.add('visible');
        // Clamp horizontally so long content never runs off-viewport.
        const margin = 8;
        const half = el.offsetWidth / 2;
        const r = anchor.getBoundingClientRect();
        let cx = r.left + r.width / 2;
        cx = Math.max(half + margin, Math.min(window.innerWidth - half - margin, cx));
        el.style.left = cx + 'px';
        el.style.top = r.top + 'px';
      }
      function hide() {
        hideTimer = setTimeout(() => el.classList.remove('visible'), HIDE_DELAY_MS);
      }
      function cancelHide() { clearTimeout(hideTimer); }
      return { show, hide, cancelHide, esc, el };
    })();
```

- [ ] **Step 2: Migrate every consumer.** For each IIFE, delete its local tooltip find-or-create, its local `hideTimer`, and its positioning block; call `Tip.show(anchor, html, opts)` / `Tip.hide()` instead, and wrap **every interpolated data-attribute value** in `Tip.esc(...)`. Specifics:
  - **Chronicle pips** (~22–85): `show` body becomes html build (with `Tip.esc(creature)` etc.) + `Tip.show(el, html)`; `hide` → `Tip.hide()`. Keep the img-error → placeholder swap logic untouched.
  - **Constellation** (~87–134): same; anchor is `portrait`.
  - **Sessions chart** (~136–187): same; anchor `barEl || bar`; escape `k.creature`, `k.method`; `k.token_url` goes into a `src` attribute — escape it too.
  - **Histograms** (~189–247): same; keep the `matchingLabel.classList` add/remove in the show/hide callbacks.
  - **Other-dice** (~249–315): delete its `document.createElement` tooltip (this one leaked a duplicate element); keep the Voronoi hit-rect construction and focus/blur wiring; `show` keeps `dot.classList.add('active')` then `Tip.show(dot, html)`; `hide` does `dot.classList.remove('active'); Tip.hide()`. Delete the `CHART_LEFT/RIGHT/HEIGHT` comment drift only if unused — the Voronoi rects still need them; keep.
  - **Pack rack/spotlight/manifest + company strip + archetype** (~347–436, 520–531): replace `_packGetTip`/`_packShowTip` calls with `Tip.show(el, html, {wide: !!desc})`; on mouseleave use `Tip.hide()` (this also gains them the shared delay instead of instant hide — intended). Then **delete** `_packShowTip` and `_packGetTip`. Escape `name`, `desc`, `cat`, `rarity`, `count`, `weight`.
  - **Ascent** (~626–731): convert `var` → `const`/`let` throughout the IIFE. Replace tooltip usage with `Tip.show(h, html, {wide: true})` / `Tip.hide()`. Move the three inline `style="..."` fragments into classes — html becomes e.g. `'<div class="tip-ctx tip-title">' + Tip.esc(label) + '</div>'`, `'<div class="tip-ctx tip-note">' + Tip.esc(note) + '</div>'`, `'<div class="tip-ctx tip-total">Running total &middot; ' + total + ' XP</div>'`.
  - **Gloss** (~739–836): keep its separate open/toggle state machine but route rendering through the singleton: replace its private `tip` element with `Tip.el`, `show()` body calls `Tip.show(anchor, html, {gloss: true})` (drop the local `place`), `hide` → `Tip.hide()`, `close()` → `Tip.el.classList.remove('visible'); openEl = null;`, and every `clearTimeout(hideTimer)` → `Tip.cancelHide()`. GLOSS bodies are build-generated strings — no escaping needed, but escape nothing *out* (they contain no user input).

- [ ] **Step 3: Add the three classes to `site/styles.css`** (near the existing `.dice-tooltip` rules):

```css
.dice-tooltip .tip-title { color: var(--paper); font-size: 13px; text-transform: none; font-family: 'Cormorant Garamond', serif; }
.dice-tooltip .tip-note { text-transform: none; font-style: italic; font-family: 'EB Garamond', serif; font-size: 13px; max-width: 260px; white-space: normal; margin-top: 8px; }
.dice-tooltip .tip-total { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--rule); }
```

- [ ] **Step 4: Verify in the browser.** Re-render; serve; on each tab: hover chronicle pips, constellation stars, session bars, histogram columns, other-dice dots (mouse AND keyboard Tab/focus), pack items, company strip, archetype badge, ascent nodes, gloss terms (hover, focus, tap-toggle, Escape). Specifically verify the flicker fix: sweep quickly from a histogram column to a constellation star — the second tooltip must not vanish. Verify an item description containing `<b>test</b>` would render as text (temporarily add one via devtools `el.dataset.description = '<img src=x onerror=alert(1)>'` and hover — expect escaped text, no dialog).
- [ ] **Step 5: Run suite; commit** — `git commit -am "refactor(script): single tooltip module with shared hide timer and HTML escaping"` (include `site/index.html`, `site/styles.css`).

---

### Task 14: Template dedup — macros, shared maps, single-source formulas

**Files:**
- Modify: `build/templates/_macros.html`, `_chronicle.html`, `_company.html`, `_fortune.html`, `_proficiencies.html`, `_character.html`, `_abilities.html`, `_script.html`, `build/render.py`, `build/inventory.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Kill-pip macro.** In `_macros.html` add:

```jinja
{% macro kill_pips(pips) -%}
  {%- for k in pips %}
    {%- if k.token_url %}
  <img class="chronicle-session-pip" src="{{ k.token_url }}" alt="{{ k.creature }}"
       data-creature="{{ k.creature }}" data-killer-name="{{ k.killer_name }}"
       data-killer-image="{{ k.killer_image }}" data-method="{{ k.method }}"
       data-date="{{ k.date_label }}" loading="lazy">
    {%- else %}
  <span class="chronicle-session-pip pip-placeholder"
        data-creature="{{ k.creature }}" data-killer-name="{{ k.killer_name }}"
        data-killer-image="{{ k.killer_image }}" data-method="{{ k.method }}"
        data-date="{{ k.date_label }}" aria-label="{{ k.creature }}"></span>
    {%- endif %}
  {%- endfor %}
{%- endmacro %}
```

In `_chronicle.html`, `{% from "_macros.html" import kill_pips %}` and replace both duplicated blocks (chapter tally ~23–35, session pips ~55–67) with `{{ kill_pips(ch.kill_pips) }}` / `{{ kill_pips(s.kill_pips) }}`.

- [ ] **Step 2: d20 histogram macro.** In `_macros.html`:

```jinja
{% macro d20_histogram(bars) -%}
  {%- for bar in bars %}
  <div class="dice-col" data-val="{{ bar.value }}" data-count="{{ bar.count }}"><div class="dice-count{% if bar.zero %} zero{% endif %}">{% if bar.zero %}&middot;{% else %}{{ bar.count }}{% endif %}</div><div class="dice-bar{% if bar.zero %} zero{% endif %}"{% if not bar.zero %} style="height:{{ bar.height_pct }}%"{% endif %}></div></div>
  {%- endfor %}
{%- endmacro %}

{% macro d20_labels(bars) -%}
  {%- for bar in bars %}
  <span class="lbl{% if bar.value == 1 or bar.value == 20 %} nat{% endif %}" data-val="{{ bar.value }}">{{ bar.value }}</span>
  {%- endfor %}
{%- endmacro %}
```

Use both in `_fortune.html` (inside `.dice-hist` / `.dice-labels`) and `_company.html`'s patron-die section (inside `.patron-die-chart` / `.dice-labels`).

- [ ] **Step 3: SKILL_DISPLAY single-source.** In `compute_all`'s returned context add `"skill_display": SKILL_DISPLAY,`. In `_proficiencies.html` delete the 18-entry `skill_names` map and use `skill_display.get(key, key)`.

- [ ] **Step 4: Archetype labels from Python.** In `compute_all` add `"archetype_labels": {a["slug"]: a["label"] for a in inventory.ARCHETYPE_SLATE},` (the `inventory` import is already local there). In `_character.html` delete the 16-entry `arc_label_map` block and use `{{ archetype_labels.get(pack_rec.archetype, pack_rec.archetype | upper) }}`.

- [ ] **Step 5: Ability-mod filter.** In `render_page` register `env.filters["ability_mod"] = lambda score: (score - 10) // 2`. In `_abilities.html` replace `{%- set mod = (score - 10) // 2 %}` with `{%- set mod = score | ability_mod %}`.

- [ ] **Step 6: Encumbrance pct single-source.** In `build/inventory.py::_build_bundle`, add to **both** strip branches a pct: `"pct": 0` in the awaiting branch and `"pct": round(rec["total_weight"] / rec["capacity"] * 100) if rec["capacity"] else 0` in the ok branch. Test:

```python
def test_company_strip_carries_pct():
    parsed = {"vex": {"items": [{"id": "a", "name": "Rock", "count": 1,
                                 "weight": 30, "category": "Adventuring Gear",
                                 "rarity": "common", "description": ""}]}}
    party = {"members": [{"id": "vex", "name": "Vex",
                          "abilities": {"str": 10}}]}
    bundle = inventory._build_bundle(parsed, party)
    strip = {s["slug"]: s for s in bundle["company_strip"]}
    assert strip["vex"]["pct"] == 20   # 30 lb of 150 capacity
```

In `_company.html` replace `{%- set pct = (s.total_weight / s.capacity * 100) | round %}` with `{%- set pct = s.pct %}` and add `data-pct="{{ s.pct }}"` to `.company-strip-bar`. In `_script.html`'s company-strip handler replace the `Math.round(w / cap * 100)` recomputation with `const pct = parseInt(el.getAttribute('data-pct'), 10) || 0;`.

- [ ] **Step 7: Verify** — run suite; re-render; `git diff site/index.html` should show only the added `data-pct` attributes (macro output must be whitespace-equivalent; if Jinja whitespace shifts, adjust `{%-`/`-%}` trims in the macros until the diff is attribute-only).
- [ ] **Step 8: Commit** — `git commit -am "refactor(templates): macros for pips/histograms, single-source maps and formulas"`

---

### Task 15: Finish the ARIA tabs pattern

`base.html` declares `role="tablist"` with no tabs/panels/keyboard support — worse for screen readers than plain links.

**Files:**
- Modify: `build/templates/base.html`, `_company.html`, `_character.html`, `_gm.html`, `_script.html` (tab IIFE)

- [ ] **Step 1: Template roles.** In `base.html`, each tab anchor gains `role="tab"`, an id, and `aria-controls`:

```jinja
    <a href="#company" class="tab" data-tab="company" role="tab" id="tab-company" aria-controls="company">
    ...
    <a href="#{{ member.id }}" class="tab" data-tab="{{ member.id }}" role="tab" id="tab-{{ member.id }}" aria-controls="{{ member.id }}"><img ...>{{ member.id | title }}</a>
    ...
    <a href="#gm" class="tab" data-tab="gm" role="tab" id="tab-gm" aria-controls="gm"><img ...>GM</a>
```

Panels: add `role="tabpanel" aria-labelledby="tab-company"` to `_company.html`'s `<article class="character" id="company">`, `role="tabpanel" aria-labelledby="tab-{{ member.id }}"` to `_character.html`'s article, `role="tabpanel" aria-labelledby="tab-gm"` to `_gm.html`'s article.

- [ ] **Step 2: JS.** Extend the tab-switcher IIFE's `activate`:

```js
      function activate(id) {
        if (!valid.has(id)) id = valid.has(landingId) ? landingId : defaultId;
        tabs.forEach(t => {
          const active = t.dataset.tab === id;
          t.classList.toggle('active', active);
          t.setAttribute('aria-selected', active ? 'true' : 'false');
          t.setAttribute('tabindex', active ? '0' : '-1');
        });
        panels.forEach(p => p.classList.toggle('active', p.id === id));
      }
```

And add roving arrow-key navigation after the initial `activate(...)` call:

```js
      const tabList = document.querySelector('.tabs');
      tabList.addEventListener('keydown', (e) => {
        const order = [...tabs];
        const i = order.indexOf(document.activeElement);
        if (i === -1) return;
        let j = null;
        if (e.key === 'ArrowRight') j = (i + 1) % order.length;
        else if (e.key === 'ArrowLeft') j = (i - 1 + order.length) % order.length;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = order.length - 1;
        if (j === null) return;
        e.preventDefault();
        order[j].focus();
        location.hash = order[j].dataset.tab;   // selection follows focus
      });
```

- [ ] **Step 3: Verify** — re-render, preview: click tabs, Tab to the tablist, arrow between tabs (panel follows), Home/End work, `aria-selected` toggles in devtools.
- [ ] **Step 4: Run suite; commit** — `git commit -am "feat(tabs): complete ARIA tabs pattern with keyboard navigation"`

---

## Phase 4 — Tests, CI, hygiene

### Task 16: Test-suite improvements (dice-player tests, registry pairing, shared fixture, assertion fixes)

**Files:**
- Modify: `tests/conftest.py`, `tests/test_loaders.py`, `tests/test_registry.py`, `tests/test_prepare.py`, `tests/test_slices.py`, `tests/test_apply_cli.py`, `tests/test_inventory.py`, `tests/test_compute.py`

- [ ] **Step 1: `_resolve_dice_player` tests** (the privacy mechanism; currently untested) in `tests/test_loaders.py`:

```python
def test_resolve_dice_player_substring_hit():
    assert render._resolve_dice_player("Zebulon Marlowe", {"Zebulon": "vex"}) == "vex"

def test_resolve_dice_player_longest_pattern_first():
    mapping = {"Z": "wrong", "Zebulon": "vex"}
    assert render._resolve_dice_player("Zebulon Marlowe", mapping) == "vex"

def test_resolve_dice_player_no_match_returns_none():
    assert render._resolve_dice_player("Nobody Special", {"Quinn": "vex"}) is None

def test_resolve_dice_player_ignores_empty_pattern():
    assert render._resolve_dice_player("Anyone", {"": "oops"}) is None
```

- [ ] **Step 2: Registry ↔ prompt pairing test** in `tests/test_registry.py`:

```python
def test_every_transformer_has_prompt_and_schema():
    from build.paths import PROMPTS_DIR
    for t in registry.ALL:
        assert (PROMPTS_DIR / f"{t.name}.md").exists(), t.name
        assert (PROMPTS_DIR / f"{t.name}.schema.json").exists(), t.name
```

- [ ] **Step 3: Shared staging fixture.** In `tests/conftest.py` add:

```python
import shutil

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def staged_env(tmp_path, monkeypatch):
    """Materialize fixture data + authored store + run root under tmp_path
    and point the BUILD_* env vars at them. Returns tmp_path."""
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
```

Rewrite `slice_env` (test_slices.py), `run_env` (test_prepare.py), and `staged_run`/`staged_refresh_run` (test_apply_cli.py) as thin wrappers over `staged_env` (each keeps its current return shape so their tests don't change).

- [ ] **Step 4: Small fixes** — `test_prepare.py` model assertion → `assert models <= {"sonnet", "opus"}`; delete `tests/test_inventory.py::test_module_exposes_load`; rename `_consteltation_inputs` → `_constellation_inputs` in `tests/test_compute.py` (and its call sites).

- [ ] **Step 5: Run full suite** → pass. **Commit** — `git commit -am "test: cover dice-player resolution and registry pairing, share staging fixture"`

---

### Task 17: Render smoke test (fixtures → compute_all → render_page) with privacy assertion

Nothing between "context computed" and "HTML deployed" is verified. `StrictUndefined` makes template/context drift a runtime crash caught only during a real build.

**Files:**
- Create: `tests/test_render_page.py`
- Modify: `tests/fixtures/sample_authored/*.json` and fixture data only as far as the smoke test demands

- [ ] **Step 1: Write the test**

```python
"""End-to-end render smoke test: fixture data through compute_all and
render_page. Any template/context drift under StrictUndefined fails here
instead of during a real build."""
import re
import subprocess
from pathlib import Path

from build import render, store

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "build" / "templates"


def _forbidden_names_regex() -> str:
    out = subprocess.run(
        ["bash", str(REPO_ROOT / ".githooks" / "_forbidden-names.sh")],
        capture_output=True, text=True, check=True)
    return out.stdout.strip().replace("[[:space:]]", r"\s")


def test_render_page_smoke(staged_env):
    data = render.load_data(staged_env / "data")
    authored = store.load_authored()
    context = render.compute_all(data, authored)
    out = staged_env / "index.html"
    render.render_page(context, TEMPLATES, out)
    html = out.read_text()
    assert len(html) > 10_000
    assert authored["site"]["page_title"] in html
    assert 'class="tab"' in html                       # tab nav rendered
    assert 'id="company"' in html                      # company panel rendered
    assert "</html>" in html


def test_rendered_html_contains_no_forbidden_names(staged_env):
    data = render.load_data(staged_env / "data")
    authored = store.load_authored()
    context = render.compute_all(data, authored)
    out = staged_env / "index.html"
    render.render_page(context, TEMPLATES, out)
    assert not re.search(_forbidden_names_regex(), out.read_text())
```

- [ ] **Step 2: Run and fix fixtures until green.** Expected friction, handle in order:
  - `compute_all` calls `inventory.load(REPO_ROOT, party=party)` which reads `data_dir()/inventory` — `staged_env` sets `BUILD_DATA_DIR`, so it resolves inside tmp_path and returns the empty bundle. Fine.
  - `StrictUndefined` failures name the missing context/site key — extend `tests/fixtures/sample_authored/*.json` (or fixture party/session data) with the minimal field. Likely candidates: `characters.json` entries missing `sworn_creed`/`archetype_badge` guards (templates use `.get`-style access via `characters_authored[...]` — a missing subkey referenced directly, e.g. `sworn_creed`, only triggers when `member.subclass` exists in fixture party; check `sample_party.json`), `xp-log.json` absent → `compute_ascent` returns None → `_ascent.html` must have a None branch (it does per its empty-state design; if it doesn't, add the fixture xp-log instead).
  - Bestiary lookups: `.claude/ext/5etools-src` may be present locally; the smoke test must not require it. If `compute_bestiary`/`bestiary_lookup` raises on a missing symlink, mark the test with the same skip guard used by `tests/test_bestiary.py:8` (read that file and copy its skipif).
- [ ] **Step 3: Full suite** → pass. **Commit** — `git commit -am "test: add render smoke test with forbidden-name assertion on output HTML"`

---

### Task 18: Rename the guard-violating fixture name

The synthetic full name at `tests/test_inventory.py:35`/`:54` and `tests/fixtures/inventory/obr-inv-backup-2026-05-02T04-21-16-825Z.json:5` (first name `Simon`, surname `Weil`) matches the forbidden-names regex exactly; every edit to those lines forces `--no-verify`, normalizing guard bypasses. (This plan deliberately never writes the two words adjacently — the hooks scan this file too.)

**Files:**
- Modify: `tests/test_inventory.py`, `tests/fixtures/inventory/obr-inv-backup-2026-05-02T04-21-16-825Z.json`

- [ ] **Step 1:** In both files, replace the first name `Simon` with `Simeon` wherever it appears paired with the surname `Weil`, and change the test's mapping key `"Simon"` → `"Simeon"` (`Simeon` does not contain `Simon` as a substring, and `\bSimon\b` cannot match inside `Simeon` — verify: `echo "Simeon Weil" | grep -E "$(bash .githooks/_forbidden-names.sh)"` prints nothing). Check for other fixture references: `grep -rn "Simon" tests/` must afterwards show only `tests/test_loaders.py:86` (`"player": "Simon"` — a bare first name, allowed by design).
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_inventory.py -v` → pass.
- [ ] **Step 3:** Commit **without** `--no-verify` (this is the point): `git add tests && git commit -m "test: rename fixture surname out of the forbidden-names alternation"` — the hook passing proves the fix.

---

### Task 19: Privacy-guard hardening — hooksPath check + regex surname class

A fresh clone is silently unguarded (`core.hooksPath` is per-clone opt-in), and the surname class `[a-zA-Z'-]` misses non-ASCII surnames.

**Files:**
- Modify: `tests/conftest.py`, `build/prepare.py`, `.githooks/_forbidden-names.sh`

- [ ] **Step 1: conftest warning** — append to `tests/conftest.py`:

```python
import subprocess
import warnings


def pytest_sessionstart(session):
    """The forbidden-names hooks only run when core.hooksPath is set — a
    fresh clone is silently unguarded. Warn loudly rather than fail."""
    repo = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath"],
            capture_output=True, text=True)
        hooks_path = out.stdout.strip()
    except OSError:
        return
    if hooks_path != ".githooks":
        warnings.warn(
            "core.hooksPath is not '.githooks' — the forbidden-name guard "
            "is INACTIVE in this clone. Run: git config core.hooksPath .githooks",
            stacklevel=1)
```

- [ ] **Step 2: prepare warning** — in `build/prepare.py::run`, at the top:

```python
    _warn_if_hooks_inactive()
```

and add:

```python
import subprocess
import sys


def _warn_if_hooks_inactive() -> None:
    """A fresh clone has no core.hooksPath; the forbidden-name guard is off."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "config", "core.hooksPath"],
            capture_output=True, text=True)
    except OSError:
        return
    if out.stdout.strip() != ".githooks":
        print("prepare: WARNING — core.hooksPath is not '.githooks'; the "
              "forbidden-name commit guard is inactive. Run: "
              "git config core.hooksPath .githooks", file=sys.stderr)
```

- [ ] **Step 3: Regex surname class** — in `.githooks/_forbidden-names.sh`, change the echoed pattern to accept accented surnames and document the known limits:

```bash
# Known limits (accepted): all-lowercase "simon weil" passes (case-insensitive
# matching floods false positives on bare first names in prose); reversed
# "Weil, Simon" passes; the rendered-HTML test in tests/test_render_page.py is
# the backstop on the published artifact.
echo "\\b(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z][[:alpha:]'-]+\\b"
```

Verify: `echo "Simon M""üller" | grep -E "$(bash .githooks/_forbidden-names.sh)"` matches (shell string concatenation keeps the full-name-shaped literal out of this file, which the hooks also scan); `echo "Simon " | grep -E ...` does not.

- [ ] **Step 4: Run suite** (warning must not fire in this clone — hooksPath IS set) → pass. **Commit** — `git commit -am "chore(privacy): warn when hooks inactive, widen surname class"`

---

### Task 20: CI test gate, pinned requirements, repo cleanup

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `.github/workflows/deploy-pages.yml`, `requirements.txt`, `.gitignore`, `docs/superpowers/plans/2026-04-25-subagent-dispatch-architecture.md`
- Ops: remove stale worktree, prune merged branches, delete stale run dirs

- [ ] **Step 1: Pin requirements** — `requirements.txt` becomes exact pins matching the venv: run `.venv/bin/pip freeze | grep -iE "^(jinja2|jsonschema|pytest|markupsafe|attrs|referencing|rpds|jsonschema-spec|pluggy|iniconfig|packaging)=="` and write the jinja2/jsonschema/pytest lines (with `==`) into `requirements.txt`; keep it to direct deps only (`jinja2==<ver>`, `jsonschema==<ver>`, `pytest==<ver>`).

- [ ] **Step 2: `.github/workflows/ci.yml`**:

```yaml
name: Tests

on:
  push:
    branches: ['**']
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

Note: `data/` is gitignored so tests that need it must already self-provision via fixtures (they do — the suite passes without `data/`; verify locally with `BUILD_DATA_DIR=/nonexistent .venv/bin/pytest tests/ -q` — if any test reads real `data/`, fix it to use fixtures before enabling CI). The bestiary tests self-skip without the 5etools symlink.

- [ ] **Step 3: Gate deploy** — in `deploy-pages.yml`, add before the `deploy` job:

```yaml
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -q
```

and add `needs: test` to the `deploy` job.

- [ ] **Step 4: Repo cleanup** (ops, not commits — except .gitignore):
  - `git worktree remove .worktrees/subagent-dispatch --force` (it holds untracked copies of real player data from the old layout — removing it is the point; the live copies in `data/` are unaffected), then `git branch -D feat/subagent-dispatch`.
  - Prune merged branches: `git branch --merged main | grep -vE '^\*|main' | xargs -r git branch -d`.
  - Delete stale run dirs: `rm -rf build/.run/*` (all are applied historical runs; Task 6 prevents future accumulation).
  - `.gitignore`: remove the duplicate of `.venv`/`.venv/` (keep `.venv/`).
- [ ] **Step 5: Mark superseded plan** — prepend to `docs/superpowers/plans/2026-04-25-subagent-dispatch-architecture.md` (line 1): `> **SUPERSEDED** by `2026-05-17-in-session-build-prose.md` — the subagent-dispatch architecture described here was replaced by the in-session /build-prose flow. Kept for history.` and the matching note at the top of `docs/superpowers/specs/2026-04-25-subagent-dispatch-architecture-design.md`.
- [ ] **Step 6: Commit** — `git add .github requirements.txt .gitignore docs && git commit -m "ci: gate deploys on the test suite; pin deps; mark superseded docs"`

---

## Phase 5 — The big split

### Task 21: Split render.py into loaders / validators / bestiary / compute

1,840 lines, five responsibilities, and a circular-import workaround (`render.py:1675`) that exists because `inventory.py` needs a *loader* out of render. Pure code motion — no behavior change; `git diff site/index.html` after re-render must be empty.

**Files:**
- Create: `build/loaders.py`, `build/validators.py`, `build/bestiary.py`, `build/compute.py`
- Modify: `build/render.py` (becomes CLI + Jinja layer + re-export shim), `build/inventory.py`, `build/slices.py`, `build/prepare.py`, `CLAUDE.md`
- Tests: unchanged (the shim keeps `build.render.X` importable) — that is the acceptance criterion.

**Interfaces:**
- `build/loaders.py`: `load_data`, `load_authored`, `load_character_pronouns`, `load_dice_player_map` (public rename of `_load_dice_player_map`), `resolve_dice_player` (public rename of `_resolve_dice_player`), `_mdy_to_iso`, `_has_chapter_marker`, `DICE_PLAYER_MAP_PATH`, `CHARACTER_PRONOUNS_PATH`, plus module-path constants it needs.
- `build/validators.py`: `ValidationError`, `KIND_*`, `kill_key`, every `validate_*`, `collect_npcs_from_log`, `REQUIRED_*`/`DEAD_SITE_FIELDS`/`_LIST_EMPTY_OK`/`_missing_or_blank`.
- `build/bestiary.py`: `BESTIARY_GLOB`, `_BESTIARY_SOURCE_PRIORITY`, `TOKEN_URL_BASE`, `_name_to_token_name`, `bestiary_lookup` and its helpers, `CUSTOM_CREATURE_TOKENS`, `XP_BY_CR`, `_kill_xp`, `_kill_cr` (move whatever lives in the 250–387 block plus the XP/CR tables it owns — read the block and take its full closure).
- `build/compute.py`: every `compute_*`, `_short_date`, `_to_roman`, `_count_word`-family survivors, radar/ascent constants, `SKILL_DISPLAY`, `_PROF_RANK`, `LEVEL_XP`, `_level_for_xp`, `_next_threshold`, `FORGOTTEN_REALMS_MONTHS`, `_render_session`, `_split_npcs`, `_compute_*` helpers, `compute_all`, `compute_reliquary`, `compute_cr_label`.
- `build/render.py` keeps: shebang + docstring + exit codes, `BUILD_DIR`/`REPO_ROOT`, `render_page`, `main`, and a re-export block.

- [ ] **Step 1: Baseline** — `.venv/bin/pytest tests/ -q` green; `.venv/bin/python build/render.py` green; `git diff site/index.html` empty.

- [ ] **Step 2: Move code.** Create the four modules with the exact allocations above (cut-paste, preserving comments/docstrings). Import direction (no cycles): `validators` ← nothing internal; `bestiary` ← nothing internal; `loaders` ← nothing internal (it owns the dice-player map); `compute` imports from `validators` (kill_key), `bestiary`, `loaders` (for `_short_date`? no — `_short_date` lives in compute), and does `from . import inventory` **at module top** (the cycle is dissolved: `inventory` now imports from `loaders`, not `render`); `render` imports from all four. Notes:
  - `compute_all`'s local `from build import inventory` becomes a top-level `from . import inventory` in `compute.py` — verify no cycle: `inventory` imports `loaders` + `paths` only.
  - `inventory.py`: `from build.render import _load_dice_player_map, _resolve_dice_player` → `from .loaders import load_dice_player_map, resolve_dice_player` (and update the two call sites).
  - `validators.py` needs `_kill_xp`-adjacent nothing; `validate_all` calls `compute_*` — **decision:** `validate_all` moves to `compute.py`? No — keep `validate_all` in `validators.py` and pass the fact-pack computation in: it already accepts `fact_pack=None` and recomputes. To avoid a validators→compute import, move ONLY `validate_all` into `render.py` itself (it is orchestration: it wires validators to computes). Also fix the double-compute the review flagged: `main()` computes the fact pack once and passes it to both `validate_all` and later reuses via `compute_all` — minimal version: in `main()`, build `fact_pack` via the same block `validate_all` used internally, call `validate_all(..., fact_pack=fact_pack)`. (`compute_all` recomputing trials/fortune internally is acceptable; do not restructure `compute_all` in this task.)
  - `loaders.load_data` calls `_resolve_dice_player`/`_load_dice_player_map` (same module now) and raises the Task-1 ordinal ValueError.
- [ ] **Step 3: Shim.** At the bottom of `build/render.py`:

```python
# Re-exports: the public surface predates the loaders/validators/bestiary/
# compute split; tests and slices.py import through build.render.
from .bestiary import (CUSTOM_CREATURE_TOKENS, XP_BY_CR, bestiary_lookup,  # noqa: F401,E402
                       _kill_cr, _kill_xp)
from .compute import (SKILL_DISPLAY, compute_all, compute_ascent,  # noqa: F401,E402
                      compute_best_skill, compute_bestiary, compute_chronicle,
                      compute_company_ledger, compute_constellation,
                      compute_cr_label, compute_d20_histogram,
                      compute_distinctions, compute_fact_pack, compute_fortune,
                      compute_other_dice, compute_party_d20_max,
                      compute_patron_die, compute_radar, compute_reliquary,
                      compute_sessions_chart, compute_trials, _short_date,
                      _to_roman)
from .loaders import (load_authored, load_character_pronouns, load_data,  # noqa: F401,E402
                      load_dice_player_map, resolve_dice_player,
                      _has_chapter_marker, _mdy_to_iso)
from .validators import (KIND_MALFORMED, KIND_MISSING, KIND_ORPHAN,  # noqa: F401,E402
                         ValidationError, collect_npcs_from_log, kill_key,
                         validate_chapters, validate_characters,
                         validate_dice_player_mapping,
                         validate_distinction_basis,
                         validate_distinction_uniqueness, validate_kills,
                         validate_npcs, validate_portraits, validate_sessions,
                         validate_site)

# Back-compat aliases for the pre-split private names.
_load_dice_player_map = load_dice_player_map
_resolve_dice_player = resolve_dice_player
```

Then run the suite; every remaining `ImportError`/`AttributeError` names a symbol to add to the shim or a helper that landed in the wrong module — chase them until green. Grep the *actual* import surface first instead of trusting the list above: `grep -rhn "from build.render import\|from build import render\|render\.\w\+" tests/ build/slices.py build/prepare.py build/apply.py | grep -oE "render\.\w+|import .*" | sort -u`.

- [ ] **Step 4: Verify** — full suite green; `.venv/bin/python build/render.py` exit 0; `git diff site/index.html` **empty**; `.venv/bin/python -m build prepare --no-refresh` runs (then delete the created run dir).
- [ ] **Step 5: Update CLAUDE.md** — in the `build/` bullet list, describe the new modules: `build/loaders.py` (data/authored/pronoun/dice-map loading + privacy scrub), `build/validators.py` (ValidationError + all validate_*), `build/bestiary.py` (5etools lookup, XP/CR tables), `build/compute.py` (all compute_* + compute_all), `build/render.py` (CLI, Jinja env, validate_all wiring, re-export shim). Remove the sentence about `render.py` resolving bestiary paths if it moved to `bestiary.py` (keep the env-var and BUILD_DIR notes accurate).
- [ ] **Step 6: Commit** — `git commit -am "refactor(build): split render.py into loaders/validators/bestiary/compute"`

---

## Consciously skipped (from the review)

- `/build-prose` SKILL.md "first stdout line" parsing — the single-line-stdout contract is documented in `__main__.py`'s docstring and stable; changing the protocol churns skill + CLI for marginal robustness.
- Case-insensitive forbidden-name regex — floods false positives on bare first names in prose; the rendered-HTML privacy test (Task 17) is the meaningful backstop.
- `paths.run_dir` mkdir-in-getter and second-granularity run-id collisions — single-operator CLI; collision requires two prepares in the same wall-clock second.
- Renaming `refreshed_through_session` in the persisted store — churn across authored data, validators, and docs; Task 1's load-time invariant makes the semantics safe instead.

## Self-review notes

- Spec coverage: every "worth doing" + "nitpick" item from the three review reports maps to a task above or to the skipped list.
- Type consistency: `Tip.show(anchor, html, {wide, gloss})` used consistently in Task 13; `_new_entries(data, authored)` consistent between Tasks 1; `staged_env` fixture name consistent between Tasks 16, 17.
- Ordering hazards: Task 2 must precede Task 3 (guards raise against the trial copy); Task 9 must precede Task 21 (`compute_reliquary` listed in the shim); Task 16's `staged_env` must precede Task 17 (smoke test uses it). Execute in numerical order.
