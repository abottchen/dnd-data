# Dashboard-first landing + Chronicle archive tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-sequence the Company tab into a fixed-height landing that leads with the latest session's story, the party's level/XP progress, and the Road Ahead; move the growing session history into a new one-chapter-at-a-time Chronicle tab.

**Architecture:** Pure render-layer change to the existing Jinja→`render.py`→single `site/index.html` build. Four new `compute_*` helpers surface already-computed data; new/edited templates re-lay-out the Company tab and add a Chronicle tabpanel that reuses the existing `.tab`/`.character` switcher; one new inline IIFE switches chapters. No authored-JSON, schema, orchestrator, or `data/` changes.

**Tech Stack:** Python 3 + Jinja2 (`build/compute.py`, `build/templates/*.html`), CSS (`site/styles.css`), vanilla JS (`build/templates/_script.html`), pytest (`tests/`).

## Global Constraints

- **No visual redesign.** Keep the illuminated-ledger identity exactly: tokens in `site/styles.css` `:root` (`--ink`, `--brass`, `--brass-hi`, `--paper`, `--paper-dim`, `--rule`, `--rule-strong`, `--seal`), fonts Cormorant Garamond (display) / EB Garamond (body) / IBM Plex Sans (utility). Reuse existing component classes and vars; introduce no new palette or type.
- **Single committed artifact.** Everything renders into one `site/index.html`; no multi-page output.
- **Render-layer only.** Do NOT touch `data/`, `build/authored/*.json`, their schemas, `.claude/prompts/`, or the orchestrator (`prepare`/`apply`/`slices.py`/`registry.py`/...).
- **Do NOT commit.** The user commits via their own flow when ready. Leave all changes staged-or-unstaged for their review. (No `git commit` steps in this plan.)
- **Inline `_script.html` is load-bearing** (tab switcher + tooltip IIFEs) — CLAUDE.md gotcha. New JS must be strictly additive.
- Party shares one XP pool and one level (characters always have equal XP) → one gauge.
- Test runner: `.venv/bin/pytest tests/`. Re-render with `.venv/bin/python build/render.py`. Preview: `python3 -m http.server 8765 --bind 127.0.0.1 --directory site`.

---

## File Structure

**Modify:**
- `build/compute.py` — add `compute_latest`, `compute_recent`, `compute_gauge`, `compute_road_ahead_digest`; wire them into `compute_all`'s returned context.
- `build/templates/base.html` — add the Chronicle `.tab` and the `_chronicle_tab.html` include.
- `build/templates/_company.html` — include the hero at top; remove the Chronicle (`co-calendar`) and Silent Roll (`co-margins`) sections; re-sequence + renumber the flavor sections and the `company_index` rail.
- `build/templates/_chronicle.html` — refactor from "rail + all chapters" to a single-chapter partial (header + sessions), rendering each session's `silent_roll` inside its `<details>` body.
- `build/templates/_script.html` — add one chapter-switcher IIFE.
- `site/styles.css` — add `.hero*`, `.gauge*`, `.roadahead*`, `.recent*`, `.chapter-switcher*`, `.chronicle-chapter-panel`, and session-body silent-roll styles.

**Create:**
- `build/templates/_hero.html` — the landing top: latest-story + gauge + Road Ahead band + "Previously" teaser.
- `build/templates/_chronicle_tab.html` — the Chronicle tabpanel: global Regnal rail + chapter switcher + one switchable panel per chapter.
- `tests/test_landing.py` — unit tests for the four new compute helpers.

**Delete (after verification):**
- `site/_mockup-landing.html` — throwaway prototype.

---

## Task 1: `compute_latest` — surface the newest session for the hero

**Files:**
- Modify: `build/compute.py` (add function after `compute_chronicle`/`_render_session`, ~line 961)
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: `chronicle` dict from `compute_chronicle` — `{"chapters": [{"label","title","sessions":[{"id","label","title","summary","silent_roll","iu_date","real_date_label","kills_count","kill_pips"}]}], "rail":[...]}`.
- Produces: `compute_latest(chronicle: dict) -> Optional[dict]` returning `{"chapter_label","chapter_title","session_label","session_id","title","iu_date","real_date_label","kills_count","kill_pips","summary"}` or `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing.py
from build.compute import compute_latest

def _chron(chapters):
    return {"chapters": chapters, "rail": []}

def _session(sid, title, kills=0):
    return {"id": sid, "label": "S", "title": title, "summary": f"sum-{sid}",
            "silent_roll": [], "iu_date": "12 Eleasis", "real_date_label": "13 JUL 2026",
            "kills_count": kills, "kill_pips": [{"creature": "x"}] * kills}

def test_latest_is_last_session_of_last_chapter():
    ch = compute_latest(_chron([
        {"label": "I", "title": "Ch One", "sessions": [_session(1, "a")]},
        {"label": "II", "title": "Ch Two", "sessions": [_session(2, "b"), _session(3, "c", kills=2)]},
    ]))
    assert ch["chapter_label"] == "II"
    assert ch["chapter_title"] == "Ch Two"
    assert ch["session_id"] == 3
    assert ch["title"] == "c"
    assert ch["summary"] == "sum-3"
    assert ch["kills_count"] == 2

def test_latest_none_when_no_sessions():
    assert compute_latest(_chron([])) is None
    assert compute_latest(_chron([{"label": "I", "title": "x", "sessions": []}])) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_landing.py -k latest -v`
Expected: FAIL — `ImportError: cannot import name 'compute_latest'`

- [ ] **Step 3: Write minimal implementation**

```python
# build/compute.py — after _render_session (~line 961)
def compute_latest(chronicle: dict) -> Optional[dict]:
    """The newest session, surfaced for the landing hero. None when the log is
    empty. The same session also renders in its chapter context in the Chronicle
    tab; this just lifts it to the front page."""
    for ch in reversed(chronicle.get("chapters", [])):
        if ch.get("sessions"):
            s = ch["sessions"][-1]
            return {
                "chapter_label": ch["label"],
                "chapter_title": ch["title"],
                "session_label": s["label"],
                "session_id": s["id"],
                "title": s["title"],
                "iu_date": s["iu_date"],
                "real_date_label": s["real_date_label"],
                "kills_count": s["kills_count"],
                "kill_pips": s["kill_pips"],
                "summary": s["summary"],
            }
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_landing.py -k latest -v`
Expected: PASS (2 tests)

---

## Task 2: `compute_recent` — the "Previously" teaser

**Files:**
- Modify: `build/compute.py` (after `compute_latest`)
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: same `chronicle` dict.
- Produces: `compute_recent(chronicle: dict, n: int = 2) -> list[dict]` — up to `n` sessions *before* the latest, most-recent first, each `{"label","title","id"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing.py
from build.compute import compute_recent

def test_recent_excludes_latest_most_recent_first():
    rec = compute_recent(_chron([
        {"label": "I", "title": "c", "sessions": [_session(1, "a"), _session(2, "b"), _session(3, "c")]},
    ]), n=2)
    assert [r["id"] for r in rec] == [2, 1]
    assert rec[0]["title"] == "b"

def test_recent_handles_single_session():
    assert compute_recent(_chron([{"label": "I", "title": "x", "sessions": [_session(1, "a")]}])) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_landing.py -k recent -v`
Expected: FAIL — `cannot import name 'compute_recent'`

- [ ] **Step 3: Implement**

```python
# build/compute.py — after compute_latest
def compute_recent(chronicle: dict, n: int = 2) -> list[dict]:
    """The n sessions immediately before the latest, most-recent first, for the
    landing's 'Previously' teaser into the Chronicle tab."""
    flat = [s for ch in chronicle.get("chapters", []) for s in ch.get("sessions", [])]
    prev = flat[:-1]  # drop the latest (surfaced by the hero)
    return [{"label": s["label"], "title": s["title"], "id": s["id"]}
            for s in reversed(prev[-n:])]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_landing.py -k recent -v`
Expected: PASS (2 tests)

---

## Task 3: `compute_gauge` — compact level-progress geometry

**Files:**
- Modify: `build/compute.py` (after `compute_ascent`, ~line 525)
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: the `ascent` dict from `compute_ascent` (or `None`). Uses keys `thresholds` (list of `{"v","lvl","y","top"}`), `plot_left`, `plot_right`, `ybase`, `line_d`, `area_d`, `last_cx`, `last_cy`, `level`, `total`, `to_next`, `next_threshold`.
- Produces: `compute_gauge(ascent: Optional[dict]) -> Optional[dict]` with `{"view_x","view_y","view_w","view_h","goal_y","goal_x1","goal_x2","line_d","area_d","last_cx","last_cy","level","total_fmt","to_next_fmt","next_fmt","at_summit"}` or `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing.py
from build.compute import compute_ascent, compute_gauge

def test_gauge_none_without_xp():
    assert compute_gauge(None) is None
    assert compute_gauge(compute_ascent({"entries": []})) is None

def test_gauge_frames_climb_below_next_level():
    xp = {"entries": [
        {"date": "2026-03-15", "perPc": 300, "type": "combat", "title": "t1", "sessionId": "1"},
        {"date": "2026-04-01", "perPc": 400, "type": "quest",  "title": "t2", "sessionId": "2"},
    ]}
    a = compute_ascent(xp)
    g = compute_gauge(a)
    # current point sits BELOW the next-level (goal) line → larger y in SVG coords
    assert g["last_cy"] > g["goal_y"]
    assert g["level"] == a["level"]
    assert g["total_fmt"] == f'{a["total"]:,}'
    assert g["next_fmt"] == f'{a["next_threshold"]:,}'
    assert g["at_summit"] is False
    # viewBox spans from just above the goal line down to the baseline
    assert g["view_y"] < g["goal_y"] < g["view_y"] + g["view_h"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_landing.py -k gauge -v`
Expected: FAIL — `cannot import name 'compute_gauge'`

- [ ] **Step 3: Implement**

```python
# build/compute.py — after compute_ascent's return (~line 525)
def compute_gauge(ascent: Optional[dict]) -> Optional[dict]:
    """Compact level-progress gauge for the landing hero, derived from the Ascent
    context. Frames the climb from just above the next-level line down to the
    baseline, so the gap above the curve reads as 'still to climb'. None when
    there is no XP yet (the hero omits the gauge)."""
    if not ascent:
        return None
    goal = next((t for t in ascent["thresholds"] if t.get("top")), None)
    goal_y = goal["y"] if goal else ascent["ybase"]  # summit: no ceiling above
    left, right = ascent["plot_left"], ascent["plot_right"]
    view_y = round(goal_y - 12, 2)  # headroom for the goal label
    return {
        "view_x": round(left - 8, 2),
        "view_y": view_y,
        "view_w": round(right - left + 16, 2),
        "view_h": round(ascent["ybase"] - view_y, 2),
        "goal_y": goal_y, "goal_x1": left, "goal_x2": right,
        "line_d": ascent["line_d"], "area_d": ascent["area_d"],
        "last_cx": ascent["last_cx"], "last_cy": ascent["last_cy"],
        "level": ascent["level"],
        "total_fmt": f'{ascent["total"]:,}',
        "to_next_fmt": f'{ascent["to_next"]:,}',
        "next_fmt": f'{ascent["next_threshold"]:,}' if ascent["next_threshold"] else None,
        "at_summit": ascent["next_threshold"] is None,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_landing.py -k gauge -v`
Expected: PASS (2 tests)

---

## Task 4: `compute_road_ahead_digest` — hero Road Ahead band

**Files:**
- Modify: `build/compute.py` (after `compute_gauge`)
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: `site["road_ahead"]` — `{"known": [{"name","gloss"}], "was_known": [...], "direction": str}`.
- Produces: `compute_road_ahead_digest(road_ahead: Optional[dict], n: int = 5) -> dict` → `{"direction","known","more_count"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing.py
from build.compute import compute_road_ahead_digest

def test_road_digest_caps_and_counts_overflow():
    ra = {"direction": "south to Shilku",
          "known": [{"name": f"n{i}", "gloss": "g"} for i in range(8)]}
    d = compute_road_ahead_digest(ra, n=5)
    assert d["direction"] == "south to Shilku"
    assert len(d["known"]) == 5
    assert d["more_count"] == 3

def test_road_digest_handles_missing():
    d = compute_road_ahead_digest(None)
    assert d == {"direction": "", "known": [], "more_count": 0}
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_landing.py -k road -v`
Expected: FAIL — `cannot import name 'compute_road_ahead_digest'`

- [ ] **Step 3: Implement**

```python
# build/compute.py — after compute_gauge
def compute_road_ahead_digest(road_ahead: Optional[dict], n: int = 5) -> dict:
    """Compact Road Ahead for the hero band: the next-move prose + the first n
    known threads + how many more remain (linking to the full flavor section)."""
    ra = road_ahead or {}
    known = ra.get("known", [])
    return {
        "direction": ra.get("direction", ""),
        "known": known[:n],
        "more_count": max(0, len(known) - n),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_landing.py -k road -v`
Expected: PASS (2 tests)

---

## Task 5: Wire the four helpers into `compute_all`

**Files:**
- Modify: `build/compute.py` — `compute_all` (~lines 1040–1093)
- Test: `tests/test_landing.py`

**Interfaces:**
- Produces: `compute_all(...)` returned dict gains keys `latest`, `recent`, `gauge`, `road_ahead_digest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing.py — integration against real data
import json
from pathlib import Path
from build.render import load_data, load_authored
from build.compute import compute_all

def test_compute_all_exposes_landing_keys():
    root = Path(__file__).resolve().parent.parent
    data = load_data(root / "data")
    authored = load_authored(root / "build" / "authored")
    ctx = compute_all(data, authored)
    assert {"latest", "recent", "gauge", "road_ahead_digest"} <= ctx.keys()
    assert ctx["latest"]["session_id"] >= 1
    assert isinstance(ctx["recent"], list)
```

(If `load_data`/`load_authored` need different args, mirror their use in `build/render.py:main`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_landing.py -k compute_all -v`
Expected: FAIL — `KeyError`/assertion on missing keys.

- [ ] **Step 3: Implement — add computations + return keys**

```python
# build/compute.py — in compute_all, after `ascent = compute_ascent(...)` (~line 1040)
    latest = compute_latest(chronicle)
    recent = compute_recent(chronicle, n=2)
    gauge = compute_gauge(ascent)
```

```python
# build/compute.py — after `site` is fully assembled (~line 1063, before party_top_xp)
    road_ahead_digest = compute_road_ahead_digest(site.get("road_ahead"))
```

```python
# build/compute.py — add to the returned dict (~line 1084, beside "ascent": ascent,)
        "latest": latest,
        "recent": recent,
        "gauge": gauge,
        "road_ahead_digest": road_ahead_digest,
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `.venv/bin/pytest tests/test_landing.py -v && .venv/bin/pytest tests/`
Expected: PASS (all landing tests + existing suite unaffected)

---

## Task 6: Add the landing/archive CSS

**Files:**
- Modify: `site/styles.css` (append a new clearly-commented block near the Company-section styles)

**Interfaces:** consumed by Tasks 7–10 via class names below.

- [ ] **Step 1: Append the component styles**

Port the validated styles from `site/_mockup-landing.html`'s `<style>` block (already tuned against the real palette). Add, verbatim in spirit, rules for: `.hero` (`grid-template-columns: 1.7fr 1px 0.9fr; gap: 40px; align-items:start`), `.hero-rule` (`align-self:stretch;width:1px;background:var(--rule)`), `.hero-eyebrow/.hero-title/.hero-meta/.hero-summary` (+ `::first-letter` drop cap), `.gauge` + `.gauge-eyebrow/.gauge-level/.gauge-chart` and `.g-fig/.g-goal/.g-togo/.g-earned` + `.g-goal-line/.g-area/.g-line/.g-pulse`, `.roadahead*` + `.ra-*`, `.recent*`, `.chapter-switcher` + `.chapter-switch-btn[aria-selected]`, `.chronicle-chapter-panel` (`display:none`) / `.chronicle-chapter-panel.active` (`display:block`), and a `.chronicle-session-quiet` block for the folded Silent Roll (small EB Garamond italic list, `--paper-dim`). Include the `@media (max-width:900px)` rules (hero → 1 col, `.hero-rule{display:none}`, `.gauge{position:static}`, `.roadahead` → 1 col, chapter switcher horizontal-scroll).

- [ ] **Step 2: Sanity — CSS parses, no selector collisions**

Run: `.venv/bin/python build/render.py` (must still exit 0; CSS isn't validated by render but this confirms nothing else broke) then grep the new classes exist:
Run: `grep -c 'chronicle-chapter-panel' site/styles.css` → Expected: `>=2`

---

## Task 7: Create `_hero.html`

**Files:**
- Create: `build/templates/_hero.html`

**Interfaces:**
- Consumes: `latest`, `gauge`, `road_ahead_digest`, `recent` from context; `kill_pips` macro from `_macros.html`.

- [ ] **Step 1: Write the partial**

Port the hero markup from `site/_mockup-landing.html` (the `.hero`, `.hero-rule`, `.roadahead`, `.recent` blocks), swapping literals for context:
- Eyebrow: `Chapter {{ latest.chapter_label }} · {{ latest.chapter_title }}`; title `{{ latest.title }}`; meta `Session {{ latest.session_label }}` / `{{ latest.iu_date }}` / `{{ latest.real_date_label }}`; then `{% if latest.kills_count %}{{ kill_pips(latest.kill_pips) }}{% else %}<span class="quiet">— no blade lifted —</span>{% endif %}`; summary `{{ latest.summary | safe }}`.
- Gauge: `{% if gauge %}` … `Level {{ gauge.level }}` … `<svg viewBox="{{ gauge.view_x }} {{ gauge.view_y }} {{ gauge.view_w }} {{ gauge.view_h }}" preserveAspectRatio="none">` with `<line class="g-goal-line" x1="{{ gauge.goal_x1 }}" y1="{{ gauge.goal_y }}" x2="{{ gauge.goal_x2 }}" y2="{{ gauge.goal_y }}"/>`, `<path class="g-area" d="{{ gauge.area_d }}"/>`, `<path class="g-line" d="{{ gauge.line_d }}"/>`, `<circle class="g-pulse" cx="{{ gauge.last_cx }}" cy="{{ gauge.last_cy }}" r="8"/>`; figures `g-goal` (`Level V` label — `{% if not gauge.at_summit %}` show `{{ gauge.next_fmt }} XP`), `g-togo` (`{{ gauge.to_next_fmt }}` + "XP still to climb"), `g-earned` (`{{ gauge.total_fmt }}` + "XP earned"). Wrap the goal/togo in `{% if not gauge.at_summit %}`.
- Road Ahead band: `{{ road_ahead_digest.direction | safe }}`; chips loop `{% for e in road_ahead_digest.known %}<span class="ra-chip">{{ e.name | safe }}</span>{% endfor %}` + `{% if road_ahead_digest.more_count %}<a class="ra-more" href="#co-horizon">+{{ road_ahead_digest.more_count }} more →</a>{% endif %}`.
- Previously: `{% for r in recent %}<span class="recent-item"><span class="n">{{ r.label }}</span>{{ r.title }}</span>{% endfor %}` + `<a class="recent-cta" href="#chronicle">Read the full Chronicle →</a>`.

Start the file with `{% from "_macros.html" import kill_pips -%}`.

- [ ] **Step 2: Verify (deferred to Task 8's render, since nothing includes it yet)**

---

## Task 8: Re-sequence `_company.html`

**Files:**
- Modify: `build/templates/_company.html`

- [ ] **Step 1: Include the hero + drop the moved sections**

- After `<article class="character" id="company" …>` and the existing `company_index`/`company_strip`, add `{% include "_hero.html" %}` as the first content.
- **Delete** the `co-calendar` section (the Chronicle, lines ~172–175 incl. `{% include "_chronicle.html" %}`) and the `co-margins` section (the Silent Roll, ~234–245).
- Update the `company_index` list (top of file, ~lines 5–15): remove the `co-calendar` and `co-margins` entries; renumber the survivors I–VII in this order: `co-reckoning` (Ledger), `co-climb` (Ascent), `co-stars` (Constellation), `co-tally` (Bestiary), `co-horizon` (Road Ahead), `co-crowns` (Distinctions), `co-fates` (Patron Die). Move the `{% include "_ascent.html" %}` up so section order matches the rail. Update each section's `section_head(...)` Roman numeral to match.

- [ ] **Step 2: Render + verify the Company tab**

Run: `.venv/bin/python build/render.py`
Expected: exit 0. Then grep: `grep -c 'id="co-calendar"' site/index.html` → `0`; `grep -c 'id="co-margins"' site/index.html` → `0`; `grep -c 'class="hero"' site/index.html` → `1`.

- [ ] **Step 3: Visual check**

Preview at `http://127.0.0.1:8765/` (Company tab): hero shows latest story + gauge + Road Ahead + Previously; flavor sections follow in I–VII order; index rail has 7 entries. Confirm the climb line stops below the Level V line and the empty-kill state reads "— no blade lifted —".

---

## Task 9: Chronicle tab — refactor `_chronicle.html`, add `_chronicle_tab.html`, wire `base.html`

**Files:**
- Modify: `build/templates/_chronicle.html` (→ single-chapter partial, silent_roll in body)
- Create: `build/templates/_chronicle_tab.html`
- Modify: `build/templates/base.html`

- [ ] **Step 1: Refactor `_chronicle.html` to render one chapter**

Replace its contents with a partial that renders a single chapter from a `ch` variable: the `chronicle-chapter-head` (label/title/epigraph/meta/pips) and the `{% for s in ch.sessions %}` `<details>` rows. Keep the `open` on the last session of the last chapter (pass an `is_latest_chapter` flag, or open the last session unconditionally within its chapter). **Add** inside `.chronicle-session-body`, after the summary: `{% if s.silent_roll %}<ul class="chronicle-session-quiet">{% for line in s.silent_roll %}<li>{{ line | safe }}</li>{% endfor %}</ul>{% endif %}`. Start with `{% from "_macros.html" import kill_pips -%}`.

- [ ] **Step 2: Create `_chronicle_tab.html`**

```jinja
{% from "_macros.html" import kill_pips -%}
<article class="character" id="chronicle" role="tabpanel" aria-labelledby="tab-chronicle">
  <nav class="chapter-switcher" aria-label="Chapters">
    {%- for ch in chronicle.chapters %}
    <button class="chapter-switch-btn" data-chapter="{{ loop.index0 }}"
            aria-selected="{{ 'true' if loop.last else 'false' }}">
      Chapter {{ ch.label }}<span>{{ ch.title }}</span>
    </button>
    {%- endfor %}
  </nav>
  <div class="chronicle">
    <aside class="chronicle-rail">
      <div class="chronicle-rail-label">Regnal</div>
      {%- for r in chronicle.rail %}
      <div class="chronicle-month">{{ r.month }}</div>
      <div class="chronicle-month-year">{{ r.year }}</div>
      <div class="chronicle-month-count">{{ r.count }} session{% if r.count != 1 %}s{% endif %}</div>
      {%- endfor %}
    </aside>
    <div class="chronicle-content">
      {%- for ch in chronicle.chapters %}
      <div class="chronicle-chapter-panel{% if loop.last %} active{% endif %}" data-chapter="{{ loop.index0 }}">
        {% include "_chronicle.html" %}
      </div>
      {%- endfor %}
    </div>
  </div>
</article>
```

- [ ] **Step 3: Wire `base.html`**

- In `.tabs`, before the GM tab, add:
```jinja
<a href="#chronicle" class="tab chronicle-tab" data-tab="chronicle" role="tab" id="tab-chronicle" aria-controls="chronicle">
  <span class="tab-glyph" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 4 h7 a2 2 0 0 1 2 2 v14 a2 2 0 0 0 -2 -2 h-7 z M20 4 h-7 a2 2 0 0 0 -2 2 v14 a2 2 0 0 1 2 -2 h7 z" stroke="currentColor" stroke-width="1.3"/></svg></span>The Chronicle
</a>
```
- In `<main>`, after the character loop and before `{% include "_gm.html" %}`, add `{% include "_chronicle_tab.html" %}`.
- Add `.tab-glyph` CSS to `site/styles.css` (from the mockup) if not already added in Task 6.

- [ ] **Step 4: Render + verify**

Run: `.venv/bin/python build/render.py`
Expected: exit 0. `grep -c 'id="chronicle"' site/index.html` → `1`; `grep -c 'chronicle-chapter-panel' site/index.html` → equals chapter count (2).

---

## Task 10: Chapter-switcher IIFE

**Files:**
- Modify: `build/templates/_script.html` (append a new IIFE at the end, before any closing)

- [ ] **Step 1: Add the switcher (strictly additive)**

```javascript
// Chronicle chapter switcher: show one chapter panel at a time.
(function () {
  const root = document.getElementById('chronicle');
  if (!root) return;
  const btns = [...root.querySelectorAll('.chapter-switch-btn')];
  const panels = [...root.querySelectorAll('.chronicle-chapter-panel')];
  function show(idx) {
    btns.forEach(b => b.setAttribute('aria-selected', String(+b.dataset.chapter === idx)));
    panels.forEach(p => p.classList.toggle('active', +p.dataset.chapter === idx));
  }
  btns.forEach(b => b.addEventListener('click', () => show(+b.dataset.chapter)));
})();
```

- [ ] **Step 2: Render + interaction check**

Run: `.venv/bin/python build/render.py` then preview. On the Chronicle tab: clicking Chapter I / Chapter II swaps the visible chapter; only one is shown; the last chapter is active on load. Confirm the main tab switcher and pip/bestiary tooltips still work (nothing regressed).

---

## Task 11: Full verification + cleanup

**Files:**
- Delete: `site/_mockup-landing.html`

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/pytest tests/`
Expected: all green (new landing tests + untouched existing tests).

- [ ] **Step 2: Re-render and visually verify end to end**

Run: `.venv/bin/python build/render.py`; preview at `http://127.0.0.1:8765/`. Check at 1440×900 and at ~700px width:
- Company tab ≈ 1–2 screens; hero answers *what happened · where are we / to next level · where headed* above the fold.
- Index rail = 7 entries; scroll-spy tracks them.
- Chronicle tab switches chapters; silent-roll lines appear inside expanded sessions; no standalone Silent Roll section anywhere.
- Keyboard tab nav works; reduced-motion honored.

- [ ] **Step 3: Remove the throwaway mockup**

Run: `rm site/_mockup-landing.html`
Then confirm it's gone from the served dir: `test ! -f site/_mockup-landing.html && echo removed`.

- [ ] **Step 4: Hand back to the user for commit**

Do not commit. Summarize what changed and let the user commit via their own flow.

---

## Self-Review

**Spec coverage:**
- Hero (latest story, full + drop cap + empty-kill state) → Tasks 1, 7, 8. ✓
- Ascent level-progress gauge (climb below unreached goal line; earned/to-go/target figures) → Tasks 3, 6, 7. ✓
- Road Ahead band (direction + top-5 chips + overflow) → Tasks 4, 7. ✓
- "Previously" teaser → Chronicle → Tasks 2, 7. ✓
- Re-sequenced flavor sections + shrunk index rail (9→7) → Task 8. ✓
- New Chronicle tab, one chapter at a time → Tasks 9, 10. ✓
- Silent Roll folded into session bodies; standalone section deleted → Tasks 8 (remove `co-margins`), 9 (fold into `_chronicle.html`). ✓
- Reuses existing tab switcher; new JS additive → Tasks 9, 10; constraint stated. ✓
- Render-layer only; no authoring/schema/orchestrator changes → Global Constraints; no task touches them. ✓
- Full-height column rule; keep `6,500` target label → Tasks 6, 7 (settled decisions honored). ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. Task 6 references the mockup's already-written CSS rather than repeating ~200 lines — acceptable since that file exists in-repo at implementation time and is deleted only in Task 11.

**Type consistency:** `compute_latest`→hero keys (`chapter_label`, `session_label`, `kills_count`, `kill_pips`, `summary`) match Task 7's template use. `compute_gauge` keys (`view_x/y/w/h`, `goal_y`, `line_d`, `area_d`, `last_cx/cy`, `total_fmt`, `to_next_fmt`, `next_fmt`, `at_summit`, `level`) match Task 7's SVG/figures. `compute_road_ahead_digest` keys (`direction`, `known`, `more_count`) match Task 7's band. `compute_recent` keys (`label`, `title`, `id`) match Task 7's teaser. ✓
