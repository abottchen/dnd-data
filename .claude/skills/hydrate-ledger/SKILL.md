---
name: hydrate-ledger
description: Add new prose entries to the dnd-data site's authored store and run build.py. Invoke whenever upstream data files change (party.json, dicex-rolls-*.json, session-log.json), when new sessions / kills / NPCs / chapters appear and need verse / summary / epithet / title authored, when build.py reports MISSING or MALFORMED errors, or when the user asks to "hydrate", "rebuild", "update the site", "refresh the data". The skill does NOT modify templates or build.py — only authored/*.json files.
---

# Hydrate Ledger

Author new prose into `authored/*.json` and run `build.py`. The build is the deterministic renderer; this skill's only writable surface is the authored store.

## Architecture (read this first)

`build.py` is the authoritative contract:
- Reads `party.json`, `dicex-rolls-*.json`, `session-log.json` (upstream, gitignored, read-only).
- Computes every number on the page (trials, fortune, constellation, bestiary, chronicle, etc.).
- Loads `authored/*.json` for prose.
- Validates: every kill, session, chapter, NPC, character, and site singleton must have an authored entry. Missing → `MISSING <type> <key>`.
- Renders `templates/*.html` (Jinja2) into `index.html`.

The page structure (HTML/CSS), every formula, the histogram math, the SVG layout, the scrubbing of upstream real names — all of that lives in `build.py` and `templates/`. You do not modify those. Your job: write prose entries that satisfy `build.py`'s schema and pass its validation.

## Workflow

### Standing rules

1. **The orchestrator never reads slice files.** Inspect helper stdout (the `{path, count, key}` metadata) and dispatch returns only. Slice files are written by helpers and consumed by dispatched subagents — that's it.
2. **Helpers are deterministic — no retries.** A non-zero exit or invalid stdout means investigate the data, not retry.
3. **The temp directory is cleaned only on full success.** Any failure preserves the temp dir so the user can inspect what each agent saw.

The skill is an orchestrator. It does not load narrative data. Slice helpers
introspect upstream + authored state; dispatch subagents author prose.

1. **Read authored state.** Read `authored/*.json` and the marker
   `site.refreshed_through_session`.
2. **Append pass — gather slices.** Invoke each `append-*` helper in turn:
   ```bash
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-kills
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-sessions
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-chapters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-npcs
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-characters
   ```
   For each, parse the stdout `{"slices": [...]}` and collect entries with
   `count > 0`. **Do not read the slice files.**
3. **Append pass — dispatch.** Issue all collected append dispatches in a
   single Agent-tool message (parallel). For each dispatch, the prompt is
   the matching `dispatch/<category>.md` template with `{slice_path}`,
   `{voice_samples_path}`, and (for append) `{existing}` (empty string)
   substituted. Voice samples path is
   `.claude/skills/hydrate-ledger/voice-samples.md`.
4. **Append pass — apply.** For each returned JSON object, validate against
   the append schema (`fields` present, `reason` present). Append entries to
   the appropriate `authored/*.json` file. For `append-chapters` (which
   returns candidates), surface candidates to the user and apply their
   selection.
5. **Refresh pass — trigger check.** Compute `latest_session = len(session_log.entries)`.
   If `latest_session == site.refreshed_through_session`, skip the refresh pass.
6. **Refresh pass — gather slices.** Invoke each `refresh-*` helper:
   ```bash
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-chapters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-npcs
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-characters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-road-ahead
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-intro-epithet
   ```
   Drop `count == 0` entries.
7. **Refresh pass — dispatch.** Issue all remaining refresh dispatches in a
   single parallel Agent-tool message. Templates use the refresh return schema
   (`decision: "no_change" | "rewrite"`).
8. **Refresh pass — apply.** For each return:
   - `no_change` → skip.
   - `rewrite` → swap fields in the appropriate authored file.
   For `refresh-road-ahead`, write the new `known` / `was_known` / `direction`
   state and compute graduations (keys removed from `known`, added to
   `was_known`) for the report.
9. **Bump marker on full refresh success.** If every refresh dispatch
   succeeded (after retries), set `site.refreshed_through_session = latest_session`.
   Partial failure → leave marker untouched.
10. **Build.** Run `.venv/bin/python build.py`. On `MISSING <type> <key>` or
    `MALFORMED <type> <key> field=<f>`: targeted single-dispatch for the
    offending entity (max 3 iterations).
11. **Report.** Print the end-of-run report (see below).

### Bundle templates

Several dispatch templates return `fields` as a dict-of-entities rather than a
single entry — one dispatch yields multiple authored writes:

- **`append-kills`**: `fields` keys are `<character>__<date>__<creature>__<method>` tuples; each value is a `{verse, annotation}` pair. Iterate keys; parse each into a kill row and append to `authored/kills.json`.
- **`append-characters`**: `fields` keys are character ids; each value is the 6-field bundle. Iterate keys; append each as a row to `authored/characters.json`.
- **`refresh-characters`**: `fields` keys are character ids; each value is the 5-field rewrite. Iterate keys; for each, find the matching row in `authored/characters.json` and overwrite the 5 evolvable fields (preserving `reliquary_header` which is locked).

For non-bundle templates (`append-sessions`, `append-chapters`, `append-npcs`, `refresh-chapters`, `refresh-npcs`, `refresh-road-ahead`, `refresh-intro-epithet`), `fields` is a single object representing one entity.

## Authored store schema

(All schemas mirror `build.py`'s validators. JSON, one file per content type.)

### `authored/kills.json`
Array. Key: `(character, date, creature, method)` tuple, case-insensitive on creature/method.
```json
{ "character": "anton", "date": "2026-04-23",
  "creature": "Goblin", "method": "Vicious Mockery",
  "verse": "...", "annotation": "..." }
```

### `authored/sessions.json`
```json
{ "session": "V", "date": "2026-04-19",
  "title": "...", "summary": "...",
  "silent_roll": ["...", "..."], "chapter_id": 1 }
```
`silent_roll` may be `[]` for sessions with no off-Chronicle beat. `chapter_id` is optional.

### `authored/chapters.json`
```json
{ "id": 2, "starts_at_session": "VII",
  "title": "...", "epigraph": "..." }
```
A new chapter opens when an upstream session log entry contains a marker like `--- Chapter II ---` or `Chapter II begins.`. Propose 2-3 candidate titles + epigraphs to the user and let them pick.

### `authored/npcs.json`
```json
{ "name": "Azlund", "allegiance": "with", "epithet": "..." }
```
`allegiance` is `"with"` or `"against"`.

### `authored/characters.json`
```json
{ "id": "anton",
  "epithet": "of the Halflings, whose tongue cuts sharper than his blade",
  "reliquary_header": "Fallen by his tongue",
  "constellation_epithet": "his rolls yet unwritten",
  "distinction_title": "Sharpest Tongue",
  "distinction_subtitle": "the only kill drawn with words alone",
  "distinction_detail": "<b>1</b> kill &middot; Vicious Mockery" }
```
`epithet` is the prose oneliner shown beneath the character's name in the page header (e.g. "of the Wulven, sworn to the hunt"). Voice: kenning-style, evocative of race/lineage and signature trait. `distinction_title` must be unique across the party (validator enforces).

### `authored/site.json`
Singleton object: `intro_epithet`, `page_title`, `page_subtitle`, `road_ahead.{known, was_known, direction}`, `gm.{name, epithet, meta}`, `known_npcs`, `footnote`, `refreshed_through_session`.

`refreshed_through_session` is the integer marker driving the refresh pass (see below). Validator requires `0 <= value <= latest_session`. The skill bumps it after every successful refresh pass.

## Refresh pass

The refresh pass evaluates evolvable entries against newly-landed data.
Trigger: `latest_session > site.refreshed_through_session`. Categories,
slice contents, and dispatch templates are defined in `helpers.py` and
`dispatch/refresh-*.md`. See spec
`docs/superpowers/specs/2026-04-25-subagent-dispatch-architecture-design.md`
for the full contract.

## Spoiler rules (highest priority)

The site is for the players. DM-only content must NOT appear on the rendered page. Apply at write time.

### Markers in the session log indicating DM-only content
- `(DM Note)` prefix → skip the entire line.
- Bracketed notes `[like this]` → DM-only.
- Future-tense planning from the DM's perspective → DM-only.
- Parentheses `(like this)` — strong indicator, not hard rule:
  Apply this test: *could the players in their seats have learned this content from the in-fiction events of the session?*
  - Yes → render freely.
  - No → DM-only; omit.

When in doubt, omit and ask the user. **A leaked name cannot be unlearned. A missing flourish can be added next session.**

### Aliases and concealed identities
If an NPC has been introduced under an alias, the rendered page uses the alias. When the players learn the true name in-fiction, propose the rename to the user; until then the true name stays out.

## Error handling

| Failure | Response |
|---|---|
| Helper exits non-zero or stdout is not valid JSON | Surface, abort the run. Helpers are deterministic — investigate before retrying. |
| Subagent returns malformed JSON | Re-dispatch once with a corrective re-prompt: *"Your last response was not valid JSON. Return only the JSON object — no prose, no markdown fence."* Second failure → surface the temp file path and the raw response so the user can author the entry manually. |
| Subagent returns valid JSON that fails the schema (wrong fields, invalid `decision`) | Same as malformed: re-dispatch once with a corrective re-prompt naming the schema violation. |
| `build.py` reports `MISSING <type> <key>` or `MALFORMED <type> <key> field=<f>` | Targeted single-dispatch for the offending entity. Max 3 iterations of build → fix → rebuild. |
| Partial refresh-pass failure (some agents succeeded, some failed after retry) | Apply the agents that succeeded. **Do not bump** `site.refreshed_through_session`. Surface failures with temp-file paths. |
| Helper produces an empty `slices` array | Treat as "nothing to do" for that category. Not an error. |

The temp directory is cleaned only on **full success**: every dispatch succeeded,
every authored write succeeded, `build.py` exited zero. On any failure, the
temp dir is preserved and its path printed in the report so the user can inspect
exactly what each agent saw.

## Voice rules

### Yes
- Single sentence, concrete, evocative, third person — no "you" or "I".
- Stakes, place, or method hinted at.
- Annotation names the method and adds one beat.
- Unique lines. Repetition across kills dilutes the ledger.

### No
- "Ye Olde", "Chronicles of", "Tome of", "Behold" — any faux-archaic chrome.
- Second-person or meta-commentary ("the player rolled well").
- Verse longer than ~12 words; annotation longer than ~14 words.
- Generic filler ("was killed", "fell in battle"). Fall back to `A {creature}, felled by {method}.` over limp prose.

### Campaign-spine voice tier
For named entities that are the SPINE of the story (Soulmonger, Death Curse, Ring of Winter), the prose names what the entity DOES — places it, names what it threatens, names what it hoards. Not catalog-voice.

### Tone reference
Saga fragment, gravestone epitaph, the one-line caption under a reliquary in a medieval chapel. Cool, compact, slightly elegiac.

## Authorial restraint (do not invent specifics)

The session log narrates the *outcome* of events more often than their mechanics. When authoring an epithet, verse, summary, or annotation, you may write evocatively about what the log *does* state — but **do not invent specifics the log does not contain**. The site is a campaign record. A flourish that contradicts what actually happened at the table is a worse failure than a line that's a bit plain.

What you may safely elaborate from log context:
- The **abstract action** — attacked, fled, betrayed, threatened, fell.
- The **outcome** — the company endured, no kill claimed, the reckoning unfinished.
- The **setting**, if named — on the rooftops, in the bilge, at the docks.
- The **general character** of the figure — treacherous, swift to flee, oath-bound.

What you may NOT invent if the log doesn't say it:
- The **specific implement or weapon** — blade, bow, fang, spell, club.
- The **specific manner of attack** — ambush, charge, shove, whisper, flame.
- **Which character** an action targeted, or **which character** dealt the blow, beyond what the log states.
- **What was said**, **what was thought**, or **what was intended** by an NPC.

Worked example (failure mode to avoid):

> A yuan-ti attacked the company by pushing a water barrel off a roof onto Urida.
> The session log recorded only that the yuan-ti attacked from above and then fled.

A previous authoring pass produced the epithet *"whose blade nearly took Urida, and who fled before the reckoning"*. The "blade" and "nearly took Urida" specifics were invented; the actual attack was a falling barrel, and the log named neither weapon nor target. Acceptable epithets that respect the log:

- *"who struck from the rooftops and fled before the reckoning"*
- *"who attacked from above, then slipped the company's grasp"*
- *"the rooftop assailant, gone before the answering blow"*

When uncertain whether a detail is in the log, **omit the detail and ask the user** — same posture as spoiler rules. A vague-but-true epithet can be sharpened later when the player gets new in-fiction knowledge; a fabricated specific has to be retracted.

## Voice anchoring

Always load `voice-samples.md` in this skill's directory before authoring. Match its register; do not drift.

## Scrubbing

Real names from upstream data files must NOT appear on the rendered page or in `authored/*.json`. The character slug is derived from the first word of `name`, lowercased (handled by `build.py`'s `load_data`). Schematically: `<id> (id) / <first name> (player) / <character name> (name) → slug`. The mapping is data-driven from `party.json`; the skill never hardcodes player or character names.

Dice-roll player names map to slugs via `dice-players.json` in this directory. Keys are first-name or handle substrings (never full real names) — `build.py:_resolve_dice_player` does longest-pattern-first substring lookup, so an upstream full name like `"Simon ___"` resolves through a key of `"Simon"` without the file ever recording the last name. Add a new entry whenever a new player appears in the dice rolls.

The git hooks in `.githooks/` enforce a separate, stricter rule: any commit, message, or pushed content matching `\b(Simon|Steve|Quinn|Mike|David)\s+[A-Z]\w+` (a known first name immediately followed by a capitalized word — i.e. a likely full name) is refused. Bare first names are allowed; full names are not. Update the alternation in `.githooks/_forbidden-names.sh` when a new player joins the table.

## What to NOT author

These are computed by `build.py`:
- Trial card values (XP, kills, means of ending, kinds slain).
- Fortune card values (avg, σ, crits, fumbles, heaviest).
- Histogram bars, Other Dice charts, sessions chart bars.
- Constellation positions (only the epithets are authored).
- Bestiary tallies.
- Chronicle session metadata (date, kill count, portrait pips).
- Chapter portrait tallies.
- Patron Die histogram.
- Company ledger totals.
- `intro_meta` ("N Sessions · Month Year DR") — derived from the session log in `build.py`. The validator rejects a still-present `intro_meta` field in `authored/site.json` as a dead-field guard.

If the user asks for a change to any of these, the change is in `build.py` or upstream data — not in `authored/*.json`.

## Page anatomy reference

For HTML structure, see `templates/*.html`. These are frozen; do not modify them as part of normal hydration.

## End-of-run report

Print, in order:

1. **Append additions** — per category, by entity key.
2. **Refresh decisions** — per category, by entity key, with `reason`.
3. **Graduations** — `road_ahead.known` → `was_known` (computed by diffing
   keys before/after the refresh-road-ahead apply step).
4. **Marker state** — old → new value of `site.refreshed_through_session`,
   or "unchanged" with the reason (no new sessions, partial failure, etc.).
5. **Temp directory path** — and whether it was cleaned or preserved.

`reason` strings come straight from the agents' return objects.
