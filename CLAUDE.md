# dnd-data

Static GitHub Pages site visualizing data from an ongoing D&D campaign.

## What's in this repo

- `index.html` — build artifact (committed); served directly by GitHub Pages.
- `styles.css` — the design system (palette, typography, components).
- `build.py` — deterministic renderer. Reads upstream data + `authored/*.json` + `templates/*.html`, validates all prose entries, and writes `index.html`.
- `authored/` — JSON prose store: `kills.json`, `sessions.json`, `chapters.json`, `npcs.json`, `characters.json`, `site.json`. The only writable surface for the hydrate-ledger skill.
- `templates/` — Jinja2 partials consumed by `build.py`. Locked; not modified during normal hydration.
- `requirements.txt`, `.venv/` — Python dependencies (Jinja2, etc.).
- `tests/` — pytest suite covering validators, key matching, computation formulas, and bestiary lookup.
- `party.json` — current party snapshot, auto-pushed from an upstream character-sheet repo.
- `dicex-rolls-*.json` — dice-roll snapshots, auto-pushed from an upstream dice-roll repo.
- `session-log.json` — per-session narrative entries with real + in-universe dates, auto-pushed from an upstream repo.
- `images/` — character portrait tokens. Filenames match each entry's `image` field in `party.json` (e.g. `chumble-crudluck.png`). The GM's token is `GM.png`.

The three upstream data files (`party.json`, `dicex-rolls-*.json`, `session-log.json`) are **gitignored and read-only from this repo's perspective.** They are never modified here.

## Build & deploy

Run `.venv/bin/python build.py` locally to regenerate `index.html`. The hydrate-ledger skill invokes this automatically.

Validation gates the render: any `MISSING` or `MALFORMED` authored entry causes `build.py` to exit 1 with an error message before writing output. Fix the authored entry and re-run.

GitHub Pages serves `index.html` straight from `main` / root. **There is no build step in CI.** The "build" is a local Claude session: pull `main`, invoke the `hydrate-ledger` skill, commit, push. GitHub Pages picks up the change.

Claude does **not** run inside the GitHub Action — no API key is configured and the user does not want one. All rebuilds happen locally.

Configure once: Settings → Pages → Source: Deploy from branch → Branch: `main` / `/ (root)`.

## Tests

`.venv/bin/pytest tests/` runs the test suite (27 tests covering validators, key matching, computation formulas, and bestiary lookup).

End-to-end verification: run `build.py` and visually check the rendered page via the local preview server.

## Skills available in this repo

- **`hydrate-ledger`** (`.claude/skills/hydrate-ledger/`) — authors new prose into `authored/*.json` and runs `build.py`. Invoked when upstream data files change, when new sessions / kills / NPCs / chapters need verse / summary / epithet / title authored, or when the user asks to "hydrate", "rebuild", "update the site", "refresh the data". **The skill directory is gitignored** (it holds the real-name mapping) — it stays local-only, clone-specific. **Invoke this skill for any change to the site's contents, panels, or Company landing view.**
- **`bestiarylookup`** (`.claude/skills/bestiarylookup/`) — looks up a creature in 5etools data and returns its stats (type, CR, source, URL). Used by `hydrate-ledger` for the "Kinds Slain" trial card.

## External dependencies

- **5etools source data**: `.claude/ext/5etools-src` must symlink to a local `5etools-src` checkout (gitignored). Required by `bestiarylookup`. On a fresh clone:
  ```bash
  ln -s /path/to/5etools-src .claude/ext/5etools-src
  ```
  See `.claude/ext/README.md` for details.

## Gotchas

- `index.html` ends with an inline `<script>` block (tab switcher + Other-Dice tooltip IIFE). It's the only client-side logic on the page — don't delete it or the page breaks silently.
- Image filenames come from `party.json[i].image`, not the character `id` (e.g. Chumble's file is `chumble-crudluck.png`).

## Privacy

`party.json` carries real player first names in the `player` field, dice-roll files carry real names or handles, and `session-log.json` narrative prose may reference real names. **None must appear on the rendered site.** All three source files are gitignored; the `hydrate-ledger` skill (also gitignored) holds the current name-to-character mapping and enforces scrubbing on every hydration.

## Preview locally

`python3 -m http.server 8765 --bind 127.0.0.1 --directory .` from the repo root, then open `http://127.0.0.1:8765/`. It's a static site; no other tooling needed.
