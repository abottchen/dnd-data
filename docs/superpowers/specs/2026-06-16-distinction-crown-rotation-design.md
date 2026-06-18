# Distinction crowns: rotating, emergent, verifiable

**Date:** 2026-06-16
**Status:** Approved design, pending implementation plan
**Area:** `build/` orchestrator — character distinction authoring

## Problem

The Distinctions section (Section VI, "The Crowns") gives each PC one party-unique
honour: a `distinction_title`, `distinction_subtitle`, and stat-backed
`distinction_detail`. The `refresh-characters` transformer re-evaluates the bundle
each build under a heavy `no_change` bias.

The crowns go stale in two distinct ways:

1. **Class-predictable monotony.** "Most-common kill method" is determined by class —
   a warlock's is always Eldritch Blast, a ranger's always the longbow. The honour
   collapses into a restatement of the character sheet (Chumble: "who fells by the
   blast and little else"; Lilac: "Every felling came off the same drawn bow"), and
   because the fact never changes, the `no_change` bias freezes the line forever.

2. **Monotonic-count permanence.** A count like distinct attack-means can only rise or
   hold. Once "4 means" is the crown (Vex), the framing "who fells by every means he
   carries" is structurally permanent — the number cannot create drama because it
   cannot fall.

A naive fix — a fixed menu of ~8 party-relative superlatives — was rejected: even if the
*holder* of each crown rotates, the page would show the same 8 honours reshuffling. That
trades class-predictability for menu-predictability. The same staleness, a different cause.

## Goals

- **Escape class-predictability** — a crown should reveal something not guessable from
  the character's class.
- **Inject real dynamism** — crowns should churn as the campaign accrues data.
- Treat both as one redesign of what a distinction is drawn from and how it rotates.

## Design decisions

These were settled during brainstorming:

| Decision | Choice |
|---|---|
| Primary goal | Both surprise and dynamism, as one redesign |
| Rotation policy | **Free rotation** — a crown may jump category whenever a stronger/fresher angle exists |
| Selection space | **Open-ended emergent patterns** composed from a computed fact pack — *not* a closed scalar menu |
| Source breadth | **Mechanical core, narrative as tiebreak** — narrative angle only when a PC had no new mechanical activity in the new sessions |
| `reliquary_header` | **One-time migration** to escape bare-method framing, then stays locked |
| `constellation_epithet` | **Own axis-bound contract** (presence × contribution + cluster), method/kill themes banned |

## Field scope

The redesign touches four authored fields per character, with three different treatments.

| Field | Renders in | Treatment |
|---|---|---|
| `distinction_title` / `_subtitle` / `_detail` | Section VI "The Crowns" | **Rotates freely** over the open emergent-pattern space; carries a machine-verifiable `basis`. |
| `constellation_epithet` | Constellation scatter plot (star label + tooltip) | **Own axis-bound contract** — presence (rolls) × contribution (XP) + cluster standing only; method/kill themes banned; refreshes when those axes shift. |
| `reliquary_header` | Reliquary section | **One-time migration** to escape bare-method framing, then re-locked (ongoing lock unchanged). |
| `epithet` | Intro/identity line | **Untouched.** Separate concern. |

### Why the constellation is a different type

The constellation is a 2-axis scatter plot: X = *Contribution · experience earned* (XP),
Y = *Presence · rolls cast* (d20s thrown). Each PC is a star positioned by `(xp, rolls)`,
grouped into "systems" (clusters of nearby stars) with connecting links. The
`constellation_epithet` labels the star and feeds its tooltip. The field is therefore
*bound to a star's standing in presence × contribution and its cluster relationships* —
not to how the character kills. Today three epithets have drifted off-axis into kill-method
themes (Vex "blade and breath both", Chumble "the pact-light's tally", Lilac "every kill the
same string"); two are already on-axis (Urida "the heaviest lift" = top XP, Grieg "ten crit
successes told" = roll/presence). The redesign fixes the three off-axis labels and binds the
field's contract to the axes going forward.

## The fact pack

Code computes a per-PC bundle of **verifiable atoms** — the open, atom-level material the
model composes a crown from. Every value is reproducible from the kill log + roll log, so a
claim grounded in an atom cannot be a hallucination.

**Kill-derived**
- `kill_count`, `xp`, `kill_pct`, `xp_pct` (+ party rank on each)
- method multiset, `distinct_method_count`, `all_kills_one_method` (+ which)
- creature list, `all_distinct_creatures`, repeat creatures
- type multiset (via bestiary), `distinct_type_count`, `all_distinct_types`
- `highest_cr_kill` (creature + CR), `is_party_highest_cr`, kills-above-CR-threshold count
- per-session: kills-per-session map, `max_in_one_session` (+ which), kill-session count,
  longest kill drought (sessions between kills), sole-killer sessions

**Roll-derived (fortune)**
- kept-d20 average (+ rank → luckiest / unluckiest)
- stdev (+ rank → steadiest / swingiest)
- crit count (+ rank), max crits in one session
- crit-fail count (+ rank)
- heaviest single damage blow (total + notation), `is_party_heaviest`

**Constellation context** (for the constellation contract)
- xp & rank, rolls & rank
- system/cluster membership (who the star orbits with), `is_outlier`
- quadrant (high/low presence × high/low contribution)

**Authoring context**
- party aggregates
- each PC's *previous* distinction (for the freshness bias)
- per-PC `had_new_activity` flag for the new-session batch (gates the narrative tiebreak)

`compute_fact_pack` lives in `build/render.py` alongside `compute_trials`,
`compute_fortune`, and `compute_constellation`, and reuses them. This follows the existing
pattern where `build/slices.py` already calls `render.compute_trials` /
`render.compute_fortune`; it introduces no new cross-module sharing. *(Flagged for review
against the "mirror patterns rather than extract shared modules" toolchain note — the
judgement here is that reusing render's compute functions from slices is the established
pattern in this codebase, not a new extraction.)*

## Authoring contracts

Both the `refresh-characters` and `append-characters` prompts carry two clearly separated
contracts.

### Crown contract (`distinction_*`)

1. A crown is an **emergent, specifically-true pattern** from the PC's fact pack — a
   superlative ("the only / the most / the largest") or a structural observation ("six kills,
   six different creatures; never the same foe twice").
2. **Banned:** bare class-method restatement ("kills mostly by Eldritch Blast", "of the N
   means") or anything true-by-default of that class.
3. **Coordination rule:** avoid landing on the raw presence/contribution axes (XP-share,
   roll count) — those belong to the constellation. Steer to the other emergent material so
   the two sections stay complementary, not redundant.
4. **Unique party-wide on both the title and the underlying `basis` atom** — no two PCs
   crowned on the same fact.
5. **Bias toward axes that moved** since the previous build; free to jump category entirely.
6. **Mechanical by default. Narrative angle only when `had_new_activity` is false** for that
   PC — grounded in explicit session-log text, never naming a real player.
7. Emit a machine-readable **`basis`** for verification (see below).

### Constellation contract (`constellation_epithet`)

1. Speaks **only** to the star's standing on presence (rolls) × contribution (XP) and its
   cluster relationships (outlier, paired, central, high-presence/low-contribution, etc.).
2. **Method/kill themes banned.**
3. Refreshes when those axes or the cluster shift. Six words or fewer, saga-fragment register.

## Verification: `basis`

Each crown emits a structured `basis` so the render step verifies the claim instead of
trusting prose:

- Mechanical: `{ "kind": "mechanical", "atom": "all_distinct_creatures", "value": 6 }`
- Narrative: `{ "kind": "narrative", "sessions": [12], "note": "..." }` — records provenance
  only; not machine-checkable.

`render.py` recomputes the fact pack and asserts every mechanical `basis` matches the
computed atom/value. A mismatch fails the render as `MALFORMED`, exactly like the existing
validators ("validation gates the render"). The uniqueness validator extends to cover the
basis atom, not just the title string.

## Cadence and churn

`refresh-characters` stays marker-gated (`latest_session > refreshed_through_session`), so
crowns re-evaluate exactly once per new-session batch. That bounds churn to genuine new-data
events and prevents build-to-build flicker on identical data — no separate hysteresis rule
needed.

## Reliquary migration (one-time)

A one-time pass rewrites all `reliquary_header` values to a durable, evocative "how foes meet
their end" line that avoids flat class-method restatement (no "all by longbow" energy). After
the migration the field's existing lock applies unchanged — it is not part of ongoing
refresh. The migration is a rollout step, not a permanent pipeline feature.

## Files touched

- `build/render.py` — new `compute_fact_pack`; extended validation (basis check +
  uniqueness-by-atom).
- `build/slices.py` — `refresh_characters` / `append_characters` pass the fact pack, the
  `had_new_activity` flags, the prior distinction, and session-log text.
- `.claude/prompts/refresh-characters.md` + `.schema.json` — two-contract rewrite + `basis`
  field.
- `.claude/prompts/append-characters.md` + `.schema.json` — same.
- One-time reliquary-header migration (throwaway prompt or scripted authoring during rollout).
- `tests/` — fact-pack atom computation, basis verification, uniqueness-by-atom.

## Non-goals

- No change to the `epithet` identity line.
- No new ongoing refresh for `reliquary_header` (migration only; lock stays).
- No new raw data sources beyond the existing kill log, roll log, and session log.
- No client-side / template changes beyond what the new fields require (the fields already
  render).

## Risks and open questions

- **Narrative honesty.** Narrative-tiebreak claims are not machine-verifiable and the session
  log carries real player names. Mitigations: the narrative path is narrow (only
  `had_new_activity == false`), the prompt forbids real player names, the `basis` records
  session provenance, and the forbidden-name git hooks guard commits/pushes.
- **Crown/constellation overlap.** The coordination rule keeps them complementary; worth a
  visual check after the first real build that they don't echo.
- **First build after rollout.** All five crowns and the three off-axis constellation epithets
  re-author at once — review the rendered page before committing.
