# dnd-data

Static GitHub Pages site visualizing data from an ongoing D&D campaign.

## What's in this repo

- `site/` — the served artifact directory. Uploaded to GitHub Pages by `.github/workflows/deploy-pages.yml`.
  - `site/index.html` — build artifact (committed).
  - `site/styles.css` — the design system (palette, typography, components).
  - `site/images/` — character portrait tokens. Filenames match each entry's `image` field in `data/party.json` (e.g. `chumble-crudluck.png`). The GM's token is `GM.png`.
- `data/` — ingestion directory for source files (gitignored contents). Holds `party.json`, `session-log.json`, plus `dice/` and `inventory/` subdirectories. Files are dropped in manually from external sources; nothing in this repo writes to `data/`.
  - `data/party.json` — current party snapshot (character-sheet export).
  - `data/dice/dicex-rolls-*.json` — dice-roll snapshots (dice-roller export).
  - `data/inventory/obr-inv-backup-*.json` — Owlbear Rodeo inventory exports.
  - `data/session-log.json` — per-session narrative entries with real + in-universe dates.
- `build/` — the build orchestrator. Python package that prepares authoring slices, applies in-session results, and renders `site/index.html`. Entry point: `python -m build`.
  - `build/__main__.py` — orchestrator entry point. Subcommands: `prepare` (gather slices into a run dir) and `apply` (validate results, write authored JSON, render).
  - `build/render.py` — CLI + Jinja render layer. Loads `data/` (`load_data`, incl. the real-name privacy scrub) + `build/authored/*.json`, wires `validate_all` (fact pack built once in `main` and passed in), and renders `site/index.html` from `build/templates/*.html`. Keeps `BUILD_DIR = Path(__file__).resolve().parent` (templates / authored) and `REPO_ROOT = BUILD_DIR.parent` (`data/`, `site/`), plus a re-export shim (absolute `from build.…` imports so `python build/render.py` still runs as a script) so the pre-split public surface stays importable through `build.render` — tests and `build/slices.py` rely on it.
  - `build/loaders.py` — authored-store, PC-pronoun, and dice-player-map loading: `load_authored`, `load_character_pronouns`, `load_dice_player_map` / `resolve_dice_player` (longest-pattern-first substring resolve), plus the `_mdy_to_iso` / `_has_chapter_marker` session-log normalizers. Owns `BUILD_DIR` for `dice-players.json` / `character-pronouns.json`.
  - `build/validators.py` — `ValidationError` + every `validate_*` (kills, sessions, chapters, npcs, characters, portraits, site, dice-player mapping, distinction basis/uniqueness) and the `kill_key` / `collect_npcs_from_log` helpers.
  - `build/bestiary.py` — 5etools bestiary lookup (`bestiary_lookup`; the `BESTIARY_GLOB` under `.claude/ext/` is resolved from `build.paths.REPO_ROOT`) plus the CR→XP tables (`XP_BY_CR`, `xp_for_cr`, `_kill_cr` / `_kill_xp`).
  - `build/compute.py` — every `compute_*` (trials, fortune, radar / ascent / constellation geometry, chronicle, reliquary, …) and `compute_all`, which assembles the full template context. Imports `inventory` at module top: the old render↔inventory circular import is dissolved because `inventory` now imports the dice-map loader from `loaders`.
  - `build/paths.py`, `store.py`, `slices.py`, `registry.py`, `prepare.py`, `apply.py`, `apply_cli.py` — orchestrator submodules (path resolution, authored-store I/O, per-category slice builders, transformer registry, run-dir preparation, returned-prose application, manifest-driven apply + render).
  - `build/authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the orchestrator's apply step.
  - `build/templates/` — Jinja2 partials consumed by `build/render.py`. Locked; not modified by normal authoring. Reference assets via paths relative to `site/index.html` (e.g. `styles.css`, `images/...`).
  - `build/dice-players.json` — substring map (first-name or handle → site slug) used by `loaders.py:resolve_dice_player` (re-exported through `build.render` for back-compat). Never records full real names.
- `.claude/prompts/` — paired prompt and schema files, one pair per transformer (`append-kills`, `append-sessions`, `append-chapters`, `append-npcs`, `append-characters`, `refresh-known-npcs`, `refresh-chapters`, `refresh-npcs`, `refresh-characters`, `refresh-road-ahead`, `refresh-intro-epithet`). Each prompt has YAML frontmatter declaring its preferred model.
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
5. Write all pending slices + frozen prompts to `build/.run/<timestamp>/pending/`.

In-session (`/build-prose` skill): dispatches one sub-agent per pending slice; each sub-agent reads the slice + frozen prompt, authors prose, and writes a JSON result file to `build/.run/<timestamp>/results/`.

Pipeline (`apply` step):
1. Validate each result file against its JSON Schema.
2. Apply results to authored sections; bump `site.refreshed_through_session` on full refresh-pass success.
3. Run `build/render.py`.

## Tests

`.venv/bin/pytest tests/` runs the test suite — covers validators, key matching, computation formulas, slice builders, and bestiary lookup.

`build/paths.py` honors three env vars for test isolation: `BUILD_DATA_DIR`, `BUILD_AUTHORED_DIR`, `BUILD_RUN_ROOT`. `tests/test_slices.py` monkeypatches `BUILD_AUTHORED_DIR` to point at a fixture copy under `tmp_path`.

End-to-end verification: run the three-step build (or just `build/render.py` to re-render without authoring) and visually check the rendered page via the local preview server.

## Skills available in this repo

- **`bestiarylookup`** (`.claude/skills/bestiarylookup/`) — looks up a creature in 5etools data and returns its stats (type, CR, source, URL). Consulted by `render.py` when rendering the "Kinds Slain" trial card.

## External dependencies

- **5etools source data**: `.claude/ext/5etools-src` must symlink to a local `5etools-src` checkout (gitignored). Required by `bestiarylookup`. On a fresh clone:
  ```bash
  ln -s /path/to/5etools-src .claude/ext/5etools-src
  ```
  See `.claude/ext/README.md` for details.

## Gotchas

- `site/index.html` ends with an inline `<script>` block (tab switcher + Other-Dice tooltip IIFE). It's the only client-side logic on the page — don't delete it or the page breaks silently.
- Image filenames come from `data/party.json[i].image`, not the character `id` (e.g. Chumble's file is `chumble-crudluck.png`).
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
