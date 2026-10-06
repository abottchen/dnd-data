# dnd-data

Static GitHub Pages site visualizing data from an ongoing D&D campaign.

## What's in this repo

- `site/` — the served artifact directory. Uploaded to GitHub Pages by `.github/workflows/deploy-pages.yml`.
  - `site/index.html` — build artifact (committed).
  - `site/styles.css` — the design system (palette, typography, components).
  - `site/images/` — character portrait tokens. Filenames match each entry's `image` field in `data/party.json` (e.g. `chumble-crudluck.png`). The GM's token is `GM.png`.
  - `site/images/chult-map.jpg` — committed web derivative of the annotated player map, built from the gitignored source by `build/mapimage.py`. Full resolution (6445×8640, ~12 MB) because the Map tab's viewer zooms past native pixel density.
- `data/` — ingestion directory for source files (gitignored contents). Holds `party.json`, `session-log.json`, plus `dice/` and `inventory/` subdirectories. Files are dropped in manually from external sources; nothing in this repo writes to `data/`.
  - `data/party.json` — current party snapshot (character-sheet export).
  - `data/chult-player-map.jpg` — the party's annotated map of Chult (~17 MB export). Source only; the served copy is the derivative in `site/images/`.
  - `data/dice/dicex-rolls-*.json` — dice-roll snapshots (dice-roller export).
  - `data/inventory/obr-inv-backup-*.json` — Owlbear Rodeo inventory exports.
  - `data/session-log.json` — per-session narrative entries with real + in-universe dates.
- `build/` — the build orchestrator. Python package that prepares authoring slices, applies in-session results, and renders `site/index.html`. Entry point: `python -m build`.
  - `build/__main__.py` — orchestrator entry point. Subcommands: `prepare` (gather slices into a run dir) and `apply` (validate results, write authored JSON, render).
  - `build/render.py` — CLI + Jinja render layer. Loads `data/` (`load_data`, incl. the real-name privacy scrub) + `build/authored/*.json`, wires `validate_all` (fact pack built once in `main` and passed in), and renders `site/index.html` from `build/templates/*.html`. Keeps `BUILD_DIR = Path(__file__).resolve().parent` (templates / authored) and `REPO_ROOT = BUILD_DIR.parent` (`data/`, `site/`), plus a re-export shim (absolute `from build.…` imports so `python build/render.py` still runs as a script) so the pre-split public surface stays importable through `build.render` — tests and `build/slices.py` rely on it.
  - `build/loaders.py` — authored-store, PC-pronoun, and dice-player-map loading: `load_authored`, `load_character_pronouns`, `load_dice_player_map` / `resolve_dice_player` (longest-pattern-first substring resolve), plus the `_mdy_to_iso` / `_has_chapter_marker` session-log normalizers. Owns `BUILD_DIR` for `dice-players.json` / `character-pronouns.json`.
  - `build/validators.py` — `ValidationError` + every `validate_*` (kills, sessions, chapters, npcs, characters, portraits, site, dice-player mapping, distinction basis/uniqueness) and the `kill_key` / `collect_npcs_from_log` helpers.
  - `build/reference.py` — the record behind a session, for the Chronicle writer: `party_sheets` from `party.json` (features, feats, attacks, spells, notable gear), `match_places` (sections of the ToA module text whose names appear in the session log, read through `.claude/ext/dnd-toa`; sections named for people, and the foreword and appendices, are never handed over), `creature_lore` (bestiary descriptions for creatures killed or named, singular or plural, never named NPCs), and `seen_before` (earlier-visit log lines with DM notes cut). Assembled by `build_reference` into the `append-sessions` slice. A missing `dnd-toa` link is tolerated: the writer gets no module text and `prepare` says so once.
  - `build/bestiary.py` — 5etools bestiary lookup (`bestiary_lookup`; the `BESTIARY_GLOB` under `.claude/ext/` is resolved from `build.paths.REPO_ROOT`) plus the CR→XP tables (`XP_BY_CR`, `xp_for_cr`, `_kill_cr` / `_kill_xp`).
  - `build/compute.py` — every `compute_*` (trials, fortune, radar / ascent / constellation geometry, chronicle, reliquary, …) and `compute_all`, which assembles the full template context. Imports `inventory` at module top: the old render↔inventory circular import is dissolved because `inventory` now imports the dice-map loader from `loaders`.
  - `build/paths.py`, `store.py`, `slices.py`, `registry.py`, `prepare.py`, `apply.py`, `apply_cli.py` — orchestrator submodules (path resolution, authored-store I/O, per-category slice builders, transformer registry, run-dir preparation, returned-prose application, manifest-driven apply + render).
  - `build/authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the orchestrator's apply step.
  - `build/mapimage.py` — re-encodes `data/chult-player-map.jpg` into `site/images/chult-map.jpg` at full resolution (`prepare_map`). Called by `apply` just before the render, and available standalone as `python -m build map [--force]`. A no-op unless the source's SHA-256 differs from the one recorded in `build/map-source.json`, so ordinary builds pay nothing.
  - `build/map-source.json` — committed record of the SHA-256 `site/images/chult-map.jpg` was last built from, plus its byte size. This is the map's staleness signal; mtimes are deliberately not consulted, because the derivative is git-tracked and git stamps working-tree files at checkout time, so a pull or stash after dropping in a new map would leave the stale derivative looking newer than its own source. Delete it to force a one-off rebuild.
  - `build/templates/` — Jinja2 partials consumed by `build/render.py`. Locked; not modified by normal authoring. Reference assets via paths relative to `site/index.html` (e.g. `styles.css`, `images/...`). `_map.html` is the Map tab; its pan/zoom viewer is the last IIFE in `_script.html`.
  - `build/dice-players.json` — substring map (first-name or handle → site slug) used by `loaders.py:resolve_dice_player` (re-exported through `build.render` for back-compat). Never records full real names.
- `.claude/prompts/` — paired prompt and schema files, one pair per transformer (`append-kills`, `append-sessions`, `append-chapters`, `append-npcs`, `append-characters`, `append-sworn`, `refresh-known-npcs`, `refresh-chapters`, `refresh-npcs`, `refresh-characters`, `refresh-road-ahead`, `refresh-intro-epithet`, `refresh-ascent-read`, `refresh-archetype-inscription`). Each prompt has YAML frontmatter declaring its preferred model. A line of the form `{{include: name.md}}` is replaced with that file's body when `prepare` freezes the prompt, so the run dir records exactly what the agents read. Three extra pairs, `plan-sessions`, `edit-sessions` and `verify-sessions`, are not transformers: they are the plan, the editor and the fact-check paired with `append-sessions`. One more file, `publisher-notes.md`, is not a prompt: it is the standard the Chronicle is held to, the publisher's own rejection notes quoted verbatim with the passages they were about, plus his telling of one fight. The writer's, editor's and planner's briefs include it. It grows by a note when a draft is rejected for a reason not already in it; the brief itself stays short and carries no rules beyond one (see below). **It is local and gitignored**: the repo is public and the players could read it, so the publisher's words never go into a commit. A fresh clone cannot build a session entry until the file exists; `prepare` says so.
  - `append-sessions` drafts a session's Chronicle entry in voice, from a plan the publisher (the user) approved first. `plan-sessions` reads the same slice and returns the story the page will tell: through-line, what it opens on, one subject per paragraph and what each is built from, why that order, the silent roll, and what goes nowhere. The skill prints it and waits for Approve; anything typed instead is notes for a new plan, with no round limit. The approved plan (`context/<stem>.plan.json`) is an input to the writer, the editor, and every revision. Its slice carries the chronicle so far (every earlier entry, which is what the reader has read and the writer's memory) and a `reference` block built by `build/reference.py` (party sheets, the module's text for the places the log names, the bestiary on the creatures met, and earlier-visit log lines). It never carries the prior session logs. The writer's only rule is no spoilers: nothing on the page the players don't have. When it cannot tell whether the company knows something in the reference, it asks with AskUserQuestion before writing.
  - Then, in the same build, the `/build-prose` skill runs the edit loop. An `edit-sessions` sub-agent reads in two stages: first as a reader, with only the chronicle (`context/<stem>.chronicle.json`, written by `prepare`), the approved plan, the previous round's critique, and the draft, and it states the plan's through-line and its verdict and writes them to disk before it is allowed to open the session log; then against the log, filling in `log_check` (how much of the log is on the page, lifted sentences, equal weighting, what to cut, what was dropped), after which it may lower the verdict to `redraft` but never raise it. The verdict is `accept`, `revise` (the author revises in place), or `redraft` (the shape is wrong: the author starts over from the plan). A draft whose paragraphs are not the plan's, or that leaves a previous note unaddressed, is `redraft`. Up to `EDIT_MAX_ROUNDS` rounds. Critiques are written beside the result as `results/<stem>.edit-<n>.json`, which apply never reads. The editor is a filter, not the gate.
  - Once the prose settles, a `verify-sessions` sub-agent checks the entry against the record (log, roster, kills, chronicle, reference) under the same one rule, treating details drawn from the reference as record rather than invention, and writes the final entry. Its output conforms to the `append-sessions` schema, so apply consumes it unchanged.
  - Then the skill prints the finished entry and waits for the publisher's Publish. Anything typed instead is notes: the writer revises against them, verify runs again, and the entry comes back, with no round limit and no sub-agent editor in between. Stop holds the entry (`results/<stem>.held.json`) and returns the slice to pending, so apply skips the render. `apply` runs only after this stop, so its pruning of a successful run happens after the publisher has seen the plans and critiques. `prepare` freezes all three pairs and records them under the manifest's `plan`, `edit` and `verify` maps for any authoring transformer that pairs them (see `build/prepare.py:PLAN_FOR` / `EDIT_FOR` / `VERIFY_FOR`).
- `requirements.txt`, `.venv/` — Python dependencies (Jinja2, etc.).
- `tests/` — pytest suite covering validators, key matching, computation formulas, slice builders, and bestiary lookup. `tests/conftest.py` adds the repo root to `sys.path` so tests can import `build.render`, `build.slices`, etc.
- `.github/workflows/deploy-pages.yml` — uploads `site/` as the Pages artifact on every push to `main`.

## Build & deploy

Building is normally a single command in a Claude Code session:

- `/build-prose` — the skill runs `python -m build prepare`, dispatches
  one sub-agent per pending slice (each writes a JSON result file), and
  then runs `python -m build apply` to validate, persist authored prose,
  bump the marker on full refresh-pass success, and render `site/index.html`.

If a slice fails, fix the prompt or slice and re-run `/build-prose <run-dir>`
(the run dir path is printed by the skill) to resume — already-authored
slices in `done/` are skipped.

The two underlying CLIs can still be invoked directly when needed:

- `.venv/bin/python -m build prepare` — gathers any pending slices into
  `build/.run/<timestamp>/` (manifest, pending slices, frozen prompts).
- `.venv/bin/python -m build apply build/.run/<timestamp>/` — validates
  each result against its schema, applies it to `build/authored/*.json`,
  bumps the marker on full refresh-pass success, and runs `build/render.py`.

A bare `python -m build` is the same as `prepare`.

Validation gates the render: any `MISSING` or `MALFORMED` authored entry
causes `render.py` to exit 1. Fix the authored entry and re-run apply.

CLI flags:
- `prepare --no-refresh` — skip the discovery and refresh passes.
- `prepare --force-refresh` — run them even when the marker is current.
- `prepare --keep-temp` — preserve the run dir on success.
- `apply --skip-render` — apply results but don't rebuild the site.

Plus one asset CLI, run automatically inside `apply`:

- `.venv/bin/python -m build map [--force]` — re-encode `data/chult-player-map.jpg`
  into `site/images/chult-map.jpg`. Skips when the derivative is already newer
  than the source.

To publish: pull `main`, run `/build-prose`, commit `site/index.html`
and `build/authored/*.json`, push.

Configure once: Settings → Pages → Source: **GitHub Actions**.

## Orchestration

The `build` package prepares authoring slices, dispatches them in-session via the `/build-prose` skill, and then applies results to `build/authored/*.json` before running `build/render.py`. The orchestrator is deterministic Python; the model's only job is to produce schema-conformant prose for one slice at a time.

Pipeline (`prepare` step):
1. Load source data from `data/` + authored prose from `build/authored/`.
2. **Discovery pass** — when `latest_session > site.refreshed_through_session`, run `refresh-known-npcs` to extract any newly named NPCs from new session text and append them to `site.known_npcs`. Runs before the append pass so newly discovered names flow into per-NPC epithet authoring on the same build. Returns `no_change` or `rewrite`.
3. **Append pass** — for each category (`kills`, `sessions`, `chapters`, `npcs`, `characters`), the slice builder in `build/slices.py` computes a set difference between `data/` and `build/authored/` (keyed on `(character, date, creature, method)` for kills, `session` id for sessions, `name` for NPCs, etc.). One slice is emitted per missing entity. Deleting a single entry from an authored file causes that one entry to be re-authored on the next run; nothing else moves.
4. **Refresh pass** — when `latest_session > site.refreshed_through_session`, evaluate each `refresh-*` transformer (`chapters`, `npcs`, `characters`, `road-ahead`, `intro-epithet`); each returns `no_change` or `rewrite`.
5. Write all pending slices + frozen prompts to `build/.run/<timestamp>/pending/`, and freeze the `plan-sessions`, `edit-sessions` and `verify-sessions` prompts when `append-sessions` emitted (recorded in the manifest's `plan`, `edit` and `verify` maps).

In-session (`/build-prose` skill): for every slice whose transformer has an entry in the manifest's `plan` map (currently `append-sessions`), it first dispatches the planner, prints the plan, and waits for the publisher's Approve (notes re-plan, Stop leaves the slice pending). Then it dispatches one sub-agent per pending slice; each sub-agent reads the slice + frozen prompt (+ the approved plan for planned slices), authors prose, and writes a JSON result file to `build/.run/<timestamp>/results/`. Then, for every slice whose transformer has an entry in the manifest's `edit` map (currently `append-sessions`), it runs the edit loop: an editor sub-agent reads the chronicle, the plan, the previous critique, and the draft first, writes its verdict, and only then reads the log (`accept`/`revise`/`redraft` with quoted notes, lowered but never raised after the log); on `revise` the author revises its own draft in place, on `redraft` it starts over from the plan, for up to `max_rounds` rounds. Then, for every slice whose transformer has an entry in the manifest's `verify` map (currently `append-sessions`), it dispatches an independent verify sub-agent that fact-checks the settled draft against the slice's canonical facts and overwrites the result with the final entry. Then it prints the finished entry and waits for the publisher's Publish (notes revise and re-verify, Stop holds the entry). Only then does apply run — so a session is planned, edited, verified and signed off in the same build it is authored.

Pipeline (`apply` step):
1. Validate each result file against its JSON Schema.
2. Apply results to authored sections; bump `site.refreshed_through_session` on full refresh-pass success.
3. Run `build/render.py`.

## Tests

`.venv/bin/pytest tests/` runs the test suite — covers validators, key matching, computation formulas, slice builders, and bestiary lookup.

`build/paths.py` honors five env vars for test isolation: `BUILD_DATA_DIR`, `BUILD_AUTHORED_DIR`, `BUILD_RUN_ROOT`, `BUILD_PROMPTS_DIR`, `BUILD_TOA_ADVENTURE`. `tests/test_slices.py` monkeypatches `BUILD_AUTHORED_DIR` to point at a fixture copy under `tmp_path`. The `staged_env` fixture in `tests/conftest.py` points `BUILD_PROMPTS_DIR` at a copy of `.claude/prompts/` with a stand-in in place of the gitignored `publisher-notes.md`, so the `prepare` and `apply` tests pass on a fresh clone and in CI, where the publisher's notes do not exist.

End-to-end verification: run the three-step build (or just `build/render.py` to re-render without authoring) and visually check the rendered page via the local preview server.

## Skills available in this repo

- **`bestiarylookup`** (`.claude/skills/bestiarylookup/`) — looks up a creature in 5etools data and returns its stats (type, CR, source, URL). Consulted by `render.py` when rendering the "Kinds Slain" trial card.
- **`chronicle-review`** (`.claude/skills/chronicle-review/`) — not a skill but a Claude Code plugin of function hooks, auto-loaded from this folder. It registers the tool `mcp__chronicle-review__review`, which `/build-prose` calls at its two stops: it opens a terminal pane showing numbered lines (the plan's bullets, or the entry one sentence per line), lets the publisher attach a note to any line, and on Approve / Send back / Stop writes `{verdict, notes:[{line, quote, note}]}` to the given `notes_path` and sends a prompt naming the verdict so the skill's turn resumes. A hook has a 10s budget, so the tool returns at once rather than waiting. Opening it again keeps notes already saved. Do not edit it while a pane is open: a reload redraws the pane.

## External dependencies

- **5etools source data**: `.claude/ext/5etools-src` must symlink to a local `5etools-src` checkout (gitignored). Required by `bestiarylookup` and by `build/reference.py` for creature descriptions. On a fresh clone:
  ```bash
  ln -s /path/to/5etools-src .claude/ext/5etools-src
  ```
- **Module text**: `.claude/ext/dnd-toa` should symlink to the local `dnd-toa` checkout (gitignored), which holds the Tomb of Annihilation module as 5etools JSON at `data/5etools/adventure-toa.json`. `build/reference.py` reads it to hand the Chronicle writer the module's own description of the places a session visits. Optional: without it the writer gets no module text.
  ```bash
  ln -s /path/to/dnd-toa .claude/ext/dnd-toa
  ```
  See `.claude/ext/README.md` for details.

## Gotchas

- `site/index.html` ends with an inline `<script>` block (tab switcher + Other-Dice tooltip IIFE). It's the only client-side logic on the page — don't delete it or the page breaks silently.
- Image filenames come from `data/party.json[i].image`, not the character `id` (e.g. Chumble's file is `chumble-crudluck.png`).
- The map source stays in `data/` (gitignored); only the re-encoded derivative in `site/images/` is committed. Dropping in a new annotated map does nothing until `python -m build map` (or any full build) re-encodes it — and `validate_map` fails the render outright if the derivative is missing. Commit `build/map-source.json` together with the derivative it describes; a record that disagrees with the committed JPEG just costs one needless re-encode, but a stale record paired with a new source would skip the rebuild and publish the wrong map.
- After re-encoding the map, hard-refresh the preview (Ctrl+Shift+R). The filename never changes and `python3 -m http.server` sends no `Cache-Control` or `ETag`, only `Last-Modified`, so browsers heuristically cache the ~12 MB JPEG for hours without revalidating and will keep showing the previous map.
- Templates use relative URLs (`styles.css`, `images/...`) — these resolve correctly only because `index.html`, `styles.css`, and `images/` all live together in `site/`. If you move any one of them, fix the others too.

## Privacy

`data/party.json` carries real player first names in the `player` field, dice-roll files carry real first names + last names or handles, and `data/session-log.json` narrative prose may reference real names. **None must appear on the rendered site.** All three source files are gitignored. Last names exist nowhere else in the repo: `build/dice-players.json` keys on first-name (or handle) substrings, and `build/loaders.py:resolve_dice_player` does longest-pattern-first substring lookup so an upstream `"FirstName LastName"` resolves through a `"FirstName"` key without the file ever recording the last name.

### Git hooks (forbidden-name guard)

`.githooks/` contains versioned hooks (`pre-commit`, `commit-msg`, `pre-push`) that refuse to commit or push any change whose staged content, commit message, or pushed-commit content matches a known full-name pattern. The pattern lives in `.githooks/_forbidden-names.sh` as a regex over the players' first names: `\b(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z][[:alpha:]'-]+\b`. Bare first names are allowed (they appear unavoidably in test fixtures and party metadata); a first name immediately followed by a capitalized word — i.e. a likely full name, including hyphenated and apostrophe forms like `O'Brien` — is refused. Update the alternation when a new player joins.

Activate per clone with:

```bash
git config core.hooksPath .githooks
```

Bypass for a single commit/push (use sparingly): `--no-verify`.

## Preview locally

`python3 -m http.server 8765 --bind 127.0.0.1 --directory site` from the repo root, then open `http://127.0.0.1:8765/`. It's a static site; no other tooling needed.
