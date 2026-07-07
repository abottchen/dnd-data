#!/usr/bin/env python3
"""render.py — render index.html from data + authored store + templates.

Exit codes:
  0  render succeeded
  1  validation errors; nothing written
  2  internal error (template syntax, file read failure, bestiary miss)

The loaders/validators/bestiary/compute responsibilities live in sibling
modules (build/loaders.py, build/validators.py, build/bestiary.py,
build/compute.py); this module keeps the CLI, the Jinja environment,
load_data + validate_all orchestration, and a re-export shim so the public
surface stays importable through build.render (tests and build/slices.py rely
on it).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def load_data(data_dir: Path) -> dict:
    """Load upstream data files. Returns dict with party, dice_rolls, session_log."""
    data_dir = Path(data_dir)
    with (data_dir / "party.json").open() as f:
        party = json.load(f)
    with (data_dir / "session-log.json").open() as f:
        session_log = json.load(f)

    # XP log (optional — gitignored, dropped in by the GM after each session).
    # Cold-start safe: a fresh clone with no xp-log.json still renders.
    xp_path = data_dir / "xp-log.json"
    xp_log = json.loads(xp_path.read_text()) if xp_path.exists() else {"entries": []}

    dice_paths = sorted((data_dir / "dice").glob("dicex-rolls-*.json"))
    dice_rolls = [json.loads(p.read_text()) for p in dice_paths]

    # Build rolls_by_slug from dice files by mapping real-name players to site slugs.
    # Upstream shape: {"players": {uuid: {"name": str, "rolls": [event]}}, "exportedAt": str}.
    # Each event has: {"dice": [die...], "total": N, "notation": str, "timestamp": str}.
    # We normalize dice->rolls (to match compute_fortune's expected shape) and extract a date.
    dice_player_map = _load_dice_player_map()
    unmapped_players: set[str] = set()
    rolls_by_slug: dict[str, list[dict]] = {}
    # Successive dicex exports are not guaranteed disjoint — a later export can
    # restate rolls already present in an earlier one (e.g. the 2026-04-27 dump
    # re-includes the 2026-04-20/21 rolls). Concatenating blindly double-counts
    # those rolls, inflating every fortune stat (crit/fumble counts, totals,
    # avg/sd) and adding phantom dots to the d20 plots. A roll's timestamp is its
    # stable identity across exports, so we drop any event whose timestamp we've
    # already taken for that slug. Events with a blank timestamp are never
    # deduped (we can't prove identity) — they pass through untouched.
    seen_ts_by_slug: dict[str, set[str]] = {}
    for f in dice_rolls:
        if not isinstance(f, dict) or "players" not in f:
            continue
        for uuid, pdata in f.get("players", {}).items():
            if not isinstance(pdata, dict):
                continue
            upstream_name = pdata.get("name", "")
            slug = _resolve_dice_player(upstream_name, dice_player_map)
            if slug is None:
                unmapped_players.add(upstream_name)
                continue
            seen_ts = seen_ts_by_slug.setdefault(slug, set())
            for ev in pdata.get("rolls", []):
                ev2 = dict(ev)
                ev2["rolls"] = ev2.pop("dice", [])
                ts = ev2.get("timestamp", "")
                if ts:
                    if ts in seen_ts:
                        continue
                    seen_ts.add(ts)
                ev2["date"] = ts[:10] if ts else ""
                rolls_by_slug.setdefault(slug, []).append(ev2)

    # Normalize party: upstream may emit a bare list; wrap it for downstream validators.
    if isinstance(party, list):
        party = {"members": party}

    # Scrub real-name data from party members at the edge.
    # Upstream `id` may embed a real player first name (e.g. "simon-fighter"); the site slug
    # is derivable from the character `name` field's first word, lowercased. `player` carries
    # the real first name and must never reach downstream code, the authored store, or git.
    scrubbed_members = []
    for m in party.get("members", []):
        m = dict(m)
        if m.get("name"):
            m["id"] = m["name"].split()[0].lower()
        m.pop("player", None)
        scrubbed_members.append(m)
    party = dict(party)
    party["members"] = scrubbed_members

    # Normalize session-log entries to the shape downstream expects:
    #   session: integer ordinal from upstream `day` (the join key into authored
    #     sessions/chapters). The Roman label is computed at render time only.
    #   date: ISO YYYY-MM-DD from upstream `realDate` MM/DD/YYYY.
    #   iu_day, iu_month, iu_year: snake-case from camelCase iuDay/iuMonth/iuYear.
    #   chapter_marker: True when the upstream `text` contains an explicit chapter
    #     boundary marker authored by the user (e.g. "--- Chapter II ---" or
    #     "Chapter II begins."). First session implicitly opens Chapter I.
    # Session 1 lacks in-universe date fields upstream; they get backfilled here,
    # per the design rule: never edit upstream data, fill the gap at render time.
    normalized_entries = []
    for e in session_log.get("entries", []):
        ne = dict(e)
        if "session" not in ne and "day" in ne:
            try:
                ne["session"] = int(ne["day"])
            except (ValueError, TypeError):
                ne["session"] = ne["day"]
        if "date" not in ne and "realDate" in ne:
            ne["date"] = _mdy_to_iso(ne["realDate"])
        for camel, snake in (("iuDay", "iu_day"), ("iuMonth", "iu_month"), ("iuYear", "iu_year")):
            if camel in ne and snake not in ne:
                ne[snake] = ne[camel]
        # Backfill Session 1's in-universe date (absent upstream).
        if ne.get("session") == 1:
            ne.setdefault("iu_day", "1")
            ne.setdefault("iu_month", "Kythorn")
            ne.setdefault("iu_year", "1494")
        text = ne.get("text", "")
        if _has_chapter_marker(text):
            ne["chapter_marker"] = True
        normalized_entries.append(ne)

    # The refresh marker (site.refreshed_through_session) and every marker
    # gate in build/slices.py treat entry position as session id. That is
    # only sound while entry i IS session i — fail loudly if the log ever
    # gains an out-of-order / inserted entry so the assumption is revisited
    # deliberately instead of silently mis-scoping every refresh pass.
    for i, ne in enumerate(normalized_entries, start=1):
        if ne.get("session") != i:
            raise ValueError(
                f"session ordinal mismatch: entry {i} carries session "
                f"{ne.get('session')!r}; the refresh marker requires entry i == session i"
            )

    session_log = dict(session_log)
    session_log["entries"] = normalized_entries

    return {
        "party": party,
        "dice_rolls": dice_rolls,  # raw file contents; downstream should prefer rolls_by_slug
        "rolls_by_slug": rolls_by_slug,
        "unmapped_players": sorted(unmapped_players),
        "session_log": session_log,
        "xp_log": xp_log,
    }

def validate_all(data: dict, authored: dict, images_dir: Path, fact_pack: dict | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_kills(data["party"], authored["kills"]))
    errors.extend(validate_sessions(data["session_log"], authored["sessions"]))
    errors.extend(validate_chapters(data["session_log"], authored["chapters"]))
    npcs = collect_npcs_from_log(data["session_log"], authored["site"])
    errors.extend(validate_npcs(npcs, authored["npcs"]))
    errors.extend(validate_characters(data["party"], authored["characters"]))
    errors.extend(validate_distinction_uniqueness(authored["characters"]))
    if fact_pack is None:
        trials = compute_trials(data["party"])
        member_ids = [m["id"] for m in data["party"].get("members", [])]
        fortune_by_char = {cid: compute_fortune(data["rolls_by_slug"].get(cid, []))
                           for cid in member_ids}
        constellation = compute_constellation(data["party"], fortune_by_char, trials)
        fact_pack = compute_fact_pack(data["party"], trials, fortune_by_char,
                                      constellation, data["session_log"])
    errors.extend(validate_distinction_basis(authored["characters"], fact_pack))
    errors.extend(validate_site(authored["site"], len(data["session_log"].get("entries", []))))
    errors.extend(validate_portraits(data["party"], images_dir))
    errors.extend(validate_dice_player_mapping(data.get("unmapped_players", [])))
    return errors

def render_page(context: dict, templates_dir: Path, out_path: Path) -> None:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        autoescape=True,
        keep_trailing_newline=True,
    )
    env.filters["roman"] = _to_roman
    env.filters["ability_mod"] = lambda score: (score - 10) // 2
    template = env.get_template("base.html")
    html = template.render(**context)
    out_path.write_text(html)

def main() -> int:
    parser = argparse.ArgumentParser(description="Render index.html.")
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"),
                        help="Directory containing party.json etc.")
    parser.add_argument("--out", default=str(REPO_ROOT / "site" / "index.html"),
                        help="Output HTML path.")
    args = parser.parse_args()

    print(f"render.py: starting (data_dir={args.data_dir})")
    data = load_data(Path(args.data_dir))
    authored = load_authored(BUILD_DIR)
    party_count = len(data['party']) if isinstance(data['party'], list) else len(data['party'].get('members', []))
    session_count = len(data['session_log'].get('entries', []))
    # Count actual dice events fed to the page (post-dedup, per-slug), not the
    # parsed-file dicts in data['dice_rolls'] — len() on those returns each
    # file's top-level key count, not an event tally.
    dice_count = sum(len(events) for events in data['rolls_by_slug'].values())
    print(f"render.py: loaded {party_count} party members, "
          f"{dice_count} dice events, "
          f"{session_count} session entries")
    print(f"render.py: authored kills={len(authored['kills'])} sessions={len(authored['sessions'])} "
          f"npcs={len(authored['npcs'])} chapters={len(authored['chapters'])}")
    images_dir = Path(args.out).parent / "images"
    # Build the distinction fact pack once and hand it to validate_all so the
    # basis check doesn't recompute trials/fortune/constellation internally.
    trials = compute_trials(data["party"])
    member_ids = [m["id"] for m in data["party"].get("members", [])]
    fortune_by_char = {cid: compute_fortune(data["rolls_by_slug"].get(cid, []))
                       for cid in member_ids}
    constellation = compute_constellation(data["party"], fortune_by_char, trials)
    fact_pack = compute_fact_pack(data["party"], trials, fortune_by_char,
                                  constellation, data["session_log"])
    errors = validate_all(data, authored, images_dir, fact_pack=fact_pack)
    if errors:
        print(f"render.py: {len(errors)} validation error(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("render.py: validation passed")

    templates_dir = BUILD_DIR / "templates"
    base_template = templates_dir / "base.html"
    if not base_template.exists():
        print(f"render.py: no {base_template} yet; skipping render (compute only).")
        return 0

    try:
        context = compute_all(data, authored)
        render_page(context, templates_dir, Path(args.out))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"render.py: render failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"render.py: rendered {args.out}")
    return 0

# Re-exports: the public surface predates the loaders/validators/bestiary/
# compute split; tests and slices.py import through build.render. Absolute
# imports (not relative) so `python build/render.py` still works as a script
# (REPO_ROOT is on sys.path above). load_data/validate_all above resolve the
# imported names at call time, so a bottom-of-module block is sufficient.
from build.bestiary import (BESTIARY_GLOB, CUSTOM_CREATURE_TOKENS,  # noqa: F401,E402
                            CUSTOM_NPC_STATBLOCKS, XP_BY_CR, bestiary_lookup,
                            xp_for_cr, _creature_token_url, _kill_cr, _kill_xp,
                            _name_to_token_name)
from build.compute import (SKILL_DISPLAY, compute_all, compute_ascent,  # noqa: F401,E402
                           compute_best_skill, compute_bestiary,
                           compute_chronicle, compute_company_ledger,
                           compute_constellation, compute_cr_label,
                           compute_d20_histogram, compute_distinctions,
                           compute_fact_pack, compute_fortune, compute_other_dice,
                           compute_party_d20_max, compute_patron_die,
                           compute_radar, compute_reliquary,
                           compute_sessions_chart, compute_trials,
                           _compute_header_eyebrow, _compute_party_top_xp,
                           _level_for_xp, _next_threshold, _short_date, _to_roman)
from build.loaders import (load_authored, load_character_pronouns,  # noqa: F401,E402
                           load_dice_player_map, resolve_dice_player,
                           _has_chapter_marker, _mdy_to_iso)
from build.validators import (KIND_MALFORMED, KIND_MISSING, KIND_ORPHAN,  # noqa: F401,E402
                              ValidationError, collect_npcs_from_log, kill_key,
                              validate_chapters, validate_characters,
                              validate_dice_player_mapping,
                              validate_distinction_basis,
                              validate_distinction_uniqueness, validate_kills,
                              validate_npcs, validate_portraits,
                              validate_sessions, validate_site)

# Back-compat aliases for the pre-split private names. load_data (above) calls
# these render-module globals, so a monkeypatch on render._load_dice_player_map
# still redirects load_data — preserving the test_loaders.py contract.
_load_dice_player_map = load_dice_player_map
_resolve_dice_player = resolve_dice_player

if __name__ == "__main__":
    sys.exit(main())
