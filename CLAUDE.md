# dnd-data

Static GitHub Pages site visualizing data from an ongoing D&D campaign.

## What's in this repo

- `site/` — the served artifact directory. Uploaded to GitHub Pages by `.github/workflows/deploy-pages.yml`.
  - `site/index.html` — build artifact (committed).
  - `site/styles.css` — the design system (palette, typography, components).
  - `site/images/` — character portrait tokens. Filenames match each entry's `image` field in `data/party.json` (e.g. `chumble-crudluck.png`). The GM's token is `GM.png`.
- `data/` — ingestion directory for upstream files (gitignored contents). Holds `party.json`, `dicex-rolls-*.json`, `session-log.json`, all auto-pushed from upstream repos. Read-only from this repo's perspective; never modified here.
  - `data/party.json` — current party snapshot, from the character-sheet repo.
  - `data/dicex-rolls-*.json` — dice-roll snapshots, from the dice-roll repo.
  - `data/session-log.json` — per-session narrative entries with real + in-universe dates, from the session-log repo.
- `build/` — the build orchestrator. Python package that authors prose into `build/authored/*.json` (via `claude -p`) and renders `site/index.html`. Entry point: `python -m build`.
  - `build/__main__.py` — orchestrator entry point. Drives the discovery pass, append pass, refresh pass, and final render.
  - `build/render.py` — deterministic renderer. Reads `data/` + `build/authored/*.json` + `build/templates/*.html` + `build/dice-players.json`, validates all prose entries, and writes `site/index.html`. Resolves its own paths via `BUILD_DIR = Path(__file__).resolve().parent` (for templates / authored / dice-players) and `REPO_ROOT = BUILD_DIR.parent` (for `data/`, `site/`, and `.claude/ext/` lookups like the bestiary glob).
  - `build/paths.py`, `store.py`, `slices.py`, `invoke.py`, `apply.py`, `build_loop.py` — orchestrator submodules (path resolution, authored-store I/O, per-category slice builders, `claude -p` invocation, returned-prose application, render-step subprocess wrapper).
  - `build/authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the orchestrator's apply step.
  - `build/templates/` — Jinja2 partials consumed by `build/render.py`. Locked; not modified by normal authoring. Reference assets via paths relative to `site/index.html` (e.g. `styles.css`, `images/...`).
  - `build/dice-players.json` — substring map (first-name or handle → site slug) used by `render.py:_resolve_dice_player`. Never records full real names.
- `.claude/prompts/` — paired prompt and schema files, one pair per transformer (`append-kills`, `append-sessions`, `append-chapters`, `append-npcs`, `append-characters`, `refresh-known-npcs`, `refresh-chapters`, `refresh-npcs`, `refresh-characters`, `refresh-road-ahead`, `refresh-intro-epithet`). Each prompt has YAML frontmatter declaring its preferred model.
- `requirements.txt`, `.venv/` — Python dependencies (Jinja2, etc.).
- `tests/` — pytest suite covering validators, key matching, computation formulas, slice builders, and bestiary lookup. `tests/conftest.py` adds the repo root to `sys.path` so tests can import `build.render`, `build.slices`, etc.
- `.github/workflows/deploy-pages.yml` — uploads `site/` as the Pages artifact on every push to `main`.

## Build & deploy

Run `.venv/bin/python -m build` to author new prose and rebuild `site/index.html`. The orchestrator runs `build/render.py` automatically once authoring completes. To rebuild without re-authoring, run `.venv/bin/python build/render.py` directly.

Validation gates the render: any `MISSING` or `MALFORMED` authored entry causes `build/render.py` to exit 1 with an error message before writing output. Fix the authored entry and re-run.

CLI flags for `python -m build`:
- `--skip-render` — author prose, but skip the final render step. Useful when iterating on authoring logic.
- `--no-refresh` — skip the refresh pass even when `latest_session > marker`.
- `--concurrency N` — parallel `claude -p` calls per pass (default 5).
- `--keep-temp` — preserve the per-run temp dir on success (default: removed on success, kept on failure).

To publish: pull `main`, run `python -m build`, commit, push. The deploy workflow uploads the committed `site/` directory to GitHub Pages — it does not invoke `build/render.py` or the orchestrator.

Configure once: Settings → Pages → Source: **GitHub Actions**.

## Orchestration

The `build` package authors new prose into `build/authored/*.json` and then runs `build/render.py`. Each transformer is a single non-interactive `claude -p` call: a system prompt from `.claude/prompts/<name>.md`, a slice JSON delivered on stdin, and a JSON Schema-validated response. The orchestrator is deterministic Python; the model's only job is to produce schema-conformant prose for one slice at a time.

Pipeline:
1. Load source data from `data/` + authored prose from `build/authored/`.
2. **Discovery pass** — when `latest_session > site.refreshed_through_session`, run `refresh-known-npcs` to extract any newly named NPCs from new session text and append them to `site.known_npcs`. Runs before the append pass so newly discovered names flow into per-NPC epithet authoring on the same build. Returns `no_change` or `rewrite`.
3. **Append pass** — for each category (`kills`, `sessions`, `chapters`, `npcs`, `characters`), the slice builder in `build/slices.py` computes a set difference between `data/` and `build/authored/` (keyed on `(character, date, creature, method)` for kills, `session` id for sessions, `name` for NPCs, etc.). One slice is emitted per missing entity, and one `claude -p` call is dispatched per slice. Deleting a single entry from an authored file causes that one entry to be re-authored on the next run; nothing else moves.
4. **Refresh pass** — when `latest_session > site.refreshed_through_session`, evaluate each `refresh-*` transformer (`chapters`, `npcs`, `characters`, `road-ahead`, `intro-epithet`); each returns `no_change` or `rewrite`.
5. Apply returns to authored sections; bump `site.refreshed_through_session` on full refresh-pass success.
6. Run `build/render.py`.

Per-slice invocation pattern (shell equivalent):

```bash
claude -p \
  --model <sonnet|opus> \
  --system-prompt-file .claude/prompts/<name>.md \
  --json-schema "$(cat .claude/prompts/<name>.schema.json)" \
  --output-format json \
  --max-budget-usd 1.00 \
  --disallowedTools "Bash Read Write Edit Glob Grep LS WebFetch WebSearch Task TodoWrite NotebookEdit NotebookRead ExitPlanMode" \
  --permission-mode plan \
  < <slice.json>
```

Tool denylist + plan mode close off all model agency: each transformer is purely "data in, prose out", with no exploration. The slice and stripped prompt body are persisted to a per-run temp dir for inspection on failure (preserved on partial failure; user removes manually after a clean run).

## Tests

`.venv/bin/pytest tests/` runs the test suite — covers validators, key matching, computation formulas, slice builders, and bestiary lookup.

`build/paths.py` honors three env vars for test isolation: `BUILD_DATA_DIR`, `BUILD_AUTHORED_DIR`, `BUILD_TEMP_DIR`. `tests/test_slices.py` monkeypatches `BUILD_AUTHORED_DIR` to point at a fixture copy under `tmp_path`.

End-to-end verification: run `python -m build` (or just `build/render.py`) and visually check the rendered page via the local preview server.

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

`data/party.json` carries real player first names in the `player` field, dice-roll files carry real first names + last names or handles, and `data/session-log.json` narrative prose may reference real names. **None must appear on the rendered site.** All three source files are gitignored. Last names exist nowhere else in the repo: `build/dice-players.json` keys on first-name (or handle) substrings, and `build/render.py:_resolve_dice_player` does longest-pattern-first substring lookup so an upstream `"FirstName LastName"` resolves through a `"FirstName"` key without the file ever recording the last name.

### Git hooks (forbidden-name guard)

`.githooks/` contains versioned hooks (`pre-commit`, `commit-msg`, `pre-push`) that refuse to commit or push any change whose staged content, commit message, or pushed-commit content matches a known full-name pattern. The pattern lives in `.githooks/_forbidden-names.sh` as a regex over the players' first names: `\b(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z][a-zA-Z'-]+\b`. Bare first names are allowed (they appear unavoidably in test fixtures and party metadata); a first name immediately followed by a capitalized word — i.e. a likely full name, including hyphenated and apostrophe forms like `O'Brien` — is refused. Update the alternation when a new player joins.

Activate per clone with:

```bash
git config core.hooksPath .githooks
```

Bypass for a single commit/push (use sparingly): `--no-verify`.

## Preview locally

`python3 -m http.server 8765 --bind 127.0.0.1 --directory site` from the repo root, then open `http://127.0.0.1:8765/`. It's a static site; no other tooling needed.
