"""End-to-end render smoke test: fixture data through compute_all and
render_page. Any template/context drift under StrictUndefined fails here
instead of during a real build."""
import re
import subprocess
from pathlib import Path

from build import render, store

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "build" / "templates"


def _forbidden_names_regex() -> str:
    out = subprocess.run(
        ["bash", str(REPO_ROOT / ".githooks" / "_forbidden-names.sh")],
        capture_output=True, text=True, check=True)
    pattern = out.stdout.strip()
    pattern = pattern.replace("[[:space:]]", r"\s")
    # POSIX [:alpha:] has no direct Python re equivalent. A plain substring
    # replace only covers the isolated "[[:alpha:]]" bracket; when the class
    # is embedded alongside extra literals (e.g. "[[:alpha:]'-]"), swap the
    # whole bracket expression for an equivalent alternation instead, so the
    # extra literals stay unioned rather than accidentally negated.
    def _sub_alpha_class(m: "re.Match") -> str:
        extra = m.group(1)
        alt = r"[^\W\d_]"
        if extra:
            alt += f"|[{re.escape(extra)}]"
        return f"(?:{alt})"

    pattern = re.sub(r"\[\[:alpha:\]([^\]]*)\]", _sub_alpha_class, pattern)
    return pattern


def _render_html(staged_env, npcs: list | None = None, circles: list | None = None) -> str:
    """Load staged fixture data + authored store, run compute_all, and render
    the page, returning the rendered HTML text and the authored store.

    `npcs` and `circles` are appended to the authored NPC list and circle
    registry in memory only: the checked-in fixture keeps the NPC list empty
    so test_slices can see Azlund as un-authored.

    The `vex` party member is deliberately left out of
    tests/fixtures/sample_authored/characters.json — test_slices.py relies on
    that gap to exercise the append-characters slice builder (it asserts
    exactly one pending "new_pcs" slice, for "vex"). Templates index
    characters_authored[member.id] directly (no .get), so a real render needs
    every party member present. Rather than authoring vex in the checked-in
    fixture (which would silently zero out that slice-builder coverage), stub
    a minimal in-memory entry here, local to this render smoke test.
    """
    data = render.load_data(staged_env / "data")
    authored = store.load_authored()
    authored["characters"].append({
        "id": "vex", "epithet": "x", "reliquary_header": "x",
        "constellation_epithet": "x", "distinction_title": "x",
        "distinction_subtitle": "x", "distinction_detail": "x",
    })
    authored["npcs"].extend(npcs or [])
    authored["site"].setdefault("circles", []).extend(circles or [])
    context = render.compute_all(data, authored)
    out = staged_env / "index.html"
    render.render_page(context, TEMPLATES, out)
    return out.read_text(), authored


def test_render_page_smoke(staged_env):
    html, authored = _render_html(staged_env)
    assert len(html) > 10_000
    assert authored["site"]["page_title"] in html
    assert 'class="tab"' in html                       # tab nav rendered
    assert 'id="company"' in html                      # company panel rendered
    assert "</html>" in html


def test_rendered_html_contains_no_forbidden_names(staged_env):
    html, _ = _render_html(staged_env)
    assert not re.search(_forbidden_names_regex(), html)


def test_forbidden_names_regex_matches_full_name():
    # Constructed at runtime so the literal never appears in this file
    # (the pre-commit/pre-push hooks scan committed content for it).
    name = "Si" + "mon Wei" + "l"
    assert re.search(_forbidden_names_regex(), name)


def test_gm_cast_renders_circles_and_folds_the_unseen(staged_env):
    html, _ = _render_html(
        staged_env,
        circles=[{"key": "merchants", "title": "The Merchants"},
                 {"key": "villains", "title": "The Villains", "billing": "principal"}],
        npcs=[
            {"name": "Azlund", "epithet": "of the House of Healing", "circle": "merchants"},
            {"name": "Hollow Ghost", "epithet": "never named again", "circle": "merchants"},
            {"name": "Acererak", "epithet": "the lich", "circle": "villains"},
            {"name": "Tiryki", "epithet": "a racer", "circle": None},
        ])
    gm = html[html.index('id="gm"'):]
    # Principals first, then the circle with someone named lately; the
    # catch-all for the ungrouped last.
    assert gm.index('data-circle="villains"') < gm.index('data-circle="merchants"') < gm.index('data-circle="road"')
    # Azlund is named in the fixture log: a full entry, name then description.
    assert 'id="npc-azlund"' in gm
    assert '<span class="npc-name">Azlund</span>' in gm
    assert 'class="npc-desc">of the House of Healing' in gm
    # Acererak never is, but a principal is always in full.
    assert 'id="npc-acererak"' in gm
    # Hollow Ghost never is, so it sits folded behind a count line.
    assert 'class="cast-fold"' in gm
    assert "Hollow Ghost" in gm
    assert "and 1 more" in gm
    for retired in ("dramatis-grid", "cast-legend", "npc-sigil", "npc-against", "cast-rollcall"):
        assert retired not in gm


def test_map_tab_and_panel_render(staged_env):
    html, _ = _render_html(staged_env)
    assert 'id="tab-map"' in html
    assert 'id="map-viewport"' in html
    assert 'data-src="images/chult-map.jpg"' in html
    # The full-resolution JPEG must not be fetched until the tab is opened:
    # a bare src= would load it on page load. Leading space so the check does
    # not match the data-src attribute it is distinguishing itself from.
    assert ' src="images/chult-map.jpg"' not in html
