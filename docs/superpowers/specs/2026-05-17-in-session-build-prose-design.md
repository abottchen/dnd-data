# In-session build prose — replacing `claude -p` with a skill

**Date:** 2026-05-17
**Status:** design (pre-implementation)

## Summary

Move per-slice prose authoring out of `claude -p` subprocesses and into the
current Claude Code session, driven by a new skill. The deterministic Python
that surrounds authoring — loading `data/`, computing slices, applying
returns, validating, rendering — stays put. The orchestrator splits into a
`prepare` step (front half) and an `apply` step (back half) with a new skill
sitting between them as the loop driver.

The build moves from one command (`python -m build`) to a three-step flow:
`python -m build prepare` writes pending slice files to a run directory, the
`/build-prose` skill walks that directory and writes results, then `python
-m build apply` validates the results, applies them to
`build/authored/*.json`, and runs `render.py`.

The main motivation is **interactive authoring**. When a returned epithet
reads wrong or a chapter title is off, the current loop requires
`--keep-temp`, deleting the bad entry from `authored/*.json`, and re-running
the whole pipeline. With the work staged on disk between deterministic steps,
the user can intervene at any point: edit a slice, edit a prompt, re-queue
one file, rerun the skill.

## What stays unchanged

- `data/` ingestion (`render.load_data`).
- Slice builders in `build/slices.py`.
- Authored store I/O (`build/store.py`) and apply functions (`build/apply.py`).
- Schemas under `.claude/prompts/<name>.schema.json`.
- Prompt bodies under `.claude/prompts/<name>.md` (frontmatter + body).
- `build/render.py`, including its validation gate on `MISSING` / `MALFORMED`.
- `build/inventory.py`, `build/paths.py`, `build/dice-players.json`,
  `build/character-pronouns.json`.
- Marker semantics (`site.refreshed_through_session`) and discovery /
  append / refresh-pass ordering.
- Existing CLI flags carry over to `prepare`: `--no-refresh`,
  `--force-refresh`, `--keep-temp`. `--concurrency` is dropped (see
  "Concurrency" below). `--skip-render` moves to `apply`.

## What changes

### 1. `build/__main__.py` splits into two subcommands

```
python -m build prepare [--no-refresh] [--force-refresh] [--keep-temp]
python -m build apply <run-dir> [--skip-render]
```

The bare `python -m build` form is retained as a convenience that runs
`prepare`, prints the skill invocation to use, and exits. (It does **not**
chain into `apply` — that requires a Claude Code session.)

`prepare` does everything the current `__main__.py` does up to the point
where it would dispatch transformers. Instead of calling `call_transformer`
in a thread pool, it writes each slice to disk under a per-run directory and
exits.

`apply` does everything the current `__main__.py` does after the transformer
pool drains — reads returned prose, calls `apply.apply_*`, persists the
authored store, bumps the marker on full refresh-pass success, runs
`build/render.py`, prints the end-of-run report.

### 2. Per-run directory layout

`prepare` creates `build/.run/<ISO-timestamp>/` (replacing the current
`temp_dir()` location; the directory becomes a first-class build artifact,
not a debug scratchpad).

```
build/.run/2026-05-17T14-32-08/
  manifest.json
  pending/
    append-kills__2026-04-30.json
    append-npcs__lady-melaine.json
    refresh-chapters__3.json
    refresh-road-ahead__all.json
    ...
  done/        (empty initially; skill moves pending files here)
  results/     (empty initially; skill writes JSON results here)
  prompts/     (frozen copy of .claude/prompts/<name>.{md,schema.json}
                for every transformer in the manifest)
```

**File naming**: `<transformer>__<key>.json` where `<key>` is the slice's
identifying key as today (date for kills, session id for sessions, NPC name
slug, chapter id, `"all"` for whole-category slices). Slashes and unsafe
characters are sanitized with `re.sub(r"[^A-Za-z0-9_.-]+", "-", key)`.

**`manifest.json`** is a single file listing every queued slice, in
submission order, with the model from prompt frontmatter and the dependency
of the result file on its slice:

```json
{
  "run_id": "2026-05-17T14-32-08",
  "marker": 8,
  "latest": 9,
  "force_refresh": false,
  "slices": [
    {
      "transformer": "append-kills",
      "key": "2026-04-30",
      "model": "sonnet",
      "pending": "pending/append-kills__2026-04-30.json",
      "result": "results/append-kills__2026-04-30.json",
      "prompt_body": "prompts/append-kills.md",
      "schema": "prompts/append-kills.schema.json"
    },
    ...
  ]
}
```

The frozen `prompts/` snapshot is taken at `prepare` time so a mid-run prompt
edit cannot silently change interpretation between two batches of the same
build.

### 3. The `build-prose` skill (new)

Lives under `.claude/skills/build-prose/SKILL.md`. The skill body is short;
the heavy lifting is procedural rather than analytical.

**Trigger phrases** (skill description): "build prose", "drive a build run",
"author a build", `/build-prose`.

**Inputs**: a path to a run directory created by `python -m build prepare`.
If the user invokes `/build-prose` without a path, the skill picks the
alphabetically maximal subdirectory of `build/.run/`.

**Procedure**:

1. Read `manifest.json`. List slices still in `pending/`.
2. For each pending slice, dispatch a sub-agent (Task tool) with:
   - `subagent_type: "general-purpose"`,
   - the matching frozen prompt body as the agent's task description,
   - the slice JSON inlined into the prompt,
   - the schema inlined into the prompt with an explicit "output JSON only,
     conforming to this schema" instruction,
   - the model override from the manifest entry.
3. The sub-agent writes its JSON output to `results/<stem>.json`. The driver
   skill does **not** parse or rewrite the result — it only checks that the
   file exists and is valid JSON, then moves the pending file into `done/`.
4. If a slice fails (sub-agent returns no result, or the result file is not
   valid JSON), log the failure to a `failures.json` in the run dir and
   leave the pending file in place for a retry.
5. After all pending slices have been processed once, print a summary and
   suggest the apply command. The user runs `apply` manually rather than the
   skill invoking it — keeps the audit boundary clean.

**What the skill does not do**:
- Touch `build/authored/*.json` directly.
- Edit prompts or schemas.
- Run `render.py`.
- Decide which slices need authoring (that's `prepare`'s job).

### 4. `build/apply.py` gains a CLI shim

The existing per-transformer `apply_*` functions stay as-is. A new
`build/apply_cli.py` (or a `python -m build apply` dispatch in `__main__.py`)
reads `manifest.json` from the run directory, then for each entry:

1. Loads `results/<stem>.json`.
2. Validates against the snapshotted schema using `jsonschema`. Any failure
   is logged to `apply-errors.json`, the result file is moved to
   `results/rejected/`, and the slice is reported as still pending.
3. On success, calls the matching `apply.apply_<transformer>(authored,
   key, slice_data, output)` with `slice_data` re-read from `done/<stem>.json`.
4. Persists `build/authored/*.json` after each pass completes (same as
   today).
5. Bumps the marker on full refresh-pass success.
6. Runs `build/render.py` (unless `--skip-render`).

Apply is **idempotent on the manifest**: re-running `python -m build apply
<dir>` after a partial failure picks up only the results that have appeared
since last run. This makes the "fix one slice and re-author" loop short.

### 5. Cleanup semantics

- `--keep-temp` (on `prepare`) preserves the run dir on success.
- Default: run dir is preserved through `apply`. On a clean `apply` with no
  rejected results, `apply` deletes the run dir as its final step (after
  render succeeds). `--keep-temp` propagates via a sentinel file
  (`.keep` in the run dir) written by `prepare`.
- On any failure (skill, schema validation, render), the run dir stays put
  for inspection.

## Concurrency

Today's `--concurrency 5` translates to "five concurrent `claude -p`
subprocesses". The new model is "N concurrent Task-tool sub-agents", which
is heavier per call (full session bootstrap, more tokens) but still
parallelizable.

The skill dispatches sub-agents in **batches of up to 5 at a time**, sent
in a single message with multiple Task tool uses (per the system prompt's
guidance on parallel tool calls). Sequencing between batches is the skill's
responsibility. Typical builds are 5–15 slices, so most builds finish in one
or two batches.

If this proves too token-heavy in practice, the fallback is fully sequential
authoring, which is still acceptable for the build frequency (a handful of
runs per week).

## Schema validation

Today: `claude -p --json-schema` validates inside the harness. A null
`structured_output` is the failure signal.

New: the sub-agent has no harness-level schema enforcement. Validation moves
to `apply`, using `jsonschema` against the snapshotted schema file. Rejected
results land in `results/rejected/<stem>.json` with a sibling
`<stem>.error.json` describing the validation failure. The user (or the
skill, on a retry pass) can re-dispatch that one slice.

The skill itself does a light pre-check (valid JSON, non-empty) before
moving the pending file to `done/`. Anything more would duplicate logic
that's better centralized in `apply`.

## Error and retry flow

A typical "something went wrong" scenario:

```
$ python -m build prepare
build/.run/2026-05-17T14-32-08/ created with 7 slices
$ # in Claude Code:
$ /build-prose build/.run/2026-05-17T14-32-08/
[6 slices succeed, 1 fails — refresh-npcs__shea-baker returned malformed JSON]
$ python -m build apply build/.run/2026-05-17T14-32-08/
6 results applied; 1 still pending (refresh-npcs__shea-baker)
render.py: BLOCKED (1 MISSING entry in authored/npcs.json)
$ # user edits the prompt or the slice, then:
$ /build-prose build/.run/2026-05-17T14-32-08/
[the one remaining pending slice gets authored]
$ python -m build apply build/.run/2026-05-17T14-32-08/
all 7 applied; render OK; run dir removed
```

The render step is gated by validation as today; nothing renders until every
slice has a clean result.

## Things the in-session model loses

- **`--max-budget-usd 1.00` per call**: there's no per-call budget for Task
  sub-agents. The whole session shares one budget. Practical impact: small,
  since most slices are short and we run a handful per build.
- **Strict tool denylist**: today `claude -p` runs with `--disallowedTools`
  covering Bash/Read/Write/etc. Sub-agents inherit a broader toolset. The
  skill body explicitly instructs sub-agents not to exercise tools beyond
  the one Write of `results/<stem>.json`, but this is a soft guarantee, not
  a harness-enforced one. Acceptable because the run dir and the
  authored-store boundary mean a misbehaving sub-agent can damage at most
  its own result file.
- **`--permission-mode plan`**: same caveat as above. The skill instructs
  sub-agents not to attempt anything that would prompt.

## Things the in-session model gains

- **Interactive intervention**: pause between `prepare` and `apply`; inspect
  any slice or result; edit prompts mid-build; re-run the skill on the same
  run dir to fill in just what's missing.
- **No subprocess bootstrap cost**: each `claude -p` call today incurs CLI
  startup and a fresh model context per slice. Sub-agents skip the CLI
  layer, though they still bootstrap a session.
- **One place to audit**: the run dir contains the manifest, slices,
  results, frozen prompts, and the failure log for one build. Today this
  state is split between the temp dir (slices) and `authored/*.json`
  (applied results) with no manifest binding them.

## Out of scope

- **Eliminating prompts entirely.** The `.claude/prompts/` directory stays
  the source of truth. The skill loads them; it does not inline them or
  rewrite them.
- **Replacing slice builders with conversation.** The deterministic
  set-difference logic in `build/slices.py` is the right shape; nothing
  about that needs to be re-thought.
- **Render-side changes.** `build/render.py` is unchanged.
- **CI integration.** The deploy workflow uploads `site/` and does not run
  the build; this design does not change that.
- **A long-running watcher.** No daemon, no file watcher. `prepare`,
  skill, `apply` is the full surface.

## File and code changes

New files:
- `.claude/skills/build-prose/SKILL.md` — skill definition.
- `build/prepare.py` — slice gathering + run-dir population. Most logic is
  lifted from current `__main__.py`'s pass-running, minus the
  `call_transformer` dispatch.
- `build/apply_cli.py` — manifest-driven apply + render entry point.
- `docs/superpowers/specs/2026-05-17-in-session-build-prose-design.md` —
  this document.

Modified files:
- `build/__main__.py` — gains subcommand dispatch (`prepare`, `apply`); the
  no-arg form delegates to `prepare` and prints next-step guidance.
- `build/paths.py` — `temp_dir()` becomes `run_dir(run_id)`, anchored at
  `build/.run/`. The env-var override (`BUILD_TEMP_DIR`) stays for tests.
- `.gitignore` — add `build/.run/`.

Removed files:
- `build/invoke.py` — no more `claude -p` subprocess.
- `build/build_loop.py` — `run_render()` moves into `apply_cli.py` (or
  stays as a one-function module if cleaner).

`build/slices.py`, `build/apply.py`, `build/store.py`, `build/inventory.py`,
`build/render.py` — unchanged.

## Testing

The existing test suite covers slice builders, validators, key matching,
computation, and bestiary lookup — all unchanged.

New tests:
- `tests/test_prepare.py` — `prepare` writes the expected manifest and
  pending file set for a fixture data dir and authored store. Schema and
  prompt-body snapshots end up in the run dir.
- `tests/test_apply.py` — `apply` correctly validates good results, rejects
  malformed ones into `results/rejected/`, applies surviving results to a
  fixture authored store, and is idempotent on re-run.

The skill itself is not unit-tested; it's exercised end-to-end by running a
real build.

## Migration

The change can land in one PR. There is no compatibility layer because the
build is a single-user tool and the run-dir format is internal. Existing
`build/authored/*.json` files keep working — they are the same shape; only
the *path that produces them* changes.

Order of operations for the implementer:

1. Land `prepare.py` and the run-dir layout. Keep `invoke.py` and the
   current `__main__.py` flow as a fallback (`python -m build legacy`).
2. Land the skill and verify it can fill a real run dir.
3. Land `apply_cli.py` and switch `python -m build apply` over.
4. Once one full real build has succeeded end-to-end, remove the legacy
   fallback (`invoke.py`, `build_loop.py`, old `__main__.py` flow).

## Open questions deferred to implementation

- Whether the skill should print per-slice token cost as it goes (currently
  `claude -p` returns this; sub-agents may or may not surface it cleanly).
- Whether `apply` should refuse to run if any prompt file under
  `.claude/prompts/` has been modified since `prepare` (the snapshot under
  `<run-dir>/prompts/` is the source of truth, but a divergence is worth
  flagging).
- Exact failure-log schema (`failures.json`, `apply-errors.json`) —
  decided at implementation time; keep it simple and human-readable.
