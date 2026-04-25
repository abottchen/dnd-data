# dnd-data

A static GitHub Pages site visualizing data from an ongoing D&D campaign.

## How it works

- `party.json`, `dicex-rolls-*.json`, and `session-log.json` are pushed here from upstream repos (gitignored from this repo's perspective).
- `build.py` reads those files plus the authored prose store, validates every authored entry, and renders `index.html` via Jinja2 templates.
- The committed `index.html` is a build artifact. GitHub Pages serves it directly from `main` (root); there is no CI build step.
- When new upstream data lands, pull `main`, run `build.py` (or invoke the `hydrate-ledger` skill in a Claude session for any prose authoring), commit, push.

See `CLAUDE.md` for architecture details, validation rules, and the hydration workflow.

## Files

- `index.html` — committed build artifact, served by GitHub Pages.
- `build.py` — deterministic Python renderer (validates authored entries, computes derived data, renders via Jinja2).
- `templates/` — Jinja2 partials for page structure.
- `authored/` — JSON prose store (`kills`, `sessions`, `chapters`, `npcs`, `characters`, `site`).
- `styles.css` — the design system.
- `tests/` — pytest suite (32 cases) covering validators, computation formulas, and bestiary lookup.
- `requirements.txt` — Python dependencies.
- `images/` — character portrait tokens, referenced by each entry's `image` field in `party.json`.
- `.githooks/` — versioned `pre-commit` / `commit-msg` / `pre-push` hooks that block forbidden-name leaks.
- `party.json`, `dicex-rolls-*.json`, `session-log.json` — upstream data files (gitignored).

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
git config core.hooksPath .githooks
```

## Local rebuild

```bash
.venv/bin/python build.py
```

The build aborts with `MISSING` / `MALFORMED` / `ORPHAN` errors before writing output if any authored entry is missing required fields. Fix the authored entry and re-run.

## Tests

```bash
.venv/bin/pytest tests/
```

## Local preview

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory .
```

Then open <http://127.0.0.1:8765/>.

## GitHub Pages

Configure once: **Settings → Pages → Source: Deploy from branch → Branch: `main` / `/ (root)`**.
