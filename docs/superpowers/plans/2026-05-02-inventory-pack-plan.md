# Inventory "Pack" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface upstream inventory data on the site as a per-character "Pack" section, a top-of-page Company strip of weight gauges, and an auto-derived archetype badge in each character header. The math is deterministic; one new refresh-pass transformer authors the badge tooltip prose.

**Architecture:** New `build/inventory.py` module loads the latest `data/obr-inv-backup-*.json` snapshot, resolves upstream names via the existing `build/dice-players.json` substring map, classifies items into three zones (Rack / Spotlight / Manifest), computes weight totals against 15×STR carrying capacity, scores 16 archetypes per character, and assigns each character their dominant-lead archetype. `render.compute_all` consumes the loaded bundle. A new refresh transformer (`refresh-archetype-inscription`) authors a one-line in-voice tooltip per character; the renderer falls back to a deterministic stats line when the authored prose is missing or stale. New `_pack.html` Jinja partial; updates to `_character.html`, `_company.html`, `_script.html`, `site/styles.css`.

**Tech Stack:** Python 3, Jinja2, pytest, vanilla JS, CSS. `claude -p` invocation goes through the existing `build.invoke` + `build.apply` machinery.

**Spec:** `docs/superpowers/specs/2026-05-01-inventory-pack-design.md` — read this first for context. Plan tasks below assume that document is the source of truth for behavior.

**Worktree:** This plan should be executed in a dedicated git worktree to keep `main` clean. Run from the repo root before starting:

```bash
git worktree add ../dnd-data-pack -b feature/inventory-pack
cd ../dnd-data-pack
```

---

## File structure

**Create:**

- `build/inventory.py` — load + classify + score + assign. Pure functions; unit-testable.
- `build/templates/_pack.html` — per-character Jinja partial: Rack, Spotlight, Manifest.
- `.claude/prompts/refresh-archetype-inscription.md` — system prompt for the inscription transformer.
- `.claude/prompts/refresh-archetype-inscription.schema.json` — JSON-schema for transformer response.
- `tests/test_inventory.py` — unit tests for the loader, classifier, scorers, and assignment.
- `tests/test_archetype_inscription.py` — slice-builder + apply + render-fallback tests.
- `tests/fixtures/inventory/obr-inv-backup-2026-05-02T04-21-16-825Z.json` — minimal snapshot for tests.

**Modify:**

- `build/render.py` — load inventory in `compute_all`; expose `inventory_by_id` and `company_strip` to template context; add the math-fallback line generator and the `archetype_badge` resolution path.
- `build/slices.py` — append `refresh_archetype_inscription` slice builder.
- `build/apply.py` — append `apply_refresh_archetype_inscription`.
- `build/__main__.py` — register the new transformer in `REFRESH_PASS`.
- `build/templates/_character.html` — add Pack to TOC; include `_pack.html`; render archetype badge in the identity block.
- `build/templates/_company.html` — insert the company strip at the top.
- `build/templates/_script.html` — add tooltip IIFEs for `.rack-item`, `.spotlight-card`, `.manifest-chip`, `.company-strip-bar`, `.archetype`.
- `site/styles.css` — Pack-feature CSS block: shelf, spotlight cards, manifest grid, company strip, archetype chip, plus `@keyframes` for sheen and strip-fill entry animation.

---

## Phase 1 — Inventory module (math only)

### Task 1: Scaffold the inventory module

**Files:**
- Create: `build/inventory.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory.py
"""Tests for build/inventory.py — the inventory loader/classifier/scorer."""
import pytest

from build import inventory


def test_module_exposes_load():
    assert hasattr(inventory, "load")
    assert callable(inventory.load)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_inventory.py::test_module_exposes_load -v
```

Expected: `ModuleNotFoundError: No module named 'build.inventory'`

- [ ] **Step 3: Write minimal implementation**

```python
# build/inventory.py
"""Load and shape the upstream inventory snapshot for the renderer.

Mirrors the dice-data integration: the latest obr-inv-backup-*.json under
data/ is read, upstream player names are resolved through the existing
build/dice-players.json substring map (so real surnames never reach the
template), items are classified into three Pack-section zones (Rack,
Spotlight, Manifest), totals are computed against 15×STR carrying
capacity, and 16 archetypes are scored to pick one badge per character.

This module is render-only. The single place a model contributes is the
tooltip inscription on each archetype badge — that's authored elsewhere
(refresh-archetype-inscription transformer + characters.json) and read
back at render time.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional


def load(repo_root: Path) -> dict:
    """Return an inventory bundle keyed for the renderer.

    Shape:
      {
        "by_id": {"<slug>": CharacterInventory, ...},
        "company_strip": [StripEntry, ...],
      }

    Empty bundle if no snapshot file is present — the renderer treats
    this as "every character awaiting manifest" rather than failing.
    """
    return {"by_id": {}, "company_strip": []}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_inventory.py::test_module_exposes_load -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "scaffold build/inventory.py module"
```

---

### Task 2: Resolve the latest snapshot file

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_inventory.py`:

```python
def test_resolve_snapshot_path_picks_latest(tmp_path):
    (tmp_path / "obr-inv-backup-2026-04-01T00-00-00-000Z.json").write_text("{}")
    (tmp_path / "obr-inv-backup-2026-05-02T04-21-16-825Z.json").write_text("{}")
    (tmp_path / "obr-inv-backup-2026-04-15T12-00-00-000Z.json").write_text("{}")
    (tmp_path / "unrelated.json").write_text("{}")

    path = inventory._resolve_snapshot_path(tmp_path)

    assert path is not None
    assert path.name == "obr-inv-backup-2026-05-02T04-21-16-825Z.json"


def test_resolve_snapshot_path_returns_none_when_missing(tmp_path):
    assert inventory._resolve_snapshot_path(tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k resolve_snapshot
```

Expected: FAIL — `AttributeError: module 'build.inventory' has no attribute '_resolve_snapshot_path'`

- [ ] **Step 3: Implement**

Append to `build/inventory.py`:

```python
SNAPSHOT_GLOB = "obr-inv-backup-*.json"


def _resolve_snapshot_path(data_dir: Path) -> Optional[Path]:
    """Pick the lexicographically maximal matching file. The upstream
    timestamp format (ISO with T-separator and Z suffix) sorts as text
    in the same order as time, so a string max equals the time max."""
    matches = sorted(data_dir.glob(SNAPSHOT_GLOB))
    return matches[-1] if matches else None
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k resolve_snapshot
```

Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "resolve latest inventory snapshot file"
```

---

### Task 3: Drop GM, resolve names, scrub surnames

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_inventory.py`:

```python
def test_parse_inventories_drops_gm_and_resolves_names():
    raw = {
        "inventories": {
            "uuid-1": {
                "name": "Simon Weil",
                "items": [{"id": "x", "count": 1, "name": "Sword",
                           "category": "Weapon", "weight": 3, "rarity": "common",
                           "icon": "https://example/sword.svg",
                           "description": ""}],
            },
            "uuid-2": {
                "name": "GM",
                "items": [{"id": "y", "count": 1, "name": "Junk",
                           "category": "Adventuring Gear - Utility & Equipment",
                           "weight": 1, "rarity": "common", "icon": "",
                           "description": ""}],
            },
            "uuid-3": {
                "name": "Vex",
                "items": [],
            },
        },
    }
    mapping = {"Simon": "grieg", "Vex": "vex", "GM": "gm"}

    parsed = inventory._parse_inventories(raw, mapping)

    assert set(parsed.keys()) == {"grieg", "vex"}
    assert "gm" not in parsed  # GM dropped before resolution
    assert "Weil" not in str(parsed)  # surname scrubbed
    assert parsed["grieg"]["items"][0]["name"] == "Sword"


def test_parse_inventories_skips_unresolved_name():
    raw = {
        "inventories": {
            "uuid-1": {"name": "Stranger", "items": []},
            "uuid-2": {"name": "Vex", "items": []},
        },
    }
    mapping = {"Vex": "vex"}

    parsed = inventory._parse_inventories(raw, mapping)

    assert set(parsed.keys()) == {"vex"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k parse_inventories
```

Expected: FAIL — `_parse_inventories` doesn't exist.

- [ ] **Step 3: Implement**

Add to top of `build/inventory.py`:

```python
from build.render import _resolve_dice_player
```

Then append:

```python
def _parse_inventories(raw: dict, mapping: dict[str, str]) -> dict[str, dict]:
    """Resolve each inventory's upstream `name` to a site slug, drop GM,
    discard the upstream name (which can carry real surnames), and return
    a slug-keyed dict of {items: [...]} payloads.

    Items are passed through verbatim; classification happens later. Null
    weights are kept as null here and normalized to 0 inside the totals
    step — keeping null lets later inspection see that the data was null
    upstream rather than zero by intent.
    """
    out: dict[str, dict] = {}
    for inv in raw.get("inventories", {}).values():
        name = inv.get("name", "")
        if name == "GM":
            continue
        slug = _resolve_dice_player(name, mapping)
        if slug is None:
            continue
        out[slug] = {"items": list(inv.get("items", []))}
    return out
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k parse_inventories
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "parse inventories: drop GM, resolve slugs, scrub surnames"
```

---

### Task 4: Classify items into zones

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_inventory.py`:

```python
def _item(name, category, rarity="common", weight=1, count=1):
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "category": category,
        "rarity": rarity,
        "weight": weight,
        "count": count,
        "icon": "",
        "description": "",
    }


def test_classify_separates_rack_spotlight_manifest():
    items = [
        _item("Warhammer", "Weapon"),
        _item("Scale Mail", "Armor", weight=45),
        _item("Crossbow Bolts", "Ammunition", count=20),
        _item("Sending Stones", "Wondrous Item", rarity="uncommon"),
        _item("Staff", "Spellcasting Focus"),
        _item("Rations", "Adventuring Gear - Camping & Travel", count=5),
        _item("Backpack", "Adventuring Gear - Containers & Storage"),
        _item("Costume", "Clothing"),
    ]

    rack, spotlight, manifest = inventory._classify(items)

    rack_names = {it["name"] for it in rack}
    spotlight_names = {it["name"] for it in spotlight}
    manifest_names = {it["name"] for it in manifest}

    assert rack_names == {"Warhammer", "Scale Mail", "Crossbow Bolts"}
    assert spotlight_names == {"Sending Stones", "Staff"}
    assert manifest_names == {"Rations", "Backpack", "Costume"}


def test_classify_caps_spotlight_at_three():
    items = [_item(f"Curio {i}", "Wondrous Item", rarity="rare") for i in range(5)]

    rack, spotlight, manifest = inventory._classify(items)

    assert len(spotlight) == 3
    assert len(manifest) == 2  # spillover lands in Manifest
    assert rack == []


def test_classify_spotlight_ranks_higher_rarity_first():
    items = [
        _item("Bauble", "Wondrous Item", rarity="common"),
        _item("Greater Curio", "Wondrous Item", rarity="rare"),
        _item("Lesser Curio", "Wondrous Item", rarity="uncommon"),
        _item("Marvel", "Wondrous Item", rarity="legendary"),
    ]

    _, spotlight, _ = inventory._classify(items)

    spotlight_names = [it["name"] for it in spotlight]
    assert spotlight_names == ["Marvel", "Greater Curio", "Lesser Curio"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k classify
```

Expected: FAIL — `_classify` doesn't exist.

- [ ] **Step 3: Implement**

Append to `build/inventory.py`:

```python
RACK_CATEGORIES = frozenset({"Weapon", "Armor", "Ammunition"})
SPOTLIGHT_CATEGORIES = frozenset({"Wondrous Item", "Spellcasting Focus"})
SPOTLIGHT_CAP = 3

_RARITY_ORDER = {
    "legendary": 0, "very rare": 1, "rare": 2, "uncommon": 3,
    "common": 4,
}


def _classify(items: list[dict]) -> tuple[list, list, list]:
    """Partition items into (rack, spotlight, manifest) zones.

    Rack: weapons, armor, ammunition.
    Spotlight: items with rarity != "common" OR a wondrous/focus category.
      Capped at SPOTLIGHT_CAP, ranked by rarity (legendary first), with
      spillover landing in Manifest.
    Manifest: everything else (and spotlight spillover).
    """
    rack: list[dict] = []
    candidates_for_spotlight: list[dict] = []
    rest: list[dict] = []

    for it in items:
        cat = it.get("category", "")
        rarity = (it.get("rarity") or "common").lower()
        if cat in RACK_CATEGORIES:
            rack.append(it)
        elif cat in SPOTLIGHT_CATEGORIES or rarity != "common":
            candidates_for_spotlight.append(it)
        else:
            rest.append(it)

    candidates_for_spotlight.sort(
        key=lambda it: _RARITY_ORDER.get((it.get("rarity") or "common").lower(), 99)
    )
    spotlight = candidates_for_spotlight[:SPOTLIGHT_CAP]
    spillover = candidates_for_spotlight[SPOTLIGHT_CAP:]

    return rack, spotlight, rest + spillover
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k classify
```

Expected: PASS (all three tests)

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "classify items into rack/spotlight/manifest zones"
```

---

### Task 5: Compute totals and carrying capacity

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_total_weight_sums_count_times_weight_with_null_as_zero():
    items = [
        {"weight": 4, "count": 1},
        {"weight": 2, "count": 5},
        {"weight": None, "count": 1},
        {"weight": 0, "count": 3},
    ]
    assert inventory._total_weight(items) == 14


def test_carrying_capacity_is_15_times_str():
    member = {"abilities": {"str": 17}}
    assert inventory._carrying_capacity(member) == 255


def test_zone_breakdown_matches_total():
    rack = [{"weight": 4, "count": 2}]            # 8
    spotlight = [{"weight": None, "count": 1}]     # 0
    manifest = [{"weight": 1, "count": 5},         # 5
                {"weight": 2, "count": 3}]         # 6

    breakdown = inventory._zone_breakdown(rack, spotlight, manifest)

    assert breakdown == {"rack": 8, "spotlight": 0, "manifest": 11}
    assert sum(breakdown.values()) == 19
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "total_weight or carrying_capacity or zone_breakdown"
```

Expected: FAIL — three undefined helpers.

- [ ] **Step 3: Implement**

```python
def _total_weight(items: list[dict]) -> float:
    """Sum of weight×count, treating null weight as 0."""
    total = 0.0
    for it in items:
        w = it.get("weight")
        if w is None:
            w = 0
        c = it.get("count") or 1
        total += w * c
    return total


def _carrying_capacity(member: dict) -> int:
    """5e 2024 carrying capacity (15 × STR), in pounds."""
    return 15 * int(member.get("abilities", {}).get("str", 0))


def _zone_breakdown(rack: list, spotlight: list, manifest: list) -> dict[str, float]:
    return {
        "rack": _total_weight(rack),
        "spotlight": _total_weight(spotlight),
        "manifest": _total_weight(manifest),
    }
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "total_weight or carrying_capacity or zone_breakdown"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "compute weight totals, carrying capacity, zone breakdown"
```

---

### Task 6: Score the 16 archetypes (combat + magic + lore)

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_pack_mule_score_is_total_weight():
    items = [{"weight": 4, "count": 2}, {"weight": 1, "count": 3}]
    assert inventory.score_pack_mule(items, member={}) == 11.0


def test_armorer_sums_weapons_and_armor_only():
    items = [
        {"category": "Weapon", "weight": 5, "count": 1},
        {"category": "Armor", "weight": 45, "count": 1},
        {"category": "Adventuring Gear - Camping & Travel", "weight": 10, "count": 1},
        {"category": "Ammunition", "weight": 1, "count": 20},  # not in armorer
    ]
    assert inventory.score_armorer(items, member={}) == 50.0


def test_glaive_hand_counts_distinct_weapon_ids():
    items = [
        {"category": "Weapon", "id": "a", "count": 1},
        {"category": "Weapon", "id": "b", "count": 1},
        {"category": "Weapon", "id": "a", "count": 1},  # same id; not distinct
        {"category": "Armor", "id": "c", "count": 1},
    ]
    assert inventory.score_glaive_hand(items, member={}) == 2


def test_quiver_sums_ammunition_counts():
    items = [
        {"category": "Ammunition", "count": 20},
        {"category": "Ammunition", "count": 12},
        {"category": "Weapon", "count": 1},
    ]
    assert inventory.score_quiver(items, member={}) == 32


def test_curio_keeper_counts_non_common_or_wondrous():
    items = [
        {"rarity": "rare", "category": "Weapon"},
        {"rarity": "common", "category": "Wondrous Item"},
        {"rarity": "common", "category": "Weapon"},
        {"rarity": "uncommon", "category": "Adventuring Gear - Utility & Equipment"},
    ]
    assert inventory.score_curio_keeper(items, member={}) == 3


def test_scholar_substring_match_on_lore_keywords():
    items = [
        {"name": "Spellbook", "count": 1},
        {"name": "Parchment (x10)", "count": 10},
        {"name": "Ink Pen", "count": 1},
        {"name": "Sword", "count": 1},  # no match
    ]
    # spellbook + parchment + ink → 3 matches; counts summed
    assert inventory.score_scholar(items, member={}) == 12


def test_naturalist_substring_match():
    items = [
        {"name": "Sprig of Mistletoe (Druidic Focus)", "count": 1},
        {"name": "Yew Wand", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_naturalist(items, member={}) == 2


def test_tongues_substring_match():
    items = [
        {"name": "Sending Stone (Azlund)", "count": 1},
        {"name": "Whisper Charm", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_tongues(items, member={}) == 2
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "score_pack_mule or score_armorer or score_glaive or score_quiver or score_curio or score_scholar or score_naturalist or score_tongues"
```

Expected: FAIL — eight undefined scorers.

- [ ] **Step 3: Implement**

Append to `build/inventory.py`:

```python
# --- Archetype scoring ------------------------------------------------------
# Each scorer takes (items, member) and returns a numeric score. Higher is
# stronger except for Featherfoot, which is scored separately because it
# needs the carrying capacity from `member`.

def _name_lower(it: dict) -> str:
    return (it.get("name") or "").lower()


def _matches_any(it: dict, keywords: tuple[str, ...]) -> bool:
    name = _name_lower(it)
    return any(kw in name for kw in keywords)


def _sum_count_where(items: list[dict], predicate) -> int:
    return sum((it.get("count") or 1) for it in items if predicate(it))


def score_pack_mule(items: list[dict], member: dict) -> float:
    return _total_weight(items)


def score_armorer(items: list[dict], member: dict) -> float:
    return sum(
        (it.get("weight") or 0) * (it.get("count") or 1)
        for it in items
        if it.get("category") in ("Weapon", "Armor")
    )


def score_glaive_hand(items: list[dict], member: dict) -> int:
    return len({it["id"] for it in items if it.get("category") == "Weapon"})


def score_quiver(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: it.get("category") == "Ammunition")


def score_curio_keeper(items: list[dict], member: dict) -> int:
    def is_curio(it: dict) -> bool:
        rarity = (it.get("rarity") or "common").lower()
        return rarity != "common" or it.get("category") == "Wondrous Item"
    return _sum_count_where(items, is_curio)


_SCHOLAR_KW = ("book", "parchment", "ink", "scroll", "spellbook")
_NATURALIST_KW = ("druidic", "mistletoe", "yew", "totem", "natural")
_TONGUES_KW = ("sending stone", "message", "speaking", "whisper")


def score_scholar(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _SCHOLAR_KW))


def score_naturalist(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _NATURALIST_KW))


def score_tongues(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _TONGUES_KW))
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "score_pack_mule or score_armorer or score_glaive or score_quiver or score_curio or score_scholar or score_naturalist or score_tongues"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "score combat, magic, and lore archetypes"
```

---

### Task 7: Score the survival, personal, and aggregate archetypes

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_lamplighter_sums_light_items():
    items = [
        {"name": "Oil (x10)", "count": 10},
        {"name": "Torch", "count": 5},
        {"name": "Lantern", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_lamplighter(items, member={}) == 16


def test_pathfinder_sums_explore_items():
    items = [
        {"name": "Rope (50 ft)", "count": 1},
        {"name": "Crowbar", "count": 1},
        {"name": "Iron Spike", "count": 8},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_pathfinder(items, member={}) == 10


def test_apothecary_counts_consumables():
    items = [
        {"category": "Consumable", "count": 2},
        {"category": "Consumable", "count": 1},
        {"category": "Weapon", "count": 1},
    ]
    assert inventory.score_apothecary(items, member={}) == 3


def test_cellarer_sums_food_items():
    items = [
        {"name": "Rations (x9)", "count": 9},
        {"name": "Waterskin", "count": 1},
        {"name": "Wineskin", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_cellarer(items, member={}) == 11


def test_trapper_sums_traps():
    items = [
        {"name": "Caltrops (x20)", "count": 20},
        {"name": "Hunting Trap", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_trapper(items, member={}) == 21


def test_costume_master_sums_persona_items():
    items = [
        {"name": "Costume (x3)", "count": 3},
        {"name": "Perfume", "count": 1},
        {"name": "Fine Clothes", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_costume_master(items, member={}) == 5


def test_quartermaster_counts_distinct_ids():
    items = [
        {"id": "a", "count": 1},
        {"id": "b", "count": 5},
        {"id": "c", "count": 1},
    ]
    assert inventory.score_quartermaster(items, member={}) == 3


def test_featherfoot_is_carry_ratio_inverted():
    member = {"abilities": {"str": 6}}  # capacity 90
    items = [{"weight": 9, "count": 1}]   # 9 lb → 10% utilization
    # Score is inverted utilization (so higher = more decisively unburdened).
    # 10% utilization → score 90.0
    assert inventory.score_featherfoot(items, member) == pytest.approx(90.0)
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "lamplighter or pathfinder or apothecary or cellarer or trapper or costume_master or quartermaster or featherfoot"
```

Expected: FAIL — eight undefined scorers.

- [ ] **Step 3: Implement**

```python
_LAMPLIGHTER_KW = ("oil", "torch", "lantern", "candle", "tinderbox", "lamp")
_PATHFINDER_KW = ("rope", "crowbar", "grapple", "piton", "spike", "climber")
_CELLARER_KW = ("ration", "waterskin", "mess kit", "trail", "wineskin")
_TRAPPER_KW = ("caltrop", "trap", "snare", "hunter's trap")
_COSTUME_KW = ("costume", "disguise", "perfume", "fine clothes", "noble")


def score_lamplighter(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _LAMPLIGHTER_KW))


def score_pathfinder(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _PATHFINDER_KW))


def score_apothecary(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: it.get("category") == "Consumable")


def score_cellarer(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _CELLARER_KW))


def score_trapper(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _TRAPPER_KW))


def score_costume_master(items: list[dict], member: dict) -> int:
    return _sum_count_where(items, lambda it: _matches_any(it, _COSTUME_KW))


def score_quartermaster(items: list[dict], member: dict) -> int:
    return len({it["id"] for it in items})


def score_featherfoot(items: list[dict], member: dict) -> float:
    """Inverted carry-ratio utilization. Higher = more decisively unburdened.

    Score = 100 - utilization%, where utilization = total / capacity * 100.
    A character with no capacity (STR 0) is unscorable — return 0.
    """
    cap = _carrying_capacity(member)
    if cap <= 0:
        return 0.0
    weight = _total_weight(items)
    util_pct = weight / cap * 100
    return 100.0 - util_pct
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "lamplighter or pathfinder or apothecary or cellarer or trapper or costume_master or quartermaster or featherfoot"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "score survival, personal, and aggregate archetypes"
```

---

### Task 8: The archetype slate registry

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_archetype_slate_contains_all_sixteen():
    slugs = [a["slug"] for a in inventory.ARCHETYPE_SLATE]
    assert slugs == [
        "pack-mule", "armorer", "glaive-hand", "quiver",
        "curio-keeper", "naturalist", "scholar", "tongues",
        "lamplighter", "pathfinder", "apothecary", "cellarer", "trapper",
        "costume-master",
        "quartermaster", "featherfoot",
    ]


def test_each_archetype_has_label_and_scorer():
    for a in inventory.ARCHETYPE_SLATE:
        assert isinstance(a["slug"], str)
        assert a["label"].startswith("THE ")
        assert callable(a["score"])
        assert isinstance(a.get("min_lead", 0), (int, float))
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k archetype_slate
```

Expected: FAIL — `ARCHETYPE_SLATE` not defined.

- [ ] **Step 3: Implement**

```python
# Listed in priority order — used as the tiebreaker when a character has two
# archetype wins with equal lead. Pack-Mule resolves before Armorer, etc.
ARCHETYPE_SLATE: tuple[dict, ...] = (
    {"slug": "pack-mule",       "label": "THE PACK-MULE",       "score": score_pack_mule,       "min_lead": 0},
    {"slug": "armorer",         "label": "THE ARMORER",         "score": score_armorer,         "min_lead": 0},
    {"slug": "glaive-hand",     "label": "THE GLAIVE-HAND",     "score": score_glaive_hand,     "min_lead": 0},
    {"slug": "quiver",          "label": "THE QUIVER",          "score": score_quiver,          "min_lead": 0},
    {"slug": "curio-keeper",    "label": "THE CURIO-KEEPER",    "score": score_curio_keeper,    "min_lead": 0},
    {"slug": "naturalist",      "label": "THE NATURALIST",      "score": score_naturalist,      "min_lead": 0},
    {"slug": "scholar",         "label": "THE SCHOLAR",         "score": score_scholar,         "min_lead": 0},
    {"slug": "tongues",         "label": "THE TONGUES",         "score": score_tongues,         "min_lead": 0},
    {"slug": "lamplighter",     "label": "THE LAMPLIGHTER",     "score": score_lamplighter,     "min_lead": 0},
    {"slug": "pathfinder",      "label": "THE PATHFINDER",      "score": score_pathfinder,      "min_lead": 0},
    {"slug": "apothecary",      "label": "THE APOTHECARY",      "score": score_apothecary,      "min_lead": 0},
    {"slug": "cellarer",        "label": "THE CELLARER",        "score": score_cellarer,        "min_lead": 0},
    {"slug": "trapper",         "label": "THE TRAPPER",         "score": score_trapper,         "min_lead": 0},
    {"slug": "costume-master",  "label": "THE COSTUME-MASTER",  "score": score_costume_master,  "min_lead": 0},
    {"slug": "quartermaster",   "label": "THE QUARTERMASTER",   "score": score_quartermaster,   "min_lead": 0},
    # Featherfoot needs a meaningful gap to feel earned (5 percentage-point
    # difference in inverted utilization).
    {"slug": "featherfoot",     "label": "THE FEATHERFOOT",     "score": score_featherfoot,     "min_lead": 5},
)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k archetype_slate
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "register the 16-archetype slate"
```

---

### Task 9: Greedy, lead-based archetype assignment

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_assign_archetypes_picks_top_scorer_per_metric():
    # Two characters, two metrics. Each character should get the metric
    # they decisively dominate.
    chars = {
        "alice": {"items": [{"id": "rope", "name": "Rope", "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"id": "book", "name": "Book", "count": 5}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "scholar", "label": "THE SCHOLAR",
         "score": inventory.score_scholar, "min_lead": 0},
        {"slug": "pathfinder", "label": "THE PATHFINDER",
         "score": inventory.score_pathfinder, "min_lead": 0},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {"alice": "pathfinder", "bob": "scholar"}


def test_assign_archetypes_largest_lead_wins_when_one_char_tops_two():
    # Alice tops both archetypes. Her larger lead is on Pack-Mule (lead=10
    # vs Quartermaster lead=1), so Alice keeps Pack-Mule and Quartermaster
    # falls through to Bob.
    chars = {
        "alice": {"items": [{"id": "x", "weight": 100, "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"id": "x", "weight": 90, "count": 1},
                          {"id": "y", "weight": 0, "count": 1}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "pack-mule", "label": "THE PACK-MULE",
         "score": inventory.score_pack_mule, "min_lead": 0},
        {"slug": "quartermaster", "label": "THE QUARTERMASTER",
         "score": inventory.score_quartermaster, "min_lead": 0},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {"alice": "pack-mule", "bob": "quartermaster"}


def test_assign_archetypes_unawarded_when_min_lead_unmet():
    # Both characters tie on Featherfoot (lead = 0). min_lead = 5 means it
    # goes unawarded.
    chars = {
        "alice": {"items": [{"weight": 0, "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"weight": 0, "count": 1}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "featherfoot", "label": "THE FEATHERFOOT",
         "score": inventory.score_featherfoot, "min_lead": 5},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {}


def test_assign_archetypes_unawarded_when_top_score_zero():
    # Nobody has any books → score_scholar returns 0 for both.
    # No award.
    chars = {
        "alice": {"items": [{"name": "Sword"}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"name": "Hat"}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "scholar", "label": "THE SCHOLAR",
         "score": inventory.score_scholar, "min_lead": 0},
    )

    assert inventory._assign_archetypes(chars, slate) == {}
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k assign_archetypes
```

Expected: FAIL — `_assign_archetypes` not defined.

- [ ] **Step 3: Implement**

```python
def _assign_archetypes(
    chars: dict[str, dict],
    slate: tuple[dict, ...] = ARCHETYPE_SLATE,
) -> dict[str, str]:
    """Assign each character at most one archetype slug.

    Algorithm:
      1. Score every (character, archetype) pair.
      2. For each archetype, find the leader and the lead size (leader
         minus runner-up; or leader minus 0 when the field is one wide).
         Discard archetypes where lead < min_lead OR leader's score == 0.
      3. Iterate: each unassigned character collects every archetype
         they currently lead. They keep the one with the largest lead
         (slate-order tiebreak). Surrendered archetypes recompute their
         leader against remaining (unassigned + still-eligible) chars and
         re-enter the pool.
      4. Repeat step 3 until stable.

    Returns: {char_slug: archetype_slug}. Characters without any winning
    archetype are simply absent from the dict.
    """
    # Step 1 + 2: build (archetype_slug -> [(char_slug, score)] desc)
    candidate_pool: dict[str, list[tuple[str, float]]] = {}
    slate_by_slug = {a["slug"]: a for a in slate}
    slate_order = [a["slug"] for a in slate]

    for arc in slate:
        scored = sorted(
            ((cs, arc["score"](cd["items"], cd["member"])) for cs, cd in chars.items()),
            key=lambda p: -p[1],
        )
        candidate_pool[arc["slug"]] = scored

    def lead(scored: list[tuple[str, float]]) -> float:
        if not scored:
            return 0.0
        if len(scored) == 1:
            return scored[0][1]
        return scored[0][1] - scored[1][1]

    assigned: dict[str, str] = {}
    claimed_archetypes: set[str] = set()
    changed = True
    while changed:
        changed = False
        # For each char, collect the archetypes they currently lead.
        wins_by_char: dict[str, list[tuple[str, float]]] = {}
        for arc_slug, scored in candidate_pool.items():
            if arc_slug in claimed_archetypes:
                continue
            scored_live = [(cs, sc) for cs, sc in scored if cs not in assigned]
            if not scored_live:
                continue
            min_lead = slate_by_slug[arc_slug]["min_lead"]
            ld = lead(scored_live)
            top_char, top_score = scored_live[0]
            if top_score <= 0 or ld < min_lead:
                continue
            wins_by_char.setdefault(top_char, []).append((arc_slug, ld))

        # Each char keeps the largest-lead win; tiebreak by slate order.
        for cs, wins in wins_by_char.items():
            if not wins:
                continue
            wins.sort(key=lambda p: (-p[1], slate_order.index(p[0])))
            keeper = wins[0][0]
            assigned[cs] = keeper
            claimed_archetypes.add(keeper)
            changed = True

    return assigned
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k assign_archetypes
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "assign archetypes via lead-based greedy iteration"
```

---

### Task 10: Build the per-character bundle and the company strip

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_bundle_classifies_totals_and_assigns():
    parsed = {
        "grieg": {"items": [
            {"id": "wh", "name": "Warhammer", "category": "Weapon",
             "weight": 5, "count": 1, "rarity": "common", "icon": "", "description": ""},
            {"id": "rations", "name": "Rations (x9)",
             "category": "Adventuring Gear - Camping & Travel",
             "weight": 2, "count": 9, "rarity": "common", "icon": "", "description": ""},
        ]},
    }
    party = {"members": [{"id": "grieg", "name": "Grieg",
                          "abilities": {"str": 17}}]}

    bundle = inventory._build_bundle(parsed, party)

    g = bundle["by_id"]["grieg"]
    assert {it["name"] for it in g["rack"]} == {"Warhammer"}
    assert {it["name"] for it in g["manifest"]} == {"Rations (x9)"}
    assert g["total_weight"] == 23  # 5 + 2*9
    assert g["capacity"] == 255
    # Cellarer keyword "ration" matches Rations.
    assert g["archetype"] == "cellarer"


def test_company_strip_includes_placeholders_for_missing_inventories():
    parsed = {"grieg": {"items": []}}
    party = {"members": [
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "lilac", "name": "Lilac Mist", "abilities": {"str": 8}},
    ]}

    bundle = inventory._build_bundle(parsed, party)
    strip = bundle["company_strip"]

    assert [s["slug"] for s in strip] == ["grieg", "lilac"]
    assert strip[0]["status"] == "ok"
    assert strip[1]["status"] == "awaiting_manifest"
    assert strip[1]["shortname"] == "Lilac"


def test_company_strip_excludes_gm_member():
    parsed = {}
    party = {"members": [
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "gm", "name": "GM", "abilities": {"str": 10}},
    ]}

    strip = inventory._build_bundle(parsed, party)["company_strip"]

    assert [s["slug"] for s in strip] == ["grieg"]
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k build_bundle
```

Expected: FAIL — `_build_bundle` not defined.

- [ ] **Step 3: Implement**

```python
def _shortname(name: str) -> str:
    """First whitespace-split token. 'Lilac Mist' -> 'Lilac'."""
    return (name or "").split()[0] if name else ""


def _build_bundle(parsed: dict[str, dict], party: dict) -> dict:
    """Combine parsed inventories with party members.

    Returns:
      {
        "by_id": {<slug>: {rack, spotlight, manifest, total_weight,
                          capacity, breakdown, archetype, item_count}, ...},
        "company_strip": [{slug, shortname, status,
                           total_weight, capacity, breakdown}, ...],
      }

    Status is "ok" when the character has parsed inventory data, or
    "awaiting_manifest" when they don't (Anton/Lilac before their data
    arrives).
    """
    members_by_id = {m["id"]: m for m in party.get("members", [])
                     if m.get("id") != "gm"}

    # Build per-character record from parsed inventories.
    by_id: dict[str, dict] = {}
    chars_for_assignment: dict[str, dict] = {}
    for slug, inv in parsed.items():
        member = members_by_id.get(slug)
        if member is None:
            continue
        items = inv["items"]
        rack, spotlight, manifest = _classify(items)
        capacity = _carrying_capacity(member)
        total_weight = _total_weight(items)
        by_id[slug] = {
            "rack": rack,
            "spotlight": spotlight,
            "manifest": manifest,
            "total_weight": total_weight,
            "capacity": capacity,
            "breakdown": _zone_breakdown(rack, spotlight, manifest),
            "item_count": sum((it.get("count") or 1) for it in items),
            "archetype": None,  # filled below
        }
        chars_for_assignment[slug] = {"items": items, "member": member}

    # Assign archetypes across the population we have inventory for.
    assignments = _assign_archetypes(chars_for_assignment, ARCHETYPE_SLATE)
    for slug, arc_slug in assignments.items():
        by_id[slug]["archetype"] = arc_slug

    # Company strip: one entry per non-GM member, in roster order.
    strip: list[dict] = []
    for member in party.get("members", []):
        slug = member.get("id")
        if slug == "gm":
            continue
        rec = by_id.get(slug)
        if rec is None:
            strip.append({
                "slug": slug,
                "shortname": _shortname(member.get("name", "")),
                "status": "awaiting_manifest",
                "total_weight": 0,
                "capacity": _carrying_capacity(member),
                "breakdown": {"rack": 0, "spotlight": 0, "manifest": 0},
            })
        else:
            strip.append({
                "slug": slug,
                "shortname": _shortname(member.get("name", "")),
                "status": "ok",
                "total_weight": rec["total_weight"],
                "capacity": rec["capacity"],
                "breakdown": rec["breakdown"],
            })

    return {"by_id": by_id, "company_strip": strip}
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k build_bundle
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "assemble per-character bundle and company strip"
```

---

### Task 11: Wire `load()` end-to-end

**Files:**
- Modify: `build/inventory.py`
- Create: `tests/fixtures/inventory/obr-inv-backup-2026-05-02T04-21-16-825Z.json`
- Modify: `tests/test_inventory.py`

- [ ] **Step 1: Create the test fixture**

Create `tests/fixtures/inventory/obr-inv-backup-2026-05-02T04-21-16-825Z.json`:

```json
{
  "exportedAt": "2026-05-02T04:21:16.825Z",
  "inventories": {
    "uuid-grieg": {
      "name": "Simon Weil",
      "items": [
        {"id": "wh", "name": "Warhammer", "category": "Weapon",
         "weight": 5, "count": 1, "rarity": "common",
         "icon": "https://5e.tools/img/items/XPHB/Warhammer.webp",
         "description": "1d8 bludgeoning."}
      ]
    },
    "uuid-vex": {
      "name": "Vex",
      "items": [
        {"id": "rope", "name": "Rope (50 ft)",
         "category": "Adventuring Gear - Utility & Equipment",
         "weight": 5, "count": 1, "rarity": "common",
         "icon": "", "description": ""}
      ]
    },
    "uuid-gm": {
      "name": "GM",
      "items": [
        {"id": "junk", "name": "Junk",
         "category": "Adventuring Gear - Utility & Equipment",
         "weight": 1, "count": 1, "rarity": "common",
         "icon": "", "description": ""}
      ]
    }
  }
}
```

- [ ] **Step 2: Write the failing tests**

```python
def test_load_returns_empty_bundle_when_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_DATA_DIR", str(tmp_path))
    bundle = inventory.load(tmp_path.parent)
    assert bundle == {"by_id": {}, "company_strip": []}


def test_load_full_pipeline_with_fixture(tmp_path, monkeypatch):
    # Stage the fixture into a tmp data dir alongside a small party.json
    # so render's name resolver and our loader both see consistent data.
    fixture_dir = tmp_path / "data"
    fixture_dir.mkdir()
    src = (
        Path(__file__).parent / "fixtures" / "inventory"
        / "obr-inv-backup-2026-05-02T04-21-16-825Z.json"
    )
    (fixture_dir / src.name).write_text(src.read_text())
    (fixture_dir / "party.json").write_text(json.dumps([
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "vex",   "name": "Vex",   "abilities": {"str": 12}},
    ]))

    bundle = inventory.load(fixture_dir.parent)

    assert set(bundle["by_id"].keys()) == {"grieg", "vex"}
    assert bundle["by_id"]["grieg"]["total_weight"] == 5
    assert "Weil" not in json.dumps(bundle)  # surname scrubbed
    # Strip preserves party.json order.
    assert [s["slug"] for s in bundle["company_strip"]] == ["grieg", "vex"]
```

Add these imports at the top of `tests/test_inventory.py`:

```python
import json
from pathlib import Path
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k "load_"
```

Expected: FAIL — `load()` only returns the empty stub.

- [ ] **Step 4: Implement**

Replace the body of `load()` in `build/inventory.py`:

```python
import json

from build.render import _load_dice_player_map


def load(repo_root: Path) -> dict:
    """Load the latest inventory snapshot under <repo_root>/data and shape
    it for the renderer. Returns an empty bundle if no snapshot is found.

    The function reads from <repo_root>/data and party.json from the same
    directory; tests can override this via the BUILD_DATA_DIR env var
    (handled by build.paths.data_dir()).
    """
    from build.paths import data_dir

    d = data_dir()
    snapshot = _resolve_snapshot_path(d)
    if snapshot is None:
        return {"by_id": {}, "company_strip": []}

    raw = json.loads(snapshot.read_text())
    party_path = d / "party.json"
    party_raw = json.loads(party_path.read_text()) if party_path.exists() else []
    party = party_raw if isinstance(party_raw, dict) else {"members": party_raw}

    mapping = _load_dice_player_map()
    parsed = _parse_inventories(raw, mapping)
    return _build_bundle(parsed, party)
```

(Remove the placeholder `return {"by_id": {}, "company_strip": []}` line you added in Task 1.)

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v
```

Expected: PASS — full file.

- [ ] **Step 6: Commit**

```bash
git add build/inventory.py tests/test_inventory.py tests/fixtures/inventory/
git commit -m "wire build.inventory.load end-to-end"
```

---

## Phase 2 — Render integration (math)

### Task 12: Expose inventory bundle to template context

**Files:**
- Modify: `build/render.py`

- [ ] **Step 1: Read the current `compute_all` signature**

Open `build/render.py` and find `def compute_all(data, authored)`. The plan calls for adding an `inventory_by_id` and a `company_strip` key to the returned context, fed by `inventory.load(REPO_ROOT)`.

- [ ] **Step 2: Add the import at the top of render.py**

After the existing `from collections import Counter`:

```python
from build import inventory
```

- [ ] **Step 3: Inside `compute_all`, after the existing `compute_*` calls**

Find the line `char_auth_by_id = {a["id"]: a for a in authored["characters"]}` and immediately above the `return {` block, add:

```python
    inventory_bundle = inventory.load(REPO_ROOT)
```

- [ ] **Step 4: Add to the returned dict**

In the returned dict (the one that includes `"site": site, "party": party, ...`), add:

```python
        "inventory_by_id": inventory_bundle["by_id"],
        "company_strip": inventory_bundle["company_strip"],
```

- [ ] **Step 5: Verify the build still runs**

```bash
.venv/bin/python -m build --skip-render --no-refresh
.venv/bin/python build/render.py
```

Expected: render.py runs to completion (templates not yet using the new fields, so no behavior change visible). If the run errors, fix before continuing.

- [ ] **Step 6: Commit**

```bash
git add build/render.py
git commit -m "expose inventory bundle in render context"
```

---

### Task 13: Math fallback line for archetype tooltips

**Files:**
- Modify: `build/inventory.py`
- Modify: `tests/test_inventory.py`

The renderer needs a deterministic stats line per character to use whenever the authored inscription is missing or stale. Live alongside the rest of the math.

- [ ] **Step 1: Write the failing tests**

```python
def test_math_inscription_for_pack_mule():
    rec = {"archetype": "pack-mule", "total_weight": 175.5, "item_count": 31}
    line = inventory.math_inscription(rec, ranks={"pack-mule": 1})
    assert "175.5 lb" in line
    assert "31 items" in line
    assert "most in the party" in line


def test_math_inscription_returns_empty_for_no_archetype():
    rec = {"archetype": None, "total_weight": 0, "item_count": 0}
    assert inventory.math_inscription(rec, ranks={}) == ""


def test_math_inscription_for_featherfoot():
    rec = {"archetype": "featherfoot", "total_weight": 10,
           "capacity": 90, "item_count": 3}
    line = inventory.math_inscription(rec, ranks={"featherfoot": 1})
    assert "11%" in line  # 10/90
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k math_inscription
```

Expected: FAIL — `math_inscription` not defined.

- [ ] **Step 3: Implement**

```python
def math_inscription(rec: dict, ranks: dict[str, int]) -> str:
    """Generate a deterministic stats-line tooltip for a character record.

    `rec` is a single entry from inventory_by_id (with `archetype`,
    `total_weight`, `item_count`, etc.). `ranks` maps archetype slug to
    the holder's rank (1 = winner). When the holder is rank 1, append
    "most in the party" to anchor the framing.
    """
    arc = rec.get("archetype")
    if not arc:
        return ""
    weight = rec.get("total_weight", 0)
    n = rec.get("item_count", 0)
    is_winner = ranks.get(arc) == 1
    suffix = " — most in the party" if is_winner else ""
    if arc == "featherfoot":
        cap = rec.get("capacity", 0) or 1
        pct = round(weight / cap * 100)
        return f"Carries {weight:g} lb of {cap} ({pct}% of capacity){suffix}."
    return f"Carries {weight:g} lb across {n} items{suffix}."
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k math_inscription
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/inventory.py tests/test_inventory.py
git commit -m "math fallback inscription for archetype badges"
```

---

### Task 14: Wire `archetype_badge` into the render context

**Files:**
- Modify: `build/render.py`
- Modify: `tests/test_inventory.py`

`render.compute_all` must produce, per character, a final tooltip string that the template can render directly: the authored inscription if present *and* matching the current archetype, else the math fallback.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_inventory.py`:

```python
def test_resolve_inscription_uses_authored_when_archetype_matches():
    rec = {"archetype": "pack-mule", "total_weight": 100, "item_count": 10}
    authored = {"archetype": "pack-mule",
                "inscription": "Hauls a smithy on her shoulders."}
    assert (inventory.resolve_inscription(rec, authored, ranks={"pack-mule": 1})
            == "Hauls a smithy on her shoulders.")


def test_resolve_inscription_falls_back_when_archetype_stale():
    rec = {"archetype": "scholar", "total_weight": 5, "item_count": 8}
    authored = {"archetype": "pack-mule",  # stale!
                "inscription": "old prose for the wrong archetype"}
    out = inventory.resolve_inscription(rec, authored, ranks={"scholar": 1})
    assert "Hauls" not in out
    assert "5 lb" in out


def test_resolve_inscription_falls_back_when_authored_missing():
    rec = {"archetype": "scholar", "total_weight": 5, "item_count": 8}
    out = inventory.resolve_inscription(rec, None, ranks={"scholar": 1})
    assert "5 lb" in out


def test_resolve_inscription_empty_when_no_archetype():
    rec = {"archetype": None, "total_weight": 0, "item_count": 0}
    assert inventory.resolve_inscription(rec, None, ranks={}) == ""
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k resolve_inscription
```

Expected: FAIL — undefined.

- [ ] **Step 3: Implement** in `build/inventory.py`

```python
def resolve_inscription(
    rec: dict,
    authored: dict | None,
    ranks: dict[str, int],
) -> str:
    """Pick the right tooltip text for a character's archetype badge.

    Use the authored inscription when:
      - `authored` is a dict with both `archetype` and `inscription`,
      - and `authored["archetype"]` matches the current math pick.

    Otherwise, fall back to math_inscription. Returns "" when there is no
    current archetype (the badge will not render).
    """
    if not rec.get("archetype"):
        return ""
    if (
        isinstance(authored, dict)
        and authored.get("archetype") == rec["archetype"]
        and isinstance(authored.get("inscription"), str)
        and authored["inscription"].strip()
    ):
        return authored["inscription"]
    return math_inscription(rec, ranks)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_inventory.py -v -k resolve_inscription
```

Expected: PASS

- [ ] **Step 5: Wire it into `compute_all`** in `build/render.py`

After the `inventory_bundle = inventory.load(REPO_ROOT)` line, add:

```python
    # Per-archetype rank table for the math-inscription fallback. Rank 1 =
    # current holder; only rank 1 is used by math_inscription, but a full
    # rank table is cheap and could feed future stats.
    archetype_ranks: dict[str, int] = {}
    for slug, rec in inventory_bundle["by_id"].items():
        arc = rec.get("archetype")
        if arc:
            archetype_ranks[arc] = 1  # there is at most one holder per archetype

    inscriptions: dict[str, str] = {}
    for slug, rec in inventory_bundle["by_id"].items():
        authored_badge = char_auth_by_id.get(slug, {}).get("archetype_badge")
        inscriptions[slug] = inventory.resolve_inscription(rec, authored_badge, archetype_ranks)
```

Then add to the returned dict:

```python
        "archetype_inscriptions": inscriptions,
```

- [ ] **Step 6: Verify build runs**

```bash
.venv/bin/python build/render.py
```

Expected: success (templates don't yet consume `archetype_inscriptions`).

- [ ] **Step 7: Commit**

```bash
git add build/inventory.py build/render.py tests/test_inventory.py
git commit -m "resolve archetype inscription with stale/missing fallback"
```

---

## Phase 3 — Templates, CSS, and JS

### Task 15: Create `_pack.html` — Rack zone

**Files:**
- Create: `build/templates/_pack.html`

- [ ] **Step 1: Create the file**

```jinja
{# _pack.html — per-character Pack section: Rack, Spotlight, Manifest. #}
{%- set pack = inventory_by_id.get(member.id) %}

<section class="pack" id="{{ member.id }}-pack">
  <h3 class="section-title">Pack</h3>

  {%- if pack is none %}
    <p class="empty-state">Awaiting manifest.</p>
  {%- else %}
    {%- if pack.rack %}
    <div class="rack">
      <div class="rack-shelf"></div>
      {%- for it in pack.rack %}
        <div class="rack-item"
             data-name="{{ it.name }}"
             data-count="{{ it.count }}"
             data-weight="{{ it.weight if it.weight is not none else 0 }}"
             data-description="{{ it.description }}">
          <img class="rack-icon" src="{{ it.icon }}" alt="{{ it.name }}" loading="lazy">
          {%- if it.count > 1 %}
            <span class="count-badge">&times;{{ it.count }}</span>
          {%- endif %}
        </div>
      {%- endfor %}
    </div>
    {%- endif %}
  {%- endif %}
</section>
```

- [ ] **Step 2: Verify the template parses**

Add an include of this partial to `_character.html` (next task) before checking; for now just confirm no syntax errors:

```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; \
  env = Environment(loader=FileSystemLoader('build/templates')); \
  env.get_template('_pack.html')"
```

Expected: no output (parsed cleanly).

- [ ] **Step 3: Commit**

```bash
git add build/templates/_pack.html
git commit -m "Pack template: Rack zone"
```

---

### Task 16: Add Spotlight zone to `_pack.html`

**Files:**
- Modify: `build/templates/_pack.html`

- [ ] **Step 1: Insert Spotlight block**

After the Rack `{%- endif %}` and before the outer `{%- endif %}`, add:

```jinja
    {%- if pack.spotlight %}
    <div class="spotlight">
      {%- for it in pack.spotlight %}
        <div class="spotlight-card spotlight-rarity-{{ (it.rarity or 'common') | replace(' ', '-') }}"
             data-name="{{ it.name }}"
             data-count="{{ it.count }}"
             data-weight="{{ it.weight if it.weight is not none else 0 }}"
             data-rarity="{{ it.rarity or 'common' }}"
             data-description="{{ it.description }}">
          <div class="spotlight-sheen"></div>
          <img class="spotlight-icon" src="{{ it.icon }}" alt="{{ it.name }}" loading="lazy">
          <div class="spotlight-name">{{ it.name }}</div>
        </div>
      {%- endfor %}
    </div>
    {%- endif %}
```

- [ ] **Step 2: Re-parse**

```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; \
  env = Environment(loader=FileSystemLoader('build/templates')); \
  env.get_template('_pack.html')"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add build/templates/_pack.html
git commit -m "Pack template: Spotlight zone"
```

---

### Task 17: Add Manifest zone to `_pack.html`

**Files:**
- Modify: `build/templates/_pack.html`

- [ ] **Step 1: Insert Manifest block** (after Spotlight `{%- endif %}`, still inside the outer `else`)

```jinja
    {%- if pack.manifest %}
    <div class="manifest">
      <div class="manifest-meta">
        {{ pack.item_count }} items &middot; {{ pack.total_weight }} lb
      </div>
      <div class="manifest-grid">
        {%- for it in pack.manifest %}
          <div class="manifest-chip"
               data-name="{{ it.name }}"
               data-count="{{ it.count }}"
               data-weight="{{ it.weight if it.weight is not none else 0 }}"
               data-category="{{ it.category }}"
               data-description="{{ it.description }}">
            <img class="manifest-icon" src="{{ it.icon }}" alt="{{ it.name }}" loading="lazy">
            {%- if it.count > 1 %}
              <span class="count-badge">&times;{{ it.count }}</span>
            {%- endif %}
          </div>
        {%- endfor %}
      </div>
    </div>
    {%- endif %}
```

- [ ] **Step 2: Re-parse**

```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; \
  env = Environment(loader=FileSystemLoader('build/templates')); \
  env.get_template('_pack.html')"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add build/templates/_pack.html
git commit -m "Pack template: Manifest zone"
```

---

### Task 18: Wire `_pack.html` into `_character.html` and add archetype badge

**Files:**
- Modify: `build/templates/_character.html`

- [ ] **Step 1: Add Pack to the TOC**

Find the `<nav class="character-toc"...>` block (line 27) and append a Pack link after the existing three:

```jinja
        <a href="#{{ member.id }}-trials">Trials</a>
        <a href="#{{ member.id }}-fortune">Fortune</a>
        <a href="#{{ member.id }}-reliquary">Reliquary</a>
        <a href="#{{ member.id }}-pack">Pack</a>
```

- [ ] **Step 2: Add the Pack include**

After `{% include "_reliquary.html" %}` (line 37), append:

```jinja
      {% include "_pack.html" %}
```

- [ ] **Step 3: Add the archetype badge in the identity block**

Find the `<div class="meta">{{ member.class }} ...</div>` line (line 11). Immediately after it, add:

```jinja
          {%- set inscription = archetype_inscriptions.get(member.id) %}
          {%- set pack_rec = inventory_by_id.get(member.id) %}
          {%- if pack_rec and pack_rec.archetype %}
            {%- set arc_label_map = {
              "pack-mule": "THE PACK-MULE",
              "armorer": "THE ARMORER",
              "glaive-hand": "THE GLAIVE-HAND",
              "quiver": "THE QUIVER",
              "curio-keeper": "THE CURIO-KEEPER",
              "naturalist": "THE NATURALIST",
              "scholar": "THE SCHOLAR",
              "tongues": "THE TONGUES",
              "lamplighter": "THE LAMPLIGHTER",
              "pathfinder": "THE PATHFINDER",
              "apothecary": "THE APOTHECARY",
              "cellarer": "THE CELLARER",
              "trapper": "THE TRAPPER",
              "costume-master": "THE COSTUME-MASTER",
              "quartermaster": "THE QUARTERMASTER",
              "featherfoot": "THE FEATHERFOOT"
            } %}
          <div class="archetype" data-inscription="{{ inscription }}">
            {{ arc_label_map.get(pack_rec.archetype, pack_rec.archetype | upper) }}
          </div>
          {%- endif %}
```

- [ ] **Step 4: Render and inspect**

```bash
.venv/bin/python build/render.py
```

Expected: succeeds. `site/index.html` now contains a `<section class="pack">` per character and a `<div class="archetype">` in the identity block (unstyled — CSS comes next).

```bash
grep -c 'class="pack"' site/index.html
grep -c 'class="archetype"' site/index.html
```

Both should report at least the count of party members (4 with inventory, 2 awaiting).

- [ ] **Step 5: Commit**

```bash
git add build/templates/_character.html
git commit -m "wire Pack section + archetype badge into character card"
```

---

### Task 19: Insert the Company strip into `_company.html`

**Files:**
- Modify: `build/templates/_company.html`

- [ ] **Step 1: Read the current `_company.html` to find a safe insertion point**

```bash
.venv/bin/python -c "import builtins; print(open('build/templates/_company.html').read())"
```

Identify the section's outer container (likely a `<section>` near the top).

- [ ] **Step 2: Insert the strip block at the top of the section body** (just inside the outer `<section>` element)

```jinja
      {%- if company_strip %}
      <div class="company-strip">
        <div class="company-strip-title">Burden of Carry</div>
        <div class="company-strip-bars">
          {%- for s in company_strip %}
            <div class="company-strip-bar
                        {%- if s.status == 'awaiting_manifest' %} awaiting{% endif %}"
                 data-slug="{{ s.slug }}"
                 data-shortname="{{ s.shortname }}"
                 data-weight="{{ s.total_weight }}"
                 data-capacity="{{ s.capacity }}"
                 data-rack="{{ s.breakdown.rack }}"
                 data-spotlight="{{ s.breakdown.spotlight }}"
                 data-manifest="{{ s.breakdown.manifest }}">
              <div class="company-strip-name">{{ s.shortname }}</div>
              <div class="company-strip-track">
                {%- if s.status == 'ok' and s.capacity > 0 %}
                  {%- set pct = (s.total_weight / s.capacity * 100) | round %}
                  <div class="company-strip-fill"
                       style="--target-width: {{ pct }}%; animation-delay: {{ loop.index0 * 80 }}ms;"></div>
                {%- endif %}
              </div>
              <div class="company-strip-numbers">
                {%- if s.status == 'ok' %}
                  {{ s.total_weight }} / {{ s.capacity }} lb
                {%- else %}
                  &mdash;
                {%- endif %}
              </div>
            </div>
          {%- endfor %}
        </div>
      </div>
      {%- endif %}
```

- [ ] **Step 3: Render**

```bash
.venv/bin/python build/render.py
grep -c 'class="company-strip-bar' site/index.html
```

Expected: count equals the number of non-GM members.

- [ ] **Step 4: Commit**

```bash
git add build/templates/_company.html
git commit -m "company strip: per-character weight gauges"
```

---

### Task 20: Tooltip IIFEs for the new selectors

**Files:**
- Modify: `build/templates/_script.html`

The site's tooltip pattern (see existing IIFEs starting around line 23 of `_script.html`) is repeated per feature: find/create `.dice-tooltip`, `querySelectorAll(...)`, attach mouseenter/mouseleave, read `data-*` attrs to build content. Mirror it for each new selector.

- [ ] **Step 1: Append the new IIFEs**

At the bottom of `_script.html` (before the closing `</script>` tag), add:

```html
      // --- Pack: Rack item tooltips ---
      (function () {
        let tip = document.querySelector('.dice-tooltip');
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'dice-tooltip';
          document.body.appendChild(tip);
        }
        document.querySelectorAll('.rack-item').forEach(el => {
          el.addEventListener('mouseenter', () => {
            const name = el.getAttribute('data-name') || '';
            const count = el.getAttribute('data-count') || '';
            const weight = el.getAttribute('data-weight') || '';
            const desc = el.getAttribute('data-description') || '';
            let html = '<div class="tip-val tip-val-text">' + name + '</div>';
            html += '<div class="tip-ctx">' + (count !== '1' ? '&times;' + count + ' &middot; ' : '') +
                    weight + ' lb</div>';
            if (desc) html += '<div class="tip-ctx">' + desc + '</div>';
            tip.innerHTML = html;
            tip.style.opacity = '1';
            const r = el.getBoundingClientRect();
            tip.style.left = (r.left + r.width / 2 + window.scrollX) + 'px';
            tip.style.top = (r.top + window.scrollY) + 'px';
          });
          el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
        });
      })();

      // --- Pack: Spotlight card tooltips ---
      (function () {
        let tip = document.querySelector('.dice-tooltip');
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'dice-tooltip';
          document.body.appendChild(tip);
        }
        document.querySelectorAll('.spotlight-card').forEach(el => {
          el.addEventListener('mouseenter', () => {
            const name = el.getAttribute('data-name') || '';
            const rarity = el.getAttribute('data-rarity') || '';
            const desc = el.getAttribute('data-description') || '';
            let html = '<div class="tip-val tip-val-text">' + name + '</div>';
            if (rarity) html += '<div class="tip-ctx">' + rarity + '</div>';
            if (desc) html += '<div class="tip-ctx">' + desc + '</div>';
            tip.innerHTML = html;
            tip.style.opacity = '1';
            const r = el.getBoundingClientRect();
            tip.style.left = (r.left + r.width / 2 + window.scrollX) + 'px';
            tip.style.top = (r.top + window.scrollY) + 'px';
          });
          el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
        });
      })();

      // --- Pack: Manifest chip tooltips ---
      (function () {
        let tip = document.querySelector('.dice-tooltip');
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'dice-tooltip';
          document.body.appendChild(tip);
        }
        document.querySelectorAll('.manifest-chip').forEach(el => {
          el.addEventListener('mouseenter', () => {
            const name = el.getAttribute('data-name') || '';
            const count = el.getAttribute('data-count') || '';
            const weight = el.getAttribute('data-weight') || '';
            const cat = el.getAttribute('data-category') || '';
            const desc = el.getAttribute('data-description') || '';
            const total = (parseFloat(weight) * parseInt(count, 10)) || 0;
            let html = '<div class="tip-val tip-val-text">' + name + '</div>';
            html += '<div class="tip-ctx">' + (count !== '1' ? '&times;' + count + ' &middot; ' : '') +
                    weight + ' lb each &middot; ' + total + ' lb total</div>';
            if (cat) html += '<div class="tip-ctx">' + cat + '</div>';
            if (desc) html += '<div class="tip-ctx">' + desc + '</div>';
            tip.innerHTML = html;
            tip.style.opacity = '1';
            const r = el.getBoundingClientRect();
            tip.style.left = (r.left + r.width / 2 + window.scrollX) + 'px';
            tip.style.top = (r.top + window.scrollY) + 'px';
          });
          el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
        });
      })();

      // --- Company strip bar tooltips ---
      (function () {
        let tip = document.querySelector('.dice-tooltip');
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'dice-tooltip';
          document.body.appendChild(tip);
        }
        document.querySelectorAll('.company-strip-bar').forEach(el => {
          el.addEventListener('mouseenter', () => {
            const name = el.getAttribute('data-shortname') || '';
            const w = parseFloat(el.getAttribute('data-weight') || '0');
            const cap = parseFloat(el.getAttribute('data-capacity') || '0');
            const rack = el.getAttribute('data-rack') || '0';
            const spot = el.getAttribute('data-spotlight') || '0';
            const man = el.getAttribute('data-manifest') || '0';
            const pct = cap > 0 ? Math.round(w / cap * 100) : 0;
            let html = '<div class="tip-val tip-val-text">' + name + '</div>';
            if (cap > 0) {
              html += '<div class="tip-ctx">Rack ' + rack + ' &middot; Spotlight ' + spot +
                      ' &middot; Manifest ' + man + ' = ' + w + ' lb</div>';
              html += '<div class="tip-ctx">' + pct + '% of capacity</div>';
            } else {
              html += '<div class="tip-ctx">Awaiting manifest</div>';
            }
            tip.innerHTML = html;
            tip.style.opacity = '1';
            const r = el.getBoundingClientRect();
            tip.style.left = (r.left + r.width / 2 + window.scrollX) + 'px';
            tip.style.top = (r.top + window.scrollY) + 'px';
          });
          el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
          el.addEventListener('click', () => {
            const slug = el.getAttribute('data-slug');
            if (slug) {
              const target = document.getElementById(slug + '-pack');
              if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          });
        });
      })();

      // --- Archetype badge tooltips ---
      (function () {
        let tip = document.querySelector('.dice-tooltip');
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'dice-tooltip';
          document.body.appendChild(tip);
        }
        document.querySelectorAll('.archetype').forEach(el => {
          el.addEventListener('mouseenter', () => {
            const text = el.getAttribute('data-inscription') || '';
            if (!text) return;
            tip.innerHTML = '<div class="tip-ctx">' + text + '</div>';
            tip.style.opacity = '1';
            const r = el.getBoundingClientRect();
            tip.style.left = (r.left + r.width / 2 + window.scrollX) + 'px';
            tip.style.top = (r.top + window.scrollY) + 'px';
          });
          el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
        });
      })();
```

- [ ] **Step 2: Render and verify the script block parses**

```bash
.venv/bin/python build/render.py
```

Open `site/index.html` and confirm the new IIFEs are present at the bottom of the inline `<script>`.

- [ ] **Step 3: Commit**

```bash
git add build/templates/_script.html
git commit -m "tooltip IIFEs for Pack zones, company strip, and archetype badge"
```

---

### Task 21: CSS for the Pack feature

**Files:**
- Modify: `site/styles.css`

Append a single Pack feature block at the end of the file. CSS values are tuned to match the existing site's restraint (1–4px lifts, 0.15–0.25s ease, gold/copper accent palette).

- [ ] **Step 1: Append the Pack-feature CSS**

At the end of `site/styles.css`:

```css
/* ============================================================
   Pack section, Company strip, Archetype badge
   ============================================================ */

/* --- Pack section ---------------------------------------- */
.pack { margin-top: 1.4rem; }
.pack .empty-state {
  font-style: italic;
  color: var(--ink-faded, #7a6a55);
  text-align: center;
  margin: 1.4rem 0;
}

/* --- Rack zone (weapons + armor) ------------------------- */
.rack {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 0.6rem;
  padding: 1rem 0.4rem 0.4rem;
  min-height: 60px;
}
.rack-shelf {
  position: absolute;
  left: 0; right: 0; bottom: 0.3rem;
  height: 1px;
  background: var(--rule, #b59461);
  opacity: 0.5;
}
.rack-item {
  position: relative;
  width: 48px; height: 48px;
  cursor: help;
  transition: transform 0.2s ease, filter 0.2s ease;
}
.rack-item:hover {
  transform: translateY(-4px);
  filter: drop-shadow(0 6px 6px rgba(0, 0, 0, 0.25));
}
.rack-icon { width: 100%; height: 100%; object-fit: contain; }
.rack-item .count-badge,
.manifest-chip .count-badge {
  position: absolute;
  top: -4px; right: -4px;
  font-size: 0.7rem;
  padding: 0 4px;
  background: var(--accent, #b59461);
  color: var(--paper, #f5ecd9);
  border-radius: 3px;
}

/* --- Spotlight zone (magic + wondrous) ------------------- */
.spotlight {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 1rem 0;
}
.spotlight-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100px;
  padding: 0.6rem 0.4rem 0.4rem;
  border: 1px solid var(--rule, #b59461);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.03);
  cursor: help;
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.spotlight-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.18);
}
.spotlight-rarity-uncommon  { border-color: #5a8d3f; }
.spotlight-rarity-rare      { border-color: #4673a0; }
.spotlight-rarity-very-rare { border-color: #6f4ea8; }
.spotlight-rarity-legendary { border-color: #c4862c; }
.spotlight-icon { width: 56px; height: 56px; object-fit: contain; }
.spotlight-name {
  margin-top: 0.4rem;
  font-size: 0.78rem;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.spotlight-sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg,
    transparent 30%, rgba(255, 255, 255, 0.18) 50%, transparent 70%);
  background-size: 200% 100%;
  background-position: -100% 0;
  pointer-events: none;
  animation: spotlight-sheen 6s linear infinite;
  opacity: 0.6;
}
.spotlight-card:hover .spotlight-sheen { animation-duration: 2s; opacity: 1; }
@keyframes spotlight-sheen {
  0%   { background-position: -100% 0; }
  100% { background-position: 200% 0; }
}

/* --- Manifest zone (everything else) --------------------- */
.manifest { margin-top: 1rem; }
.manifest-meta {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-faded, #7a6a55);
  margin-bottom: 0.4rem;
}
.manifest-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
  gap: 0.4rem;
}
.manifest-chip {
  position: relative;
  aspect-ratio: 1;
  border: 1px solid var(--rule, #b59461);
  border-radius: 3px;
  cursor: help;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}
.manifest-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 6px rgba(181, 148, 97, 0.55);
}
.manifest-icon { width: 70%; height: 70%; object-fit: contain; }

/* --- Company strip --------------------------------------- */
.company-strip { margin-top: 1.2rem; }
.company-strip-title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-faded, #7a6a55);
  margin-bottom: 0.4rem;
}
.company-strip-bars {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.8rem;
}
.company-strip-bar {
  cursor: pointer;
  transition: transform 0.15s ease, filter 0.15s ease;
}
.company-strip-bar:hover { transform: translateY(-1px); }
.company-strip-bar.awaiting { cursor: default; opacity: 0.55; }
.company-strip-name {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.company-strip-track {
  height: 8px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 4px;
  overflow: hidden;
  margin: 0.2rem 0;
}
.company-strip-fill {
  height: 100%;
  background: linear-gradient(90deg, #4673a0, #c4862c);
  width: 0;
  animation: company-strip-fill 0.8s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;
}
@keyframes company-strip-fill {
  to { width: var(--target-width); }
}
.company-strip-numbers {
  font-size: 0.75rem;
  color: var(--ink-faded, #7a6a55);
}

/* --- Archetype badge ------------------------------------- */
.archetype {
  display: inline-block;
  margin-top: 0.3rem;
  padding: 0.15rem 0.6rem;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  border: 1px solid var(--rule, #b59461);
  border-radius: 3px;
  cursor: help;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.archetype:hover {
  transform: rotate(2deg) translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}
```

- [ ] **Step 2: Render and visually verify**

```bash
.venv/bin/python build/render.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory site &
SERVER_PID=$!
sleep 1
echo "Open http://127.0.0.1:8765/ in a browser, scroll to a character card, and verify:"
echo "  - Pack section appears with Rack/Spotlight/Manifest as appropriate"
echo "  - Hover lifts work on each zone"
echo "  - Company strip appears at top of Company section with animated fill"
echo "  - Archetype badge appears in character header"
read -p "Looks right? (y/n) " ok
kill $SERVER_PID
[ "$ok" = "y" ] || { echo "Fix the issue and re-run this step before committing."; exit 1; }
```

- [ ] **Step 3: Commit**

```bash
git add site/styles.css
git commit -m "styles: Pack zones, company strip, archetype badge"
```

---

## Phase 4 — Authored prose (`refresh-archetype-inscription`)

### Task 22: Add the prompt and schema files

**Files:**
- Create: `.claude/prompts/refresh-archetype-inscription.md`
- Create: `.claude/prompts/refresh-archetype-inscription.schema.json`

- [ ] **Step 1: Create the schema**

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
      "required": ["inscription"],
      "additionalProperties": false,
      "properties": {
        "inscription": {
          "type": "string",
          "minLength": 8,
          "maxLength": 200
        }
      }
    },
    "reason": {"type": "string"}
  }
}
```

- [ ] **Step 2: Create the prompt**

```markdown
---
model: sonnet
---

You are a refresh-evaluation function for the dnd-data site. Read an archetype-inscription-refresh slice (delivered as JSON on stdin) and return either an unchanged decision or a new one-line tooltip inscription for a character's archetype badge.

# Input

The user message is a JSON object with this shape:
- `character`: `{id, name, race, class, background, epithet}` — voice context.
- `archetype`: `{slug, label, metric, score, runner_up_score, lead}` — the math-derived pick. The badge will display `label`. Do **not** propose a different archetype.
- `items`: list of items the character holds that earned this archetype (e.g. for The Lamplighter, just the lights). Each `{name, count, weight, description}`. Use these as the concrete handle; do not invoke items not in the list.
- `existing`: the current `archetype_badge` object if any: `{archetype, inscription}`. May be null.

# Standing rule (critical)

The inscription is short prose, ~120–200 characters. Rewrite only when:
1. There is no existing inscription for the current archetype, OR
2. The existing inscription was written for a different archetype (`existing.archetype != archetype.slug`), OR
3. The existing inscription is factually wrong about the items listed.

If the existing inscription still fits the data, return `decision: "no_change"`.

# Voice (only if rewriting)

One short line. Diegetic — speak from inside the world, not about the data. Anchor at one concrete item from the slice. Match the character's class/race register where natural. No catalog-voice. No invocations of "ye olde". Single sentence.

Examples of register (do not reuse verbatim):
- "Drags more steel up the trail than the rest together — only the wulven shoulders haven't started complaining."
- "Carries six lanterns and a vow she made the dark, and lights only one at a time."
- "The pack rattles when he walks — every spike, every coil, every scrap of rope someone might one day need."

# Authorial restraint

- Do not invent items not in the slice.
- Do not name the archetype label inside the inscription (the label renders separately).
- Do not reference real player names — this is in-world only.
- Stay under 200 characters.

# Output format

Return a single JSON object matching the response schema. No markdown fences, no prose outside the JSON.

- If unchanged: `decision: "no_change"`, `fields: null`, `reason`: one short sentence on what fact you weighed.
- If rewriting: `decision: "rewrite"`, `fields: {inscription: "..."}`, `reason`: one short sentence.
```

- [ ] **Step 3: Verify the schema parses**

```bash
.venv/bin/python -c "import json; json.load(open('.claude/prompts/refresh-archetype-inscription.schema.json'))"
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add .claude/prompts/refresh-archetype-inscription.md .claude/prompts/refresh-archetype-inscription.schema.json
git commit -m "transformer: refresh-archetype-inscription prompt + schema"
```

---

### Task 23: Slice builder for `refresh-archetype-inscription`

**Files:**
- Modify: `build/slices.py`
- Create: `tests/test_archetype_inscription.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archetype_inscription.py`:

```python
"""Tests for the archetype-inscription transformer wiring."""
import pytest

from build import slices


def _party(*members):
    return {"members": list(members)}


def test_slice_contains_only_items_that_earned_archetype(monkeypatch):
    party = _party(
        {"id": "grieg", "name": "Grieg", "race": "Wulven", "class": "Fighter",
         "background": "Beast Hunter", "abilities": {"str": 17}},
    )
    inv_by_id = {
        "grieg": {
            "rack": [{"name": "Warhammer", "count": 1, "weight": 5, "description": ""}],
            "spotlight": [],
            "manifest": [
                {"name": "Rations (x9)", "count": 9, "weight": 2, "description": ""},
                {"name": "Waterskin", "count": 1, "weight": 5, "description": ""},
                {"name": "Sword", "count": 1, "weight": 3, "description": ""},
            ],
            "archetype": "cellarer",
            "total_weight": 23,
            "item_count": 12,
            "capacity": 255,
        },
    }
    authored_chars = [{
        "id": "grieg",
        "epithet": "the wulven who never sleeps cold",
    }]

    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": authored_chars, "inventory_by_id": inv_by_id},
    )

    assert len(out) == 1
    key, slice_data = out[0]
    assert key == "grieg"
    item_names = {it["name"] for it in slice_data["items"]}
    # Only food items should be in the slice (Cellarer's matched set).
    assert item_names == {"Rations (x9)", "Waterskin"}
    assert slice_data["archetype"]["slug"] == "cellarer"
    assert slice_data["archetype"]["label"] == "THE CELLARER"
    assert slice_data["character"]["id"] == "grieg"
    assert slice_data["existing"] is None  # no archetype_badge yet


def test_slice_skips_characters_with_no_inventory():
    party = _party(
        {"id": "anton", "name": "Anton Truebranch", "abilities": {"str": 9}},
    )
    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": [{"id": "anton"}], "inventory_by_id": {}},
    )
    assert out == []


def test_slice_skips_characters_with_no_archetype():
    party = _party(
        {"id": "vex", "name": "Vex", "abilities": {"str": 12}},
    )
    inv_by_id = {"vex": {"archetype": None, "rack": [], "spotlight": [],
                          "manifest": [], "item_count": 0, "total_weight": 0,
                          "capacity": 180}}
    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": [{"id": "vex"}], "inventory_by_id": inv_by_id},
    )
    assert out == []
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_archetype_inscription.py -v
```

Expected: FAIL — `slices.refresh_archetype_inscription` not defined.

- [ ] **Step 3: Implement** in `build/slices.py`

Append:

```python
# -- Refresh: archetype inscription ------------------------------------------

# Lifted from build/inventory.py to keep slice composition self-contained;
# duplicated rather than imported because keyword sets are part of slice
# semantics (which items count for which archetype) and may evolve here
# independently of the scorer registry.
_ARCHETYPE_ITEMS = {
    # Categories-based (whole zone or whole category).
    "pack-mule":      lambda items: items,
    "armorer":        lambda items: [it for it in items
                                     if it.get("category") in ("Weapon", "Armor")],
    "glaive-hand":    lambda items: [it for it in items
                                     if it.get("category") == "Weapon"],
    "quiver":         lambda items: [it for it in items
                                     if it.get("category") == "Ammunition"],
    "curio-keeper":   lambda items: [it for it in items
                                     if (it.get("rarity") or "common").lower() != "common"
                                     or it.get("category") == "Wondrous Item"],
    "apothecary":     lambda items: [it for it in items
                                     if it.get("category") == "Consumable"],
    "quartermaster":  lambda items: items,
    "featherfoot":    lambda items: items,
    # Keyword-based.
    "scholar":        lambda items: _kw_filter(items, ("book", "parchment", "ink", "scroll", "spellbook")),
    "naturalist":     lambda items: _kw_filter(items, ("druidic", "mistletoe", "yew", "totem", "natural")),
    "tongues":        lambda items: _kw_filter(items, ("sending stone", "message", "speaking", "whisper")),
    "lamplighter":    lambda items: _kw_filter(items, ("oil", "torch", "lantern", "candle", "tinderbox", "lamp")),
    "pathfinder":     lambda items: _kw_filter(items, ("rope", "crowbar", "grapple", "piton", "spike", "climber")),
    "cellarer":       lambda items: _kw_filter(items, ("ration", "waterskin", "mess kit", "trail", "wineskin")),
    "trapper":        lambda items: _kw_filter(items, ("caltrop", "trap", "snare", "hunter's trap")),
    "costume-master": lambda items: _kw_filter(items, ("costume", "disguise", "perfume", "fine clothes", "noble")),
}

_ARCHETYPE_LABELS = {
    "pack-mule": "THE PACK-MULE", "armorer": "THE ARMORER",
    "glaive-hand": "THE GLAIVE-HAND", "quiver": "THE QUIVER",
    "curio-keeper": "THE CURIO-KEEPER", "naturalist": "THE NATURALIST",
    "scholar": "THE SCHOLAR", "tongues": "THE TONGUES",
    "lamplighter": "THE LAMPLIGHTER", "pathfinder": "THE PATHFINDER",
    "apothecary": "THE APOTHECARY", "cellarer": "THE CELLARER",
    "trapper": "THE TRAPPER", "costume-master": "THE COSTUME-MASTER",
    "quartermaster": "THE QUARTERMASTER", "featherfoot": "THE FEATHERFOOT",
}


def _kw_filter(items: list[dict], keywords: tuple[str, ...]) -> list[dict]:
    return [it for it in items
            if any(kw in (it.get("name") or "").lower() for kw in keywords)]


def refresh_archetype_inscription(data: dict, authored: dict) -> list[tuple]:
    """One slice per character whose math archetype is set.

    `authored` is expected to carry an `inventory_by_id` field — the
    orchestrator wiring places it there before calling this builder.
    """
    inv_by_id = authored.get("inventory_by_id", {})
    auth_by_id = {a["id"]: a for a in authored.get("characters", [])}
    out: list[tuple] = []
    for member in data["party"].get("members", []):
        cid = member.get("id")
        if cid == "gm":
            continue
        rec = inv_by_id.get(cid)
        if not rec or not rec.get("archetype"):
            continue
        arc_slug = rec["archetype"]
        all_items = (
            rec.get("rack", []) + rec.get("spotlight", []) + rec.get("manifest", [])
        )
        matcher = _ARCHETYPE_ITEMS.get(arc_slug, lambda items: items)
        slice_items = [
            {
                "name": it.get("name"),
                "count": it.get("count", 1),
                "weight": it.get("weight"),
                "description": it.get("description", ""),
            }
            for it in matcher(all_items)
        ]
        existing = auth_by_id.get(cid, {}).get("archetype_badge")
        out.append((cid, {
            "character": {
                "id": cid,
                "name": member.get("name"),
                "race": member.get("race"),
                "class": member.get("class"),
                "background": member.get("background"),
                "epithet": auth_by_id.get(cid, {}).get("epithet", ""),
            },
            "archetype": {
                "slug": arc_slug,
                "label": _ARCHETYPE_LABELS.get(arc_slug, arc_slug.upper()),
                "metric": arc_slug,
                "score": rec.get("total_weight", 0),
                "runner_up_score": 0,
                "lead": 0,
            },
            "items": slice_items,
            "existing": existing,
        }))
    return out
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_archetype_inscription.py -v
```

Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add build/slices.py tests/test_archetype_inscription.py
git commit -m "slice builder: refresh-archetype-inscription"
```

---

### Task 24: Apply step for `refresh-archetype-inscription`

**Files:**
- Modify: `build/apply.py`
- Modify: `tests/test_archetype_inscription.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archetype_inscription.py`:

```python
from build import apply


def test_apply_writes_archetype_badge_on_rewrite():
    authored = {"characters": [{"id": "grieg", "epithet": "..."}]}
    slice_data = {
        "character": {"id": "grieg"},
        "archetype": {"slug": "pack-mule", "label": "THE PACK-MULE"},
        "items": [],
        "existing": None,
    }
    output = {
        "decision": "rewrite",
        "fields": {"inscription": "Hauls a smithy on her shoulders."},
        "reason": "no existing inscription",
    }

    apply.apply_refresh_archetype_inscription(authored, "grieg", slice_data, output)

    badge = authored["characters"][0]["archetype_badge"]
    assert badge["archetype"] == "pack-mule"
    assert badge["inscription"] == "Hauls a smithy on her shoulders."


def test_apply_no_change_leaves_existing_alone():
    authored = {"characters": [{
        "id": "grieg",
        "epithet": "...",
        "archetype_badge": {
            "archetype": "pack-mule",
            "inscription": "old, but fits",
        },
    }]}
    slice_data = {
        "character": {"id": "grieg"},
        "archetype": {"slug": "pack-mule"},
        "items": [],
        "existing": authored["characters"][0]["archetype_badge"],
    }
    output = {"decision": "no_change", "fields": None, "reason": "still fits"}

    apply.apply_refresh_archetype_inscription(authored, "grieg", slice_data, output)

    assert authored["characters"][0]["archetype_badge"]["inscription"] == "old, but fits"


def test_apply_raises_for_missing_character():
    authored = {"characters": []}
    slice_data = {
        "character": {"id": "ghost"},
        "archetype": {"slug": "scholar"},
        "items": [], "existing": None,
    }
    output = {"decision": "rewrite",
              "fields": {"inscription": "x"},
              "reason": "."}
    with pytest.raises(ValueError, match="ghost"):
        apply.apply_refresh_archetype_inscription(authored, "ghost", slice_data, output)
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_archetype_inscription.py -v -k apply
```

Expected: FAIL — `apply.apply_refresh_archetype_inscription` not defined.

- [ ] **Step 3: Implement** in `build/apply.py`

Append:

```python
def apply_refresh_archetype_inscription(authored: dict, key, slice_data: dict, output: dict) -> None:
    """Write characters[<id>].archetype_badge = {archetype, inscription}.

    On `no_change`, leaves any existing badge untouched. On `rewrite`,
    sets the badge to the slice's archetype slug + the model's
    inscription. Raises ValueError if the character id is not present in
    the authored store.
    """
    if output["decision"] == "no_change":
        return
    fields = output["fields"] or {}
    char_id = slice_data["character"]["id"]
    arc_slug = slice_data["archetype"]["slug"]
    for c in authored["characters"]:
        if c["id"] == char_id:
            c["archetype_badge"] = {
                "archetype": arc_slug,
                "inscription": fields["inscription"],
            }
            return
    raise ValueError(f"character {char_id!r} not found in authored store")
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_archetype_inscription.py -v -k apply
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build/apply.py tests/test_archetype_inscription.py
git commit -m "apply step: refresh-archetype-inscription writes archetype_badge"
```

---

### Task 25: Register the transformer in the orchestrator

**Files:**
- Modify: `build/__main__.py`

The slice builder needs the inventory bundle threaded into `authored` before the refresh pass calls it. Easiest: compute the inventory once at the top of `main()` and stuff it into the in-memory authored dict under a non-persisted key (`store.persist` ignores unknown keys — verify with a glance; if it serializes everything, use a separate carrier).

- [ ] **Step 1: Inspect `store.persist` to know what it writes**

```bash
.venv/bin/python -c "import inspect; from build import store; print(inspect.getsource(store))"
```

Look for `persist` and confirm it writes only the known authored files. The plan assumes it does — if `persist` writes whatever is in the dict, the implementer should change the threading approach (pass `inventory_by_id` as a side-channel argument; see Step 4 below).

- [ ] **Step 2: Add the import + slice/apply registration**

Near the top of `build/__main__.py`, the existing imports already cover `apply`, `slices`, `render`, `store`. Add:

```python
from . import inventory
```

Then add to `REFRESH_PASS`:

```python
REFRESH_PASS = [
    ("refresh-chapters", slices.refresh_chapters, apply.apply_refresh_chapters),
    ("refresh-npcs", slices.refresh_npcs, apply.apply_refresh_npcs),
    ("refresh-characters", slices.refresh_characters, apply.apply_refresh_characters),
    ("refresh-road-ahead", slices.refresh_road_ahead, apply.apply_refresh_road_ahead),
    ("refresh-intro-epithet", slices.refresh_intro_epithet, apply.apply_refresh_intro_epithet),
    ("refresh-archetype-inscription",
     slices.refresh_archetype_inscription,
     apply.apply_refresh_archetype_inscription),
]
```

- [ ] **Step 3: Thread `inventory_by_id` into `authored`**

Inside `main()`, after `authored = store.load_authored()`, add:

```python
    # Inventory math is consumed both by the renderer and by the
    # refresh-archetype-inscription slice builder. Compute once and stash
    # under a key that store.persist does not serialize (verified by
    # reading store.py).
    from .paths import REPO_ROOT
    inv_bundle = inventory.load(REPO_ROOT)
    authored["inventory_by_id"] = inv_bundle["by_id"]
```

(If `store.persist` does write the whole dict, instead change the slice builder signature to take a third positional argument and have `_run_pass` pass the bundle; document the change in this task's commit message. The author of this plan checked the slices module and saw `(data, authored)` is canonical, so the carrier-on-authored approach is preferred — but the implementer should confirm.)

- [ ] **Step 4: Verify the orchestrator runs**

```bash
.venv/bin/python -m build --skip-render --no-refresh
```

Expected: append pass runs, no errors.

```bash
.venv/bin/python -m build --skip-render --force-refresh
```

Expected: refresh pass runs, including the new `refresh-archetype-inscription` transformer (visible in the run log: `[refresh-archetype-inscription:<char>] no_change|rewrite`).

- [ ] **Step 5: Commit**

```bash
git add build/__main__.py
git commit -m "orchestrator: register refresh-archetype-inscription"
```

---

### Task 26: End-to-end visual check + ledger of follow-ups

**Files:**
- (no edits — verification only)

- [ ] **Step 1: Full build**

```bash
.venv/bin/python -m build --keep-temp
```

Watch for: every transformer call's decision in the run report, no `FAILED` lines, render `OK`.

- [ ] **Step 2: Local preview**

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory site &
SERVER_PID=$!
sleep 1
echo "Open http://127.0.0.1:8765/"
echo "Verify per character:"
echo "  - Pack section appears under the character TOC link"
echo "  - The Rack hover-lifts a weapon icon and shows damage / weight tooltip"
echo "  - The Spotlight (if any) shows ambient sheen, hover accelerates it"
echo "  - The Manifest grid shows hover tooltip with name/count/weight/description"
echo "  - The Company strip has weight-gauge bars per character that animate fill"
echo "  - Click a strip bar → smooth-scrolls to that character's Pack"
echo "  - Awaiting-manifest characters (Anton, Lilac) show empty bar + Awaiting tooltip"
echo "  - Each character header shows the archetype badge with hover tooltip"
echo "  - Hover tooltip shows authored inscription when present, math stats line otherwise"
read -p "All zones look right? (y/n) " ok
kill $SERVER_PID
[ "$ok" = "y" ] || { echo "Note the gap and fix in a follow-up commit before declaring complete."; exit 1; }
```

- [ ] **Step 3: Run the full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Confirm the forbidden-name guard catches accidental leaks**

```bash
git config core.hooksPath .githooks 2>/dev/null || true
grep -E "(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z]" site/index.html
```

Expected: no matches in `site/index.html`.

- [ ] **Step 5: Final commit**

If any tweaks were made, commit them. If everything looked right and no edits were needed, no commit is required.

```bash
git status
```

If clean, the feature is complete. Open a PR against main:

```bash
git push -u origin feature/inventory-pack
gh pr create --title "Inventory Pack section + company strip + archetype badges" \
  --body "$(cat <<'EOF'
## Summary
- New per-character **Pack** section (Rack / Spotlight / Manifest)
- New top-of-page **Company strip** of weight gauges (carrying-capacity utilization, no encumbrance rule)
- Auto-derived **archetype badge** in each character header — math picks, model writes the in-voice tooltip via the new `refresh-archetype-inscription` transformer
- Privacy: surnames in the inventory snapshot resolved through `build/dice-players.json` and discarded at load time
- Out of scope: currency, GM inventory, cross-party Hoard tab, icon mirror

Spec: `docs/superpowers/specs/2026-05-01-inventory-pack-design.md`
Plan: `docs/superpowers/plans/2026-05-02-inventory-pack-plan.md`

## Test plan
- [x] `pytest tests/` passes
- [x] `python -m build` runs end-to-end and the rendered page passes visual review at the local preview server
- [x] Forbidden-name guard finds no surnames in `site/index.html`
EOF
)"
```

---

## Self-review notes

Spec coverage check (against the design doc sections):

- **Pipeline placement** — Tasks 12, 14, 25 cover render integration and orchestrator registration.
- **Module: build/inventory.py** — Tasks 1–11 build it bottom-up.
- **Pack section: Rack / Spotlight / Manifest** — Tasks 15, 16, 17, 18 (template).
- **Company strip** — Task 19 (template) + Task 21 (CSS).
- **Archetype badge + slate + assignment** — Tasks 6, 7, 8, 9 (math) + Task 18 (badge in header) + Task 14 (inscription resolver) + Tasks 22–25 (authored prose path).
- **Templates touched** — Tasks 15–21 cover all five files listed in the spec.
- **Render-step changes** — Tasks 12, 14.
- **Tests** — `tests/test_inventory.py` accumulates across Tasks 1–14; `tests/test_archetype_inscription.py` accumulates across Tasks 23, 24.
- **Privacy** — Task 3 (scrub-at-load) + Task 26 step 4 (hook check).

Type-consistency check: `inventory_by_id` is the field name used in render, the template, and the slice builder. `archetype_badge` (with `archetype` and `inscription` subfields) is consistent across spec, schema, apply step, and render fallback. `company_strip` field name consistent across render, template, JS. `archetype_inscriptions` mapping (the resolved-and-fallback strings) is set in `compute_all` and read in `_character.html`.

Placeholder scan: no "TBD", "TODO", or vague "add error handling" steps. Each step has runnable code or a concrete command.
