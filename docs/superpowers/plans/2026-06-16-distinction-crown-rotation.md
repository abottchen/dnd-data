# Distinction Crown Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make character distinction crowns rotate over an open, emergent-pattern space drawn from a computed, machine-verifiable fact pack — escaping class-predictable monotony and monotonic-count permanence — while giving `constellation_epithet` its own presence×contribution contract and migrating the locked reliquary headers off bare-method framing.

**Architecture:** A new pure function `compute_fact_pack` in `build/render.py` derives ~29 verifiable per-PC atoms from already-computed `trials`, `fortune_by_char`, `constellation`, plus the party kill log and session log. The `refresh-characters` / `append-characters` slice builders feed that fact pack (plus a `had_new_activity` flag and new-session text) to the authoring prompts, whose rewritten contracts compose crowns from atoms and emit a structured `distinction_basis`. `render.py` recomputes the fact pack and verifies every mechanical basis (mismatch → `MALFORMED`, failing the render), and the uniqueness validator extends to the basis atom. A one-time content migration rewrites the locked `reliquary_header` lines.

**Tech Stack:** Python 3 (stdlib only: `collections.Counter`, `statistics`), Jinja2 (templates, unchanged), pytest, JSON Schema (`jsonschema`) for prompt-output validation.

---

## Background the implementer needs

- **Run the suite:** `.venv/bin/pytest tests/ -q` (52 tests pass today). The 5etools symlink at `.claude/ext/5etools-src` is present, so `bestiary_lookup`-dependent code (XP/CR/type) works in tests.
- **The authored store** is `build/authored/*.json`. Characters live in `characters.json`; each entry has `id`, `epithet`, `reliquary_header`, `constellation_epithet`, `distinction_title`, `distinction_subtitle`, `distinction_detail`, and (after this work) `distinction_basis`.
- **The pipeline:** `slices.py` builds a slice → a prompt authors prose → `apply.py` writes it into the authored store → `render.py` validates everything and renders `site/index.html`. `validate_all` gating means any `MALFORMED` entry exits the render non-zero.
- **Key existing helpers in `render.py`:** `compute_trials(party)` (per-char `xp`, `kill_count`, `means`, `means_n`, `kinds` [list of `{type,count}`], `kinds_count`, `xp_pct`, `kill_pct`); `compute_fortune(events)` (`avg`, `sd`, `crits`, `fumbles`, `heaviest`, `kept_d20s_count`, `rolls_total`, `events`); `compute_constellation(party, fortune_by_char, trials)` (returns `stars` with `system_size`, `xp`, `rolls`); `_kill_xp(creature)`, `_kill_cr(creature)`, `bestiary_lookup(creature)`. **Do not extract a shared module** — follow the existing pattern where `slices.py` imports and calls `render.*`.
- **Privacy:** `data/session-log.json` contains real player first names. Authoring prompts must never emit a real player name. Git hooks (`.githooks/`) guard commits/pushes.

## File structure (what changes)

- `build/render.py` — add `_date_to_session_index`, `compute_fact_pack`, `validate_distinction_basis`; extend `validate_distinction_uniqueness`; wire both into `validate_all`; call `compute_fact_pack` in the render context build.
- `build/slices.py` — `refresh_characters` and `append_characters` emit the fact pack, `had_new_activity`, and `session_text`.
- `build/apply.py` — `apply_refresh_characters` and `apply_append_characters` persist `distinction_basis`.
- `.claude/prompts/refresh-characters.md` + `.schema.json` — two-contract rewrite + `distinction_basis`.
- `.claude/prompts/append-characters.md` + `.schema.json` — same.
- `build/authored/characters.json` — one-time `reliquary_header` migration (Task 9), and `distinction_basis` added by the first real re-author (Task 10).
- `tests/test_compute.py`, `tests/test_validator.py`, `tests/test_apply.py`, `tests/test_slices.py` — new tests.

## Atom reference (the fact pack `compute_fact_pack` returns)

Per non-GM PC id, a flat dict. Booleans named `is_party_*`/`all_*` make superlatives trivially verifiable.

| Atom | Type | Meaning |
|---|---|---|
| `kill_count` | int | total kills |
| `kill_pct` | int | share of party kills (from trials) |
| `xp_pct` | int | share of party XP (from trials) |
| `distinct_method_count` | int | number of distinct kill methods |
| `all_kills_one_method` | bool | every kill via the same method (≥1 kill) |
| `all_distinct_creatures` | bool | no creature name killed twice (≥1 kill) |
| `distinct_type_count` | int | distinct creature *types* (from trials `kinds_count`) |
| `all_distinct_types` | bool | every kill a different type (≥1 kill) |
| `biggest_kill_xp` | int | XP of the single highest-XP kill (0 if none) |
| `is_party_biggest_kill` | bool | holds the party's single highest-XP kill |
| `max_kills_in_one_session` | int | most kills on one session date |
| `kill_session_count` | int | distinct session dates with a kill |
| `longest_drought` | int | max kill-less campaign sessions strictly between two of this PC's kills |
| `kept_d20_avg` | float | mean kept d20 (from fortune `avg`) |
| `is_party_luckiest` | bool | highest `avg` among PCs with ≥1 kept d20 |
| `is_party_unluckiest` | bool | lowest `avg` among PCs with ≥1 kept d20 |
| `sd` | float | kept-d20 stdev |
| `is_party_steadiest` | bool | lowest `sd` among PCs with ≥2 kept d20 |
| `is_party_swingiest` | bool | highest `sd` among PCs with ≥2 kept d20 |
| `crits` | int | natural 20s (from fortune) |
| `is_party_most_crits` | bool | most crits in the party |
| `max_crits_in_one_session` | int | most crits on one session date |
| `fumbles` | int | natural 1s |
| `is_party_most_fumbles` | bool | most crit-fails in the party |
| `heaviest_blow` | int | biggest single damage roll (from fortune `heaviest.total`) |
| `is_party_heaviest` | bool | holds the party's heaviest blow |
| `system_size` | int | constellation cluster size (1 = alone) |
| `is_constellation_outlier` | bool | `system_size == 1` |
| `quadrant` | str | `"{hi/lo}-presence/{hi/lo}-contribution"` vs party medians |

`had_new_activity` (bool per PC) and the previous distinction are **not** atoms — `slices.py` attaches them to the slice (Task 6). Party-rank booleans break ties by being true for all tied holders.

---

### Task 1: Fact pack — kill-derived atoms + session helper

**Files:**
- Modify: `build/render.py` (add `_date_to_session_index` and `compute_fact_pack` near `compute_trials`, ~line 428)
- Test: `tests/test_compute.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_compute.py`. First extend the import line at the top to include `compute_fact_pack`:

```python
from build.render import (xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune,
                   compute_d20_histogram, compute_other_dice, compute_best_skill,
                   compute_intro_meta, compute_constellation, compute_fact_pack,
                   _compute_party_top_xp, _compute_header_eyebrow,
                   _creature_token_url, _name_to_token_name,
                   compute_radar)
```

Then add these tests at the end of the file:

```python
# -- Fact pack: kill-derived atoms -------------------------------------------

def _session_log(dates):
    """Build a minimal session log: one entry per date, session ids 1..N."""
    return {"entries": [{"session": i + 1, "date": d, "text": ""} for i, d in enumerate(dates)]}

def test_fact_pack_kill_pattern_atoms():
    party = {"members": [
        {"id": "a", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-08", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-08", "creature": "Goblin", "method": "Longbow"},
        ]},
        {"id": "b", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Dagger"},
            {"date": "2026-04-15", "creature": "Bandit", "method": "Longbow"},
        ]},
    ]}
    trials = compute_trials(party)
    fortune = {"a": compute_fortune([]), "b": compute_fortune([])}
    constellation = compute_constellation(party, fortune, trials)
    log = _session_log(["2026-04-01", "2026-04-08", "2026-04-15"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)

    assert fp["a"]["kill_count"] == 3
    assert fp["a"]["all_kills_one_method"] is True
    assert fp["a"]["distinct_method_count"] == 1
    assert fp["a"]["all_distinct_creatures"] is False     # Goblin thrice
    assert fp["a"]["max_kills_in_one_session"] == 2        # two on 2026-04-08
    assert fp["a"]["kill_session_count"] == 2

    assert fp["b"]["all_kills_one_method"] is False        # Dagger + Longbow
    assert fp["b"]["distinct_method_count"] == 2
    assert fp["b"]["all_distinct_creatures"] is True       # Goblin + Bandit
    assert fp["b"]["max_kills_in_one_session"] == 1

def test_fact_pack_longest_drought_counts_interior_silent_sessions():
    party = {"members": [
        {"id": "a", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-22", "creature": "Goblin", "method": "Longbow"},
        ]},
    ]}
    trials = compute_trials(party)
    fortune = {"a": compute_fortune([])}
    constellation = compute_constellation(party, fortune, trials)
    # Campaign sessions on 4 dates; PC killed only on the 1st and 4th.
    log = _session_log(["2026-04-01", "2026-04-08", "2026-04-15", "2026-04-22"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)
    assert fp["a"]["longest_drought"] == 2   # two silent sessions between
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_kill_pattern_atoms -v`
Expected: FAIL with `ImportError: cannot import name 'compute_fact_pack'`.

- [ ] **Step 3: Write minimal implementation**

In `build/render.py`, ensure `from statistics import pstdev, median` (the file already imports `pstdev`; add `median`). Then add directly after `compute_trials` (after line 428):

```python
def _date_to_session_index(session_log: dict) -> dict:
    """Map each session date to its 0-based campaign position."""
    return {e["date"]: i for i, e in enumerate(session_log.get("entries", []))}


def compute_fact_pack(party: dict, trials: dict, fortune_by_char: dict,
                      constellation: dict, session_log: dict) -> dict:
    """Per non-GM PC, a flat dict of verifiable 'atoms' a distinction can rest
    on. Reuses already-computed trials/fortune/constellation; only biggest-kill
    XP reaches back to the bestiary (via _kill_xp). See the plan's atom table."""
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    date_to_idx = _date_to_session_index(session_log)
    per_char = trials["per_char"]

    fp: dict[str, dict] = {}
    for m in members:
        cid = m["id"]
        kills = m.get("kills", [])
        n = len(kills)
        methods = [k["method"] for k in kills]
        creatures = [k["creature"].strip().lower() for k in kills]
        t = per_char[cid]

        # Kills grouped by campaign session index.
        by_session: Counter = Counter()
        for k in kills:
            idx = date_to_idx.get(k["date"])
            if idx is not None:
                by_session[idx] += 1

        # Interior drought: max run of kill-less sessions strictly between two
        # of this PC's kill sessions.
        kill_idxs = sorted(by_session)
        drought = 0
        for a, b in zip(kill_idxs, kill_idxs[1:]):
            drought = max(drought, b - a - 1)

        biggest = max((_kill_xp(k["creature"]) for k in kills), default=0)

        fp[cid] = {
            "kill_count": n,
            "kill_pct": t["kill_pct"],
            "xp_pct": t["xp_pct"],
            "distinct_method_count": len(set(methods)),
            "all_kills_one_method": n > 0 and len(set(methods)) == 1,
            "all_distinct_creatures": n > 0 and len(set(creatures)) == n,
            "distinct_type_count": t["kinds_count"],
            "all_distinct_types": n > 0 and t["kinds_count"] == n,
            "biggest_kill_xp": biggest,
            "max_kills_in_one_session": max(by_session.values(), default=0),
            "kill_session_count": len(kill_idxs),
            "longest_drought": drought,
        }
    return fp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_kill_pattern_atoms tests/test_compute.py::test_fact_pack_longest_drought_counts_interior_silent_sessions -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_compute.py
git commit -m "feat(render): fact pack kill-derived atoms"
```

---

### Task 2: Fact pack — roll-derived atoms + party-rank booleans

**Files:**
- Modify: `build/render.py` (`compute_fact_pack`)
- Test: `tests/test_compute.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_compute.py`:

```python
# -- Fact pack: roll-derived atoms -------------------------------------------

def _d20_events(values, date="2026-04-01"):
    return [{"rolls": [{"type": "d20", "value": v, "dropped": False}],
             "total": v, "notation": "1d20", "date": date} for v in values]

def test_fact_pack_roll_rank_booleans():
    party = {"members": [
        {"id": "a", "kills": []},
        {"id": "b", "kills": []},
    ]}
    trials = compute_trials(party)
    fortune = {
        # a: high average, two crits, both on the same date
        "a": compute_fortune(_d20_events([20, 20, 18, 16])),
        # b: low average, one fumble
        "b": compute_fortune(_d20_events([1, 5, 8, 6])),
    }
    constellation = compute_constellation(party, fortune, trials)
    log = _session_log(["2026-04-01"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)

    assert fp["a"]["is_party_luckiest"] is True
    assert fp["a"]["is_party_unluckiest"] is False
    assert fp["a"]["crits"] == 2
    assert fp["a"]["is_party_most_crits"] is True
    assert fp["a"]["max_crits_in_one_session"] == 2
    assert fp["b"]["is_party_unluckiest"] is True
    assert fp["b"]["fumbles"] == 1
    assert fp["b"]["is_party_most_fumbles"] is True

def test_fact_pack_heaviest_blow_rank():
    party = {"members": [{"id": "a", "kills": []}, {"id": "b", "kills": []}]}
    trials = compute_trials(party)
    fortune = {
        "a": compute_fortune([{"rolls": [{"type": "d8", "value": 7}], "total": 7,
                               "notation": "1d8", "date": "2026-04-01"}]),
        "b": compute_fortune([{"rolls": [{"type": "d12", "value": 11}], "total": 11,
                               "notation": "1d12", "date": "2026-04-01"}]),
    }
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))
    assert fp["b"]["heaviest_blow"] == 11
    assert fp["b"]["is_party_heaviest"] is True
    assert fp["a"]["is_party_heaviest"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_roll_rank_booleans -v`
Expected: FAIL with `KeyError: 'is_party_luckiest'`.

- [ ] **Step 3: Write minimal implementation**

In `compute_fact_pack`, before the `for m in members` loop, compute party-wide maxima/minima for the rank booleans:

```python
    # Party-wide extrema for rank booleans (computed once).
    avgs = {m["id"]: fortune_by_char[m["id"]]["avg"]
            for m in members if fortune_by_char[m["id"]]["kept_d20s_count"] >= 1}
    sds = {m["id"]: fortune_by_char[m["id"]]["sd"]
           for m in members if fortune_by_char[m["id"]]["kept_d20s_count"] >= 2}
    crit_counts = {m["id"]: fortune_by_char[m["id"]]["crits"] for m in members}
    fumble_counts = {m["id"]: fortune_by_char[m["id"]]["fumbles"] for m in members}
    heaviest = {m["id"]: fortune_by_char[m["id"]]["heaviest"]["total"] for m in members}
    biggest_kills = {m["id"]: max((_kill_xp(k["creature"]) for k in m.get("kills", [])), default=0)
                     for m in members}

    max_avg = max(avgs.values(), default=None)
    min_avg = min(avgs.values(), default=None)
    min_sd = min(sds.values(), default=None)
    max_sd = max(sds.values(), default=None)
    max_crits = max(crit_counts.values(), default=0)
    max_fumbles = max(fumble_counts.values(), default=0)
    max_heaviest = max(heaviest.values(), default=0)
    max_biggest_kill = max(biggest_kills.values(), default=0)
```

Then inside the loop, compute per-PC crit clustering by session date and add the roll atoms to the `fp[cid]` dict. Add this just before `fp[cid] = {` to compute crit clustering:

```python
        f = fortune_by_char[cid]
        crits_by_date: Counter = Counter()
        for ev in f["events"]:
            for d in ev.get("rolls", []):
                if d.get("type") == "d20" and not d.get("dropped") and int(d["value"]) == 20:
                    crits_by_date[ev.get("date")] += 1
```

And add these keys to the `fp[cid]` dict literal (alongside the kill atoms from Task 1):

```python
            "kept_d20_avg": f["avg"],
            "is_party_luckiest": cid in avgs and avgs[cid] == max_avg,
            "is_party_unluckiest": cid in avgs and avgs[cid] == min_avg,
            "sd": f["sd"],
            "is_party_steadiest": cid in sds and sds[cid] == min_sd,
            "is_party_swingiest": cid in sds and sds[cid] == max_sd,
            "crits": f["crits"],
            "is_party_most_crits": f["crits"] == max_crits and max_crits > 0,
            "max_crits_in_one_session": max(crits_by_date.values(), default=0),
            "fumbles": f["fumbles"],
            "is_party_most_fumbles": f["fumbles"] == max_fumbles and max_fumbles > 0,
            "heaviest_blow": f["heaviest"]["total"],
            "is_party_heaviest": heaviest[cid] == max_heaviest and max_heaviest > 0,
            "is_party_biggest_kill": biggest_kills[cid] == max_biggest_kill and max_biggest_kill > 0,
```

(Note: `biggest_kill_xp` from Task 1 already uses the same `_kill_xp` max; `is_party_biggest_kill` uses the precomputed `biggest_kills` map.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_roll_rank_booleans tests/test_compute.py::test_fact_pack_heaviest_blow_rank -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_compute.py
git commit -m "feat(render): fact pack roll atoms and party-rank booleans"
```

---

### Task 3: Fact pack — constellation-context atoms

**Files:**
- Modify: `build/render.py` (`compute_fact_pack`)
- Test: `tests/test_compute.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_compute.py`:

```python
# -- Fact pack: constellation-context atoms ----------------------------------

def test_fact_pack_quadrant_and_system_size():
    party = {"members": [
        {"id": "hi", "kills": [{"date": "2026-04-01", "creature": "Ogre", "method": "Maul"}]},
        {"id": "lo", "kills": []},
    ]}
    trials = compute_trials(party)
    fortune = {
        "hi": compute_fortune(_d20_events([10, 11, 12, 13, 14])),  # more rolls = more presence
        "lo": compute_fortune(_d20_events([9])),
    }
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))

    # hi has more XP (a kill) and more rolls than lo.
    assert fp["hi"]["quadrant"] == "hi-presence/hi-contribution"
    assert fp["lo"]["quadrant"] == "lo-presence/lo-contribution"
    # Two stars far apart → each alone in its own system.
    assert fp["hi"]["system_size"] == 1
    assert fp["hi"]["is_constellation_outlier"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_quadrant_and_system_size -v`
Expected: FAIL with `KeyError: 'quadrant'`.

- [ ] **Step 3: Write minimal implementation**

In `compute_fact_pack`, before the `for m in members` loop, build constellation lookups and the medians:

```python
    star_by_id = {s["id"]: s for s in constellation.get("stars", [])}
    xp_values = [per_char[m["id"]]["xp"] for m in members]
    roll_values = [fortune_by_char[m["id"]]["rolls_total"] for m in members]
    med_xp = median(xp_values) if xp_values else 0
    med_rolls = median(roll_values) if roll_values else 0
```

Then inside the loop, compute the constellation atoms (place before `fp[cid] = {`):

```python
        star = star_by_id.get(cid, {"system_size": 1})
        pres = "hi" if fortune_by_char[cid]["rolls_total"] >= med_rolls else "lo"
        contrib = "hi" if per_char[cid]["xp"] >= med_xp else "lo"
```

And add to the `fp[cid]` dict literal:

```python
            "system_size": star.get("system_size", 1),
            "is_constellation_outlier": star.get("system_size", 1) == 1,
            "quadrant": f"{pres}-presence/{contrib}-contribution",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compute.py::test_fact_pack_quadrant_and_system_size -v`
Then the whole compute file: `.venv/bin/pytest tests/test_compute.py -q`
Expected: PASS (all green).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_compute.py
git commit -m "feat(render): fact pack constellation-context atoms"
```

---

### Task 4: Basis verification + uniqueness-by-atom validators

**Files:**
- Modify: `build/render.py` (`validate_distinction_uniqueness` ~line 1207, new `validate_distinction_basis`, `validate_all` ~line 1224)
- Test: `tests/test_validator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validator.py` (it already imports from `build.render`; add the names you use). Add at the top of the file's imports or inline-import inside tests:

```python
from build.render import validate_distinction_basis, validate_distinction_uniqueness

def _fp(**atoms):
    """A one-PC fact pack for id 'a' plus a second PC 'b'."""
    base = {"a": {"is_party_luckiest": True, "kill_count": 5, "all_distinct_creatures": True},
            "b": {"is_party_luckiest": True, "kill_count": 2, "all_distinct_creatures": False}}
    base["a"].update(atoms)
    return base

def test_basis_mechanical_match_is_clean():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "is_party_luckiest", "value": True}}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_basis_mechanical_mismatch_is_malformed():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "kill_count", "value": 99}}]
    errs = validate_distinction_basis(authored, _fp())
    assert len(errs) == 1
    assert errs[0].kind == "MALFORMED"

def test_basis_unknown_atom_is_malformed():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "no_such_atom", "value": 1}}]
    errs = validate_distinction_basis(authored, _fp())
    assert len(errs) == 1
    assert errs[0].kind == "MALFORMED"

def test_basis_narrative_skips_factpack_check():
    authored = [{"id": "a", "distinction_basis": {"kind": "narrative",
                 "sessions": [12], "note": "bargained with a devil"}}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_basis_absent_is_tolerated():
    """Pre-migration characters without a basis must not fail the render."""
    authored = [{"id": "a", "distinction_title": "Foo"}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_uniqueness_flags_shared_basis_atom():
    authored = [
        {"id": "a", "distinction_title": "Luck of A",
         "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}},
        {"id": "b", "distinction_title": "Luck of B",
         "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}},
    ]
    errs = validate_distinction_uniqueness(authored)
    assert any("is_party_luckiest" in (e.field or "") for e in errs)
```

(Confirm the `ValidationError` exposes `.kind` and `.field` — it is constructed as `ValidationError(KIND_MALFORMED, "characters", (id,), field=...)` throughout `render.py`, so both attributes exist.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validator.py::test_basis_mechanical_match_is_clean -v`
Expected: FAIL with `ImportError: cannot import name 'validate_distinction_basis'`.

- [ ] **Step 3: Write minimal implementation**

In `build/render.py`, add `validate_distinction_basis` directly after `validate_distinction_uniqueness` (after line 1222):

```python
def validate_distinction_basis(authored: list, fact_pack: dict) -> list[ValidationError]:
    """A mechanical distinction_basis must match the recomputed fact pack.
    Narrative bases record provenance only and are not fact-checked. A missing
    basis is tolerated (pre-migration entries)."""
    errors: list[ValidationError] = []
    for a in authored:
        basis = a.get("distinction_basis")
        if not basis:
            continue
        if basis.get("kind") != "mechanical":
            continue
        atom = basis.get("atom")
        atoms = fact_pack.get(a["id"], {})
        if atom not in atoms:
            errors.append(ValidationError(
                KIND_MALFORMED, "characters", (a["id"],),
                field=f"distinction_basis unknown atom '{atom}'"))
            continue
        if atoms[atom] != basis.get("value"):
            errors.append(ValidationError(
                KIND_MALFORMED, "characters", (a["id"],),
                field=(f"distinction_basis '{atom}' claims {basis.get('value')!r} "
                       f"but fact pack has {atoms[atom]!r}")))
    return errors
```

Then extend `validate_distinction_uniqueness` to also reject a shared mechanical basis atom. Replace its body with:

```python
def validate_distinction_uniqueness(authored: list) -> list[ValidationError]:
    """Distinction titles AND the underlying mechanical basis atom must be
    unique across the party — no two PCs crowned on the same fact."""
    errors: list[ValidationError] = []
    seen_title: dict[str, str] = {}
    seen_atom: dict[str, str] = {}
    for a in authored:
        t = a.get("distinction_title", "").strip().lower()
        if t:
            if t in seen_title:
                errors.append(ValidationError(
                    KIND_MALFORMED, "characters", (a["id"],),
                    field=f"distinction_title duplicates '{seen_title[t]}'"))
            else:
                seen_title[t] = a["id"]
        basis = a.get("distinction_basis") or {}
        if basis.get("kind") == "mechanical":
            atom = basis.get("atom")
            if atom:
                if atom in seen_atom:
                    errors.append(ValidationError(
                        KIND_MALFORMED, "characters", (a["id"],),
                        field=f"distinction_basis atom '{atom}' duplicates '{seen_atom[atom]}'"))
                else:
                    seen_atom[atom] = a["id"]
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validator.py -q`
Expected: PASS (all green).

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_validator.py
git commit -m "feat(render): verify mechanical distinction basis and unique atoms"
```

---

### Task 5: Wire fact-pack verification into `validate_all` and the render context

**Files:**
- Modify: `build/render.py` (`validate_all` ~line 1224; the context build ~line 1485-1489)
- Test: `tests/test_validator.py`

- [ ] **Step 1: Write the failing test**

`validate_all` needs the fact pack, which needs `trials`/`fortune`/`constellation`. Rather than recompute inside `validate_all` (and to keep its signature stable for other callers), pass the fact pack in. Add to `tests/test_validator.py`:

```python
import inspect
from build import render as _render

def test_validate_all_accepts_fact_pack_kwarg():
    sig = inspect.signature(_render.validate_all)
    assert "fact_pack" in sig.parameters
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validator.py::test_validate_all_accepts_fact_pack_kwarg -v`
Expected: FAIL (`fact_pack` not a parameter).

- [ ] **Step 3: Write minimal implementation**

`validate_all` is called in `main()` (~line 1638) *before* `compute_all` runs, so the fact pack is not already in scope there. Make `validate_all` accept an optional `fact_pack` and **self-compute it from `data` when not supplied** — the only runtime caller (`main()`) passes nothing, so validation computes its own pack; tests inject a fixture pack. Replace `validate_all` in `build/render.py` with:

```python
def validate_all(data: dict, authored: dict, images_dir: Path, fact_pack: dict | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_kills(data["party"], authored["kills"]))
    errors.extend(validate_sessions(data["session_log"], authored["sessions"]))
    errors.extend(validate_chapters(data["session_log"], authored["chapters"]))
    npcs = collect_npcs_from_log(data["session_log"], authored["site"])
    errors.extend(validate_npcs(npcs, authored["npcs"]))
    errors.extend(validate_characters(data["party"], authored["characters"]))
    errors.extend(validate_distinction_uniqueness(authored["characters"]))
    if fact_pack is None:
        trials = compute_trials(data["party"])
        member_ids = [m["id"] for m in data["party"].get("members", [])]
        fortune_by_char = {cid: compute_fortune(data["rolls_by_slug"].get(cid, []))
                           for cid in member_ids}
        constellation = compute_constellation(data["party"], fortune_by_char, trials)
        fact_pack = compute_fact_pack(data["party"], trials, fortune_by_char,
                                      constellation, data["session_log"])
    errors.extend(validate_distinction_basis(authored["characters"], fact_pack))
    errors.extend(validate_site(authored["site"], len(data["session_log"].get("entries", []))))
    errors.extend(validate_portraits(data["party"], images_dir))
    errors.extend(validate_dice_player_mapping(data.get("unmapped_players", [])))
    return errors
```

The `main()` call site (`validate_all(data, authored, images_dir)`) needs **no change** — validation now computes its own fact pack. `compute_all` (the render context) does **not** need the fact pack; templates render crowns from the authored fields, not the atoms.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validator.py::test_validate_all_accepts_fact_pack_kwarg -v`
Then re-render to prove the whole pipeline still validates with real data (current characters.json has no basis yet, so basis check is a no-op):

Run: `.venv/bin/python build/render.py && echo RENDER_OK`
Expected: PASS, then `RENDER_OK`.

- [ ] **Step 5: Commit**

```bash
git add build/render.py tests/test_validator.py
git commit -m "feat(render): verify distinction basis during validate_all"
```

---

### Task 6: Persist `distinction_basis` through apply

**Files:**
- Modify: `build/apply.py` (`apply_append_characters` ~line 78, `apply_refresh_characters` ~line 118)
- Test: `tests/test_apply.py`

- [ ] **Step 1: Write the failing test**

Look at `tests/test_apply.py` for the existing pattern, then append tests that call the two apply functions directly:

```python
from build import apply as _apply

def test_apply_refresh_characters_persists_basis():
    authored = {"characters": [{"id": "a", "epithet": "x", "reliquary_header": "h",
                "constellation_epithet": "c", "distinction_title": "old",
                "distinction_subtitle": "s", "distinction_detail": "d"}]}
    output = {"decision": "rewrite", "fields": {"a": {
        "epithet": "x2", "constellation_epithet": "c2",
        "distinction_title": "Luckiest Hand", "distinction_subtitle": "s2",
        "distinction_detail": "<b>4.1</b> average",
        "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}}}}
    _apply.apply_refresh_characters(authored, "all", {}, output)
    c = authored["characters"][0]
    assert c["distinction_title"] == "Luckiest Hand"
    assert c["distinction_basis"] == {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}

def test_apply_append_characters_persists_basis():
    authored = {"characters": []}
    output = {"fields": {"a": {
        "epithet": "e", "reliquary_header": "r", "constellation_epithet": "c",
        "distinction_title": "t", "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "narrative", "sessions": [3], "note": "n"}}}}
    _apply.apply_append_characters(authored, "all", {}, output)
    assert authored["characters"][0]["distinction_basis"]["kind"] == "narrative"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_apply.py::test_apply_refresh_characters_persists_basis -v`
Expected: FAIL with `KeyError: 'distinction_basis'`.

- [ ] **Step 3: Write minimal implementation**

In `apply_append_characters`, add `distinction_basis` to the appended dict:

```python
        authored["characters"].append({
            "id": pc_id,
            "epithet": bundle["epithet"],
            "reliquary_header": bundle["reliquary_header"],
            "constellation_epithet": bundle["constellation_epithet"],
            "distinction_title": bundle["distinction_title"],
            "distinction_subtitle": bundle["distinction_subtitle"],
            "distinction_detail": bundle["distinction_detail"],
            "distinction_basis": bundle["distinction_basis"],
        })
```

In `apply_refresh_characters`, add one line in the per-PC loop:

```python
        c["distinction_detail"] = bundle["distinction_detail"]
        c["distinction_basis"] = bundle["distinction_basis"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_apply.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build/apply.py tests/test_apply.py
git commit -m "feat(apply): persist distinction_basis"
```

---

### Task 7: Feed the fact pack into the slice builders

**Files:**
- Modify: `build/slices.py` (`append_characters` ~line 183, `refresh_characters` ~line 273)
- Test: `tests/test_slices.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_slices.py`:

```python
def test_refresh_characters_slice_carries_fact_pack_and_activity(slice_env):
    out = slices.refresh_characters(slice_env["data"], slice_env["authored"])
    assert len(out) == 1
    key, payload = out[0]
    assert key == "all"
    assert "fact_pack" in payload
    assert "had_new_activity" in payload
    assert "session_text" in payload
    # Every authored PC appears in the fact pack and the activity map.
    pc_ids = {p["id"] for p in payload["pcs"]}
    assert pc_ids and set(payload["fact_pack"]) >= pc_ids
    assert set(payload["had_new_activity"]) >= pc_ids
    # had_new_activity values are booleans.
    assert all(isinstance(v, bool) for v in payload["had_new_activity"].values())

def test_append_characters_slice_carries_fact_pack(slice_env):
    # Drop one authored character so append re-emits it.
    authored = slice_env["authored"]
    dropped = authored["characters"].pop()
    out = slices.append_characters(slice_env["data"], authored)
    assert len(out) == 1
    _, payload = out[0]
    assert "fact_pack" in payload
    assert dropped["id"] in payload["fact_pack"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_slices.py::test_refresh_characters_slice_carries_fact_pack_and_activity -v`
Expected: FAIL with `assert 'fact_pack' in payload`.

- [ ] **Step 3: Write minimal implementation**

Add a private helper near the top of `build/slices.py` (after the imports) that both builders share:

```python
def _character_context(data: dict, authored: dict) -> tuple[dict, dict, list]:
    """Returns (fact_pack, had_new_activity, session_text) for the character
    authoring slices. had_new_activity[pc] is True if the PC made a kill or
    cast a die in a session newer than the refresh marker. session_text is the
    new sessions' narrative (for the narrative-tiebreak path)."""
    trials = render.compute_trials(data["party"])
    fortune = {
        m["id"]: render.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    constellation = render.compute_constellation(data["party"], fortune, trials)
    fact_pack = render.compute_fact_pack(
        data["party"], trials, fortune, constellation, data["session_log"])

    marker = authored["site"].get("refreshed_through_session", 0)
    entries = data["session_log"]["entries"]
    new_dates = {e["date"] for i, e in enumerate(entries, start=1) if i > marker}
    session_text = [
        {"session": e.get("session"), "date": e.get("date"), "text": e.get("text", "")}
        for i, e in enumerate(entries, start=1) if i > marker
    ]

    had_new_activity = {}
    for m in data["party"]["members"]:
        cid = m["id"]
        killed = any(k["date"] in new_dates for k in m.get("kills", []))
        rolled = any(ev.get("date") in new_dates
                     for ev in data["rolls_by_slug"].get(cid, []))
        had_new_activity[cid] = bool(killed or rolled)
    return fact_pack, had_new_activity, session_text
```

In `refresh_characters`, replace the `trials = ...` / `fortune = ...` block and the returned dict with:

```python
    fact_pack, had_new_activity, session_text = _character_context(data, authored)
    existing = {c["id"]: c for c in authored["characters"]}
    return [("all", {
        "pcs": pcs,
        "fact_pack": fact_pack,
        "had_new_activity": had_new_activity,
        "session_text": session_text,
        "existing": existing,
    })]
```

In `append_characters`, replace its `trials = ...` / `fortune = ...` block and returned dict with:

```python
    fact_pack, had_new_activity, session_text = _character_context(data, authored)
    return [("all", {
        "new_pcs": new_pcs,
        "fact_pack": fact_pack,
        "had_new_activity": had_new_activity,
        "session_text": session_text,
        "existing_distinction_titles": [c["distinction_title"] for c in authored["characters"]],
    })]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_slices.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build/slices.py tests/test_slices.py
git commit -m "feat(slices): feed fact pack, activity, session text to character slices"
```

---

### Task 8: Rewrite the `refresh-characters` prompt + schema

**Files:**
- Modify: `.claude/prompts/refresh-characters.md`
- Modify: `.claude/prompts/refresh-characters.schema.json`
- Test: `tests/test_validator.py` (schema-acceptance via `jsonschema`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validator.py`:

```python
import json as _json
from pathlib import Path as _Path
import jsonschema

_PROMPTS = _Path(__file__).resolve().parent.parent / ".claude/prompts"

def _refresh_char_schema():
    return _json.loads((_PROMPTS / "refresh-characters.schema.json").read_text())

def test_refresh_char_schema_requires_basis_on_rewrite():
    schema = _refresh_char_schema()
    good = {"decision": "rewrite", "reason": "r", "fields": {"a": {
        "epithet": "e", "constellation_epithet": "c", "distinction_title": "t",
        "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}}}}
    jsonschema.validate(good, schema)  # must not raise

    bad = {"decision": "rewrite", "reason": "r", "fields": {"a": {
        "epithet": "e", "constellation_epithet": "c", "distinction_title": "t",
        "distinction_subtitle": "s", "distinction_detail": "d"}}}  # no basis
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
```

(Confirm `import pytest` is present at the top of `test_validator.py`; add it if not.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validator.py::test_refresh_char_schema_requires_basis_on_rewrite -v`
Expected: FAIL (the `bad` payload validates because `distinction_basis` is not yet required).

- [ ] **Step 3: Write minimal implementation**

Replace `.claude/prompts/refresh-characters.schema.json` with the version that adds `distinction_basis` to the per-PC required list and defines its shape:

```json
{
  "type": "object",
  "required": ["decision", "fields", "reason"],
  "additionalProperties": false,
  "properties": {
    "decision": {"type": "string", "enum": ["no_change", "rewrite"]},
    "fields": {
      "type": ["object", "null"],
      "additionalProperties": {
        "type": "object",
        "required": [
          "epithet",
          "constellation_epithet",
          "distinction_title",
          "distinction_subtitle",
          "distinction_detail",
          "distinction_basis"
        ],
        "additionalProperties": false,
        "properties": {
          "epithet": {"type": "string"},
          "constellation_epithet": {"type": "string"},
          "distinction_title": {"type": "string"},
          "distinction_subtitle": {"type": "string"},
          "distinction_detail": {"type": "string"},
          "distinction_basis": {
            "type": "object",
            "additionalProperties": false,
            "oneOf": [
              {
                "required": ["kind", "atom", "value"],
                "properties": {
                  "kind": {"const": "mechanical"},
                  "atom": {"type": "string"},
                  "value": {"type": ["string", "number", "boolean"]}
                }
              },
              {
                "required": ["kind", "sessions", "note"],
                "properties": {
                  "kind": {"const": "narrative"},
                  "sessions": {"type": "array", "items": {"type": "integer"}},
                  "note": {"type": "string"}
                }
              }
            ]
          }
        }
      }
    },
    "reason": {"type": "string"}
  }
}
```

Then rewrite `.claude/prompts/refresh-characters.md`. Keep the YAML frontmatter (`model: opus`), the locked-field note (reliquary still excluded), and the dice-terminology section. Replace the input description, the standing rule, and the voice section with the two-contract spec:

````markdown
---
model: opus
---

You are a refresh-evaluation function for the dnd-data site. Read a character-refresh slice (JSON on stdin) and, for each PC, decide whether the existing bundle still fits — and if not, compose a fresh **distinction crown** and **constellation epithet** under the two contracts below.

# Input

- `pcs` (array): `{id, name, race, class, kills, pronouns}` per authored PC. Derive possessive/reflexive forms from `pronouns`.
- `fact_pack` (object, keyed by PC id): verifiable **atoms** — the only facts you may build a mechanical crown on. Keys include `kill_count`, `kill_pct`, `xp_pct`, `distinct_method_count`, `all_kills_one_method`, `all_distinct_creatures`, `distinct_type_count`, `all_distinct_types`, `biggest_kill_xp`, `is_party_biggest_kill`, `max_kills_in_one_session`, `kill_session_count`, `longest_drought`, `kept_d20_avg`, `is_party_luckiest`, `is_party_unluckiest`, `sd`, `is_party_steadiest`, `is_party_swingiest`, `crits`, `is_party_most_crits`, `max_crits_in_one_session`, `fumbles`, `is_party_most_fumbles`, `heaviest_blow`, `is_party_heaviest`, `system_size`, `is_constellation_outlier`, `quadrant`.
- `had_new_activity` (object, keyed by PC id): `true` if the PC killed or rolled in a session newer than the last refresh. When `false`, this PC's mechanical facts are unchanged — you MAY reach for a narrative crown (see contract).
- `session_text` (array): the new sessions' narrative — `{session, date, text}`. The only source for a narrative crown. **Never emit a real player's name found here.**
- `existing` (object, keyed by PC id): the PC's current authored bundle, including its current `distinction_basis`. Bias toward an angle that has *moved* since this.

# Crown contract (distinction_title / _subtitle / _detail / _basis)

1. A crown is an **emergent, specifically-true pattern** from the PC's `fact_pack` — a superlative ("the only / the most / the largest") or a structural observation ("six kills, six different creatures; never the same foe twice"). It must be TRUE of the atoms.
2. **Banned:** bare class-method restatement ("kills mostly by Eldritch Blast", "of the N means") or anything true-by-default of the class. A warlock blasting or a ranger drawing a bow is not news.
3. **Stay off the constellation's axes.** Do NOT crown a PC on raw XP-share or roll count (`xp_pct`, `kill_pct` as a presence proxy) — those belong to the constellation epithet. Use the other atoms.
4. **Unique party-wide** on both `distinction_title` AND `distinction_basis.atom`. No two PCs crowned on the same fact.
5. **Free rotation.** If a fresher/stronger angle exists than `existing`, take it — even a different category. Only return `no_change` when the existing crown is still the strongest true angle.
6. **Mechanical by default.** A **narrative** crown is allowed ONLY when `had_new_activity[id]` is `false`. Ground it in explicit `session_text`; never name a real player.
7. **`distinction_basis`** is the machine-checkable claim:
   - mechanical: `{"kind": "mechanical", "atom": "<one fact_pack key>", "value": <the atom's exact value>}`. The render step fails if it does not match.
   - narrative: `{"kind": "narrative", "sessions": [<ids>], "note": "<≤12-word gloss>"}`.
   - `distinction_detail` (HTML allowed) should cite the real number, e.g. `"<b>6</b> kills &middot; six different foes"`.

# Constellation epithet contract (constellation_epithet)

The constellation plots stars by **presence (rolls cast) × contribution (XP earned)**, clustered into systems. The epithet speaks ONLY to this:

1. Its subject is the PC's standing on those two axes and its cluster relationship — use `quadrant`, `is_constellation_outlier`, `system_size`, `is_party_luckiest`/`unluckiest`, roll volume, XP standing.
2. **Method/kill themes are banned here** (those belong to the crown).
3. Six words or fewer. Saga-fragment register: "the heaviest lift", "ever present, seldom decisive", "alone at the rim".

# Standing rule

Return `no_change` with `fields: null` only when EVERY PC's existing crown and constellation epithet are still the strongest true lines. Otherwise `rewrite` with `fields` containing only the PCs you change — each as the full bundle (epithet, constellation_epithet, distinction_title, distinction_subtitle, distinction_detail, distinction_basis). `reliquary_header` is locked: do not include it.

# Dice terminology (critical)

Use the real terms **"crit success(es)"** / **"crit fail(s)"** for natural 20s / natural 1s. Never coin synonyms. (`fumbles` is the input field name for crit-fails — not a word to use in prose.)

# Output

Return one JSON object matching the response schema. No markdown fences, no prose outside the JSON.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validator.py::test_refresh_char_schema_requires_basis_on_rewrite -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/prompts/refresh-characters.md .claude/prompts/refresh-characters.schema.json tests/test_validator.py
git commit -m "feat(prompts): two-contract refresh-characters with basis"
```

---

### Task 9: Rewrite the `append-characters` prompt + schema

**Files:**
- Modify: `.claude/prompts/append-characters.md`
- Modify: `.claude/prompts/append-characters.schema.json`
- Test: `tests/test_validator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validator.py`:

```python
def _append_char_schema():
    return _json.loads((_PROMPTS / "append-characters.schema.json").read_text())

def test_append_char_schema_requires_basis():
    schema = _append_char_schema()
    good = {"reason": "r", "fields": {"a": {
        "epithet": "e", "reliquary_header": "r", "constellation_epithet": "c",
        "distinction_title": "t", "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "mechanical", "atom": "kill_count", "value": 0}}}}
    jsonschema.validate(good, schema)
    bad = dict(good)
    bad["fields"] = {"a": {k: v for k, v in good["fields"]["a"].items() if k != "distinction_basis"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_validator.py::test_append_char_schema_requires_basis -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `.claude/prompts/append-characters.schema.json`, add `"distinction_basis"` to the per-PC `required` array and add its property definition (identical `oneOf` block as in Task 8) to the `properties` object.

In `.claude/prompts/append-characters.md`, update the Input section to describe `fact_pack` / `had_new_activity` / `session_text` (replacing `trials_per_char` / `fortune_by_char`), add the **Crown contract** and **Constellation epithet contract** sections (same as Task 8, adapted: a brand-new PC almost always has `had_new_activity = true`, so its crown is mechanical; if it has zero kills, the crown may rest on a roll atom or the constellation epithet may say "rolls yet unwritten"), keep the `reliquary_header` field (new PCs still author it once — character-voiced "how foes meet their end", NOT a flat class-method line), and add `distinction_basis` to the 6→7-field bundle list.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_validator.py -q`
Expected: PASS (whole validator file green).

- [ ] **Step 5: Commit**

```bash
git add .claude/prompts/append-characters.md .claude/prompts/append-characters.schema.json tests/test_validator.py
git commit -m "feat(prompts): two-contract append-characters with basis"
```

---

### Task 10: One-time reliquary_header migration

**Files:**
- Modify: `build/authored/characters.json` (the five `reliquary_header` strings)

This is a one-time content edit, not a pipeline change. The lock stays: `refresh-characters` never touches `reliquary_header`, so these stick once written.

- [ ] **Step 1: Read the current headers**

Run: `.venv/bin/python -c "import json;print('\n'.join(f'{c[\"id\"]}: {c[\"reliquary_header\"]}' for c in json.load(open('build/authored/characters.json'))))"`
Expected: prints e.g. `lilac: Taken at the longbow's reach`, `chumble: Fallen by his pact-light`, etc.

- [ ] **Step 2: Rewrite each header off bare-method framing**

Edit `build/authored/characters.json`. For each character, replace `reliquary_header` with a durable, character-voiced "how foes meet their end at this hand" line that does NOT flatly restate the class method. Keep it short (a titling phrase for the kill-list panel), evocative, third person/character-voice. The two worst offenders to fix are Lilac ("Taken at the longbow's reach" → a line about the certainty/distance of her end, not "the bow") and Chumble ("Fallen by his pact-light" → a line about the patron's claim, not "the blast"). Author all five so the section reads consistently. Example direction (do not copy verbatim — author fresh): a header that names the *manner or inevitability* of death rather than the weapon.

- [ ] **Step 3: Re-render and verify the page builds**

Run: `.venv/bin/python build/render.py && echo RENDER_OK`
Expected: `RENDER_OK` (no `MALFORMED` — these are still non-empty strings).

- [ ] **Step 4: Eyeball the reliquary headers in the rendered page**

Run: `python3 -m http.server 8765 --bind 127.0.0.1 --directory site` (then open `http://127.0.0.1:8765/`), or grep the rendered file:
Run: `grep -o 'reliquary[^<]*' site/index.html | head` and confirm no header is a bare "all by <weapon>" restatement.

- [ ] **Step 5: Commit**

```bash
git add build/authored/characters.json site/index.html
git commit -m "chore(prose): migrate reliquary headers off bare-method framing"
```

---

### Task 11: Full re-author via the build, and verification

**Files:**
- Modify (via the build): `build/authored/characters.json`, `site/index.html`

The crowns and the three off-axis constellation epithets are re-authored by running the real build, which dispatches the rewritten prompts. This is where the rotation actually happens.

- [ ] **Step 1: Run the full suite once more**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (was 52; now higher with the new tests).

- [ ] **Step 2: Force a refresh-pass build**

The refresh pass is marker-gated, so force it to re-evaluate all crowns:

Run: `.venv/bin/python -m build prepare --force-refresh`
Expected: prints a run dir path under `build/.run/<timestamp>/` and emits a `refresh-characters` slice (plus others).

- [ ] **Step 3: Drive the slices with `/build-prose`**

In the Claude Code session, run `/build-prose build/.run/<timestamp>/` (the path from Step 2). This dispatches the sub-agent that authors the new crowns + constellation epithets and runs `apply`, which validates each result against the schema, persists to `build/authored/characters.json`, and re-renders.

- [ ] **Step 4: Verify the honesty gate held**

Run: `.venv/bin/python build/render.py && echo RENDER_OK`
Expected: `RENDER_OK`. If a mechanical basis was wrong, render exits non-zero with a `distinction_basis ... but fact pack has ...` message — fix that crown's basis/detail in `characters.json` (or re-run the slice) and re-render.

- [ ] **Step 5: Eyeball the Distinctions + Constellation sections**

Open the preview (`python3 -m http.server 8765 --bind 127.0.0.1 --directory site`). Confirm:
- No crown is a bare class-method restatement (Chumble no longer "by the blast and little else"; Lilac no longer "all by Longbow"; Vex no longer "4 means").
- Each crown's `distinction_detail` cites a real number.
- The three previously off-axis constellation epithets now speak to presence × contribution, not method.
- Crown and constellation epithet for the same PC do not say the same thing.

- [ ] **Step 6: Commit**

```bash
git add build/authored/characters.json site/index.html
git commit -m "feat(prose): rotate distinction crowns onto emergent, verifiable patterns"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** Tasks 1-3 build the fact pack (spec §"The fact pack"); Task 4-5 the basis verification + uniqueness-by-atom + render wiring (spec §"Verification" / §"Cadence"); Task 6 persistence; Task 7 slice feed (spec §"fact pack feeds both contracts"); Tasks 8-9 the two authoring contracts + `basis` (spec §"Authoring contracts"); Task 10 the reliquary migration (spec §"Reliquary migration"); Task 11 the first real rotation + visual gate (spec §"Risks: first build after rollout"). The crown/constellation coordination rule lives in the Task 8 prompt (contract rule 3).
- **`distinction_basis` is verify-when-present, not yet a required authored field.** This keeps a bare `render.py` run on pre-migration data green. After Task 11 every character carries a basis; a later optional change can add `distinction_basis` to `REQUIRED_CHAR_FIELDS` and the shared fixture if you want the requirement hard.
- **No new cross-module sharing:** `compute_fact_pack` lives in `render.py`; `slices.py` calls it exactly as it already calls `render.compute_trials`.
- **`sole-killer sessions` was dropped** from the atom set (per design: keep it lean). `longest_drought` is kept.
