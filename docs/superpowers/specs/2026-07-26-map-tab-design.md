# The Map tab — design

**Date:** 2026-07-26
**Status:** approved

Add a tab to the rendered site that displays the party's annotated player map
of Chult in a pan-and-zoom viewer, with a zoom ceiling deep enough to read
handwritten annotations at native pixel density.

## Source material

`data/chult-player-map.jpg` — 6445 × 8640 (55.7 MP), 17 MB JPEG. Dropped in
manually like every other file under `data/`, and gitignored along with the
rest of that directory. The served copy is a re-encoded derivative committed to
`site/images/`.

## Decisions

| Question | Decision |
|---|---|
| Image delivery | One full-resolution re-encode, deferred until the tab is first opened |
| Encoding | Pillow, run from inside the build package |
| Panel chrome | Slim in-voice header, then a viewer filling the remaining viewport height |
| Interactions | Wheel, drag, touch/pinch, double-click, keyboard, fullscreen |
| Tab name | "The Map", between The Chronicle and GM |

Rejected: a preview+full-res swap (extra moving part for a few seconds of first
paint), a downscaled derivative (defeats the deep-zoom requirement), and a tile
pyramid (~1000+ files and a tile engine for a single map).

## Asset pipeline

New module `build/mapimage.py`, exposing `prepare_map(force: bool = False) -> dict`.

It reads `data/chult-player-map.jpg` and writes `site/images/chult-map.jpg` at
native 6445 × 8640 with:

- `quality=80`, `progressive=True`, `optimize=True`
- `subsampling=0` (4:4:4) — no chroma subsampling, so colored annotation
  strokes and small handwriting keep their edges
- EXIF dropped (not passed through on save)

`pillow` is added to `requirements.txt`.

**Idempotency.** Re-encoding 55 megapixels is not free and most builds carry no
new map. `prepare_map` skips when the derivative exists and its mtime is at or
after the source's; `force=True` overrides. When the source is absent — a clone
with no `data/` — it skips quietly and leaves the committed derivative in place.

**Return value** — a dict the caller can report: `{"status": "rebuilt" |
"skipped" | "no-source", "src_bytes": int | None, "out_bytes": int | None}`.

**Size expectation.** Roughly 5–7 MB at these settings. If the actual output
lands materially above ~8 MB, report the number and step quality down rather
than silently changing the plan.

## Build integration

Two entry points, both in the existing orchestrator:

1. **Automatic** — `apply_cli.apply_run()` calls `prepare_map()` immediately
   before `_run_render()`, behind the same gate
   (`not skip_render and not pending and not rejected`). `/build-prose` already
   runs `python -m build apply <run-dir>`, so a build produces the map
   derivative and the rendered page together, ready to commit in one go. The
   summary dict gains a `map` key; `__main__._cmd_apply` prints it alongside
   the marker and render lines, e.g. `map: rebuilt (17.0 MB → 6.2 MB)` or
   `map: up to date`.
2. **Standalone** — `python -m build map [--force]`, a third subcommand beside
   `prepare` and `apply`, for re-encoding a freshly dropped map without an
   authoring pass.

`.claude/skills/build-prose/SKILL.md` step 8 changes only to list `map` among
the summary fields it surfaces. Its `allowed-tools` already permits
`python -m build apply *`, so no permission change is needed.

## Validation

`build/validators.py` gains `validate_map(images_dir: Path) -> list[ValidationError]`,
modeled on `validate_portraits`: if `chult-map.jpg` is not present in
`site/images/`, emit one `MISSING` error naming the file and the fix. Wired
into `validate_all` in `build/render.py`, so a missing map fails the render the
same way a missing portrait does.

## Authored prose

`build/authored/site.json` gains a `player_map` block:

```json
"player_map": {
  "image": "chult-map.jpg",
  "heading": "The Map",
  "subtitle": "The company's own chart of Chult &middot; marked as they walked it"
}
```

Hand-set, like `page_title` and `footnote` — no transformer, no slice, no
refresh pass. Both strings are authored text: changing the heading or subtitle
is an edit to `site.json` and a re-render, not a code change. The key is `player_map` rather than `map` so template access
cannot be confused with Jinja's `map` filter. The subtitle is static text the
author updates when a new annotated map is dropped in; it is not derived from
the session count, because the map's currency depends on when the JPEG was
exported, not on how many sessions have been logged.

## Markup

New partial `build/templates/_map.html`:

```
<article class="character" id="map" role="tabpanel" aria-labelledby="tab-map">
  header: heading + subtitle
  <div class="map-frame">
    <div class="map-viewport" tabindex="0" role="img" aria-label="...">
      <img class="map-image" data-src="images/chult-map.jpg" alt="" draggable="false">
      <div class="map-loading">unrolling the chart…</div>
    </div>
    <div class="map-controls"> + · ↺ · − · ⛶ </div>
  </div>
  <p class="map-hint">drag to pan · scroll to zoom · double-click to dive</p>
</article>
```

`build/templates/base.html` gains a nav entry between The Chronicle and GM,
with an inline compass glyph in the same style as the Chronicle's book icon,
and `{% include "_map.html" %}` in `<main>` in the matching position.

**Deferred load.** The `<img>` ships with `data-src`, not `src`. The first time
the `#map` panel activates, JS assigns `src`, and the placeholder is removed on
`load`. `loading="lazy"` alone is not reliable for an element inside a
`display: none` panel, and nothing should download for visitors who never open
the tab.

## Viewer

A new IIFE in `build/templates/_script.html` (the page's single inline script),
following the shape of `toa-browser`'s `setupPanZoom` and extending it.

The image is CSS-fitted to the frame (`max-width/max-height: 100%`), so
**scale 1 is fit-to-frame** and is the minimum. Pan is stored as a translate in
pixels and clamped to `±(scaled − viewport) / 2` per axis, snapping to 0 on any
axis where the scaled image is smaller than the viewport.

**Zoom ceiling.** Computed once the image loads, from its real dimensions:

```
maxScale = max(6, (img.naturalWidth / img.clientWidth) * 2)
```

At a typical desktop frame width this is roughly 14×, letting the viewer reach
twice native pixel density — well past `toa-browser`'s flat 5× cap, which is
the limitation this feature exists to remove.

**Interactions:**

- **Wheel** — zoom anchored at the cursor. `ctrl+wheel` (trackpad pinch, and
  browser page-zoom gesture) is intercepted the same way so a pinch on a laptop
  trackpad zooms the map rather than the page.
- **Drag** — pointer-based pan, `grab` / `grabbing` cursors.
- **Touch** — pointer events with a live pointer map: one pointer pans, two
  pointers pinch-zoom anchored at their midpoint.
- **Double-click / double-tap** — zoom 2× at the point; shift-double-click
  zooms back out by the same factor.
- **Keyboard**, when the viewport has focus — arrows pan (shift for a coarse
  step), `+`/`=` and `-` zoom about the center, `0` resets.
- **Fullscreen** — a control that calls `requestFullscreen()` on the frame;
  clamping and the fit basis are recomputed on `fullscreenchange` and `resize`.

Transforms are written as `translate3d(...) scale(...)` and applied inside a
`requestAnimationFrame` so a burst of wheel or pointermove events collapses to
one paint per frame. View state persists across tab switches.

## Styles

A new block in `site/styles.css` using the existing tokens (`--brass`,
`--paper`, `--rule`, `--ink-deep`): an inset frame in the established idiom, a
soft vignette over the map edges, control buttons matching the site's existing
button treatment, and the grab cursors. Frame height is
`calc(100vh - <header + tabs + panel header>)` with a `min-height` floor, so the
map gets the viewport without pushing the hint off screen.

The site sets `min-width: 1200px` on `html, body` and is desktop-first by
design; the map tab follows that convention rather than introducing a
responsive breakpoint. Touch support is for tablets in landscape and for
trackpad gestures, not for a phone layout.

## Tests

- `validate_map` — missing file yields exactly one `MISSING` error against the
  `map` category; present file yields none. Follows the existing
  `validate_portraits` test style with a `tmp_path` images dir.
- `prepare_map` skip logic — with a fabricated tiny source and derivative under
  a `tmp_path`, assert: newer derivative → `skipped`; older derivative →
  `rebuilt`; absent source → `no-source`; `force=True` → `rebuilt` regardless.
- The existing suite must stay green.

Manual verification: run the build, serve `site/` locally, and drive the tab in
a real browser — confirm the deferred load fires on first activation, fit-to-
frame on load, sharpness at maximum zoom, pan clamping at the edges, pinch,
double-click, keyboard, and fullscreen.

## Documentation

`CLAUDE.md` updates: the new tab and its partial, `build/mapimage.py` and the
`map` subcommand, the `pillow` dependency, `site/images/chult-map.jpg` as a
committed artifact, and the note that the 17 MB source stays gitignored under
`data/`.

## Known limitations

- First open of the tab downloads the full multi-megabyte file. There is a
  loading state, but it is a few seconds on a slow connection.
- Mobile browsers commonly subsample images this large during decode, so deep
  zoom on a phone or tablet may look softer than on desktop.
- Each map refresh adds several megabytes to git history permanently.
