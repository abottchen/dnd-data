# Ability Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-character ability-score radar chart beside each hero's ability cards, with a draw-on reveal on tab activation and a linked pie-slice hover binding the radar to the cards.

**Architecture:** Geometry is computed deterministically in Python (`compute_radar` in `build/render.py`), surfaced in the render context as `radar_by_id`, and laid into a static SVG by a new Jinja partial (`build/templates/_radar.html`). The inline page `<script>` only *enhances* — it animates the reveal and wires hover; it never recomputes geometry. The chart therefore renders correctly with JavaScript disabled.

**Tech Stack:** Python 3 + Jinja2 (build), vanilla SVG/CSS/JS (output), pytest (tests). This is the existing `dnd-data` toolchain — no new dependencies.

**Design spec:** `docs/superpowers/specs/2026-06-01-ability-radar-design.md`

**Conventions for every commit in this plan:**
- Run from the repo root `/home/adam/projects/dnd-data`.
- Use the venv interpreter: `.venv/bin/python`, `.venv/bin/pytest`.
- Commit messages: **no trailers, no "Claude"/AI references** (project rule). Use the `(type) Subject` style seen in `git log` (e.g. `(feat)`, `(maint)`).
- Work stays on branch `feature/ability-radar` (already created).

---

### Task 1: `compute_radar` geometry function

Pure function + module constants that produce all radar coordinates for one member. This is the only unit-tested piece (mirrors how `compute_best_skill` / `compute_intro_meta` are tested in `tests/test_compute.py`).

**Files:**
- Modify: `build/render.py` (add constants + helpers + `compute_radar`, near `compute_best_skill` at line 607). `import math` already exists at line 13.
- Test: `tests/test_compute.py` (add tests; extend the import on lines 1–5).

- [ ] **Step 1: Write the failing tests**

Add to the import block at the top of `tests/test_compute.py` (append `compute_radar` to the existing parenthesised import):

```python
from build.render import (xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune,
                   compute_d20_histogram, compute_other_dice, compute_best_skill,
                   compute_intro_meta, compute_constellation,
                   _compute_party_top_xp, _compute_header_eyebrow,
                   _creature_token_url, _name_to_token_name,
                   compute_radar)
```

Append these tests to the end of `tests/test_compute.py`:

```python
def _radar_member(scores, prof=()):
    return {
        "abilities": {k: scores[k] for k in ("str", "dex", "con", "int", "wis", "cha")},
        "savingThrows": {k: {"mod": 0, "prof": k in prof}
                         for k in ("str", "dex", "con", "int", "wis", "cha")},
    }

def test_radar_returns_six_of_each_element():
    r = compute_radar(_radar_member({"str": 12, "dex": 12, "con": 12,
                                     "int": 12, "wis": 12, "cha": 12}))
    assert len(r["axes"]) == 6
    assert len(r["dots"]) == 6
    assert len(r["labels"]) == 6
    assert len(r["sectors"]) == 6
    assert len(r["rings"]) == 6           # rings at 10,12,14,16,18,20
    assert len(r["shape"].split(" ")) == 6

def test_radar_top_axis_vertex_uses_score_scale():
    # STR is index 0 = straight up. score 14 -> radius (14-8)/12*76 = 38 -> y = 120-38 = 82.
    r = compute_radar(_radar_member({"str": 14, "dex": 8, "con": 8,
                                     "int": 8, "wis": 8, "cha": 8}))
    assert r["dots"][0] == {"i": 0, "key": "str", "x": 120.0, "y": 82.0, "prof": False}
    assert r["shape"].split(" ")[0] == "120.0,82.0"

def test_radar_clamps_low_scores_to_center():
    # score 6 (below floor 8) clamps to center (120,120).
    r = compute_radar(_radar_member({"str": 6, "dex": 8, "con": 8,
                                     "int": 8, "wis": 8, "cha": 8}))
    assert r["dots"][0]["x"] == 120.0 and r["dots"][0]["y"] == 120.0
    # score 8 (floor) also sits at center.
    assert r["dots"][1]["x"] == 120.0 and r["dots"][1]["y"] == 120.0

def test_radar_radius_increases_with_score():
    # Distance from center grows monotonically: 8 (center) < 14 < 20 (outer ring).
    def top_y(score):
        return compute_radar(_radar_member({"str": score, "dex": 8, "con": 8,
                                            "int": 8, "wis": 8, "cha": 8}))["dots"][0]["y"]
    assert top_y(20) < top_y(14) < top_y(8)   # smaller y = farther up = bigger radius
    assert top_y(20) == 44.0                  # outer ring: 120 - 76

def test_radar_marks_proficient_saves():
    r = compute_radar(_radar_member({"str": 10, "dex": 10, "con": 10,
                                     "int": 10, "wis": 10, "cha": 10},
                                    prof=("dex", "cha")))
    by_key = {d["key"]: d["prof"] for d in r["dots"]}
    assert by_key == {"str": False, "dex": True, "con": False,
                      "int": False, "wis": False, "cha": True}

def test_radar_sector_path_is_a_closed_wedge():
    r = compute_radar(_radar_member({"str": 12, "dex": 12, "con": 12,
                                     "int": 12, "wis": 12, "cha": 12}))
    d = r["sectors"][0]["d"]
    assert d.startswith("M120 120 L")   # wedge starts at center
    assert " A112 112 " in d            # arc at the hit radius
    assert d.endswith("Z")              # closed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_compute.py -k radar -v`
Expected: FAIL — `ImportError: cannot import name 'compute_radar'`.

- [ ] **Step 3: Implement the constants, helpers, and function**

In `build/render.py`, immediately **after** `compute_best_skill` (it ends at line 622, before `compute_constellation`), insert:

```python
# ── Ability radar geometry ──────────────────────────────────────────
# Fixed 240x240 viewBox. Score-based scale: RADAR_FLOOR (center) -> RADAR_CEIL
# (outer ring), one grid ring per RADAR_STEP points. Scores below the floor
# clamp to the center. All coordinates are pre-rounded so the template lays
# them out directly and the client script only animates/links — never recomputes.
RADAR_KEYS = ("str", "dex", "con", "int", "wis", "cha")
RADAR_LABELS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
RADAR_FLOOR = 8
RADAR_CEIL = 20
RADAR_STEP = 2
RADAR_TICKS = (10, 14, 18)
RADAR_CX = 120.0
RADAR_CY = 120.0
RADAR_R = 76.0        # outer-ring radius
RADAR_HIT_R = 112.0   # pie-slice hit radius (beyond the outer ring, inside the viewBox)
RADAR_LABEL_R = 93.0  # label radius (RADAR_R + 17)

def _radar_angle(i: int) -> float:
    """Angle of axis i, with STR (i=0) pointing straight up."""
    return -math.pi / 2 + (i / 6) * 2 * math.pi

def _radar_radius(score: float) -> float:
    clamped = max(RADAR_FLOOR, min(RADAR_CEIL, score))
    return (clamped - RADAR_FLOOR) / (RADAR_CEIL - RADAR_FLOOR) * RADAR_R

def _radar_point(angle: float, radius: float) -> tuple[float, float]:
    return (RADAR_CX + math.cos(angle) * radius, RADAR_CY + math.sin(angle) * radius)

def _radar_xy(p: tuple[float, float]) -> str:
    return f"{p[0]:.1f},{p[1]:.1f}"

def compute_radar(member: dict) -> dict:
    """Geometry for a character's six-axis ability-score radar.

    Returns pre-rounded coordinates for: concentric grid `rings` (point-string
    each), `axes` endpoints, `ticks`, the filled `shape` (point-string), vertex
    `dots` (with proficient-save flag), `labels`, and invisible pie-slice
    `sectors` (60-degree hover hit zones tiling the disc). See module constants
    for the scale."""
    abilities = member.get("abilities", {})
    saves = member.get("savingThrows", {})

    rings = []
    for rv in range(RADAR_FLOOR + RADAR_STEP, RADAR_CEIL + 1, RADAR_STEP):
        rr = _radar_radius(rv)
        rings.append(" ".join(_radar_xy(_radar_point(_radar_angle(i), rr)) for i in range(6)))

    axes = []
    for i in range(6):
        p = _radar_point(_radar_angle(i), RADAR_R)
        axes.append({"x2": round(p[0], 1), "y2": round(p[1], 1)})

    ticks = []
    for tv in RADAR_TICKS:
        y = RADAR_CY - _radar_radius(tv)
        ticks.append({"x": round(RADAR_CX + 4, 1), "y": round(y + 3, 1), "text": str(tv)})

    shape_pts, dots = [], []
    for i, key in enumerate(RADAR_KEYS):
        score = abilities.get(key, RADAR_FLOOR)
        p = _radar_point(_radar_angle(i), _radar_radius(score))
        shape_pts.append(_radar_xy(p))
        dots.append({
            "i": i, "key": key,
            "x": round(p[0], 1), "y": round(p[1], 1),
            "prof": bool(saves.get(key, {}).get("prof")),
        })
    shape = " ".join(shape_pts)

    labels = []
    for i, lab in enumerate(RADAR_LABELS):
        a = _radar_angle(i)
        p = _radar_point(a, RADAR_LABEL_R)
        cos_a, sin_a = math.cos(a), math.sin(a)
        anchor = "middle"
        if cos_a > 0.4:
            anchor = "start"
        elif cos_a < -0.4:
            anchor = "end"
        dy = 4.0
        if sin_a > 0.5:
            dy = 11.0
        elif sin_a < -0.5:
            dy = -3.0
        labels.append({"i": i, "text": lab, "anchor": anchor,
                       "x": round(p[0], 1), "y": round(p[1] + dy, 1)})

    sectors = []
    for i, key in enumerate(RADAR_KEYS):
        a = _radar_angle(i)
        p0 = _radar_point(a - math.pi / 6, RADAR_HIT_R)
        p1 = _radar_point(a + math.pi / 6, RADAR_HIT_R)
        d = (f"M{RADAR_CX:.0f} {RADAR_CY:.0f} "
             f"L{p0[0]:.1f} {p0[1]:.1f} "
             f"A{RADAR_HIT_R:.0f} {RADAR_HIT_R:.0f} 0 0 1 {p1[0]:.1f} {p1[1]:.1f} Z")
        sectors.append({"i": i, "key": key, "d": d})

    return {"rings": rings, "axes": axes, "ticks": ticks,
            "shape": shape, "dots": dots, "labels": labels, "sectors": sectors}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_compute.py -k radar -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_compute.py
git commit -m "(feat) Add compute_radar ability-score geometry helper"
```

---

### Task 2: Wire `radar_by_id` into the render context

Expose one `compute_radar` result per non-GM member, mirroring the `best_skill_by_id` line.

**Files:**
- Modify: `build/render.py` — `compute_all`, at the `best_skill_by_id` assignment (line 1206) and the returned context dict (after `"best_skill_by_id"`, line 1250).

- [ ] **Step 1: Add the per-member computation**

In `compute_all`, directly **after** line 1206:

```python
    best_skill_by_id = {m["id"]: compute_best_skill(m) for m in party.get("members", [])}
    radar_by_id = {m["id"]: compute_radar(m)
                   for m in party.get("members", []) if m.get("id") != "gm"}
```

- [ ] **Step 2: Add it to the returned context dict**

In the `return {` block of `compute_all`, **after** the `"best_skill_by_id": best_skill_by_id,` line (line 1250):

```python
        "best_skill_by_id": best_skill_by_id,
        "radar_by_id": radar_by_id,
```

- [ ] **Step 3: Verify the full suite still passes**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS (all existing tests + the 6 new radar tests; no failures).

- [ ] **Step 4: Commit**

```bash
git add build/render.py
git commit -m "(feat) Surface radar geometry per character in render context"
```

---

### Task 3: New `_radar.html` partial

A declarative include that lays the precomputed geometry into an SVG. Stamps `data-i` on the elements the hover wiring pairs (axes, dots, labels, sectors) and `data-key` where useful.

**Files:**
- Create: `build/templates/_radar.html`

- [ ] **Step 1: Create the partial**

Create `build/templates/_radar.html` with exactly:

```html
      {%- set r = radar_by_id[member.id] %}
      <svg class="ability-radar" viewBox="0 0 240 240" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        {%- for pts in r.rings %}
        <polygon class="ar-grid{% if loop.last %} ar-grid-outer{% endif %}" points="{{ pts }}"></polygon>
        {%- endfor %}
        {%- for ax in r.axes %}
        <line class="ar-axis" data-i="{{ loop.index0 }}" x1="120" y1="120" x2="{{ ax.x2 }}" y2="{{ ax.y2 }}"></line>
        {%- endfor %}
        {%- for t in r.ticks %}
        <text class="ar-tick" x="{{ t.x }}" y="{{ t.y }}">{{ t.text }}</text>
        {%- endfor %}
        <polygon class="ar-shape" points="{{ r.shape }}"></polygon>
        {%- for d in r.dots %}
        <circle class="ar-dot{% if d.prof %} ar-dot-prof{% endif %}" data-i="{{ d.i }}" data-key="{{ d.key }}" cx="{{ d.x }}" cy="{{ d.y }}" r="{{ 4 if d.prof else 3 }}"></circle>
        {%- endfor %}
        {%- for l in r.labels %}
        <text class="ar-label" data-i="{{ l.i }}" x="{{ l.x }}" y="{{ l.y }}" text-anchor="{{ l.anchor }}">{{ l.text }}</text>
        {%- endfor %}
        {%- for s in r.sectors %}
        <path class="ar-sector" data-i="{{ s.i }}" data-key="{{ s.key }}" d="{{ s.d }}"></path>
        {%- endfor %}
      </svg>
```

(The partial is consumed in Task 4; it is verified end-to-end in Task 7.)

- [ ] **Step 2: Commit**

```bash
git add build/templates/_radar.html
git commit -m "(feat) Add _radar.html SVG partial"
```

---

### Task 4: Layout B in `_abilities.html`

Wrap the radar + the existing card grid in a flex row, and tag each card with `data-i` for the hover link. Card markup is otherwise unchanged.

**Files:**
- Modify: `build/templates/_abilities.html` (current full contents below).

- [ ] **Step 1: Rewrite the partial**

Replace the entire contents of `build/templates/_abilities.html` with:

```html
      <section class="abilities-layout">
        {% include "_radar.html" %}
        <div class="abilities">
        {%- set ability_keys = ["str", "dex", "con", "int", "wis", "cha"] %}
        {%- set ability_labels = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"} %}
        {%- for key in ability_keys %}
          {%- set score = member.abilities[key] %}
          {%- set mod = (score - 10) // 2 %}
          {%- set mod_str = ("+" if mod >= 0 else "") ~ mod %}
          {%- set mod_display = mod_str | replace("-", "&minus;") %}
          {%- set st = member.savingThrows[key] %}
          {%- set save_val = st.mod %}
          {%- set save_str = ("+" if save_val >= 0 else "") ~ save_val %}
          {%- set save_display = save_str | replace("-", "&minus;") %}
          {%- set is_proficient = st.prof %}
        <div class="stat-card" data-i="{{ loop.index0 }}" data-key="{{ key }}"><div class="stat-label">{{ ability_labels[key] }}</div><div class="stat-val">{{ score }}</div><div class="stat-mod">{{ mod_display | safe }}</div><div class="stat-save{% if is_proficient %} proficient{% endif %}"><span class="save-mark"></span>Save {{ save_display | safe }}</div></div>
        {%- endfor %}
        </div>
      </section>
```

- [ ] **Step 2: Commit**

```bash
git add build/templates/_abilities.html
git commit -m "(feat) Lay out radar beside ability cards (Layout B)"
```

---

### Task 5: Styles in `site/styles.css`

Add the layout wrapper, the radar element styles, and the card `.hot` highlight; switch the existing `.abilities` grid from 6 to 3 columns and move its bottom margin to the wrapper.

**IMPORTANT:** Do **not** modify the existing `.stat-card .stat-save.proficient` rules — proficient saves on the *cards* stay brass. Seal-red is used only on the radar's proficient vertices (`.ar-dot-prof`).

**Files:**
- Modify: `site/styles.css` — update the tight-spacing selectors (lines 260–266); edit the `.abilities` rule (lines 469–476); append a new block after the `.stat-card .stat-save.proficient .save-mark` rule (ends line 539).

- [ ] **Step 1: Re-point the tight-spacing selectors at the new wrapper**

Task 4 renamed the section's outer element from `section.abilities` to `section.abilities-layout`, which orphaned the existing tight-spacing rule. Update it so the wrapper keeps `padding-top: 0; margin-bottom: 24px` (otherwise it falls back to the generic `.character > section` rule's 96px bottom margin). Replace lines 260–266:

```css
/* Abilities and proficiencies sit tight under the character header — no big gap */
main > article > section.abilities,
main > article > section.proficiencies,
.character > section.abilities,
.character > section.proficiencies {
  padding-top: 0;
  margin-bottom: 24px;
}
```

with (only the two `.abilities` selectors change to `.abilities-layout`):

```css
/* Abilities and proficiencies sit tight under the character header — no big gap */
main > article > section.abilities-layout,
main > article > section.proficiencies,
.character > section.abilities-layout,
.character > section.proficiencies {
  padding-top: 0;
  margin-bottom: 24px;
}
```

- [ ] **Step 2: Change `.abilities` to a 3-column block**

Replace the existing rule at lines 469–476:

```css
.abilities {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule-strong);
  margin-bottom: 36px;
}
```

with:

```css
.abilities {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule-strong);
  flex: 1;
  margin-bottom: 0;
}
```

- [ ] **Step 3: Append the layout + radar + hover styles**

Immediately **after** line 539 (the closing `}` of `.stat-card .stat-save.proficient .save-mark`), insert. Note `.abilities-layout` deliberately carries **no** `margin-bottom` — the section's bottom spacing is owned by the tight-spacing rule updated in Step 1, and the inner `.abilities` card grid is set to `margin-bottom: 0` in Step 2, so the gap is not double-counted:

```css

/* ─────────────────────────────────────────────────────────────────
   Ability radar (per character) + Layout B
   ───────────────────────────────────────────────────────────────── */
.abilities-layout {
  display: flex;
  align-items: center;
  gap: 28px;
}

.ability-radar {
  flex: 0 0 250px;
  width: 250px;
  height: 250px;
  display: block;
}
.ability-radar .ar-grid       { stroke: var(--rule); fill: none; stroke-width: 0.75; }
.ability-radar .ar-grid-outer { stroke: var(--rule-strong); }
.ability-radar .ar-axis       { stroke: var(--rule); stroke-width: 0.75; opacity: 0.6; transition: stroke 0.2s, opacity 0.2s, stroke-width 0.2s; }
.ability-radar .ar-axis.hot   { stroke: var(--brass-hi); opacity: 1; stroke-width: 1.4; }
.ability-radar .ar-shape      { fill: rgba(184,137,74,0.17); stroke: var(--brass-hi); stroke-width: 1.7; stroke-linejoin: round; filter: drop-shadow(0 0 7px rgba(184,137,74,0.5)); }
.ability-radar .ar-dot        { fill: var(--brass-hi); transition: r 0.15s; }
.ability-radar .ar-dot-prof   { fill: var(--seal); }
.ability-radar .ar-dot.hot    { r: 6; }
.ability-radar .ar-label      { fill: var(--paper); font-family: 'IBM Plex Sans', sans-serif; font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase; transition: fill 0.2s; }
.ability-radar .ar-label.hot  { fill: var(--brass-hi); }
.ability-radar .ar-tick       { fill: var(--paper-dim); font-family: 'IBM Plex Sans', sans-serif; font-size: 8px; opacity: 0.7; }
.ability-radar .ar-sector     { fill: transparent; cursor: pointer; transition: fill 0.18s ease; }
.ability-radar .ar-sector.hot { fill: rgba(184,137,74,0.10); }

.stat-card { transition: background 0.2s, box-shadow 0.2s; }
.stat-card.hot {
  background: #241d15;
  box-shadow: inset 0 0 0 1px var(--brass);
}

@media (prefers-reduced-motion: reduce) {
  .ability-radar .ar-axis,
  .ability-radar .ar-dot,
  .ability-radar .ar-label,
  .ability-radar .ar-sector { transition: none; }
}
```

- [ ] **Step 4: Commit**

```bash
git add site/styles.css
git commit -m "(feat) Style ability radar and Layout B"
```

---

### Task 6: Reveal + linked-hover script

One new IIFE appended to the inline page script. No geometry — it reads the server-rendered shape, animates it from center on tab activation, and toggles `.hot` between wedges and cards.

**Files:**
- Modify: `build/templates/_script.html` — append at the very end of the file (after the final Archetype-badge IIFE).

- [ ] **Step 1: Append the IIFE**

Add to the end of `build/templates/_script.html`:

```html

    // --- Ability radar: draw-on reveal + linked pie-slice hover ---
    (function () {
      const reduce = window.matchMedia
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const CX = 120, CY = 120, DUR = 700;

      function parsePoints(str) {
        return str.trim().split(/\s+/).map(p => {
          const xy = p.split(',');
          return [parseFloat(xy[0]), parseFloat(xy[1])];
        });
      }
      function setShape(svg, pts) {
        const poly = svg.querySelector('.ar-shape');
        const dots = svg.querySelectorAll('.ar-dot');
        poly.setAttribute('points', pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '));
        for (let i = 0; i < dots.length; i++) {
          if (pts[i]) { dots[i].setAttribute('cx', pts[i][0].toFixed(1)); dots[i].setAttribute('cy', pts[i][1].toFixed(1)); }
        }
      }
      function targetFor(svg) {
        if (!svg._radarTarget) svg._radarTarget = parsePoints(svg.querySelector('.ar-shape').getAttribute('points'));
        return svg._radarTarget;
      }
      function reveal(svg) {
        const target = targetFor(svg);
        if (reduce) { setShape(svg, target); return; }
        let t0 = null;
        function step(now) {
          if (t0 === null) t0 = now;
          const t = Math.min(1, (now - t0) / DUR), e = 1 - Math.pow(1 - t, 3);
          setShape(svg, target.map(p => [CX + (p[0] - CX) * e, CY + (p[1] - CY) * e]));
          if (t < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
      }

      function wireHover(panel) {
        const svg = panel.querySelector('.ability-radar');
        if (!svg) return;
        function setHot(i, on) {
          ['.ar-axis', '.ar-label', '.ar-dot', '.ar-sector'].forEach(sel => {
            const el = svg.querySelector(sel + '[data-i="' + i + '"]');
            if (el) el.classList.toggle('hot', on);
          });
          const card = panel.querySelector('.stat-card[data-i="' + i + '"]');
          if (card) card.classList.toggle('hot', on);
        }
        svg.querySelectorAll('.ar-sector').forEach(sec => {
          const i = sec.getAttribute('data-i');
          sec.addEventListener('mouseenter', () => setHot(i, true));
          sec.addEventListener('mouseleave', () => setHot(i, false));
        });
        panel.querySelectorAll('.stat-card').forEach(card => {
          const i = card.getAttribute('data-i');
          card.addEventListener('mouseenter', () => setHot(i, true));
          card.addEventListener('mouseleave', () => setHot(i, false));
        });
      }

      const panels = document.querySelectorAll('.character');
      panels.forEach(p => {
        const svg = p.querySelector('.ability-radar');
        if (svg) targetFor(svg);   // cache the real target before any reveal collapses it
        wireHover(p);              // wireHover early-returns when the panel has no radar
      });

      // Replay the draw-on whenever a panel becomes active (every tab switch).
      const obs = new MutationObserver(muts => {
        muts.forEach(m => {
          const p = m.target;
          if (p.classList && p.classList.contains('active')) {
            const svg = p.querySelector('.ability-radar');
            if (svg) reveal(svg);
          }
        });
      });
      panels.forEach(p => obs.observe(p, { attributes: true, attributeFilter: ['class'] }));

      // Reveal whichever panel is already active at load (e.g. a deep-linked hash).
      panels.forEach(p => {
        if (p.classList.contains('active')) {
          const svg = p.querySelector('.ability-radar');
          if (svg) reveal(svg);
        }
      });
    })();
```

Note: the `company` and `gm` panels carry no `.ability-radar`, so they never reach `reveal` — both the active-at-load loop and the MutationObserver `querySelector('.ability-radar')` and guard on the result, and `wireHover` early-returns when the panel has no radar.

- [ ] **Step 2: Commit**

```bash
git add build/templates/_script.html
git commit -m "(feat) Animate radar reveal and link hover to ability cards"
```

---

### Task 7: Rebuild the site and verify end-to-end

Render the page and verify the radar renders, animates, and links — then commit the rebuilt artifact.

**Files:**
- Modify (generated): `site/index.html`

- [ ] **Step 1: Re-render the site**

Run: `.venv/bin/python build/render.py`
Expected: exits 0, prints its `render.py: ...` status lines, no validation errors.

- [ ] **Step 2: Confirm the SVG is in the output**

Run: `grep -c 'class="ability-radar"' site/index.html`
Expected: `6` (one radar per non-GM character).

Run: `grep -o 'class="ar-sector"' site/index.html | wc -l`
Expected: `36` (6 wedges × 6 characters).

- [ ] **Step 3: Visual verification in the preview server**

Run: `python3 -m http.server 8765 --bind 127.0.0.1 --directory site`
Open `http://127.0.0.1:8765/` and check, on a character tab (e.g. Anton):
- Radar sits to the **left** of a 3×2 block of ability cards (Layout B).
- Switching to that character's tab makes the shape **draw on from the center**; switching away and back replays it.
- The polygon's reach matches the scores (high stats near the rim, low stats near the center); proficient-save vertices are **seal-red**.
- Hovering anywhere in a wedge highlights that stat's axis/dot/label **and** its card; hovering a card highlights the wedge in return.
- The six stat cards still show score, modifier, and the `Save ±N` line (proficient saves still **brass** on the card).

Stop the server with Ctrl-C when done.

- [ ] **Step 4: Confirm reduced-motion (optional but recommended)**

In the browser devtools, emulate `prefers-reduced-motion: reduce` (Rendering tab), reload, switch tabs: the shape should appear **fully drawn with no animation**, and hover linking should still work.

- [ ] **Step 5: Commit the rebuilt artifact**

```bash
git add site/index.html
git commit -m "(build) Render ability radars into the site"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** Layout B (Task 4/5), score-based 8→20 scale (Task 1 constants), draw-on reveal on every activation (Task 6 MutationObserver), linked pie-slice hover (Task 1 sectors + Task 6), seal-red proficient dots (Task 1 flag + Task 5 `.ar-dot-prof`), no ghost / no company radar / GM excluded (Task 2 filter, partial only in non-GM loop), reduced-motion (Task 5/6), tests (Task 1). All spec requirements map to a task.
- **Graceful degradation:** the SVG is fully server-rendered (Task 3), so it is correct with JS off; the script only enhances.
- **Naming consistency:** `radar_by_id`, `compute_radar`, `.ability-radar`, `.ar-shape`, `.ar-dot(-prof)`, `.ar-sector`, `.ar-axis`, `.ar-label`, `.ar-tick`, `data-i`, `.stat-card.hot` are used identically across Python, template, CSS, and JS tasks.
- **After all tasks:** run `.venv/bin/pytest tests/ -q` once more; open a PR from `feature/ability-radar`. PR test-plan items must be tickable at review time (no "next build" deferrals).
