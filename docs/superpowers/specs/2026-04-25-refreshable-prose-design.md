# Refreshable prose — design

**Date:** 2026-04-25
**Branch:** `feat/refreshable-prose`

## Problem

The hydrate-ledger skill is append-only: it authors prose for new entities (kills, sessions, chapters, NPCs, characters) but never revisits existing entries. As the campaign evolves, prose that was written early — chapter epigraphs, character distinctions, Road Ahead glosses, NPC epithets, the spine line — goes stale. The user wants those entries to evolve as new data lands, while preserving the existing architecture.

## Architectural contract (preserved)

- **`templates/`** — page layout. Frozen.
- **`build.py`** — does all the math; reads computed inputs and `authored/*.json`, writes `index.html`.
- **`authored/*.json`** — the prose store; the only thing the skill writes.

The change is entirely inside the skill (which gains a refresh pass) and a single new computed value in `build.py` (`intro_meta`).

## Scope

### Evolvable — subject to refresh

| File | Field(s) | Granularity |
|---|---|---|
| `site.json` | `intro_epithet` | singleton string |
| `site.json` | `road_ahead.known[]` (`name`, `gloss`) | per entry |
| `site.json` | `road_ahead.was_known[]` (`name`, `gloss`) | per entry |
| `site.json` | `road_ahead.direction` | singleton string |
| `chapters.json` | `title`, `epigraph` | per chapter |
| `characters.json` | `epithet`, `constellation_epithet`, `distinction_title`, `distinction_subtitle`, `distinction_detail` | per character (refreshed as a set) |
| `npcs.json` | `epithet` | per NPC |

### Not evolvable — left alone

- `kills[]` `verse` / `annotation` — point-in-time records of a single kill.
- `sessions[]` `title` / `summary` / `silent_roll` — locked at the time of authoring; once a session has happened it doesn't change.
- `site.footnote`, `site.page_title`, `site.page_subtitle`, `site.gm.*` — campaign-tone strings, not data-coupled.
- `site.known_npcs` — allowlist, not prose.
- `characters[].reliquary_header` — character-voice title for the kill list panel.

### Moves out of the store entirely

- `site.intro_meta` ("Five Sessions · Kythorn 1494 DR") → computed in `build.py` from `len(session_log.entries)` plus the latest entry's `iu_month` / `iu_year`.

## Trigger mechanism

A single global integer marker in `site.json`:

```json
"refreshed_through_session": 5
```

On each skill invocation:

1. Load all data and authored stores; compute `latest_session = len(session_log.entries)`.
2. **If `latest_session > site.refreshed_through_session`:** run the refresh pass over every evolvable entry; then set `refreshed_through_session = latest_session`.
3. **Else:** skip the refresh pass entirely (append-only behavior, like today).

Coarse-grained on purpose. Forcing re-evaluation of one entry is best handled by the user telling the skill directly ("rewrite Chumble's distinction") — bypassing the marker. Refreshes are silent and idempotent (the standing prompt is "leave it alone if it's still right"), so a no-op refresh costs nothing visible.

## Skill workflow

The skill's per-invocation order:

1. **Load** — `party.json`, dice rolls, session log, all `authored/*.json`, `voice-samples.md`. Compute `latest_session`.
2. **Append pass** (unchanged from today) — author prose for any kill / session / NPC / chapter / character that has no matching authored entry yet.
3. **Refresh pass** (new) — if `latest_session > refreshed_through_session`, iterate every evolvable entry and rewrite-if-changed.
4. **Bump** — set `site.refreshed_through_session = latest_session`.
5. **Build + validate** — run `build.py`. On `MISSING` / `MALFORMED`, fix and re-run (max 3 iterations, same as today).
6. **Report** — list every entry created (append) and every entry rewritten (refresh) with before→after.

### Per-category refresh policy

The data context fed to each rewrite, plus the standing rule "leave it alone unless materially out of step":

| Category | Data context fed to the rewrite | Notes |
|---|---|---|
| `chapters[]` title + epigraph | Every session inside this chapter (real + in-universe dates, narrative text). Existing title + epigraph. | Reconsider when a new session has landed inside this chapter. |
| `characters[]` epithet, constellation_epithet, distinction_title, distinction_subtitle, distinction_detail | The character's accumulated kills (creature, method, CR), fortune stats (rolls, kept d20s, avg, σ, crits, fumbles, heaviest), and the party-wide rankings on each axis (so the skill can pick a true superlative for distinction_title and the right supporting stat string for distinction_detail). Existing prose. | The five fields are authored and refreshed as a set per character. `distinction_title` must remain unique across the party (existing validator). |
| `npcs[]` epithet | Every session-log narrative line that names this NPC, across all sessions. Existing epithet. | Effectively a no-op when the NPC isn't named in any newer session — no new context, so the standing prompt returns the existing line unchanged. |
| `site.road_ahead.known[]` (name + gloss) | Full narrative of newly-landed sessions; current entry's name + gloss. | Skill may rewrite the gloss **and may graduate an entry** from `known` to `was_known` if the thread reads as resolved. Graduations appear in the end-of-run report so the user can see what moved. |
| `site.road_ahead.was_known[]` | Same as above. | Glosses can still sharpen even after a thread closes. |
| `site.road_ahead.direction` | Full narrative of newly-landed sessions, with the latest weighted heaviest. Existing prose. | Single string; rewritten only when the campaign genuinely turned. |
| `site.intro_epithet` | Campaign-spine summary derived from the session log + Road Ahead's `known` list. Existing prose. | Mostly stable; rewrites only on real spine shifts. |

### Standing rewrite prompt

For every refresh: *"Here is the existing prose and the latest data. If the existing prose is still consistent with the data and still good prose by the voice rules, return it unchanged. Only rewrite if a fact has shifted, a stronger angle exists, or the line has gone stale."*

## `build.py` changes

- Compute `intro_meta` from the session log: `"{N} Sessions · {iu_month} {iu_year} DR"`, with `N` rendered as a word for 0–20 and as digits beyond. Latest session's `iu_month` and `iu_year` drive month + year. Empty log → `"No Sessions Yet"` (graceful sentinel; would also imply nothing else renders, but cover the case).
- `site.json` validator:
  - **Drop** `intro_meta` from required fields.
  - **Add** required `refreshed_through_session: int`, `0 <= value <= latest_session`.
  - **Reject** a still-present `intro_meta` field (dead-field guard so a half-applied migration is caught).
- All other validators (`chapters.json`, `npcs.json`, `characters.json`, `sessions.json`, `kills.json`) **unchanged**.

## Migration

One-off, committed as part of this change:

1. Edit `authored/site.json`:
   - Remove `intro_meta`.
   - Add `"refreshed_through_session": <current latest session number>`. Today that's `5` (session V is the latest in the log).
2. No format changes elsewhere; existing `chapters[]` / `npcs[]` / `characters[]` entries remain valid.

After commit, the next hydrate sees `latest == refreshed_through_session` and skips the refresh pass entirely. The first real refresh triggers when session VI lands.

## Tests

Added to `tests/test_validator.py` and `tests/test_compute.py`:

1. `intro_meta` computes correctly:
   - 5 sessions in Kythorn 1494 → `"Five Sessions · Kythorn 1494 DR"`.
   - 12+ sessions → digit form for the count.
   - Empty log → `"No Sessions Yet"`.
2. `site.json` validator rejects:
   - Missing `refreshed_through_session`.
   - Negative `refreshed_through_session`.
   - `refreshed_through_session > latest_session`.
3. `site.json` validator rejects a still-present `intro_meta` field.

The skill's refresh logic itself is not unit-tested in this repo (the skill is gitignored and runs interactively). The validator gates catch a misbehaving refresh pass: if the skill writes a malformed entry, the next `build.py` run fails with a `MALFORMED` line.

## Out of scope

- History retention. Refresh **overwrites**; prior prose lives only in `git log -p authored/*.json`.
- Per-entry as-of metadata. The single global marker is sufficient because refreshes are silent, idempotent, and the rewrite prompt enforces stability.
- A user-facing approval gate. The skill writes silently and reports at the end, same trust model as new entries today.
- Page-side editing. The site stays a static-rendered artifact.
- Refreshing `kills[]` or `sessions[]` prose. Locked once authored.
