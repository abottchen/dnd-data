# NPC circles: grouping the Dramatis Personae

Design for grouping the GM tab's cast by the groups the players know them as,
with a recency fold inside each group. Agreed in conversation on 2026-10-26;
the "Decisions made without the user" section lists calls made after the user
stepped away, for review.

## Intent

The cast list on the GM tab is 82 names after 31 sessions and grows by two to
four a session. Today it is two columns split by allegiance (55 "with" against
12 "against"; 15 with no allegiance are silently dropped), 4,700 px tall, with
the GM's Fortune section buried beneath it. Two things make it read as long:
nothing is current (14 of 82 were named in the latest session) and nothing is
grouped (the players think in groups: "the guides", "the merchant princes",
"the Shilku dwarves").

The page should show, in one screen, the groups the party has dealt with,
with the people currently in play prominent and the rest one click away, and
it should keep every name on the page.

## Goals

- Every NPC files under the group the players would name for them.
- NPCs named in the last few sessions are prominent; the rest fold, but
  never out of existence: names stay visible and findable.
- Groups with both current and stale members read as one group.
- Faction membership (Harpers, Flaming Fist, ...) is visible without being
  the structure, because it cuts across the groups.
- The authoring pipeline produces the grouping data; no hand curation going
  forward.

## Non-goals

- Person-to-person relationships (Salida as Ras Nsi's asset, River paired
  with Flask). Those live in the epithet prose. No `ties` field until a view
  needs it.
- Geography. Where someone was met is epithet detail, not structure
  (Musharib and Shago are "the guides", not "Port Nyanzaru").
- Nested folds. One fold, one meaning.

## Vocabulary

- **Circle**: a named group of NPCs. Two kinds:
  - **company**: the group the party knew them as. The memory test the
    prompt applies: "if a player had to say who this person was in five
    words, which group would they name?" Examples: the guides, the merchant
    princes, the crew of the Horizon, Camp Vengeance, the Shilku dwarves.
  - **faction**: an organisation that cuts across companies: the Harpers,
    the Zhentarim, the Flaming Fist, the Order of the Gauntlet, the Emerald
    Enclave, the Ytepka Society.
- **Home circle**: the first company in an NPC's `circles` list. Where their
  entry lives on the page.
- **Present**: named in the session log within the last
  `CAST_PRESENT_WINDOW` (5) sessions, by the conservative matcher in
  `build/compute.py` (`npc_sessions`).

## Data contract

### Registry: `build/authored/site.json` → `circles`

```json
"circles": [
  {"key": "guides",          "title": "The Guides",            "kind": "company"},
  {"key": "merchant-princes","title": "The Merchant Princes",  "kind": "company"},
  {"key": "harpers",         "title": "The Harpers",           "kind": "faction"}
]
```

- `key`: slug, `^[a-z0-9]+(-[a-z0-9]+)*$`, unique, stable once published
  (entries reference it).
- `title`: the party's name for the group, display text, non-blank.
- `kind`: `"company"` or `"faction"`.
- Order in the list is not significant; the renderer orders by recency.

### Per NPC: `build/authored/npcs.json`

```json
{"name": "Wren", "allegiance": "with", "epithet": "...", "circles": ["port-nyanzaru", "harpers"]}
```

- `circles`: required list of registry keys. May be empty (the NPC belongs to
  no named group and files under the catch-all). No duplicates.
- Companies first, most salient first. The first company is the home circle.
  Factions may appear anywhere in the list.
- The ordinary case is one company and zero or one faction. Two companies is
  allowed and rendered as a cross-reference (below).

### Validation (gates the render, like every other `validate_*`)

- Registry: unique keys matching the slug pattern; non-blank titles; `kind`
  in the two values.
- Every key in every NPC's `circles` exists in the registry; no duplicate
  keys within one NPC.
- An NPC with no `circles` field at all is MALFORMED once the backfill has
  landed. (Renderer tolerates it as `[]` so a half-migrated tree still
  renders during development.)
- Every registry circle has at least one member. A circle nobody belongs to
  is clutter and most likely a key typo.

## Pipeline changes (`build/`, `.claude/prompts/`)

- **Registry ownership**: the discovery pass (`refresh-known-npcs`) owns
  additions to the registry. It already reads new session text to find newly
  named NPCs; it now also proposes new circles (company or faction) that the
  new text introduces, choosing keys and the party's own words for titles,
  with the current registry in front of it so it never duplicates. Result
  schema gains an optional `circles` addition list. Existing circles are
  never renamed or removed by the pipeline.
- **`append-npcs`**: the slice carries the registry. The result's `fields`
  gains `circles` (required). The prompt states the memory test, that
  companies come first with the home circle first, that factions are listed
  after companies, and that an empty list is the honest answer when no
  registry circle fits (it is better than inventing a key; a later discovery
  pass or refresh can place them).
- **`refresh-npcs`**: a `rewrite` result's `fields` also carries `circles`,
  so a refresh can move someone (for example when a guide joins the company
  for good).
- **`apply`**: writes `circles` on NPC entries; merges registry additions
  into `site.circles` (append only, skip keys already present).
- **Validators**: as above, wired into `validate_all`.
- **Slices**: the registry is part of the slice data for `append-npcs` and
  `refresh-npcs`.
- **Schemas**: `.claude/prompts/*.schema.json` updated to match; the schema
  tests in `tests/test_schemas.py` must cover the new fields.
- **Docs**: CLAUDE.md's authored-store and orchestration sections describe
  the registry and the field.

### Initial population

The 82 existing NPCs are assigned directly in the authored store (hand
backfill by the implementing agent, from the epithets and the session log),
and the registry is seeded at the same time. This is a one-time act; the
pipeline handles every NPC from then on. Starting registry, to be refined
against the evidence:

Companies: the crew of the Horizon; the House of Healing (Azlund, Tessa);
the merchant princes; the guides (Musharib, Shago, Salida, River, Flask,
Qawasha, Eku, Azaka Stormfang, Hew Hackinstone, Faroul & Gondolo, ...); the
people of Port Nyanzaru (Grandfather Zitembe, Wren, Wakanga, Zindar, ...);
Camp Vengeance; Fort Beluarian; Nuanwa Olerro's scouts; the Shilku dwarves;
Sithi Vinecutter's company; Ras Nsi's yuan-ti; Kaya's House of Repose;
Orolunga; Mbala. Factions: the Harpers; the Zhentarim; the Flaming Fist; the
Order of the Gauntlet; the Emerald Enclave.

Singletons (Volo, Nava, Acererak, ...) get an empty list and file under the
catch-all; a company of one is not a group.

## Rendering (`build/compute.py`, `build/templates/_gm.html`, `site/styles.css`)

- **One plate, circles as blocks**, flowing in two columns on wide screens,
  one under 900 px. Each block: heading (title, member count), then full
  run-in entries for present home members, then the **roll call**: one line
  of bare names for everyone else in the circle, which is a native
  `<details>` whose open state expands those names into full entries. The
  roll call is the only fold on the page. A circle with no present members
  is a heading and a roll call.
- **Order**: circles by most recent mention among their members, most recent
  first, then by first mention. The catch-all ("Met along the road") is
  always last.
- **Entry**: name in brass, comma, epithet inline, hanging indent. Each
  entry has an `id` so cross-references can link to it.
- **Cross-references**: an NPC with two companies has one entry, in the
  home circle. In the other company they appear in the roll call as a link
  to that entry (dimmer, so the eye reads "see elsewhere"); the entry itself
  carries a small "also of ..." tag linking back. Counts include them.
- **Marks**, in the same place on every line so the eye learns them once:
  - allegiance `against`: a small seal-red glyph before the name with a
    title attribute ("stood against them"). Colour never carries it alone.
  - faction: a small brass heraldic sigil after the name per faction, with
    a title attribute naming the faction. Known faction keys map to drawn
    sigils; an unknown faction key gets a generic mark. A legend under the
    plate names the sigils that appear.
- **Tolerance**: a missing `circles` field reads as `[]`; a key missing from
  the registry is ignored by the renderer (the validator reports it); an
  absent registry means every NPC files under the catch-all.

## As built (deviations recorded after implementation)

- Registry proposals from the discovery pass carry a required `members`
  list (canonical NPC names, at least one), and apply files already
  authored members under the new circle at once. Reason: every slice in a
  run is prepared from the pre-run store, so a circle proposed for NPCs who
  are already authored could never gain members through the pipeline, and
  the memberless-circle rule would then fail the render until a hand edit.
  Members not yet authored are placed by their own `append-npcs` slice on
  the next build.
- Apply normalises `circles` to companies-first order rather than trusting
  the model's ordering; the validator accepts either order.
- Registry as populated for session 31: twelve companies (the House of
  Healing, the Horizon, the Companions, the Guides, the People of Port
  Nyanzaru, the Merchant Princes, the Dinosaur Racers, Camp Vengeance,
  Yokka's Goblins, Nuanwa Olerro's Scouts, Fort Beluarian, the Shilku
  Dwarves) and five factions (Harpers, Zhentarim, Order of the Gauntlet,
  Emerald Enclave, Flaming Fist). Fifteen NPCs file under the catch-all.
  Calls worth a second look are listed in the implementing agent's report
  and summarised in the pull request.
- The Companions (Artus Cimber, Dragonbait, Vorn, Wickles) is the circle
  for everyone who travels with the party for the long haul. The first
  backfill had filed Artus and Dragonbait under the Horizon because they
  arrived on it, and kept a separate "Company's Own" circle for the two
  PC-bound creatures; the user corrected the first on review, and the
  second was folded in rather than leave two two-member circles that both
  mean "goes where the party goes". The prompts now say that how someone
  arrived is not their group.
- Three of the 82 were not NPCs at all: Lilac Mist is a player character
  (the discovery prompt had used her name as its example of a named
  person), Wickles is Chumble's familiar and Vorn a shield guardian the
  party owns. All three are out of the store. The discovery slice now
  carries the party roster and a `site.not_npcs` deny list (Wickles,
  Vorn, each with a why), apply drops any such name from a result, and a
  validator fails the render if one reaches `known_npcs` or `npcs.json`.
  Faroul & Gondolo file under the Guides only, on the user's word.

## Decisions made without the user

- Factions are marks, companies are the spine (agreed in conversation).
- Registry additions come only from the discovery pass, not from per-NPC
  slices, so two slices in one run cannot invent the same circle twice under
  different keys. Per-NPC slices choose from the registry or return `[]`.
- Backfill is written directly into the authored store rather than by a
  forced refresh of 82 slices: one author seeing all 82 at once keeps the
  grouping consistent, and it costs nothing to run.
- The catch-all is synthesised by the renderer, not stored as a circle.
- Cross-referenced members always sit in the roll call of their secondary
  circle, even when present; the presence shows in the home entry.
- The present window stays at five sessions.

## Revised on review (2026-10-27)

Adam reviewed the first build on the live page and the contract above was
cut down to what the page actually uses. What stands now:

- **One circle per NPC.** `circles` (a list) became `circle` (one registry
  key or null). Cross-references were clutter, and without them a second
  company had no job; without chips, a faction had no job either, so the
  `kind` split is gone. An organisation (the Harpers) is simply a circle
  for people no closer group claims (Azlund); Wren's Harper membership
  lives in his epithet.
- **No allegiance.** The field was authored, reviewed, wrong four times in
  ten, and shown nowhere once the against-mark went. Removed from prompts,
  schemas, apply, slices, validators and the store; the validator refuses
  the retired fields so the store cannot drift back.
- **No marks at all.** Sigils needed a legend; chips felt out of place.
  Death is stated in the epithet, which the prompts now require.
- **Billing.** A registry entry may carry `billing`: `principal` (The
  Companions, The Enemy: Acererak and Ras Nsi) or `aside` (The Dinosaur
  Racers). The discovery pass proposes it; the GM can hand-edit it.
- **Layout.** One column at an 880 px measure; group titles in the display
  serif; entries as a name column and a roman description column; the
  present window is three sessions. Principals come first and never fold.
  Circles with nobody named lately drop out of the column into one folded
  row each under a rule. Every fold is the same control, one open at a
  time, animated, with a "fold" control while open.
- **Removed from the store on review:** Lilac Mist (a player character),
  Wickles and Vorn (a familiar and a shield guardian; `site.not_npcs`
  keeps them out), The Fleeing Yuan-ti (not a name), The House of Healing
  and Yokka's Goblins (not groups the players would name).
