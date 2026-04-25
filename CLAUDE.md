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
- `build/` — the build script and its inputs.
  - `build/build.py` — deterministic renderer. Reads `data/` + `build/authored/*.json` + `build/templates/*.html`, validates all prose entries, and writes `site/index.html`. Resolves its own paths via `BUILD_DIR = Path(__file__).resolve().parent` (for templates / authored) and `REPO_ROOT = BUILD_DIR.parent` (for `data/`, `site/`, and `.claude/` lookups like the bestiary glob and the dice-player map).
  - `build/authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the hydrate-ledger skill.
  - `build/templates/` — Jinja2 partials consumed by `build/build.py`. Locked; not modified during normal hydration. Reference assets via paths relative to `site/index.html` (e.g. `styles.css`, `images/...`).
- `requirements.txt`, `.venv/` — Python dependencies (Jinja2, etc.).
- `tests/` — pytest suite covering validators, key matching, computation formulas, and bestiary lookup. `tests/conftest.py` adds `build/` to `sys.path` so tests can `import build`.
- `.github/workflows/deploy-pages.yml` — uploads `site/` as the Pages artifact on every push to `main`.

## Build & deploy

Run `.venv/bin/python build/build.py` locally to regenerate `site/index.html`. The hydrate-ledger skill invokes this automatically.

Validation gates the render: any `MISSING` or `MALFORMED` authored entry causes `build/build.py` to exit 1 with an error message before writing output. Fix the authored entry and re-run.

The "build" is a local Claude session: pull `main`, invoke the `hydrate-ledger` skill, commit, push. The deploy workflow then uploads the already-committed `site/` directory to GitHub Pages — it does not invoke `build/build.py`.

Configure once: Settings → Pages → Source: **GitHub Actions**.

## Tests

`.venv/bin/pytest tests/` runs the test suite (27 tests covering validators, key matching, computation formulas, and bestiary lookup).

End-to-end verification: run `build/build.py` and visually check the rendered page via the local preview server.

## Skills available in this repo

- **`hydrate-ledger`** (`.claude/skills/hydrate-ledger/`) — authors new prose into `build/authored/*.json` and runs `build/build.py`. Invoked when upstream data files change, when new sessions / kills / NPCs / chapters need verse / summary / epithet / title authored, or when the user asks to "hydrate", "rebuild", "update the site", "refresh the data". **Invoke this skill for any change to the site's contents, panels, or Company landing view.**
- **`bestiarylookup`** (`.claude/skills/bestiarylookup/`) — looks up a creature in 5etools data and returns its stats (type, CR, source, URL). Used by `hydrate-ledger` for the "Kinds Slain" trial card.

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

`data/party.json` carries real player first names in the `player` field, dice-roll files carry real first names + last names or handles, and `data/session-log.json` narrative prose may reference real names. **None must appear on the rendered site.** All three source files are gitignored. Last names exist nowhere else in the repo: the `hydrate-ledger` skill's `dice-players.json` keys on first-name (or handle) substrings, and `build/build.py:_resolve_dice_player` does longest-pattern-first substring lookup so an upstream `"FirstName LastName"` resolves through a `"FirstName"` key without the file ever recording the last name.

### Git hooks (forbidden-name guard)

`.githooks/` contains versioned hooks (`pre-commit`, `commit-msg`, `pre-push`) that refuse to commit or push any change whose staged content, commit message, or pushed-commit content matches a known full-name pattern. The pattern lives in `.githooks/_forbidden-names.sh` as a regex over the players' first names: `\b(Simon|Steve|Quinn|Mike|David)[[:space:]]+[A-Z][a-zA-Z'-]+\b`. Bare first names are allowed (they appear unavoidably in test fixtures and party metadata); a first name immediately followed by a capitalized word — i.e. a likely full name, including hyphenated and apostrophe forms like `O'Brien` — is refused. Update the alternation when a new player joins.

Activate per clone with:

```bash
git config core.hooksPath .githooks
```

Bypass for a single commit/push (use sparingly): `--no-verify`.

## Preview locally

`python3 -m http.server 8765 --bind 127.0.0.1 --directory site` from the repo root, then open `http://127.0.0.1:8765/`. It's a static site; no other tooling needed.
