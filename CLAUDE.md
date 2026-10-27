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
  - `build/validators.py` — `ValidationError` + every `validate_*` (kills, sessions, chapters, npcs, circles, characters, portraits, site, dice-player mapping, distinction basis/uniqueness) and the `kill_key` / `collect_npcs_from_log` helpers.
  - `build/bestiary.py` — 5etools bestiary lookup (`bestiary_lookup`; the `BESTIARY_GLOB` under `.claude/ext/` is resolved from `build.paths.REPO_ROOT`) plus the CR→XP tables (`XP_BY_CR`, `xp_for_cr`, `_kill_cr` / `_kill_xp`).
  - `build/compute.py` — every `compute_*` (trials, fortune, radar / ascent / constellation geometry, chronicle, reliquary, cast, …) and `compute_all`, which assembles the full template context. Imports `inventory` at module top: the old render↔inventory circular import is dissolved because `inventory` now imports the dice-map loader from `loaders`.
  - `build/paths.py`, `store.py`, `slices.py`, `registry.py`, `prepare.py`, `apply.py`, `apply_cli.py` — orchestrator submodules (path resolution, authored-store I/O, per-category slice builders, transformer registry, run-dir preparation, returned-prose application, manifest-driven apply + render).
  - `build/authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the orchestrator's apply step.
    - `site.json` → `circles`: the NPC-circle registry, `[{"key", "title", "billing"?}]`; `billing` is `principal` or `aside`, keys are slugs and stable once published.
    - `npcs.json` → `circle`: required on every entry, one registry key or `null`.
    - `site.json` → `not_npcs`: `[{"name", "why"}]`, recurring names that are not NPCs (a familiar, a construct the party owns); with the party roster it is the exclusion set that apply and `validate_not_npcs` enforce.
  - `build/mapimage.py` — re-encodes `data/chult-player-map.jpg` into `site/images/chult-map.jpg` at full resolution (`prepare_map`). Called by `apply` just before the render, and available standalone as `python -m build map [--force]`. A no-op unless the source's SHA-256 differs from the one recorded in `build/map-source.json`, so ordinary builds pay nothing.
  - `build/map-source.json` — committed record of the SHA-256 `site/images/chult-map.jpg` was last built from, plus its byte size. This is the map's staleness signal; mtimes are deliberately not consulted, because the derivative is git-tracked and git stamps working-tree files at checkout time, so a pull or stash after dropping in a new map would leave the stale derivative looking newer than its own source. Delete it to force a one-off rebuild.
  - `build/templates/` — Jinja2 partials consumed by `build/render.py`. Locked; not modified by normal authoring. Reference assets via paths relative to `site/index.html` (e.g. `styles.css`, `images/...`). `_map.html` is the Map tab; its pan/zoom viewer is the last IIFE in `_script.html`.
  - `build/dice-players.json` — substring map (first-name or handle → site slug) used by `loaders.py:resolve_dice_player` (re-exported through `build.render` for back-compat). Never records full real names.
- `.claude/prompts/` — paired prompt and schema files, one pair per transformer (`append-kills`, `append-chapters`, `append-npcs`, `append-characters`, `append-sworn`, `refresh-known-npcs`, `refresh-chapters`, `refresh-npcs`, `refresh-characters`, `refresh-road-ahead`, `refresh-intro-epithet`, `refresh-ascent-read`, `refresh-archetype-inscription`). Each prompt has YAML frontmatter declaring its preferred model. A line of the form `{{include: name.md}}` is replaced with that file's body when `prepare` freezes the prompt, so the run dir records exactly what the agents read.
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
2. **Discovery pass** — when `latest_session > site.refreshed_through_session`, run `refresh-known-npcs` to extract any newly named NPCs from new session text and append them to `site.known_npcs`. Runs before the append pass so newly discovered names flow into per-NPC epithet authoring on the same build. Returns `no_change` or `rewrite`. It also proposes new circles for the registry, and never a name from the party roster or `site.not_npcs`; apply enforces both.
3. **Append pass** — for each category (`kills`, `chapters`, `npcs`, `characters`, `sworn`), the slice builder in `build/slices.py` computes a set difference between `data/` and `build/authored/` (keyed on `(character, date, creature, method)` for kills, `name` for NPCs, etc.). One slice is emitted per missing entity. Deleting a single entry from an authored file causes that one entry to be re-authored on the next run; nothing else moves. The `append-npcs` result places the NPC in `circle` with a registry key or null.
4. **Refresh pass** — when `latest_session > site.refreshed_through_session`, evaluate each `refresh-*` transformer (`chapters`, `npcs`, `characters`, `road-ahead`, `intro-epithet`); each returns `no_change` or `rewrite`. A `refresh-npcs` rewrite returns `circle`, so a refresh can move an NPC.
5. Write all pending slices + frozen prompts to `build/.run/<timestamp>/pending/`.

In-session (`/build-prose` skill): it dispatches one sub-agent per pending slice; each sub-agent reads the slice + frozen prompt, authors prose, and writes a JSON result file to `build/.run/<timestamp>/results/`. Then apply runs.

Pipeline (`apply` step):
1. Validate each result file against its JSON Schema.
2. Apply results to authored sections; bump `site.refreshed_through_session` on full refresh-pass success. An NPC's `circle` is checked against the registry; registry proposals merge append-only (key, title, billing) and file their already-authored members, and the pipeline never renames or removes a circle.
3. Run `build/render.py`.

### NPC circles

The GM tab's cast is grouped by circle. The authoring rules live in the three NPC prompts (`append-npcs`, `refresh-npcs`, `refresh-known-npcs`); `validate_circles` and `validate_not_npcs` gate the render; the renderer is `compute.compute_cast` → `_gm.html`; the design record is `docs/superpowers/specs/2026-10-26-npc-circles-design.md`.

## Chronicle session entries

The Chronicle's per-session entries are not authored by any transformer or by `/build-prose`. Whatever produces them must meet this interface, which the renderer and validators enforce:

- **Where:** `build/authored/sessions.json`, a JSON list with one object per session in `data/session-log.json`. Order doesn't matter (render looks entries up by `session`). It's public and committed, so the privacy rules below apply to every string in it.
- **Shape:**
  ```json
  {"session": 31, "date": "2026-10-25", "title": "…", "summary": "…", "silent_roll": ["…", "…"]}
  ```
  - `session` (int): the session-log entry's `session` id. This is the key.
  - `date` (`YYYY-MM-DD`): the session-log entry's real date. Stored for the record only; render takes the date from the log.
  - `title` (string, non-blank): the session's heading in the Chronicle tab, and in the landing hero / "Previously" list when it's recent.
  - `summary` (string, non-blank): the entry's prose. Plain text; a blank line (`\n\n`) is the only paragraph break, and it is HTML-escaped at render (`render._paragraphs`). The latest session's summary also appears in the landing hero (`_hero.html`).
  - `silent_roll` (list of strings, required, may be empty): rendered after the summary as a `<ul class="chronicle-session-quiet">` list, one `<li>` per string, inserted with `| safe` (not escaped). Escape `&` and `<` yourself.
- **Validation** (`validators.validate_sessions`, run by `render.py`, gates the render): a log session with no entry is `MISSING`; an entry whose `session` isn't in the log is `ORPHAN`; a blank `title` / `summary` or an absent `silent_roll` is `MALFORMED`. Until something writes an entry for a newly logged session, `apply` and `render.py` exit 1.
- **Computed, not authored:** the session number label, in-universe date, real-date label, kill count and kill pips in each session header all come from `data/` (`compute.compute_chronicle` / `_render_session`). An entry carries only the fields above.
- **Plugging in:** `apply` is the orchestrator's only writer of `build/authored/`. To produce entries through the existing pipeline, add a transformer: a prompt + schema pair in `.claude/prompts/`, a slice builder in `build/slices.py` (signature `(data, authored) -> [(key, slice_data)]`, returning one slice per log session missing from `authored["sessions"]`), an apply function in `build/apply.py` (signature `(authored, key, slice_data, output)`, appending to `authored["sessions"]`), and an entry in `build/registry.py`. `store.persist` already writes the `sessions` section. `prepare`, `/build-prose` and `apply` then run it with no other changes. Anything outside that pipeline has to leave `sessions.json` in the same shape.
- **Source material:** `data/session-log.json` entries, normalized by `render.load_data` to `session`, `date`, `text` (the session's log), `iu_day` / `iu_month` / `iu_year`, and `chapter_marker`; `slices.iu_date(entry)` formats the in-universe date. `data/party.json` members carry `kills` (`date`, `creature`, `method`) that match sessions by `date`. Earlier entries in `sessions.json` are the Chronicle as published so far.

## Tests

`.venv/bin/pytest tests/` runs the test suite — covers validators, key matching, computation formulas, slice builders, and bestiary lookup.

`build/paths.py` honors four env vars for test isolation: `BUILD_DATA_DIR`, `BUILD_AUTHORED_DIR`, `BUILD_RUN_ROOT`, `BUILD_PROMPTS_DIR`. `tests/test_slices.py` monkeypatches `BUILD_AUTHORED_DIR` to point at a fixture copy under `tmp_path`. The `staged_env` fixture in `tests/conftest.py` points `BUILD_PROMPTS_DIR` at a copy of `.claude/prompts/`.

End-to-end verification: run the three-step build (or just `build/render.py` to re-render without authoring) and visually check the rendered page via the local preview server.

## Skills available in this repo

- **`bestiarylookup`** (`.claude/skills/bestiarylookup/`) — looks up a creature in 5etools data and returns its stats (type, CR, source, URL). Consulted by `render.py` when rendering the "Kinds Slain" trial card.

## External dependencies

- **5etools source data**: `.claude/ext/5etools-src` must symlink to a local `5etools-src` checkout (gitignored). Required by `bestiarylookup` and `build/bestiary.py`. On a fresh clone:
  ```bash
  ln -s /path/to/5etools-src .claude/ext/5etools-src
  ```
- **Module text**: `.claude/ext/dnd-toa` may symlink to the local `dnd-toa` checkout (gitignored), which holds the Tomb of Annihilation module as 5etools JSON at `data/5etools/adventure-toa.json`. Optional; nothing in the build reads it at present.
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
