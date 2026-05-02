# Inventory visualization — "Pack" section + Company strip

**Date:** 2026-05-01
**Status:** design (pre-implementation)

## Summary

Surface the upstream inventory snapshot (`data/obr-inv-backup-*.json`) on the
site as a per-character **Pack** section, a top-of-page **Company strip** of
weight gauges, and an **archetype badge** in each character header. The
feature is render-only: no `claude -p` calls, no authored prose, no entries in
`build/authored/`. It mirrors the dice-data integration in shape — read latest
glob, resolve names through `build/dice-players.json`, render deterministically.

The campaign uses 2024 (5.5e) rules, and the 2024 optional encumbrance rule is
**not** in effect at this table. The weight gauge therefore shows pure
carrying-capacity utilization (current / 15×STR), with no threshold lines and
no claim of speed penalty.

## Out of scope

The following are deliberately excluded from this spec:

- **Currency / gold totals** — upstream values are inaccurate; not surfaced.
  `party.json[*].money` remains the source of truth elsewhere on the site.
- **GM inventory** (`name == "GM"`) — scratch space, dropped at load time and
  permanently disregarded going forward.
- **Cross-party "Hoard" tab** — deferred. Each character renders within their
  own card; no dedicated cross-party inventory view in this pass.
- **Icon mirroring** — first pass hot-links upstream icon URLs (5e.tools webp
  and game-icons.net svg). A `site/images/items/` mirror is a possible
  follow-up if hot-linking proves fragile, but is not part of this spec.

## Source data

`data/obr-inv-backup-<timestamp>.json` — Owlbear Rodeo inventory export.
Filenames change over time; the build picks the alphabetically maximal match,
mirroring `data/dicex-rolls-*.json`. Top-level shape:

```
{
  "exportedAt": "...",
  "inventories": {
    "<uuid>": {
      "name": "Simon Weil" | "ScorpioTHK" | "Chumble Crudluck" | "Vex" | "GM",
      "color": "#...",
      "items": [ { id, count, name, category, icon, description, rarity, weight }, ... ],
      "currency": { cp, sp, gp, pp }    // ignored
    },
    ...
  }
}
```

Notes on the data:

- `weight: null` appears on small/wondrous items (Bell, Signal Whistle,
  Cloak of Billowing, Sending Stones, Perfume, Dice Set, etc.). Treated as 0
  lb everywhere — matches 5e norms for spell components and trinkets.
- `rarity` is a lowercase string ("common", "uncommon", ...). Anything above
  "common" qualifies the item for the Spotlight zone.
- `category` values are the upstream Owlbear taxonomy. The renderer maps them
  into four logical groups (see "Pack section" below).
- `icon` is an external URL. Hot-linked in this pass.
- Upstream inventory `name` fields can include real surnames ("Simon Weil").
  The site must never render these — see "Privacy" below.

## Privacy

The existing `build/dice-players.json` substring map already covers every
inventory holder we have today:

```
Simon       → grieg
Chumble     → chumble
Vex         → vex
ScorpioTHK  → urida
Jodi        → lilac
GM          → gm
```

`render.py` already exposes a longest-pattern-first substring resolver
(`_resolve_dice_player`). The inventory loader uses the **same** resolver
against inventory `name` fields. "Simon Weil" matches the "Simon" key and
resolves to slug `grieg`; the surname never enters the renderer's view of the
data and never reaches the template. No new mapping file. No new resolver.

The git-hook forbidden-name guard (`.githooks/_forbidden-names.sh`) continues
to gate any commit that contains a real-name pattern, so the protection is
defence-in-depth: the renderer drops surnames at load time, and the hook
catches accidental leaks elsewhere.

## Pipeline placement

The build orchestrator pipeline (discovery → append → refresh → render) is
unchanged. The new feature lives entirely inside the **render step**:

- `build/render.py` already loads `data/party.json`, `data/dicex-rolls-*.json`,
  `build/authored/*.json` and the dice-player resolver.
- A new module **`build/inventory.py`** loads and shapes the inventory snapshot
  (see "Module: build/inventory.py" below).
- `render.py` calls `inventory.load(repo_root)` once at render time and
  passes the shaped result into the Jinja2 context as `inventory_by_id` and
  `company_strip`.
- No `claude -p` invocations. No new entries in `build/authored/`. No new
  slice builders. No changes to `build/__main__.py`.

## Module: `build/inventory.py`

New file. Contract:

```python
def load(repo_root: Path) -> InventoryBundle: ...
```

Returns a frozen dataclass `InventoryBundle` with two fields the templates
care about:

- `by_id: dict[str, CharacterInventory]` — keyed by character slug
  (`grieg`, `chumble`, `vex`, `urida`, plus `anton` and `lilac` once their
  data appears). Characters without an inventory are absent from the dict.
- `company_strip: list[StripEntry]` — one entry per `data/party.json` member
  in roster order, including placeholder entries for characters with no
  inventory yet.

Internals, all in this module (no shared helpers with `render.py`; the dnd-data
toolchain rule says modules mirror patterns rather than extract shared code):

1. **Resolve latest snapshot.** `glob("obr-inv-backup-*.json")` under the
   data dir, sort, take the last. If no file matches, return an empty bundle
   and the templates render placeholders for every character.
2. **Drop GM.** Skip any inventory whose `name == "GM"`.
3. **Resolve names.** For each remaining inventory, run the upstream `name`
   through the existing dice-player substring resolver to obtain a slug. If
   the resolver returns no match, log a warning and skip — the build does not
   fail (consistent with the rest of the renderer's tolerant ingest).
4. **Group items.** For each item, classify into one of four logical groups:
   - **Arms** — categories `Weapon`, `Armor`, `Ammunition`.
   - **Spotlight** — items with `rarity != "common"` OR category in
     {`Wondrous Item`, `Spellcasting Focus`}. Capped at 3 per character;
     selection ranks rare > uncommon > common-but-wondrous, then by upstream
     order.
   - **Manifest** — everything else: all `Adventuring Gear - *`,
     `Tool`, `Consumable`, `Clothing`, plus any wondrous/focus items that
     spilled past the Spotlight cap.
   - An item appears in exactly one group (Spotlight wins over Manifest for
     items eligible for both).
5. **Compute totals.** `total_weight` (sum of `weight × count`, null=0),
   `item_count` (sum of `count`), and a per-zone breakdown
   `{rack_weight, spotlight_weight, manifest_weight}` summing to
   `total_weight` (one figure per Pack-section zone, used by the
   company-strip tooltip).
6. **Compute carrying capacity.** `15 × party_member.abilities.str`.
7. **Score archetypes.** See "Archetype scoring" below. Returns a single
   archetype slug per character (or `None` if all archetypes were either
   unqualified or claimed by another character).
8. **Build company strip.** One entry per `data/party.json` member. Members
   with inventory get full data; members without get
   `StripEntry(slug=..., status="awaiting_manifest")`.

## Pack section — per-character

New Jinja2 partial **`build/templates/_pack.html`**, included from
`_character.html` after `_reliquary.html`. Adds **"Pack"** to the
character TOC.

Three zones in order:

### A. The Rack — armor and weapons

Horizontal "shelf" element (a thin rule across the section). Items sit on the
shelf as portrait-sized icons, ordered: Armor → Shield → Melee weapons (main →
off-hand) → Ranged weapons. Ammunition does **not** appear as a standalone
item; instead it renders as a small `×N` badge fused to the matching ranged
weapon's icon (Crossbow Bolts ×20 attaches to Heavy Crossbow; Arrows ×20 to
Longbow).

Motion (matching the existing site language — see `styles.css` `.portrait`,
`.session-bar`, `.constellation-star` for precedents):

- Default state: icons rest flush against the shelf line; subtle drop-shadow.
- Hover: 0.2s ease, icon translates `translateY(-4px)`, drop-shadow grows
  beneath. The visual is "lifted off the rack."
- Tooltip (existing JS tooltip layer, same DOM as session-bar/constellation
  tooltips) appears beneath the icon: damage line, properties, mastery, weight,
  count.

If the character has no Arms items, the zone is omitted.

### B. The Spotlight — magic and wondrous

Up to 3 items. Each renders as a "trading card" — larger icon, full name, a
1-line description excerpt, with a tinted border keyed to rarity (common /
uncommon / rare / very-rare / legendary palette tokens, defined in the new
CSS block).

Motion:

- **Ambient** (matching the constellation orbit precedent — page already has
  long-running motion): a slow ~6-second linear-gradient sheen sweeps
  diagonally across each card via CSS `@keyframes`. Subtle — opacity
  oscillates between ~0 and ~0.18.
- Hover: card lifts `translateY(-2px)`, sheen animation duration briefly
  shortens (~2s) for the duration of the hover, full description tooltip
  shows the upstream `description` field verbatim.

Zone is omitted if the character has zero Spotlight items.

### C. The Manifest — everything else

Compact responsive grid of icon chips. Each chip is a square tile with the
item icon and a small `×N` count badge in the top-right corner when count
> 1. Chips are sorted by category (alphabetical), then by `weight × count`
descending within category.

Motion:

- Default: chips are flat with a thin border.
- Hover: 0.15s, chip lifts `translateY(-1px)`, gains a thin glow (box-shadow);
  tooltip shows name, count, per-item weight, total weight, and the upstream
  description.

A small heading line above the grid: *"{item_count} items · {weight} lb"* —
e.g. *"28 items · 64 lb"*.

If the character has no Manifest items (rare, but possible), the zone is
omitted; the section renders just Rack + Spotlight.

### Empty-section behavior

If the character has no inventory data at all (Anton, Lilac), the Pack
section renders a single centred line — *"Awaiting manifest."* — with the
same archaic-italic styling as the empty-state lines used elsewhere on the
page. The TOC still lists "Pack" so anchor links remain stable.

## Company strip — top-of-page weight gauges

Thin row inserted at the top of the existing **Company** section (extends
`_company.html` rather than introducing a new partial — the strip is a
property of the company view, not a separate concern).

One horizontal gauge per `data/party.json` member, in roster order. Each
gauge:

- A bar element ranging 0 → 15 × STR (carrying capacity in lb).
- Filled portion = current carried weight.
- Fill colour = a cool→warm CSS gradient applied to the *fill width itself*,
  so a low-utilisation bar reads cool-blue and a high-utilisation bar reads
  warm-amber. Crucially **not** threshold-coloured (no encumbrance rule in
  play).
- Label above bar: character shortname (the first whitespace-split token of
  `data/party.json[*].name` — "Chumble Crudluck" → "Chumble", "Lilac Mist" →
  "Lilac"). Label below bar: `{carried} / {max} lb`, e.g. *"175.5 / 255 lb"*.

Motion:

- **Entry**: on initial render, each bar's fill animates 0 → current over
  ~800ms with the same `cubic-bezier` easing curve already used by the
  constellation appearance. Bars stagger ~80ms apart in roster order so the
  strip "fills in" as a small page-load flourish. Implemented via CSS
  `@keyframes` plus per-bar `animation-delay`, **not** via JS — the existing
  page deliberately keeps motion CSS-driven where possible.
- **Hover**: bar lifts `translateY(-1px)`, gains the same thin glow used by
  Manifest chips; tooltip (existing JS layer) shows the breakdown line —
  *"Rack 56 · Spotlight 0 · Manifest 29.5 = 85.5 lb · 48% of capacity"*
  (one figure per Pack-section zone, summing to total weight). Spotlight
  weight is often 0 because most wondrous items have `weight: null`; that
  zero is shown explicitly to keep the breakdown legible.
- **Click**: smooth-scroll to that character's `#<slug>-pack` anchor. (The
  Pack section's `id` is generated by the existing TOC pattern.)

Anton/Lilac slots show an empty bar (no fill, no animation) with
*"Awaiting manifest"* on hover. The slot still occupies its grid cell so the
strip's layout is stable as inventories arrive.

## Archetype badge

Small uppercase chip rendered in the character header, immediately below the
existing `class · tier · background` meta line. One badge per character, or
none if the character has no qualifying archetype this build.

### Slate (16 archetypes)

Themed groups; ranking metric in parens. All metrics are computed strictly
from the items the character holds (counts and the upstream `name`/`category`
fields), with one exception for Featherfoot which references `15 × STR`.

**Combat (4):**

- **The Pack-Mule** — highest `total_weight`.
- **The Armorer** — highest summed weight across categories
  `{Armor, Weapon}`.
- **The Glaive-Hand** — most *distinct* `Weapon`-category items
  (different `id`s, not summed counts).
- **The Quiver** — highest summed `count` across `Ammunition`-category
  items.

**Magic & lore (4):**

- **The Curio-Keeper** — most items where `rarity != "common"` OR category
  is `Wondrous Item`.
- **The Naturalist** — case-insensitive substring match on item names against
  `{"druidic", "mistletoe", "yew", "totem", "natural"}` plus category
  `Spellcasting Focus` where description mentions "druid". Highest count
  wins.
- **The Scholar** — substring match on `{"book", "parchment", "ink",
  "scroll", "spellbook"}` in item names. Highest count wins.
- **The Tongues** — substring match on `{"sending stone", "message",
  "speaking", "whisper"}`. Highest count wins.

**Survival (5):**

- **The Lamplighter** — substring match on `{"oil", "torch", "lantern",
  "candle", "tinderbox", "lamp"}`. Sum of counts wins.
- **The Pathfinder** — substring match on `{"rope", "crowbar", "grapple",
  "piton", "spike", "climber"}`. Sum of counts wins.
- **The Apothecary** — most items in category `Consumable`.
- **The Cellarer** — substring match on `{"ration", "waterskin", "mess kit",
  "trail", "wineskin"}`. Sum of counts wins.
- **The Trapper** — substring match on `{"caltrop", "trap", "snare",
  "hunter's trap"}`. Sum of counts wins.

**Personal (1):**

- **The Costume-Master** — substring match on `{"costume", "disguise",
  "perfume", "fine clothes", "noble"}`. Highest count wins.

**Aggregate (2):**

- **The Quartermaster** — most distinct items overall (count of unique `id`s).
- **The Featherfoot** — lowest `total_weight / (15 × STR)` ratio.
  Tiebreaker: lowest absolute `total_weight`. Only awarded if the lead over
  second-place is ≥ 5 percentage points (otherwise unawarded — the badge
  shouldn't go to a 2-pp difference).

### Assignment

Greedy, deterministic, no randomness:

1. For each archetype, compute every character's score.
2. For each character, compute `(archetype, score, lead)` for every
   archetype where they rank first, where `lead` = their score minus the
   runner-up's score (in absolute units, except Featherfoot's lead is in
   percentage points).
3. Each character keeps the archetype with the largest `lead`. Ties broken
   by the slate's listed order above (Pack-Mule before Armorer, etc.).
4. Archetypes a character "lost" via the lead-tiebreak fall through to the
   second-place character, who runs through step 3 again with the new
   addition. Iterate until stable.
5. An archetype with zero qualifying scorers (e.g. nobody has any rope) is
   simply unawarded that build.

This guarantees each character gets at most one badge, and that the badge a
character holds reflects the metric they dominate the *most decisively*. With
4 characters of inventory data right now, four badges will be awarded; the
remaining 12 archetypes wait in the slate.

### Motion

- Default: flat chip, 1px border in a muted accent colour.
- Hover: 0.18s, chip rotates `2deg` and lifts `translateY(-2px)` with a
  brighter glow; tooltip explains the math, e.g.
  *"Carries 175.5 lb across 31 items — most in the party."*

## Templates touched

- **`build/templates/_character.html`** — add the new `Pack` link to
  `.character-toc` and `{% include "_pack.html" %}` after `_reliquary.html`.
  Also: render the archetype badge below the existing `meta` line in
  `.character-header > .identity`.
- **`build/templates/_company.html`** — insert the company strip element at
  the top of the section.
- **`build/templates/_pack.html`** — new partial; renders the three zones
  (Rack, Spotlight, Manifest) or the empty-state line.
- **`build/templates/_script.html`** — add new per-feature tooltip IIFEs that
  mirror the existing ones (chronicle pip, constellation star, sessions chart,
  dt-chart) for the new hoverable selectors: `.rack-item`, `.spotlight-card`,
  `.manifest-chip`, `.company-strip-bar`, `.archetype`. Each IIFE finds the
  shared `.dice-tooltip` element, queries its selector, attaches mouseenter
  / mouseleave handlers, and reads tooltip content from `data-*` attributes
  on the element. Pattern is mirrored, not extracted into a shared helper —
  consistent with the toolchain rule that modules mirror rather than share
  code.
- **`site/styles.css`** — add the Pack-feature CSS block at the end:
  layout for shelf / spotlight cards / manifest grid / company strip /
  archetype chip, plus `@keyframes` for the spotlight sheen and the
  strip-fill entry animation. ~150–200 lines, scoped under feature-prefixed
  classes (`.pack-*`, `.rack-*`, `.spotlight-*`, `.manifest-*`,
  `.company-strip-*`, `.archetype`).

## Render-step changes

`build/render.py`:

- Import `build.inventory`.
- Call `inventory.load(REPO_ROOT)` once after the existing data loads.
- Pass `inventory_by_id` and `company_strip` into the Jinja2 render context.
- No changes to existing data loading, the dice-player resolver, or
  validation gates. The inventory loader is non-fatal: if the snapshot is
  missing or malformed, an empty bundle is returned and the build proceeds —
  every character renders the *Awaiting manifest* placeholder. Logged at
  warning level.

## Tests

Add a new file **`tests/test_inventory.py`** with cases that exercise the
loader contract on fixture data placed under `tests/fixtures/inventory/`:

- A snapshot with all four current inventories → bundle has 4 entries; GM is
  absent; "Simon Weil" resolves to `grieg`.
- An item with `weight: null` contributes 0 to the total.
- A snapshot with only Lilac/Anton (i.e. neither resolved) → bundle is empty,
  no exception.
- Spotlight cap of 3 — supplying 5 wondrous items keeps the top 3.
- Archetype assignment determinism — fixed scores produce the expected
  badge map.
- The company strip preserves `data/party.json` member order including
  placeholder entries for characters without inventory.

Tests use the existing `BUILD_DATA_DIR` env-var override (`build/paths.py`)
to point at the fixture directory; no monkeypatching of internals.

End-to-end verification still happens by running `python -m build` and
visually checking the rendered page in the local preview server.

## Privacy & forbidden-name guard

The existing `.githooks/_forbidden-names.sh` regex catches surnames
adjacent to player first names. The inventory loader's first action after
parsing JSON is to resolve `name` through the dice-player substring map and
discard the original `name` field. The slug is the only identifier that flows
into templates. No surname can reach `site/index.html`.

Defence in depth: a unit test asserts that the rendered HTML for a fixture
build contains no occurrence of the substring "Weil" (the only real surname
present in current inventory fixtures). The test is part of
`tests/test_inventory.py`.

## Risks & mitigations

- **Hot-linked icons going stale.** 5e.tools and game-icons.net are stable
  hosts, but a long-tail outage would render broken images. *Mitigation:*
  CSS sets a fallback background colour on icon containers so chips remain
  legible without their icon, and item names always render alongside.
  A future `site/images/items/` mirror is the durable fix.
- **Upstream taxonomy changes.** The classification step in
  `build/inventory.py` keys on string equality of `category`. New upstream
  categories would silently land in **Manifest** as a fallback. *Mitigation:*
  the loader logs any unrecognised category at info level so a
  classification update is visible without breaking the build.
- **Archetype assignment producing surprising badges.** With small data, a
  character might get a badge that feels accidental (e.g. Chumble holds the
  only book, becoming The Scholar by default). *Mitigation:* the lead-based
  greedy assignment means a character who narrowly wins one metric while
  decisively winning another keeps the decisive one. The minimum-lead floor
  on Featherfoot guards against the most pathological tie. If specific
  archetypes feel wrong in practice, the slate is a single dictionary in
  `inventory.py` — easy to retune.

## Open follow-ups (not in this spec)

- `site/images/items/` icon mirror.
- Currency surfacing once upstream values are reliable.
- Cross-party "Hoard" tab.
- Inventory history (snapshots over time → "what did the party gain this
  arc?"). Will require keeping older `obr-inv-backup-*.json` files instead
  of only loading the latest.
