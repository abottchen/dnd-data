# dnd-data

A static GitHub Pages site visualizing data from an ongoing D&D campaign.

## How it works

- `party.json` is pushed here by the character-sheet repo.
- `dicex-rolls-*.json` files are pushed by the dice-roll repo.
- When new data lands, pull `main` locally, run Claude to rehydrate `index.html` against the latest data, commit, push. There is no build step.
- GitHub Pages serves `index.html` from `main` (root).

See `CLAUDE.md` for the hydration workflow and design-system rules.

## Files

- `index.html` — the rendered page.
- `styles.css` — the design system.
- `party.json` — current party snapshot (pushed from upstream).
- `dicex-rolls-*.json` — dice-roll snapshots (pushed from upstream).
- `images/` — character portrait tokens, referenced by each entry's `image` field in `party.json`.

## GitHub Pages

Configure once: **Settings → Pages → Source: Deploy from branch → Branch: `main` / `/ (root)`**.
