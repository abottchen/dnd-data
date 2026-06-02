# Ability Radar — Design

**Date:** 2026-06-01
**Status:** Approved (brainstorm); ready for implementation plan
**Scope:** Add a per-character ability-score radar chart to each hero's panel,
inspired by the `dnd-toa` toa-browser radar, adapted to this site's static
build and manuscript aesthetic.

## Goal

Give every player character a small, animated radar chart of their six ability
scores, sitting beside their existing ability cards inside their own tab/panel.
The chart should feel native to the site's vellum-and-brass aesthetic, draw on
when the panel opens, and link interactively to the numeric cards.

## Inspiration & how this differs from toa

The toa-browser (`~/projects/dnd-toa/toa-browser/js/enhance.js`) renders a
hand-rolled SVG radar (six axes, concentric grid, glowing filled polygon) whose
signature move is **morphing the shape between characters** as the user pages
through PCs in that single-page app.

This site is different: it is a static page with a **tab switcher** — each
character is a pre-rendered `<article class="character">` shown/hidden by class
`.active` (see `build/templates/_script.html`). There is no shared chart paging
between heroes, so the cross-character morph does not apply. Instead:

- Each hero gets **their own** radar on **their own** page (no Company-page
  radar — that data is static and would only waste space there).
- The signature animation becomes a **draw-on reveal** that fires when a
  character's tab is activated.
- Interactivity is **within** one hero's panel: a linked highlight binding the
  radar to the ability cards.

Rejected ideas (considered and cut during brainstorming):
- **Party-average ghost polygon** — a single hero's spikes always exceed a
  rounded mean, so the comparison reads as noise, not signal.
- **Cross-character morph** — does not fit the tab/panel model.

## Placement & layout (Layout B)

Inside each character panel's abilities region, arrange as a horizontal flex row
on this desktop-only layout (`body { min-width: 1200px }`):

```
┌─ abilities region ─────────────────────────────────────────┐
│  ┌──────────────┐   ┌────────┬────────┬────────┐           │
│  │              │   │  STR   │  DEX   │  CON   │           │
│  │   RADAR      │   ├────────┼────────┼────────┤           │
│  │  (≈250px)    │   │  INT   │  WIS   │  CHA   │           │
│  └──────────────┘   └────────┴────────┴────────┘           │
│   radar (left)        six stat cards, 3×2 grid (right)      │
└─────────────────────────────────────────────────────────────┘
```

- Radar: fixed-basis flex item (`flex: 0 0 ~250px`).
- Cards: the existing `.stat-card`s, reflowed from the current
  full-width `repeat(6,1fr)` row into a `repeat(3,1fr)` block that fills the
  remaining width.
- The cards keep everything they show today: score, modifier, and the
  `Save ±N` line with seal-red coloring for proficient saves.

## Data & scale

- Source: `data/party.json` → `member.abilities` (`str,dex,con,int,wis,cha`)
  and `member.savingThrows[key].prof`. No new data files.
- **Scale:** score-based. Center = score **8**, outer ring = score **20**, one
  grid ring per **2** points (8,10,12,14,16,18,20). Scores below 8 clamp to
  center. Rationale: bigger number sits farther out (matches the big card
  numbers), and the fixed 8→20 range leaves headroom so shapes visibly grow as
  the party levels up over the campaign. The floor (8), ceiling (20), and ring
  step (2) are single named constants, easy to tune.
- Tick labels at scores 10 / 14 / 18 on the top (STR) axis anchor the scale.

## Architecture (Approach A — server-rendered SVG, JS enhances)

Geometry is computed deterministically in Python at build time and emitted as a
complete static `<svg>`. The inline script only *enhances* (animation + hover),
so the chart is correct even with JavaScript disabled. This matches the repo's
deterministic-renderer principle and lets the geometry be unit-tested. (The
alternative — letting the client build the SVG from data attributes, toa-style —
was rejected: nothing would render without JS and the geometry would escape the
pytest suite.)

### 1. `build/render.py` — `compute_radar(member) -> dict`

A new pure function mirroring the existing `compute_best_skill` pattern, wired
into `compute_all` as:

```python
radar_by_id = {m["id"]: compute_radar(m)
               for m in party.get("members", []) if m["id"] != "gm"}
# ... added to the context dict as "radar_by_id": radar_by_id
```

`compute_radar` returns everything the template needs as pre-rounded
coordinates (the SVG is a fixed `viewBox`, e.g. `0 0 240 240`, cx=cy=120):

- `rings`: list of ring polygons (each a list of `"x,y"` points) — one per grid
  step.
- `axes`: six `{x2, y2}` endpoints from center.
- `labels`: six `{x, y, anchor, text}` (STR…CHA), with anchor/`dy` chosen by
  quadrant so labels sit cleanly outside the disc.
- `ticks`: `{x, y, text}` for 10/14/18.
- `shape`: six `"x,y"` points of the filled polygon at the hero's actual scores.
- `dots`: six `{x, y, key, prof}` vertex markers (prof drives seal-red styling).
- `sectors`: six `{d, key}` SVG path strings — invisible 60° pie-slice hit
  zones tiling the full disc (radius slightly beyond the outer ring), each
  centered on one axis. `d` is a `M cx cy L … A … Z` wedge.

All six entries carry an index `i` (0–5) and the lowercase ability `key`, so the
template can stamp `data-i` / `data-key` for the hover wiring.

### 2. `build/templates/_radar.html` (new partial)

A declarative include that lays `radar_by_id[member.id]` into an
`<svg class="ability-radar">`: grid polygons, axes, ticks, the filled
`.ar-shape` polygon, vertex `.ar-dot`s (`.ar-dot-prof` when proficient), labels,
and the invisible `.ar-sector` hit-zone paths **last** (so they sit on top for
pointer events). `aria-hidden="true"` on the SVG (the cards are the accessible
representation of the same numbers).

### 3. `build/templates/_abilities.html` (modified)

Wrap the radar include + the existing card grid in a flex container
(`.abilities-layout`) realizing Layout B. The six `.stat-card`s each gain a
`data-i`/`data-key` matching the radar, for hover linking. Card markup otherwise
unchanged.

### 4. `site/styles.css` (additions)

- `.abilities-layout` flex row; radar `flex:0 0` basis; cards block fills rest.
- `.ability-radar` element classes: `.ar-grid`, `.ar-grid-outer`, `.ar-axis`
  (+`.hot`), `.ar-shape`, `.ar-dot` (+`.ar-dot-prof`, +`.hot`), `.ar-label`
  (+`.hot`), `.ar-tick`, `.ar-sector` (transparent; faint brass fill when
  `.hot`). Palette uses existing tokens (`--brass-hi` shape/stroke + glow,
  `--seal` proficient dots, `--rule`/`--rule-strong` grid).
- `.stat-card.hot` highlight (inset brass ring + darker fill).
- Adjust the existing `.abilities` grid rule (it is currently `repeat(6,1fr)`;
  the card block becomes `repeat(3,1fr)` within Layout B).

### 5. `build/templates/_script.html` (one new IIFE)

Pure enhancement, no geometry:

- **Linked hover:** for each `.ability-radar`, hovering an `.ar-sector` toggles
  `.hot` on the matching axis/dot/label/sector and the matching `.stat-card`;
  hovering a `.stat-card` toggles the same set in reverse. Matching is by
  `data-i` within the enclosing character panel.
- **Draw-on reveal:** animate the `.ar-shape` points (and dots) from the center
  outward to their final rendered positions over ~700 ms with easeOutCubic via
  `requestAnimationFrame`. The final coordinates are read from the
  server-rendered polygon, cached on first run, then animated from center.
  **Fires on every tab activation** — integrated with the existing tab switcher
  so that whenever a panel gains `.active`, its radar replays. (Implementation:
  extend/observe the existing `activate(id)` flow rather than duplicating it.)
- **Reduced motion:** if `matchMedia('(prefers-reduced-motion: reduce)')`
  matches, skip the animation entirely — the static server-rendered shape is
  already correct.

## Interactions (summary)

| Behaviour | Trigger | Mechanism |
|-----------|---------|-----------|
| Draw-on reveal | Tab/panel becomes `.active` (every time) | rAF animates shape from center; reduced-motion skips |
| Linked highlight | Hover a wedge **or** a card | Toggle `.hot` on the paired elements (CSS does the visual) |
| Proficient saves | static | `.ar-dot-prof` seal-red vertices + existing seal-red `Save` line |
| Reliable hit target | hover anywhere in chart | Six invisible 60° `.ar-sector` wedges tile the disc |

## Accessibility & graceful degradation

- The SVG is decorative (`aria-hidden`); the `.stat-card`s remain the readable
  source of the numbers (unchanged for screen readers).
- With JS disabled: the full static radar still renders (shape, dots, grid,
  labels); only the reveal animation and hover linking are absent.
- `prefers-reduced-motion` disables the reveal animation.

## Testing

- `tests/` gains coverage for `compute_radar`: correct point count (6),
  monotonic radius vs. score, clamping at/below the floor, proficient flags
  passed through, and stable rounded coordinates for a known fixture member
  (mirrors how `compute_best_skill` and other formulas are tested).
- End-to-end: re-render via the build (or `build/render.py` directly) and
  verify in the local preview server
  (`python3 -m http.server 8765 --directory site`):
  open a character tab, confirm the radar draws on, sweep the cursor to confirm
  every wedge highlights its card, and toggle a system reduced-motion setting to
  confirm the animation is skipped.

## Out of scope

- No Company-page radar; no cross-character morph; no party-average ghost.
- No new data files or authored-prose changes; this is a render/template/style
  feature only.
- GM panel is excluded (no `abilities` block).

## Files touched

- `build/render.py` — add `compute_radar`, wire `radar_by_id` into context.
- `build/templates/_radar.html` — new partial.
- `build/templates/_abilities.html` — Layout B wrapper + card `data-*`.
- `site/styles.css` — radar + layout + `.hot` rules; card grid adjustment.
- `build/templates/_script.html` — new enhancement IIFE.
- `tests/` — `compute_radar` coverage.
- `site/index.html` — rebuilt artifact (committed).
