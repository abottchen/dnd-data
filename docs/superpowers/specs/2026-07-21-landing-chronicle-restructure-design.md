# Dashboard-first landing + Chronicle archive tab

**Date:** 2026-07-21
**Status:** Design approved (landing hero), pending spec review
**Reference mockup:** `site/_mockup-landing.html` (throwaway; renders against real `styles.css` + real data — delete after implementation)

## Problem

The site is a single tab-switched `index.html`. The **Company** tab holds both an aggregate dashboard *and* the full campaign history in one scroll. Measured on the live page at 1440×900, that tab is already **12,259px — 13.6 screens** tall, and the growth is concentrated in the three session-linear sections:

| Section | Height @ 17 sessions | Nature |
|---|---|---|
| VIII · The Silent Roll | 3,590px (already the tallest) | flat list, every quiet moment, all sessions |
| IV · The Chronicle | 2,410px (~140px/session) | collapsed session rows + chapter heads |
| IX · The Ascent | 1,151px | time-axis chart |
| six aggregate sections (Ledger, Constellation, Bestiary, Road Ahead, Distinctions, Patron Die) | ~4,900px combined | fixed-size dashboard |

The campaign is 17 sessions / 2 chapters into a projected **~100 sessions / 5 chapters**. At that scale the Chronicle projects to ~14,000px and the Silent Roll to ~20,000px — the Company tab becomes ~40 screens, and the in-tab index rail (which only jumps *within* one enormous scroll) stops being sufficient.

The single most-wanted thing — the latest session's story — currently sits at **section IV**, four-plus screens down.

## Intent (decided with the user)

- **The page's job is a living dashboard.** The instant it loads, the two live-campaign questions should be answered above the fold:
  1. **What just happened** — the latest session's story, in full.
  2. **Where are we / how close to leveling** — the party's level, XP, and progress to next level (from the Ascent, *not* the aggregate XP tally).
  Plus **where they're headed** (Road Ahead) as a close third — also current data.
- **Everything else is flavor.** The aggregate visualizations (Constellation, Bestiary, Distinctions, Patron Die, the full Ledger and Ascent) stay, beautiful, but below the fold.
- **The deep history moves one step away** into its own space, capped so its scroll length never grows with the campaign.

## Non-goals

- **No visual redesign.** The illuminated-ledger identity (starfield ink, brass Cormorant display, EB Garamond body, hairline rules, Roman numerals, oldstyle figures) is kept exactly. This is an information-architecture change.
- **No multi-page split.** Stays one committed `site/index.html`, tab-switched.
- **No change to the authoring pipeline.** No new transformers, no authored-JSON schema changes, no orchestrator changes. This is entirely a **render-layer** change (templates + `styles.css` + `_script.html` + `compute.py`). Every value the new layout shows is already authored or already computed.

## Design overview

Two parts:

1. **The Company tab becomes the landing dashboard** — re-sequenced so the latest story, the level/XP gauge, and Road Ahead come first; the aggregate sections follow as flavor. Fixed height forever.
2. **A new top-level "The Chronicle" tab** holds the growing archive — the session log and the quiet moments — shown **one chapter at a time** via a chapter switcher, so its scroll length is bounded by chapter size (~20 sessions), constant no matter how long the campaign runs.

The latest session lives in both places: surfaced in full on the landing, and in its proper chapter context in the archive.

---

## Part 1 — The landing (Company tab)

### 1a. Hero: latest story + Ascent gauge

Two columns separated by a hairline column rule (the same `--rule` language as the index rail):

```
THE LATEST
CHAPTER II · Down the Soshenstar to the Failing Camps
                                              │
The Long Road to Shilku Bay                   │   THE ASCENT
SESSION XVII · 12 Eleasis 1494 DR · 13 Jul    │   Level IV
              — no blade lifted —             │
                                              │   ‑‑‑‑ Level V · 6,500 XP ‑‑‑‑
[B]efore the company quit the trading post…   │   3,733
(the latest session's full authored summary,  │   XP still to climb
 drop-capped)                                 │        ______·  ← you-are-here
                                              │   __/‑‑     2,767 XP earned
```

- **Latest story, in full.** Renders the newest session entry: chapter label + title, session number (Roman), in-universe date, real date, and the complete authored `summary`, with the brass drop-cap already used on the current last-session treatment.
- **Empty-kill state honored.** When the session has no kills, show `— no blade lifted —` where the pip row goes; when it has kills, show the kill-pip row (reusing the `kill_pips` macro).
- **The Ascent gauge** (right column) shows the *level-progress* question, not the aggregate tally:
  - `Level IV` headline (Roman, brass, hero scale — spelled out; never abbreviated to "Lv" next to a numeral).
  - A compact climb chart that rises *toward* a dashed **Level V — 6,500 XP** threshold line and **stops short of it** — the vertical gap is the remaining climb. X-axis is time (as in the full Ascent), so "not there yet" is shown by the gap, never by the line reaching an edge.
  - Two figures placed in the chart's own empty regions: **`3,733 XP still to climb`** in the open area above the curve (left-justified); **`2,767 XP earned`** in the shaded fill near the current point (right-justified).
  - A "you-are-here" pulse at the current point.
  - Reuses the existing `ascent` compute context (`level`, `total`, `to_next`, `next_threshold`, `level_num`, `line_d`, `thresholds`) — no new data. Party shares one XP pool and one level (confirmed: characters always have equal XP), so one gauge is correct.

### 1b. Road Ahead band

A full-width band under the hero (current data, so above the fold):

```
THE ROAD AHEAD
WHERE THEY TURN                          WHAT IS KNOWN
Rokah's bargain dead at the gate…        [The Death Curse] [The Soulmonger]
sails south to Shilku, to learn          [Ring of Winter] [Azlund's Oath]
why the city has gone dark.              [The Map of Chult]   +3 more →
```

- Left: `site.road_ahead.direction` (the immediate next move), in prose.
- Right: the first ~5 `site.road_ahead.known` threads as chips, with `+N more →` linking down to the full Road Ahead flavor section.

### 1c. "Previously" teaser → Chronicle

A thin strip: the previous two sessions (number + title) and a single link, **Read the full Chronicle →**, into the Chronicle tab.

### 1d. Flavor sections (below the fold)

The aggregate sections remain, re-sequenced, reachable by scroll or the index rail. The Chronicle (was IV) and Silent Roll (was VIII) are **removed** from this tab (they move to Part 2). Proposed order and renumbered index rail:

```
I   The Ledger          (grand totals — souls, fallen, rolls, sessions)
II  The Ascent          (full climb + level-up nodes + "By What Deeds")
III The Constellation
IV  The Bestiary
V   The Road Ahead      (complete standing list — the band above is a digest)
VI  Distinctions
VII The Patron Die
```

The index rail shrinks from 9 entries to 7, and — critically — every remaining entry is a **fixed-count aggregate**, so the rail's length is now stable for the life of the campaign. The Ascent is promoted high because it *is* the XP-over-time story; unlike the Chronicle and Silent Roll it does **not** grow unboundedly — its x-axis is already thinned to month anchors (see the "thin x-axis to month anchors" work in `_ascent.html`), so it scales in place and stays in the dashboard. The Bestiary grows only slowly, with each *new kind* of creature, not with sessions.

---

## Part 2 — The Chronicle tab (archive)

A new top-level tab, peer to the Company / PC / GM tabs, holding the two session-linear sections.

```
NAV:  [The Company] [Grieg][Vex][Urida][Chumble][Lilac] · [The Chronicle] · [GM]

[ Chapter I ][ Chapter II ]…[ Chapter V ]      ← chapter switcher, renders ONE
  Regnal rail     CHAPTER II — drop cap · epigraph · N fallen · pip row
   Kythorn         Session XVI …                    (this chapter only)
   Flamerule       Session XVII ▸ expands → summary · pips · quiet moments
```

- **One chapter at a time.** A chapter switcher shows the selected chapter only. Scroll length ≈ one chapter (~20 sessions max), constant regardless of total campaign length. This is the mechanism that permanently caps growth.
- Reuses the existing `_chronicle.html` components (Regnal rail, chapter header, `<details>` session rows, `kill_pips`) — refactored to render a single chapter rather than looping all chapters.
- **The standalone Silent Roll section is deleted.** Each session's `silent_roll` lines render *inside* that session's expanded `<details>` body — below the summary, alongside the kill pips. The 3,590px→20,000px flat list disappears entirely, and the quiet moments grow naturally with the accordion, scoped to whatever session/chapter is open.

---

## Implementation surface

Files touched (all render-layer):

- **`build/templates/base.html`** — add a `The Chronicle` tab to `.tabs` (book glyph; between the PCs and GM); add the Chronicle tabpanel include in `<main>`.
- **`build/templates/_company.html`** — insert the hero (latest story + gauge), the Road Ahead band, and the "Previously" teaser at the top; remove the Chronicle (IV) and Silent Roll (VIII) sections; re-sequence and renumber the flavor sections and the `company_index` rail.
- **`build/templates/_hero.html`** (new) — the hero partial, kept separate so `_company.html` stays readable.
- **`build/templates/_chronicle_tab.html`** (new) — the Chronicle tabpanel: chapter switcher + one-chapter render + scoped Silent Roll. `class="character"` + `id="chronicle"` so it reuses the existing tab switcher with **zero** change to the tab JS.
- **`build/templates/_chronicle.html`** — refactor to render a single chapter (parameterized), consumed by `_chronicle_tab.html`; render each session's `silent_roll` lines inside its `<details>` body (below the summary, beside the pips). The standalone Silent Roll section is removed with `_company.html`.
- **`build/templates/_script.html`** — add ONE new IIFE for the in-tab chapter switcher (show/hide chapters). ⚠️ *CLAUDE.md gotcha:* this file is the page's only client-side logic (tab switcher + tooltip IIFEs); the new IIFE must be additive and must not disturb the existing ones.
- **`site/styles.css`** — new components: `.hero`, `.hero-rule`, `.gauge` (+ chart/figures), `.roadahead`, `.recent`, chapter switcher. Reuse existing tokens/vars throughout; no palette or type changes.
- **`build/compute.py`** — small additions to `compute_all`'s context:
  - `latest` — the newest session surfaced for the hero (chapter label/title, session Roman label, title, iu/real dates, kill pips or no-blade flag, full summary). Derived from existing chronicle data.
  - `recent` — the previous two sessions (label + title) for the teaser.
  - Gauge geometry — reuse the existing `ascent` context; if a distinct viewBox is wanted for the compact chart, add a small derived `gauge` sub-context from the same numbers.
  - `road_ahead` digest (direction + first N known + overflow count) — from existing `site.road_ahead`.

**Not touched:** `data/`, `build/authored/*.json` and their schemas, the orchestrator (`prepare`/`apply`/`slices.py`/etc.), `.claude/prompts/`, the `/build-prose` flow. No new authoring.

## Testing

- **Unit** (`tests/`, pytest — covers compute formulas): add cases for the new `compute` outputs — `latest` (incl. the no-kills → "no blade lifted" branch and a with-kills branch), `recent` (fewer-than-two-sessions edge), the Road Ahead digest (fewer-than-N known, overflow count), and gauge geometry (current point below the next threshold; summit case where `next_threshold` is null).
- **Render + visual**: run `build/render.py`, preview via `python3 -m http.server --directory site`, and check: hero at 1440×900 fits ~1.2 screens; the climb stops below the Level V line; the Chronicle tab switches chapters and renders one at a time; the index rail scroll-spy still tracks the shrunk section set; keyboard tab nav + reduced-motion still hold.
- **Growth check**: confirm the Company tab height is now independent of session count, and the Chronicle tab height is bounded by the largest single chapter.

## Settled decisions

- **Silent Roll:** no standalone section. Each session's `silent_roll` renders inside that session's expanded `<details>` body (Chronicle tab).
- **Road Ahead chips:** uniform weight; first ~5 known threads + `+N more →`. No authoring/schema change.
- **Hero column rule:** full story height (editorial column divider).
- **Gauge ceiling label:** keep the target — `Level V — 6,500 XP` on the dashed line.

### Deferred to build (implementation detail, not a design fork)

- **Mobile:** hero stacks (gauge below story, rule hidden); Road Ahead stacks; the chapter switcher collapses to a `<select>` or horizontal scroll. Settle while building against a narrow viewport.

## Risk notes

- The inline `_script.html` is load-bearing and easy to break silently; the chapter-switcher IIFE is the only new JS and must be isolated.
- The Ascent is referenced twice (compact gauge in the hero, full chart in flavor). Keep them consistent by driving both from the one `ascent` context.
- Removing sections from `_company.html` must keep the `company_index` rail, the section `id`s, and the scroll-spy `data-spy` targets in lockstep (see the existing comment at the top of `_company.html`).
