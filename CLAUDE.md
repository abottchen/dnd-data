# dnd-data

Static GitHub Pages site visualizing data from an ongoing D&D campaign.

## What's in this repo

- `index.html` — the rendered site.
- `styles.css` — the design system (palette, typography, components).
- `party.json` — current party snapshot, auto-pushed from an upstream character-sheet repo.
- `dicex-rolls-*.json` — dice-roll snapshots, auto-pushed from an upstream dice-roll repo.
- `session-log.json` — per-session narrative entries with real + in-universe dates, auto-pushed from an upstream repo.
- `images/` — character portrait tokens. Filenames match each entry's `image` field in `party.json` (e.g. `chumble-crudluck.png`). The GM's token is `GM.png`.

All three data files are **gitignored and read-only from this repo's perspective.** They are never modified here; if a value is missing (e.g. a backfilled in-universe date), that correction lives in the rendered `index.html`, never in the source.

## Build & deploy

GitHub Pages serves `index.html` straight from `main` / root. **There is no build step in CI.** The "build" is a local Claude session: pull `main`, invoke the `hydrate-ledger` skill, commit, push. GitHub Pages picks up the change.

Claude does **not** run inside the GitHub Action — no API key is configured and the user does not want one. All rebuilds happen locally.

Configure once: Settings → Pages → Source: Deploy from branch → Branch: `main` / `/ (root)`.

## Skills available in this repo

- **`hydrate-ledger`** (`.claude/skills/hydrate-ledger/`) — rebuilds `index.html` from `party.json`, dice-roll files, and `session-log.json`. Contains the design system, voice rules, computation formulas, Company page conventions, and scrubbing mappings. **The skill directory is gitignored** (it holds the real-name mapping) — it stays local-only, clone-specific. **Invoke this skill for any change to the site's contents, panels, or Company landing view.**
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
