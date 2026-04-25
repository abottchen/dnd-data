# Subagent dispatch architecture for hydrate-ledger — design

**Date:** 2026-04-25
**Branch:** TBD

## Problem

The `hydrate-ledger` skill currently loads upstream files (`session-log.json`, `party.json`, `dicex-rolls-*.json`) plus the full `authored/*.json` store into its main context, then authors prose for both the append pass (new entities) and the refresh pass (evolvable entries). Two costs scale with campaign length:

1. **Refresh pass.** Re-evaluating every NPC epithet, chapter epigraph, character bundle, road-ahead entry, and the intro epithet requires reading session-log narrative slices that grow as more sessions land.
2. **Append pass.** Authoring a new kill verse, session summary, or NPC epithet also reads the relevant session narrative — same scaling concern.

As the campaign grows, the skill spends more tokens loading data than authoring prose, and risks running out of useful context. The architecture below cuts the orchestrator's context footprint to roughly constant, regardless of campaign length, by moving slice extraction to deterministic helpers and prose authoring to focused subagents.

## Architectural contract (preserved)

- **`templates/`** — frozen.
- **`build.py`** — does all the math; reads computed inputs and `authored/*.json`, writes `index.html`. Unchanged by this design.
- **`authored/*.json`** — the prose store; the only thing the skill writes.
- **Spoiler rules, voice rules, scrubbing, authorial restraint** — unchanged. These propagate into every dispatch prompt.

The change is entirely inside the `hydrate-ledger` skill: a new helper module, a dispatch layer, and a slimmed-down orchestrator workflow. No template or `build.py` changes.

## Architecture

Three layers with one-way data flow:

```
upstream files ──► helpers.py ──► temp/<category>_<key>.json
                                           │
authored/*.json ─────────► orchestrator (skill) ─► Agent dispatch (parallel) ─► JSON decisions
                                           │                                            │
                                           └──── apply rewrites ◄───────────────────────┘
                                                      │
                                                      └─► build.py ─► index.html
```

- **Orchestrator (the skill).** Reads `authored/*.json` and minimal upstream metadata for diffing; never reads narrative. Calls helpers, dispatches subagents in parallel, validates returned JSON, writes authored files, runs `build.py`, iterates on validation errors.
- **Slice helpers** (`.claude/skills/hydrate-ledger/helpers.py`). Single python module exposing CLI subcommands. Imports loader functions from `build.py` so loader logic isn't duplicated. Writes one slice JSON file per entity to a per-run temp dir; prints a small metadata array to stdout.
- **Dispatch subagents.** Spawned via the Agent tool, one per dispatch unit. Receive the slice file path, the `voice-samples.md` path, the existing entry (inline, small), and the dispatch prompt template. Return one JSON decision object.

### Core invariant

**The orchestrator never reads slice contents.** Helpers write slice bodies to disk; their stdout returns only `{path, count, key}` metadata. The skill forwards `path` into the dispatch prompt and never opens the slice file itself. The subagent is the only consumer of slice bytes.

This is the rule that makes the architecture worth doing. If the orchestrator ever ingests slice contents, its context grows with the slice and we're back to the original problem. The same applies to `voice-samples.md` — its path is forwarded into prompts; the orchestrator never reads it.

### Temp directory lifecycle

- Created per skill run via `tempfile.mkdtemp(prefix="hydrate-")`.
- Cleaned on full success (all dispatches succeed, all writes succeed, `build.py` exits zero).
- Preserved on any failure path so the user can inspect what each agent saw.
- Path always echoed in the end-of-run report.

## Slice helper contract

### Stdout schema (uniform across all subcommands)

```json
{"slices": [
  {"key": "<entity-key>", "path": "<temp file>", "count": <int>}
]}
```

- **`key`** — entity identifier (NPC name, chapter id, character slug, session roman, or a sentinel like `"all"` / `"singleton"`).
- **`path`** — absolute path to the slice JSON file.
- **`count`** — gating metric: `0` means no relevant data and the orchestrator skips dispatch. For categories where gating is meaningless (always-dispatch singletons), helpers return `count = 1`.

The orchestrator iterates `slices`, drops `count == 0`, dispatches one agent per remaining entry.

### Parameter rule

**Helpers take no parameters.** Each subcommand introspects all state it needs from upstream files (`session-log.json`, `party.json`, `dicex-rolls-*.json`) and authored files (`authored/*.json`, including `site.refreshed_through_session` for `--since` semantics).

The orchestrator invokes the subcommand verbatim. It does not compute session counts, look up keys, or pre-read upstream data to derive arguments. The helper is the single source of truth for "what entities are in scope this run."

### Responsibility split

- **Helper writes** the slice body for each entity to `<temp_dir>/<category>_<key>.json`.
- **Helper prints** the metadata array to stdout (small, fixed-size).
- **Skill reads** stdout. Skill does **not** read any slice file.
- **Skill forwards** the relevant `path` value into the agent dispatch prompt.
- **Subagent reads** the slice file (and `voice-samples.md`). Sole consumer of slice bytes.

Helpers never write to `authored/*.json`. The orchestrator owns all writes to the authored store, only after validating each subagent's returned JSON.

### Subcommands

| Subcommand | Pass | Slices returned |
|---|---|---|
| `append-kills` | append | one per session that has new kills |
| `append-sessions` | append | one per session log entry not in authored |
| `append-chapters` | append | one per detected chapter marker not in authored |
| `append-npcs` | append | one per NPC in `collect_npcs_from_log` not in authored |
| `append-characters` | append | one bundled entry covering all PCs in `party.json` not in authored (mirrors `refresh-characters`); zero entries if none |
| `refresh-chapters` | refresh | one per chapter; `count` = sessions inside chapter that postdate the marker |
| `refresh-npcs` | refresh | one per NPC mentioned in any session; `count` = mentions postdating the marker |
| `refresh-characters` | refresh | one entry, the all-PC bundle (always-dispatch when refresh runs) |
| `refresh-road-ahead` | refresh | one entry covering `known` + `was_known` + `direction` |
| `refresh-intro-epithet` | refresh | one entry |

### Slice contents (per category)

The subagent must receive enough context to make its decision and nothing more. Per-category slice contents:

- **`append-kills`**: the session log entry, the kills (`character`, `creature`, `method`, `date`) in that session.
- **`append-sessions`**: the session log entry (real + in-universe dates, narrative text, chapter marker if any).
- **`append-chapters`**: the marker session and 1–2 surrounding sessions for context.
- **`append-npcs`**: every session log line naming each new NPC, that NPC's `allegiance` (computed by helper if derivable from log; otherwise leave for agent / user).
- **`append-characters`**: for each unauthored PC: kills (creature, method, CR), fortune stats (rolls, kept d20s, avg, σ, crits, fumbles, heaviest); plus the party-wide rankings on each axis and the currently-authored `distinction_title` values (so the agent picks non-colliding titles for the new PCs).
- **`refresh-chapters`**: every session inside the chapter, the existing `title` + `epigraph`.
- **`refresh-npcs`**: every session log line naming the NPC across all sessions, the existing `epithet`.
- **`refresh-characters`**: every PC's kills + fortune + party rankings, the existing 5-field bundle for each PC.
- **`refresh-road-ahead`**: full narrative of newly-landed sessions (since marker), the entire current `road_ahead` block.
- **`refresh-intro-epithet`**: campaign-spine summary (newly-landed sessions + current `road_ahead.known` list), the existing `intro_epithet`.

## Dispatch contract

### Templates

One Jinja-flavored prompt template per category at `.claude/skills/hydrate-ledger/dispatch/<category>.md`. Placeholders `{slice_path}`, `{voice_samples_path}`, `{existing}`. Orchestrator does simple string substitution, then passes the resolved string to the Agent tool's `prompt`.

### Standing rules baked into every template

- **"Read only `<slice_path>` and `<voice_samples_path>`. Do not explore other files."**
- **"Return only the JSON object. No prose, no markdown fence."**
- **"If unsure whether the log supports a specific detail, prefer the existing prose over invention."** (Carries the existing authorial-restraint rule into agent context.)

### Return schema

**Refresh:**

```json
{
  "decision": "no_change" | "rewrite",
  "fields": { ... } | null,
  "reason": "one short sentence"
}
```

- `fields` is `null` when `decision == "no_change"`, otherwise contains the new field values.
- For `refresh-road-ahead`, `fields` contains the full new state of `known`, `was_known`, and `direction` (one decision covers the whole block). The orchestrator detects **graduations** post-hoc by diffing key sets between old and new `known` arrays — entries that disappeared from `known` but appear in `was_known` are graduations and surface in the end-of-run report.

**Append:**

```json
{
  "fields": { ... },
  "reason": "one short sentence"
}
```

Append always produces fresh prose; no `decision` discriminator.

### Worked example (refresh-npcs, no-change)

Input slice file (orchestrator never reads this; shown for completeness):

```json
{
  "name": "Azlund",
  "mentions": [
    {"session": "III", "line": "Azlund the merchant offered to broker the sale of the captured chests."}
  ],
  "existing_epithet": "the merchant who brokers what others would not"
}
```

Existing entry passed inline to template: `"the merchant who brokers what others would not"`.

Expected return:

```json
{
  "decision": "no_change",
  "fields": null,
  "reason": "no new mentions; existing line still fits the data"
}
```

### Worked example (append-kills, single new kill)

Input slice (orchestrator never reads):

```json
{
  "session_iu_date": "5 Kythorn 1494 DR",
  "session_real_date": "2026-04-23",
  "kills": [
    {"character": "anton", "creature": "Goblin", "method": "Vicious Mockery"}
  ],
  "narrative_excerpt": "Anton's whispered insult curdled the goblin's nerve; it slumped without a wound."
}
```

Expected return:

```json
{
  "fields": {
    "anton__2026-04-23__Goblin__Vicious Mockery": {
      "verse": "A goblin, undone by a halfling's whispered scorn.",
      "annotation": "Vicious Mockery — the only kill drawn with words alone."
    }
  },
  "reason": "single new kill, voice held"
}
```

(The orchestrator owns the key shape and translates `fields` into the array entry written to `authored/kills.json`.)

## Append pass orchestration

1. For each `append-*` subcommand, invoke the helper.
2. Read the metadata array from stdout.
3. Drop entries with `count == 0` (none expected for append, but the contract is uniform).
4. For each remaining entry: load the dispatch template, substitute `{slice_path}` / `{voice_samples_path}` / `{existing}` (`existing` is empty for append).
5. Issue all dispatches in a single multi-Agent message (parallel).
6. Validate returns; retry-once-on-malformed-JSON (see Error handling).
7. Apply `fields` to the appropriate `authored/*.json` file.

Batching is implicit in the helper output: `append-kills` emits one slice per session-with-new-kills, so a session with five new kills is one agent dispatch handling all five (no cross-kill constraint to violate). Same for `append-npcs` per session.

## Refresh pass orchestration

Trigger unchanged: refresh runs only when `latest_session > site.refreshed_through_session`. If equal, skip the entire refresh pass.

1. For each `refresh-*` subcommand, invoke the helper.
2. Read the metadata array from stdout.
3. Drop entries with `count == 0` (no-op refreshes).
4. For each remaining entry: load the dispatch template, substitute placeholders.
5. Issue all dispatches across all categories in a single multi-Agent message (parallel).
6. Validate returns; retry-once-on-malformed-JSON.
7. Apply decisions to authored files: `no_change` → skip; `rewrite` → swap fields. For `refresh-road-ahead`, the orchestrator writes the agent's new `known` / `was_known` / `direction` state and then computes graduations (keys removed from `known`, added to `was_known`) for the end-of-run report.
8. **Only on full success:** bump `site.refreshed_through_session = latest_session`. Partial failure leaves the marker untouched so the next run retries.

### Special cases

- **Character bundle.** `refresh-characters` returns one slice covering all PCs because `distinction_title` must be unique party-wide (validator enforces). One agent decides all characters atomically.
- **Road-ahead.** `refresh-road-ahead` returns one slice covering `known`, `was_known`, and `direction` together. Graduation logic spans entries within `known`, so a single agent maintains coherence.

## End-of-run report

The skill prints, in order:

1. **Append additions** (per category, by entity key).
2. **Refresh decisions** (per category, by entity key, with `reason`).
3. **Graduations** (`road_ahead.known` → `was_known`).
4. **Marker state** (old → new value of `site.refreshed_through_session`, or unchanged with reason).
5. **Temp directory path** (whether cleaned or preserved).

`reason` strings come straight from the agents' return objects.

## Error handling

| Failure | Response |
|---|---|
| Helper exits non-zero or stdout is not valid JSON | Surface, abort. Helpers are deterministic — investigate before retry. |
| Subagent returns malformed JSON | Retry once with corrective re-prompt: *"Your last response was not valid JSON. Return only the JSON object — no prose, no markdown fence."* Second failure → surface temp file path and raw response so the user can author manually. |
| Subagent returns valid JSON that fails schema (wrong fields, invalid `decision`) | Same as malformed: retry once with corrective re-prompt naming the schema violation. |
| `build.py` reports `MISSING <type> <key>` or `MALFORMED <type> <key> field=<f>` | Existing iteration loop (max 3). Each error triggers a single targeted dispatch (one agent for the offending entity) — no full re-run. |
| Partial refresh-pass failure (some agents succeeded, some failed after retry) | Apply the agents that succeeded. Do **not** bump `site.refreshed_through_session`. Surface the failed entries with temp paths. |
| Helper produces empty `slices` array | Treat as "nothing to do" for that category. Not an error. |

Temp directory cleanup is gated on **full success**: every dispatch succeeded, every authored write succeeded, `build.py` exited zero.

## Voice consistency

`voice-samples.md` is shared across all dispatches. Every template includes its path; every agent reads it as part of its slice load. Voice anchoring is unchanged from the existing skill — only the loading mechanism shifts (path-forward instead of inline).

## Scrubbing

Real-name scrubbing rules are unchanged. The mapping in `dice-players.json` and the skill-level Scrubbing section in `SKILL.md` continue to enforce no real names in `authored/*.json` or rendered HTML.

**New surfaces to audit:**

- **Helper output (slice files).** Slices may quote upstream narrative directly. The helpers must apply the same scrubbing rules as the skill before writing the slice file. A leaked name in a temp file isn't rendered, but it ends up in agent context, and an agent that quotes from its slice could write a scrubbed name through to authored prose.
- **Dispatch prompts.** Existing entries are inlined into prompts; these are already in `authored/*.json` and have been scrubbed.
- **Agent outputs.** Validators in `build.py` already check final authored files. The scrubber should also run on `fields` in returned JSON before writing to authored, as a belt-and-braces check.

## Testing posture

Helper test files live in `tests/test_helpers.py` (versioned). They `import` from `.claude/skills/hydrate-ledger/helpers.py` with a graceful skip if the path is absent (so clones without the skill — CI, GitHub Pages, drive-by readers — don't error out).

- **Versioned**: `tests/test_helpers.py`, `tests/fixtures/` (small synthetic upstream files with no PII).
- **Skill-local manual harness**: `.claude/skills/hydrate-ledger/test_harness.sh` runs each subcommand against current real upstream data, prints `count` and slice file size per entry. Used when modifying helpers; not part of the pytest suite.

Dispatch templates are tested manually: the spec includes one worked input/output pair per category (above), and the user can replay any dispatch by reading the agent's preserved temp slice on a failed run.

End-to-end verification stays the existing path: run `build.py`, preview `index.html` via the local HTTP server.

## Out of scope

- Modifications to `templates/`, `build.py` rendering, or page layout.
- Changes to spoiler rules, authorial-restraint rules, or voice samples.
- Persistent storage backends (Postgres, SQLite, etc.) — explicitly considered and rejected during brainstorming as overengineering.
- Caching of slice files across skill runs — slices are per-run only; the marker handles "what's new."
- A general-purpose plugin / extension system for adding new evolvable categories — categories are added by the spec author writing a new helper subcommand + dispatch template.

## Migration

The existing `SKILL.md` workflow becomes:

1. Read `authored/*.json` and `site.refreshed_through_session`.
2. Append pass: invoke each `append-*` helper (sequential, cheap), collect all slice metadata, then dispatch all append subagents in a single parallel batch and apply returns.
3. Refresh pass: if `latest_session > site.refreshed_through_session`, invoke each `refresh-*` helper, then dispatch all refresh subagents in a single parallel batch, apply returns, bump marker on full success.
4. Run `build.py`.
5. On validation errors: targeted single-dispatch per error, max 3 iterations.
6. End-of-run report.

`SKILL.md` is rewritten to describe this orchestration. The data-context tables for evolvable entries are removed (the helpers carry that knowledge now). Voice rules, spoiler rules, authorial restraint, and scrubbing rules stay in `SKILL.md` because every dispatch template references them.

## Open questions deferred to implementation

- Exact prompt wording per template — drafted during implementation, validated by running each on current data and inspecting the agent's response.
- `key` shape for `append-kills` slice (the kill tuple `character__date__creature__method` is one option; an integer index per session is another). Decided when writing the orchestrator.
- Whether `append-npcs` should attempt to derive `allegiance` deterministically (some session log lines tag this; others don't). Resolved during helper implementation; if uncertain, the helper omits the field and the agent / user fills it.
