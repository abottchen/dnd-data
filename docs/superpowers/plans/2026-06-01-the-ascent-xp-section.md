# The Ascent — XP Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Repo commit rule (overrides defaults):** Commit messages must **never reference Claude** and must carry **no trailers** (no `Co-Authored-By`, no `Generated with`). If you dispatch subagents to commit, tell them this explicitly — they do not inherit it.

**Goal:** Add a party-wide "The Ascent" section (§IX) to the Company tab that visualizes cumulative XP climbing toward the next level, with a source-of-XP breakdown and an AI-authored one-line "character read."

**Architecture:** Two parts. **Part A** is deterministic rendering: a new optional source file `data/xp-log.json` is loaded by `build/render.py`, a new `compute_ascent()` computes the chart geometry server-side (mirroring `compute_other_dice`), a new `_ascent.html` partial emits the SVG, a new IIFE in `_script.html` wires tooltips + hover highlight + the load animation, and the component CSS is lifted from the existing visual mockup (`site/xp-mockup.html`) into `styles.css`. **Part B** makes the one-line "character read" dynamic via a `refresh-ascent-read` transformer that mirrors `refresh-intro-epithet` exactly (single `"all"` slice, marker-gated, writes `site.json["ascent_read"]`).

**Tech Stack:** Python 3 (stdlib + Jinja2), pytest, jsonschema. No new dependencies. Run Python via `.venv/bin/python` and tests via `.venv/bin/pytest`.

---

## Reference artifact

`site/xp-mockup.html` is the approved visual prototype. It contains the final CSS (the `.ascent-*`, `.whence-*` rules and the `--c-*` type-color variables) and the chart logic built in JS. This plan **ports** it: geometry moves from JS into `compute_ascent()` (Python), the SVG becomes a server-rendered Jinja partial, and the JS shrinks to interaction-only. The mockup file is deleted in the final task.

Key data facts (party at time of writing): total **900 XP = Level 3**, **1,800 to Level 4**; by type Combat 337 · Milestone 308 · Quest 90 · Roleplay 90 · Discovery 75. The 5e (2024) XP table is identical to 2014 for these levels.

---

## File Structure

**Part A (renderer + chart):**
- Modify `build/render.py` — add `LEVEL_XP` table + `_level_for_xp()`/`_next_threshold()` helpers; add `compute_ascent()`; load `data/xp-log.json` (optional) in `load_data()`; add `"ascent"` to the `compute_all()` context dict.
- Create `build/templates/_ascent.html` — server-rendered SVG section partial (the §IX block).
- Modify `build/templates/_company.html` — insert `_ascent.html` after the Silent Roll `</section>`.
- Modify `build/templates/_script.html` — append one IIFE: ascent tooltips + hover highlight + draw/pulse triggers.
- Modify `site/styles.css` — add `--c-*` vars + `.ascent-*` / `.whence-*` rules (lifted from the mockup, colors moved to type classes).
- Create `tests/fixtures/sample_xp_log.json` — fixture for tests.
- Modify `tests/test_loaders.py` — assert `load_data` returns `xp_log` and tolerates a missing file.
- Create `tests/test_ascent.py` — unit tests for the XP table helpers + `compute_ascent()`.

**Part B (dynamic prose):**
- Modify `build/slices.py` — add `refresh_ascent_read()` slice builder.
- Modify `build/apply.py` — add `apply_refresh_ascent_read()`.
- Modify `build/registry.py` — register the transformer.
- Create `.claude/prompts/refresh-ascent-read.md` + `.claude/prompts/refresh-ascent-read.schema.json`.
- Modify `build/render.py` — `compute_ascent()` reads `site["ascent_read"]` with a static fallback (the field is optional, not validation-gated).
- Modify `tests/test_registry.py` — add the new transformer name to the expected set.
- Modify `tests/test_slices.py` — test the new slice builder's marker gating.
- Modify `tests/test_apply.py` — test `apply_refresh_ascent_read`.

---

# PART A — Renderer + chart

### Task A1: XP threshold helpers

**Files:**
- Modify: `build/render.py` (add near the other small helpers, e.g. just above `def _to_roman`)
- Test: `tests/test_ascent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ascent.py`:

```python
"""Tests for the XP-threshold helpers and compute_ascent geometry."""
from build import render


def test_level_for_xp_boundaries():
    assert render._level_for_xp(0) == 1
    assert render._level_for_xp(299) == 1
    assert render._level_for_xp(300) == 2
    assert render._level_for_xp(899) == 2
    assert render._level_for_xp(900) == 3      # party sits exactly here
    assert render._level_for_xp(2699) == 3
    assert render._level_for_xp(2700) == 4


def test_next_threshold():
    assert render._next_threshold(2) == 900
    assert render._next_threshold(3) == 2700
    assert render._next_threshold(20) is None  # capped
```

- [ ] **Step 2: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_ascent.py -q`
Expected: FAIL — `AttributeError: module 'build.render' has no attribute '_level_for_xp'`.

- [ ] **Step 3: Implement the helpers**

Add to `build/render.py` (place above `def _to_roman`):

```python
# D&D 5e (2024) cumulative XP per level — identical to 2014 at all tiers.
LEVEL_XP = {
    1: 0, 2: 300, 3: 900, 4: 2700, 5: 6500, 6: 14000, 7: 23000,
    8: 34000, 9: 48000, 10: 64000, 11: 85000, 12: 100000, 13: 120000,
    14: 140000, 15: 165000, 16: 195000, 17: 225000, 18: 265000,
    19: 305000, 20: 355000,
}


def _level_for_xp(total: int) -> int:
    """Highest level whose threshold is <= total."""
    lvl = 1
    for l in range(1, 21):
        if total >= LEVEL_XP[l]:
            lvl = l
    return lvl


def _next_threshold(level: int) -> Optional[int]:
    """XP needed for the next level, or None at level 20."""
    return LEVEL_XP.get(level + 1)
```

(`Optional` is already imported at the top of `render.py`.)

- [ ] **Step 4: Run it and confirm pass**

Run: `.venv/bin/pytest tests/test_ascent.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_ascent.py
git commit -m "feat(render): add 5e XP threshold helpers"
```

---

### Task A2: `compute_ascent()` geometry

**Files:**
- Modify: `build/render.py` (add `compute_ascent()` near the other `compute_*` functions, e.g. after `compute_other_dice`)
- Create: `tests/fixtures/sample_xp_log.json`
- Test: `tests/test_ascent.py`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/sample_xp_log.json` (a trimmed but representative slice — two sessions, mixed types, a level-up crossing):

```json
{
  "entries": [
    { "id": "a", "date": "2026-04-19", "sessionId": "s1", "title": "Reached Port Nyanzaru", "type": "milestone", "source": "Survived the voyage", "perPc": 300 },
    { "id": "b", "date": "2026-04-26", "sessionId": "s2", "title": "Winning the Dinosaur Race", "type": "roleplay", "source": "A triumph of nerve", "perPc": 90 },
    { "id": "c", "date": "2026-05-03", "sessionId": "s3", "title": "Temple of Tymora defense", "type": "combat", "source": "Skeletons and zombies", "perPc": 220 },
    { "id": "d", "date": "2026-05-31", "sessionId": "s4", "title": "Discovered Fort Righteous", "type": "discovery", "source": "A ruin in the green", "perPc": 75 },
    { "id": "e", "date": "2026-05-31", "sessionId": "s4", "title": "Fort Righteous puzzle", "type": "quest", "source": "The alchemy jug", "perPc": 90 },
    { "id": "f", "date": "2026-05-31", "sessionId": "s4", "title": "First puzzle in Chult", "type": "milestone", "source": "A rounding error", "perPc": 125 }
  ]
}
```

(Totals: 300, 390, 610, 685, 775, **900** — lands exactly on Level 3 for a clean level-up assertion.)

- [ ] **Step 2: Write the failing test**

Append to `tests/test_ascent.py`:

```python
import json
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures" / "sample_xp_log.json"


def _load_fixture():
    return json.loads(FIX.read_text())


def test_compute_ascent_none_when_empty():
    assert render.compute_ascent({"entries": []}) is None
    assert render.compute_ascent(None) is None


def test_compute_ascent_cumulative_and_summary():
    a = render.compute_ascent(_load_fixture())
    # 7 nodes: a ground node at 0 plus 6 deeds
    assert len(a["nodes"]) == 7
    assert a["nodes"][0]["total"] == 0
    assert a["nodes"][0]["type"] is None
    assert [n["total"] for n in a["nodes"]] == [0, 300, 390, 610, 685, 775, 900]
    assert a["total"] == 900
    assert a["level_num"] == 3
    assert a["level"] == "III"
    assert a["next_threshold"] == 2700
    assert a["to_next"] == 1800
    assert a["deeds"] == 6
    assert a["sessions"] == 4
    assert a["richest_xp"] == 300
    assert a["richest_title"] == "Reached Port Nyanzaru"


def test_compute_ascent_levelups_and_sources():
    a = render.compute_ascent(_load_fixture())
    ups = {n["total"]: n["up"] for n in a["nodes"] if n["up"]}
    assert ups == {300: "II", 900: "III"}      # the two threshold crossings
    src = {s["type"]: s["xp"] for s in a["sources"]}
    assert src == {"milestone": 425, "combat": 220, "quest": 90, "roleplay": 90, "discovery": 75}
    # ymax is the next threshold; thresholds within (0, ymax] are II, III, IV
    assert a["ymax"] == 2700
    assert [t["lvl"] for t in a["thresholds"]] == ["II", "III", "IV"]
    assert a["thresholds"][-1]["top"] is True


def test_compute_ascent_geometry_well_formed():
    a = render.compute_ascent(_load_fixture())
    assert a["line_d"].startswith("M ")
    assert a["area_d"].endswith(" Z")
    # every node x is inside the plot box, ascending left to right
    xs = [n["cx"] for n in a["nodes"]]
    assert xs == sorted(xs)
    assert a["plot_left"] <= xs[0] and xs[-1] <= a["plot_right"]
    # session ticks: one per distinct session (4), the s4 group is multi
    assert len(a["ticks"]) == 4
    assert a["ticks"][-1]["multi"] is True
```

- [ ] **Step 3: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_ascent.py -q`
Expected: FAIL — `AttributeError: module 'build.render' has no attribute 'compute_ascent'`.

- [ ] **Step 4: Implement `compute_ascent()`**

Add to `build/render.py` (after `compute_other_dice`):

```python
# Ascent chart viewBox + plot margins (mirrors the other-dice geometry style:
# coordinates are computed here; the template emits static SVG).
_ASCENT_W, _ASCENT_H = 1000, 440
_ASCENT_ML, _ASCENT_MR, _ASCENT_MT, _ASCENT_MB = 60, 128, 26, 52


def compute_ascent(xp_log: Optional[dict]) -> Optional[dict]:
    """Cumulative-XP climb for the Company tab. Returns None when there are no
    XP entries (template renders an empty state). Geometry is server-side so
    the chart matches the established other-dice/patron-die pattern."""
    entries = (xp_log or {}).get("entries", [])
    if not entries:
        return None

    # Chronological; stable sort preserves the GM's intra-day authoring order
    # (so a closing "rounding error" event stays last within its session).
    ev = sorted(entries, key=lambda e: e.get("date", ""))

    nodes = [{"label": "Where it began", "type": None, "gain": 0, "total": 0,
              "date": "", "source": "Level 1 · the road begins", "session_id": ""}]
    running = 0
    for e in ev:
        running += int(e.get("perPc", 0))
        nodes.append({
            "label": e.get("title", ""),
            "type": e.get("type"),
            "gain": int(e.get("perPc", 0)),
            "total": running,
            "date": _short_date(e["date"]) if e.get("date") else "",
            "source": e.get("source", ""),
            "session_id": e.get("sessionId", ""),
        })

    total = running
    level = _level_for_xp(total)
    nxt = _next_threshold(level)
    ymax = nxt if nxt else max(total, 1)
    to_next = (nxt - total) if nxt else 0

    plot_w = _ASCENT_W - _ASCENT_ML - _ASCENT_MR
    plot_h = _ASCENT_H - _ASCENT_MT - _ASCENT_MB
    n_seg = len(nodes) - 1

    def fx(i):
        return round(_ASCENT_ML + plot_w * (i / n_seg if n_seg else 0), 2)

    def fy(v):
        return round(_ASCENT_MT + plot_h * (1 - v / ymax), 2)

    ybase = fy(0)

    # node coordinates + level-up crossings
    prev = 0
    for i, nd in enumerate(nodes):
        nd["i"] = i
        nd["cx"] = fx(i)
        nd["cy"] = fy(nd["total"])
        up = None
        for l in range(2, 21):
            if prev < LEVEL_XP[l] <= nd["total"]:
                up = _to_roman(l)
        nd["up"] = up
        nd["r"] = 6.5 if up else (3.5 if i == 0 else 5)
        prev = nd["total"]

    # threshold lines visible within (0, ymax]
    thresholds = []
    for l in range(2, 21):
        v = LEVEL_XP[l]
        if v > ymax:
            break
        thresholds.append({"v": v, "lvl": _to_roman(l), "y": fy(v), "top": v == ymax})

    # session date ticks: group consecutive nodes sharing a sessionId
    groups: list[dict] = []
    for nd in nodes[1:]:
        sid = nd["session_id"]
        if groups and groups[-1]["sid"] == sid:
            groups[-1]["xs"].append(nd["cx"])
            groups[-1]["date"] = nd["date"]
        else:
            groups.append({"sid": sid, "xs": [nd["cx"]], "date": nd["date"]})
    ticks = [{
        "x": round(sum(g["xs"]) / len(g["xs"]), 2),
        "x0": g["xs"][0], "x1": g["xs"][-1],
        "label": g["date"], "multi": len(g["xs"]) > 1,
    } for g in groups]

    # path strings
    line_d = "M " + " L ".join(f"{nd['cx']} {nd['cy']}" for nd in nodes)
    area_d = (f"M {nodes[0]['cx']} {ybase} "
              + " ".join(f"L {nd['cx']} {nd['cy']}" for nd in nodes)
              + f" L {nodes[-1]['cx']} {ybase} Z")

    # by-type breakdown for the source bar (descending)
    by_type: dict[str, int] = {}
    for e in ev:
        t = e.get("type") or "other"
        by_type[t] = by_type.get(t, 0) + int(e.get("perPc", 0))
    sources = [{
        "type": t, "label": t.capitalize(), "xp": x,
        "pct": round(x / total * 100) if total else 0,
    } for t, x in sorted(by_type.items(), key=lambda kv: -kv[1])]

    richest = max(ev, key=lambda e: int(e.get("perPc", 0)))

    return {
        "view_w": _ASCENT_W, "view_h": _ASCENT_H,
        "plot_left": _ASCENT_ML, "plot_right": round(_ASCENT_ML + plot_w, 2),
        "ybase": ybase, "ymax": ymax,
        "nodes": nodes, "thresholds": thresholds, "ticks": ticks,
        "line_d": line_d, "area_d": area_d,
        "proj_y": fy(total),
        "road_x": round(_ASCENT_ML + plot_w * 0.52, 2),
        "road_y": fy((total + ymax) / 2),
        "last_cx": nodes[-1]["cx"], "last_cy": nodes[-1]["cy"],
        "sources": sources,
        "total": total, "level": _to_roman(level), "level_num": level,
        "to_next": to_next, "next_threshold": nxt,
        "deeds": len(ev), "sessions": len({e.get("sessionId") for e in ev}),
        "richest_xp": int(richest.get("perPc", 0)),
        "richest_title": richest.get("title", ""),
    }
```

- [ ] **Step 5: Run it and confirm pass**

Run: `.venv/bin/pytest tests/test_ascent.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add build/render.py tests/test_ascent.py tests/fixtures/sample_xp_log.json
git commit -m "feat(render): compute cumulative XP ascent geometry"
```

---

### Task A3: Load `data/xp-log.json` (optional) and add to context

**Files:**
- Modify: `build/render.py` — `load_data()` (after the session-log load) and `compute_all()` (context dict)
- Modify: `tests/test_loaders.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loaders.py`:

```python
def test_load_data_loads_xp_log_when_present(tmp_path: Path):
    (tmp_path / "party.json").write_text('{"members": []}')
    (tmp_path / "session-log.json").write_text('{"entries": []}')
    (tmp_path / "dice").mkdir()
    (tmp_path / "xp-log.json").write_text(
        '{"entries": [{"id": "a", "date": "2026-04-19", "sessionId": "s1", '
        '"title": "T", "type": "combat", "perPc": 50}]}')
    data = load_data(tmp_path)
    assert data["xp_log"]["entries"][0]["perPc"] == 50


def test_load_data_tolerates_missing_xp_log(tmp_path: Path):
    (tmp_path / "party.json").write_text('{"members": []}')
    (tmp_path / "session-log.json").write_text('{"entries": []}')
    (tmp_path / "dice").mkdir()
    data = load_data(tmp_path)          # no xp-log.json on disk
    assert data["xp_log"] == {"entries": []}
```

- [ ] **Step 2: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_loaders.py -q -k xp_log`
Expected: FAIL — `KeyError: 'xp_log'`.

- [ ] **Step 3: Implement the optional load**

In `build/render.py`, inside `load_data()`, immediately after the `session-log.json` block (before the `dice_paths = ...` line), add:

```python
    # XP log (optional — gitignored, dropped in by the GM after each session).
    # Cold-start safe: a fresh clone with no xp-log.json still renders.
    xp_path = data_dir / "xp-log.json"
    xp_log = json.loads(xp_path.read_text()) if xp_path.exists() else {"entries": []}
```

Then add `"xp_log": xp_log,` to the returned dict at the end of `load_data()` (alongside `"session_log": session_log,`).

- [ ] **Step 4: Wire it into the context**

In `compute_all()`, add a line near the other `compute_*` calls:

```python
    ascent = compute_ascent(data.get("xp_log"))
```

and add `"ascent": ascent,` to the returned context dict (e.g. right after `"patron_die": patron,`).

- [ ] **Step 5: Run the loader + ascent tests**

Run: `.venv/bin/pytest tests/test_loaders.py tests/test_ascent.py -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add build/render.py tests/test_loaders.py
git commit -m "feat(render): load optional data/xp-log.json into the context"
```

---

### Task A4: CSS — lift component styles into `styles.css`

**Files:**
- Modify: `site/styles.css` (append a new section at the end)
- Reference: `site/xp-mockup.html` `<style>` block

- [ ] **Step 1: Copy the component rules**

Open `site/xp-mockup.html`. From its `<style>` block, copy the rule groups for: the `--c-*` variables, `.ascent`, `.ascent-chart`, `.ascent-band`, `.ascent-grid`, `.ascent-threshold`, `.ascent-axis`, `.ascent-lvl-tag`, `.ascent-lvl-xp`, `.ascent-tick`, `.ascent-session-bracket`, `.ascent-area`, `.ascent-line`, `.ascent-projection`, `.ascent-roadtext`, `.ascent-node` (incl. `.up`, `.pop`, `.halo`, `.active`, the `ascentPop` keyframe), `.ascent-guide`, `.ascent-pulse` (+ `ascentPulse` keyframe), `.ascent-uptag` (+ `fadeIn`), `.ascent-hit`, `.whence`, `.whence-bar`, `.whence-seg` (+ spotlight/zoom hover + `whenceGrow`), `.whence-seg .seg-pct`, `.whence-legend`, `.whence-read`, and the `@media (prefers-reduced-motion: reduce)` block.

Append them to the end of `site/styles.css`, under a banner comment:

```css
/* ─────────────────────────────────────────────────────────────────
   The Ascent (XP) — §IX, Company tab
   ───────────────────────────────────────────────────────────────── */
```

- [ ] **Step 2: Move type colors from inline to classes**

The mockup set node/segment colors inline via JS (`style.background = TYPE_COLOR[...]`). The server-rendered version uses type classes instead. Add these rules to the new section:

```css
.ascent-node.t-combat    { fill: var(--c-combat); }
.ascent-node.t-milestone { fill: var(--c-milestone); }
.ascent-node.t-quest     { fill: var(--c-quest); }
.ascent-node.t-discovery { fill: var(--c-discovery); }
.ascent-node.t-roleplay  { fill: var(--c-roleplay); }
.ascent-node.t-none,
.ascent-node.t-other     { fill: var(--paper-dim); }

.whence-seg.t-combat    { background: var(--c-combat); }
.whence-seg.t-milestone { background: var(--c-milestone); }
.whence-seg.t-quest     { background: var(--c-quest); }
.whence-seg.t-discovery { background: var(--c-discovery); }
.whence-seg.t-roleplay  { background: var(--c-roleplay); }
.whence-seg.t-other     { background: var(--brass-dim); }

/* discovery swatch is light → dark percentage text */
.whence-seg.t-discovery .seg-pct { color: var(--paper); }
```

Confirm the `:root { --c-combat: var(--seal); ... }` block from the mockup is included (these vars are required by the rules above).

- [ ] **Step 3: Sanity check the stylesheet parses**

Run: `.venv/bin/python -c "open('site/styles.css').read(); print('css read ok')"`
Expected: `css read ok` (this only checks the file is readable; visual verification happens in Task A7).

- [ ] **Step 4: Commit**

```bash
git add site/styles.css
git commit -m "feat(styles): add The Ascent component styles"
```

---

### Task A5: Template partial `_ascent.html`

**Files:**
- Create: `build/templates/_ascent.html`
- Modify: `build/templates/_company.html`

- [ ] **Step 1: Create the partial**

Create `build/templates/_ascent.html`:

```jinja2
{% import "_macros.html" as m %}
<section class="company-section">
  {{ m.section_head("IX", "The Long Climb", "The Ascent",
     "Every blow struck, every riddle unknotted, every horizon crossed — set down in the long account of experience.") }}
  {%- if not ascent %}
  <p class="fortune-empty">No experience yet recorded for the company.</p>
  {%- else %}

  <div class="ledger-grid lead">
    <div class="ledger-cell">
      <div class="ledger-eyebrow">XP Earned</div>
      <div class="ledger-val">{{ "{:,}".format(ascent.total) }}</div>
      <div class="ledger-sub">Level <b>{{ ascent.level }}</b> attained</div>
    </div>
    <div class="ledger-cell">
      <div class="ledger-eyebrow">Richest Haul</div>
      <div class="ledger-val">{{ ascent.richest_xp }}</div>
      <div class="ledger-sub">{{ ascent.richest_title }}</div>
    </div>
    <div class="ledger-cell">
      <div class="ledger-eyebrow">Deeds Recorded</div>
      <div class="ledger-val">{{ ascent.deeds }}</div>
      <div class="ledger-sub">across <b>{{ ascent.sessions }}</b> sessions</div>
    </div>
    <div class="ledger-cell">
      <div class="ledger-eyebrow">To Ascension</div>
      <div class="ledger-val">{{ "{:,}".format(ascent.to_next) }}</div>
      <div class="ledger-sub seal">Level {{ (ascent.level_num + 1) | roman }} at <b>{{ "{:,}".format(ascent.next_threshold) }}</b></div>
    </div>
  </div>

  {{ m.sub_head("The Climb to " ~ (ascent.level_num + 1) | roman) }}
  <div class="ascent">
    <svg class="ascent-chart" viewBox="0 0 {{ ascent.view_w }} {{ ascent.view_h }}" role="img"
         aria-label="Cumulative party experience climbing toward the next level">
      <defs>
        <linearGradient id="ascentFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(184,137,74,0.34)"/>
          <stop offset="100%" stop-color="rgba(184,137,74,0.02)"/>
        </linearGradient>
      </defs>

      {%- for t in ascent.thresholds %}
      <line class="ascent-threshold{% if t.top %} top{% endif %}" x1="{{ ascent.plot_left }}" y1="{{ t.y }}" x2="{{ ascent.plot_right }}" y2="{{ t.y }}"/>
      <text class="ascent-lvl-tag" x="{{ ascent.plot_right + 16 }}" y="{{ t.y - 2 }}">Lv {{ t.lvl }}</text>
      <text class="ascent-lvl-xp" x="{{ ascent.plot_right + 16 }}" y="{{ t.y + 11 }}">{{ "{:,}".format(t.v) }} XP</text>
      {%- endfor %}

      <line class="ascent-axis" x1="{{ ascent.plot_left }}" y1="{{ ascent.ybase }}" x2="{{ ascent.plot_right }}" y2="{{ ascent.ybase }}"/>

      {%- for tk in ascent.ticks %}
      <text class="ascent-tick" x="{{ tk.x }}" y="{{ ascent.ybase + 30 }}">{{ tk.label }}</text>
      {%- if tk.multi %}<line class="ascent-session-bracket" x1="{{ tk.x0 }}" y1="{{ ascent.ybase + 12 }}" x2="{{ tk.x1 }}" y2="{{ ascent.ybase + 12 }}"/>{% endif %}
      {%- endfor %}

      <path class="ascent-area" d="{{ ascent.area_d }}"/>
      <path class="ascent-line" d="{{ ascent.line_d }}"/>
      <path class="ascent-projection" d="M {{ ascent.last_cx }} {{ ascent.proj_y }} L {{ ascent.plot_right }} {{ ascent.proj_y }}"/>
      <text class="ascent-roadtext" x="{{ ascent.road_x }}" y="{{ ascent.road_y }}">
        <tspan class="big" x="{{ ascent.road_x }}" dy="0">{{ "{:,}".format(ascent.to_next) }} XP</tspan>
        <tspan x="{{ ascent.road_x }}" dy="18">the road to Level {{ (ascent.level_num + 1) | roman }}</tspan>
      </text>

      <line class="ascent-guide" x1="0" y1="0" x2="0" y2="0"/>

      {%- for n in ascent.nodes %}
      <circle class="ascent-node t-{{ n.type or 'none' }}{% if n.up %} up halo{% endif %}" cx="{{ n.cx }}" cy="{{ n.cy }}" r="{{ n.r }}" style="animation-delay:{{ '%.2f'|format(0.7 + n.i * 0.13) }}s"/>
      {%- if n.up %}<text class="ascent-uptag" x="{{ n.cx }}" y="{{ n.cy - 16 }}" style="animation-delay:{{ '%.2f'|format(1.0 + n.i * 0.13) }}s">Lv {{ n.up }}</text>{% endif %}
      <circle class="ascent-hit" cx="{{ n.cx }}" cy="{{ n.cy }}" r="18"
              data-i="{{ n.i }}" data-cx="{{ n.cx }}" data-cy="{{ n.cy }}" data-ybase="{{ ascent.ybase }}"
              data-gain="{{ n.gain }}" data-total="{{ n.total }}" data-type="{{ n.type or '' }}"
              data-date="{{ n.date }}" data-label="{{ n.label }}" data-note="{{ n.source }}"/>
      {%- endfor %}

      <circle class="ascent-pulse" cx="{{ ascent.last_cx }}" cy="{{ ascent.last_cy }}" r="7"/>
    </svg>
  </div>

  {{ m.sub_head("By What Deeds") }}
  <div class="whence">
    <div class="whence-bar">
      {%- for s in ascent.sources %}
      <div class="whence-seg t-{{ s.type }}" style="--w:{{ s.pct }}%; animation-delay:{{ '%.2f'|format(0.3 + loop.index0 * 0.1) }}s"
           data-label="{{ s.label }}" data-xp="{{ s.xp }}" data-pct="{{ s.pct }}">
        <span class="seg-pct">{% if s.pct >= 4 %}{{ s.pct }}%{% endif %}</span>
      </div>
      {%- endfor %}
    </div>
    <div class="whence-legend">
      {%- for s in ascent.sources %}
      <span class="item"><span class="swatch t-{{ s.type }}"></span>{{ s.label }}</span>
      {%- endfor %}
    </div>
    <p class="whence-read">{{ site.ascent_read }}</p>
  </div>
  {%- endif %}
</section>
```

Notes for the implementer:
- `t-{{ s.type }}` on `.swatch` colors the legend dots; add matching `.swatch.t-combat { background: var(--c-combat); } …` rules to the CSS section from Task A4 (one line per type — mirror the `.whence-seg.t-*` set).
- `site.ascent_read` is provided with a fallback in Task A6; until then it is undefined under `StrictUndefined` and will raise — so **do not render** before Task A6 is done. Task A6 is ordered next for this reason.

- [ ] **Step 2: Include the partial in the Company tab**

In `build/templates/_company.html`, find the Silent Roll section's closing `</section>` (the last `</section>` before `</article>`). Insert immediately after it (and before `</article>`):

```jinja2

  {% include "_ascent.html" %}
```

- [ ] **Step 3: Commit (render verified in A7)**

```bash
git add build/templates/_ascent.html build/templates/_company.html
git commit -m "feat(templates): add The Ascent partial to the Company tab"
```

---

### Task A6: `site.ascent_read` fallback in the renderer

**Files:**
- Modify: `build/render.py` — `compute_all()` (the `site = dict(authored["site"])` area)

- [ ] **Step 1: Add the fallback**

In `compute_all()`, just after `site = dict(authored["site"])` and the existing `site[...] = ...` lines, add:

```python
    site.setdefault(
        "ascent_read",
        "Blade and book in equal measure — the company earns its name as "
        "readily by riddle and road as at the edge of a sword.",
    )
```

This keeps `render.py` runnable standalone before any prose authoring (the field is optional, not validation-gated). Part B replaces it with an authored, regenerating line.

- [ ] **Step 2: Commit**

```bash
git add build/render.py
git commit -m "feat(render): default ascent_read so the section renders pre-authoring"
```

---

### Task A7: Full render + visual verification

**Files:** none modified (verification task)

- [ ] **Step 1: Ensure a real `data/xp-log.json` exists**

The live file is gitignored and supplied by the GM. Confirm it is present:

Run: `ls -l data/xp-log.json`
Expected: the file exists. (If not, the section renders its empty state — still valid, but copy the fixture to preview the chart: `cp tests/fixtures/sample_xp_log.json data/xp-log.json` for local preview only, never commit `data/`.)

- [ ] **Step 2: Run the full render**

Run: `.venv/bin/python -m build.render`
Expected: `render.py: validation passed` then `render.py: rendered .../site/index.html`, exit 0.

- [ ] **Step 3: Grep the artifact for the new section**

Run: `grep -c "ascent-chart\|The Ascent\|By What Deeds" site/index.html`
Expected: a count ≥ 3.

- [ ] **Step 4: Preview and eyeball**

Run: `python3 -m http.server 8765 --bind 127.0.0.1 --directory site` (background), open `http://127.0.0.1:8765/`, click **The Company** tab, scroll to §IX. Verify against `site/xp-mockup.html`: the climb draws on load, level-up nodes glow, hovering a node swells it + drops the plumb-line + shows the tooltip, the source bar segments zoom/spotlight on hover, percentages show on all five bands, the "you are here" pulse breathes on the last node.

(The hover/tooltip JS lands in Task A8 — at this step the static chart + animations render, but tooltips/highlight are not wired yet. Confirm the static SVG looks correct here; re-verify interaction after A8.)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (the renderer smoke + existing tests still green).

- [ ] **Step 6: Commit the rendered artifact**

```bash
git add site/index.html
git commit -m "build: render The Ascent section into the site"
```

---

### Task A8: Client-side IIFE — tooltips, hover highlight, load animation

**Files:**
- Modify: `build/templates/_script.html` (append a new IIFE after the last one)

- [ ] **Step 1: Append the ascent IIFE**

At the end of `build/templates/_script.html`, append:

```javascript
    // ── The Ascent (XP) — tooltips, hover highlight, load animation ──────────
    (function () {
      var svg = document.querySelector('.ascent-chart');
      if (!svg) return;
      var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      var CAP = { combat: 'Combat', milestone: 'Milestone', quest: 'Quest', discovery: 'Discovery', roleplay: 'Roleplay' };

      var line = svg.querySelector('.ascent-line');
      var area = svg.querySelector('.ascent-area');
      var proj = svg.querySelector('.ascent-projection');
      var road = svg.querySelector('.ascent-roadtext');
      var guide = svg.querySelector('.ascent-guide');
      var pulse = svg.querySelector('.ascent-pulse');
      var nodes = svg.querySelectorAll('.ascent-node');
      var uptags = svg.querySelectorAll('.ascent-uptag');

      // Load animation
      if (REDUCED) {
        if (area) area.classList.add('drawn');
        if (proj) proj.classList.add('drawn');
        if (road) road.classList.add('drawn');
        nodes.forEach(function (n) { n.style.transform = 'scale(1)'; });
        uptags.forEach(function (t) { t.style.opacity = 1; });
      } else {
        if (line) {
          var len = line.getTotalLength();
          line.style.strokeDasharray = len;
          line.style.strokeDashoffset = len;
          line.getBoundingClientRect();
          line.style.transition = 'stroke-dashoffset 1.8s cubic-bezier(0.3,0.5,0.2,1) 0.4s';
          line.style.strokeDashoffset = '0';
        }
        if (area) area.classList.add('drawn');
        if (proj) proj.classList.add('drawn');
        if (road) road.classList.add('drawn');
        nodes.forEach(function (n) { n.classList.add('pop'); });
        uptags.forEach(function (t) { t.classList.add('show'); });
        if (pulse) pulse.classList.add('run');
      }

      // map node index -> visible node for hover highlight
      var visByI = {};
      nodes.forEach(function (n, idx) { visByI[idx] = n; });

      var tip = document.querySelector('.dice-tooltip') || (function () {
        var t = document.createElement('div'); t.className = 'dice-tooltip';
        document.body.appendChild(t); return t;
      })();
      var hideTimer;

      svg.querySelectorAll('.ascent-hit').forEach(function (h) {
        var i = h.getAttribute('data-i');
        h.addEventListener('mouseenter', function () {
          clearTimeout(hideTimer);
          var gain = +h.getAttribute('data-gain');
          var total = (+h.getAttribute('data-total')).toLocaleString();
          var type = h.getAttribute('data-type');
          var date = h.getAttribute('data-date');
          var label = h.getAttribute('data-label');
          var note = h.getAttribute('data-note');
          var html = '<div class="tip-val">' + (gain > 0 ? '+' + gain : '&mdash;') + '</div>';
          html += '<div class="tip-ctx" style="color:var(--paper);font-size:13px;text-transform:none;font-family:\'Cormorant Garamond\',serif;">' + label + '</div>';
          var meta = [];
          if (type) meta.push(CAP[type] || type);
          if (date) meta.push(date);
          if (meta.length) html += '<div class="tip-ctx">' + meta.join(' &middot; ') + '</div>';
          if (note) html += '<div class="tip-ctx" style="text-transform:none;font-style:italic;font-family:\'EB Garamond\',serif;font-size:13px;max-width:260px;white-space:normal;margin-top:8px;">' + note + '</div>';
          if (gain > 0) html += '<div class="tip-ctx" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--rule);">Running total &middot; ' + total + ' XP</div>';
          tip.className = 'dice-tooltip tip-wide';
          tip.innerHTML = html;
          var r = h.getBoundingClientRect();
          tip.style.left = (r.left + r.width / 2) + 'px';
          tip.style.top = r.top + 'px';
          tip.classList.add('visible');
          if (visByI[i]) visByI[i].classList.add('active');
          if (guide) {
            guide.setAttribute('x1', h.getAttribute('data-cx'));
            guide.setAttribute('x2', h.getAttribute('data-cx'));
            guide.setAttribute('y1', h.getAttribute('data-cy'));
            guide.setAttribute('y2', h.getAttribute('data-ybase'));
            guide.classList.add('on');
          }
        });
        h.addEventListener('mouseleave', function () {
          hideTimer = setTimeout(function () { tip.classList.remove('visible'); }, 80);
          if (visByI[i]) visByI[i].classList.remove('active');
          if (guide) guide.classList.remove('on');
        });
      });

      svg.parentNode.querySelectorAll('.whence-seg').forEach(function (s) {
        s.addEventListener('mouseenter', function () {
          clearTimeout(hideTimer);
          var html = '<div class="tip-val">' + s.getAttribute('data-xp') + '</div>';
          html += '<div class="tip-ctx">' + s.getAttribute('data-label') + ' &middot; ' + s.getAttribute('data-pct') + '% of all XP</div>';
          tip.className = 'dice-tooltip tip-wide';
          tip.innerHTML = html;
          var r = s.getBoundingClientRect();
          tip.style.left = (r.left + r.width / 2) + 'px';
          tip.style.top = r.top + 'px';
          tip.classList.add('visible');
        });
        s.addEventListener('mouseleave', function () {
          hideTimer = setTimeout(function () { tip.classList.remove('visible'); }, 80);
        });
      });
    })();
```

- [ ] **Step 2: Re-render**

Run: `.venv/bin/python -m build.render`
Expected: exit 0, `rendered`.

- [ ] **Step 3: Verify interaction in the browser**

Reload `http://127.0.0.1:8765/`, Company tab → §IX. Confirm node hover swells the dot + drops the plumb-line + tooltip; bar segment hover zooms/dims; all five percentages show. Confirm no console errors (favicon 404 is fine).

- [ ] **Step 4: Commit**

```bash
git add build/templates/_script.html site/index.html
git commit -m "feat(script): wire The Ascent tooltips, hover highlight, and reveal"
```

---

# PART B — Dynamic "character read" prose

This makes the `.whence-read` line regenerate as the XP distribution shifts, mirroring `refresh-intro-epithet` exactly.

### Task B1: Slice builder `refresh_ascent_read`

**Files:**
- Modify: `build/slices.py`
- Modify: `tests/test_slices.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_slices.py` (uses the existing `slice_env` fixture; add an `xp-log.json` to the fixture copy inline):

```python
def test_refresh_ascent_read_gates_on_marker(slice_env, tmp_path, monkeypatch):
    data, authored = slice_env
    # attach an xp log + a composition so the builder has something to summarize
    data["xp_log"] = {"entries": [
        {"id": "a", "date": "2026-04-19", "sessionId": "s1", "title": "T",
         "type": "combat", "perPc": 100},
    ]}
    authored["site"]["ascent_read"] = "existing read"

    # marker current → no new sessions → still emits one "all" slice carrying
    # new_sessions=[] (refresh transformers always emit; the prompt decides)
    authored["site"]["refreshed_through_session"] = 999
    out = slices.refresh_ascent_read(data, authored)
    assert len(out) == 1
    key, payload = out[0]
    assert key == "all"
    assert payload["existing"] == "existing read"
    assert payload["new_sessions"] == []
    assert payload["composition"][0]["type"] == "combat"

    # marker behind → new sessions surface
    authored["site"]["refreshed_through_session"] = 0
    _, payload2 = slices.refresh_ascent_read(data, authored)[0]
    assert len(payload2["new_sessions"]) == len(data["session_log"]["entries"])
```

- [ ] **Step 2: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_slices.py -q -k ascent_read`
Expected: FAIL — `AttributeError: module 'build.slices' has no attribute 'refresh_ascent_read'`.

- [ ] **Step 3: Implement the builder**

Add to `build/slices.py` (near `refresh_intro_epithet`):

```python
def refresh_ascent_read(data: dict, authored: dict) -> list[tuple]:
    """One slice carrying the new sessions, the current XP-by-type composition,
    and the existing one-line 'character read' for the prompt to weigh."""
    marker = authored["site"].get("refreshed_through_session", 0)
    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1) if i > marker
    ]
    by_type: dict[str, int] = defaultdict(int)
    for e in (data.get("xp_log") or {}).get("entries", []):
        by_type[e.get("type") or "other"] += int(e.get("perPc", 0))
    total = sum(by_type.values())
    composition = [
        {"type": t, "xp": x, "pct": round(x / total * 100) if total else 0}
        for t, x in sorted(by_type.items(), key=lambda kv: -kv[1])
    ]
    return [("all", {
        "new_sessions": new_sessions,
        "composition": composition,
        "existing": authored["site"].get("ascent_read", ""),
    })]
```

(`defaultdict` is already imported at the top of `slices.py`.)

- [ ] **Step 4: Run it and confirm pass**

Run: `.venv/bin/pytest tests/test_slices.py -q -k ascent_read`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build/slices.py tests/test_slices.py
git commit -m "feat(slices): add refresh-ascent-read slice builder"
```

---

### Task B2: Apply function `apply_refresh_ascent_read`

**Files:**
- Modify: `build/apply.py`
- Modify: `tests/test_apply.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_apply.py` (match the file's existing style of constructing an `authored` dict; a minimal `{"site": {...}}` is sufficient):

```python
def test_apply_refresh_ascent_read_rewrite():
    authored = {"site": {"ascent_read": "old"}}
    apply.apply_refresh_ascent_read(
        authored, "all", {}, {"decision": "rewrite",
                              "fields": {"ascent_read": "new line"}, "reason": "x"})
    assert authored["site"]["ascent_read"] == "new line"


def test_apply_refresh_ascent_read_no_change():
    authored = {"site": {"ascent_read": "old"}}
    apply.apply_refresh_ascent_read(
        authored, "all", {}, {"decision": "no_change", "fields": None, "reason": "x"})
    assert authored["site"]["ascent_read"] == "old"
```

- [ ] **Step 2: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_apply.py -q -k ascent_read`
Expected: FAIL — `AttributeError: module 'build.apply' has no attribute 'apply_refresh_ascent_read'`.

- [ ] **Step 3: Implement it**

Add to `build/apply.py` (near `apply_refresh_intro_epithet`):

```python
def apply_refresh_ascent_read(authored: dict, key, slice_data: dict, output: dict) -> None:
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    authored["site"]["ascent_read"] = fields["ascent_read"]
```

- [ ] **Step 4: Run it and confirm pass**

Run: `.venv/bin/pytest tests/test_apply.py -q -k ascent_read`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build/apply.py tests/test_apply.py
git commit -m "feat(apply): add apply_refresh_ascent_read"
```

---

### Task B3: Register the transformer

**Files:**
- Modify: `build/registry.py`
- Modify: `tests/test_registry.py`

- [ ] **Step 1: Update the registry test first**

In `tests/test_registry.py::test_registry_lists_every_transformer`, add `"refresh-ascent-read",` to the expected set.

- [ ] **Step 2: Run it and confirm failure**

Run: `.venv/bin/pytest tests/test_registry.py -q`
Expected: FAIL — the set assertion mismatches (registry does not yet contain `refresh-ascent-read`).

- [ ] **Step 3: Register the transformer**

In `build/registry.py`, add to the `ALL` tuple alongside the other refresh entries:

```python
    Transformer("refresh-ascent-read", "refresh",
                slices.refresh_ascent_read, apply.apply_refresh_ascent_read),
```

- [ ] **Step 4: Run it and confirm pass**

Run: `.venv/bin/pytest tests/test_registry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build/registry.py tests/test_registry.py
git commit -m "feat(registry): wire refresh-ascent-read transformer"
```

---

### Task B4: Prompt + schema

**Files:**
- Create: `.claude/prompts/refresh-ascent-read.md`
- Create: `.claude/prompts/refresh-ascent-read.schema.json`

- [ ] **Step 1: Create the schema**

Create `.claude/prompts/refresh-ascent-read.schema.json`:

```json
{
  "type": "object",
  "required": ["decision", "fields", "reason"],
  "additionalProperties": false,
  "properties": {
    "decision": {
      "type": "string",
      "enum": ["no_change", "rewrite"]
    },
    "fields": {
      "type": ["object", "null"],
      "required": ["ascent_read"],
      "additionalProperties": false,
      "properties": {
        "ascent_read": {"type": "string"}
      }
    },
    "reason": {"type": "string"}
  }
}
```

- [ ] **Step 2: Create the prompt**

Create `.claude/prompts/refresh-ascent-read.md`:

```markdown
---
model: sonnet
---

You are a refresh-evaluation function for the dnd-data site. Read an ascent-read-refresh slice (delivered as JSON on stdin) and decide whether the company's one-line "character read" still fits how they earn their experience.

# Input

The user message is a JSON object with this shape:
- `new_sessions` (array): every session that has landed since the last refresh.
- `composition` (array): XP-by-type totals for the whole campaign, descending — each `{type, xp, pct}`. Types are `combat`, `milestone`, `quest`, `discovery`, `roleplay`.
- `existing` (str): the current one-line character read shown beneath the XP source bar.

# Standing rule (critical)

This line is mostly stable. Rewrite only when the **balance of how the company earns XP has genuinely shifted** — e.g. a party that was combat-dominated has become an exploration/roleplay party, or a new mode (a big discovery or social arc) has clearly entered the mix. A few points of drift in the percentages is not a reason to rewrite.

If the existing line still fits the composition and is good prose by the voice rules, return it unchanged.

# Output

- If unchanged: `decision: "no_change"`, `fields: null`.
- If rewriting: `decision: "rewrite"`, `fields: {ascent_read: "..."}`.
- `reason`: one short sentence naming the composition fact you weighed.

# Voice (only if rewriting)

A single sentence, in the site's register: cool, compact, a touch elegiac. Characterize the company by HOW they earn their legend (steel vs. riddle vs. road vs. word), grounded in the composition. Do not quote raw numbers or percentages. No "Ye Olde", no chrome. Roughly 20–30 words.

# Authorial restraint

- Do not invent deeds, places, or stakes the data does not support.
- Do not rewrite for incremental drift.

# Output format

Return a single JSON object matching the response schema. No markdown fences, no prose outside the JSON.
```

- [ ] **Step 3: Validate the schema parses and the frontmatter is well-formed**

Run:
```bash
.venv/bin/python - <<'PY'
import json, pathlib
json.loads(pathlib.Path(".claude/prompts/refresh-ascent-read.schema.json").read_text())
body = pathlib.Path(".claude/prompts/refresh-ascent-read.md").read_text()
assert body.startswith("---\nmodel: sonnet\n---"), "frontmatter missing/!= sonnet"
print("prompt + schema ok")
PY
```
Expected: `prompt + schema ok`.

- [ ] **Step 4: Commit**

```bash
git add .claude/prompts/refresh-ascent-read.md .claude/prompts/refresh-ascent-read.schema.json
git commit -m "feat(prompts): add refresh-ascent-read prompt and schema"
```

---

### Task B5: End-to-end prepare/apply dry check

**Files:** none modified (verification)

- [ ] **Step 1: Prepare a run**

Run: `.venv/bin/python -m build prepare --force-refresh`
Expected: a run dir under `build/.run/<timestamp>/`; the manifest's `slices[]` includes one entry with `"transformer": "refresh-ascent-read"`.

Verify:
```bash
RUN=$(ls -td build/.run/*/ | head -1)
grep -c "refresh-ascent-read" "$RUN/manifest.json"
```
Expected: ≥ 1.

- [ ] **Step 2: Confirm the slice payload is well-formed**

Run: `cat "$RUN"/pending/refresh-ascent-read*.json`
Expected: JSON with `new_sessions`, `composition` (descending by xp), and `existing`.

- [ ] **Step 3: Full build via the skill (real authoring)**

This is the real end-to-end path the GM will use. In a Claude Code session run `/build-prose`. The dispatched sub-agent authors `refresh-ascent-read`'s result; `apply` validates it against the schema, writes `site.json["ascent_read"]`, bumps the marker (only if every refresh slice succeeded), and re-renders.

Verify after:
```bash
grep -n "ascent_read" build/authored/site.json
grep -c "whence-read" site/index.html
```
Expected: `ascent_read` present in `site.json`; `whence-read` present in the artifact.

- [ ] **Step 4: Commit authored + artifact**

```bash
git add build/authored/site.json site/index.html
git commit -m "build: author the ascent character read and render"
```

---

### Task C1: Remove the mockup harness

**Files:**
- Delete: `site/xp-mockup.html`

- [ ] **Step 1: Confirm the production section fully supersedes the mockup**

Run: `grep -c "ascent-chart" site/index.html`
Expected: ≥ 1 (the real section is live).

- [ ] **Step 2: Delete and commit**

```bash
git rm site/xp-mockup.html
git commit -m "chore: remove the XP mockup harness, superseded by §IX"
```

---

## Self-Review

**1. Spec coverage**
- Cumulative XP chart climbing to next level → Tasks A2 (geometry), A5 (template), A8 (interaction). ✔
- Source-of-XP breakdown bar + percentages (incl. the Discovery fix at ≥4%) → A2 (`sources`), A5 (bar), A4 (colors). ✔
- Headline ledger numbers → A2 (`total`/`level`/`to_next`/`richest`/`deeds`/`sessions`), A5 (ledger-grid). ✔
- Animations/interaction (draw, pulse, node highlight + plumb-line, segment zoom/spotlight) → A4 (CSS), A8 (JS). ✔
- "Lives on the Company tab as §IX, not a new tab/page" → A5 insertion point. ✔
- AI prose that "populates correctly" via the build-prose pipeline → Part B (slice/apply/registry/prompt/schema), B5 (e2e). ✔
- Renderer integration → A1–A3, A6. ✔

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to". CSS reuse in A4 references concrete, in-repo lines of `site/xp-mockup.html` with explicit edits shown — acceptable (a readable artifact, not a vague pointer).

**3. Type/name consistency:**
- `compute_ascent` returns the exact keys consumed by `_ascent.html` (`nodes`, `thresholds`, `ticks`, `line_d`, `area_d`, `proj_y`, `last_cx/cy`, `road_x/y`, `sources`, `total`, `level`, `level_num`, `to_next`, `next_threshold`, `deeds`, `sessions`, `richest_xp/title`, `view_w/h`, `plot_left/right`, `ybase`, `ymax`). ✔
- Node fields used in template (`type`, `up`, `cx`, `cy`, `r`, `i`, `gain`, `total`, `date`, `label`, `source`) all set in A2. ✔
- `data-i/-cx/-cy/-ybase/-gain/-total/-type/-date/-label/-note` emitted in A5 are exactly the attributes read by the A8 IIFE. ✔
- Transformer name `refresh-ascent-read` consistent across slices/apply/registry/prompt/schema/tests. ✔
- `site.ascent_read` written by B2, read by A5, defaulted by A6. ✔

**4. Known-breakage pre-emption:** `test_registry.py` (B3 step 1) and `test_loaders.py` (A3) updated in the same tasks that cause the change. Full-suite gate in A7 step 5.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-01-the-ascent-xp-section.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. (Each subagent must be told: no Claude references and no trailers in commit messages.)

**2. Inline Execution** — I execute the tasks in this session with checkpoints for your review.

**Which approach?**
