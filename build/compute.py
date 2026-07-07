"""compute.py — deterministic view-model computations.

Every compute_* function that turns source data + authored prose into the
template context, plus compute_all which assembles the full render context.
Geometry (radar, ascent, constellation, other-dice) is computed server-side so
the templates emit static SVG and the client script only animates.
"""
from __future__ import annotations
import math
from collections import Counter
from statistics import pstdev, median
from typing import Optional

from . import inventory
from .paths import REPO_ROOT
from .validators import kill_key
from .bestiary import (bestiary_lookup, XP_BY_CR, _kill_xp, _kill_cr,
                       CUSTOM_CREATURE_TOKENS)

def compute_trials(party: dict) -> dict:
    """Return per-character trials dict + party-wide aggregates needed by templates."""
    members = party.get("members", [])
    per_char: dict[str, dict] = {}

    for m in members:
        cid = m["id"]
        kills = m.get("kills", [])
        xp = sum(_kill_xp(k["creature"]) for k in kills)
        kill_count = len(kills)

        # Means of Ending: most common method; tiebreak highest CR; then alphabetical.
        method_counter = Counter(k["method"] for k in kills)
        if method_counter:
            top_n = method_counter.most_common(1)[0][1]
            tied = [m_ for m_, n in method_counter.items() if n == top_n]
            if len(tied) == 1:
                means = tied[0]
            else:
                # Tiebreak by max CR among kills using that method
                def max_xp_for_method(method):
                    crs = [_kill_cr(k["creature"]) for k in kills if k["method"] == method]
                    return max((XP_BY_CR.get(c, 0) for c in crs), default=0)
                tied.sort(key=lambda mm: (-max_xp_for_method(mm), mm.lower()))
                means = tied[0]
            means_n = top_n
        else:
            means = "—"
            means_n = 0

        # Kinds Slain: distinct creature types
        type_counter: Counter = Counter()
        for k in kills:
            info = bestiary_lookup(k["creature"])
            if info:
                type_counter[info["type"]] += 1
        kinds = sorted(type_counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))

        per_char[cid] = {
            "xp": xp,
            "kill_count": kill_count,
            "means": means,
            "means_n": means_n,
            "kinds": [{"type": t, "count": c} for t, c in kinds],
            "kinds_count": len(kinds),
        }

    party_xp = sum(c["xp"] for c in per_char.values())
    party_kills = sum(c["kill_count"] for c in per_char.values())

    for cid, c in per_char.items():
        c["xp_pct"] = round(c["xp"] / party_xp * 100) if party_xp else 0
        c["kill_pct"] = round(c["kill_count"] / party_kills * 100) if party_kills else 0

    return {
        "per_char": per_char,
        "party_xp": party_xp,
        "party_kills": party_kills,
    }

def _date_to_session_index(session_log: dict) -> dict:
    """Map each session date to its 0-based campaign position."""
    return {e["date"]: i for i, e in enumerate(session_log.get("entries", []))}


def compute_fact_pack(party: dict, trials: dict, fortune_by_char: dict,
                      constellation: dict, session_log: dict) -> dict:
    """Per non-GM PC, a flat dict of verifiable 'atoms' a distinction can rest
    on. Reuses already-computed trials/fortune/constellation; only biggest-kill
    XP reaches back to the bestiary (via _kill_xp)."""
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    date_to_idx = _date_to_session_index(session_log)
    per_char = trials["per_char"]

    star_by_id = {s["id"]: s for s in constellation.get("stars", [])}
    xp_values = [per_char[m["id"]]["xp"] for m in members]
    roll_values = [fortune_by_char[m["id"]]["rolls_total"] for m in members]
    med_xp = median(xp_values) if xp_values else 0
    med_rolls = median(roll_values) if roll_values else 0

    # Party-wide extrema for rank booleans (computed once).
    avgs = {m["id"]: fortune_by_char[m["id"]]["avg"]
            for m in members if fortune_by_char[m["id"]]["kept_d20s_count"] >= 1}
    sds = {m["id"]: fortune_by_char[m["id"]]["sd"]
           for m in members if fortune_by_char[m["id"]]["kept_d20s_count"] >= 2}
    crit_counts = {m["id"]: fortune_by_char[m["id"]]["crits"] for m in members}
    fumble_counts = {m["id"]: fortune_by_char[m["id"]]["fumbles"] for m in members}
    heaviest = {m["id"]: fortune_by_char[m["id"]]["heaviest"]["total"] for m in members}
    biggest_kills = {m["id"]: max((_kill_xp(k["creature"]) for k in m.get("kills", [])), default=0)
                     for m in members}

    max_avg = max(avgs.values(), default=None)
    min_avg = min(avgs.values(), default=None)
    min_sd = min(sds.values(), default=None)
    max_sd = max(sds.values(), default=None)
    max_crits = max(crit_counts.values(), default=0)
    max_fumbles = max(fumble_counts.values(), default=0)
    max_heaviest = max(heaviest.values(), default=0)
    max_biggest_kill = max(biggest_kills.values(), default=0)

    fp: dict[str, dict] = {}
    for m in members:
        cid = m["id"]
        kills = m.get("kills", [])
        n = len(kills)
        methods = [k["method"] for k in kills]
        creatures = [k["creature"].strip().lower() for k in kills]
        t = per_char[cid]

        # Kills grouped by campaign session index.
        by_session: Counter = Counter()
        for k in kills:
            idx = date_to_idx.get(k["date"])
            if idx is not None:
                by_session[idx] += 1

        # Interior drought: max run of kill-less sessions strictly between two
        # of this PC's kill sessions.
        kill_idxs = sorted(by_session)
        drought = 0
        for a, b in zip(kill_idxs, kill_idxs[1:]):
            drought = max(drought, b - a - 1)

        f = fortune_by_char[cid]
        crits_by_date: Counter = Counter()
        for ev in f["events"]:
            for d in ev.get("rolls", []):
                if d.get("type") == "d20" and not d.get("dropped") and int(d["value"]) == 20:
                    crits_by_date[ev.get("date")] += 1

        star = star_by_id.get(cid, {"system_size": 1})
        pres = "hi" if fortune_by_char[cid]["rolls_total"] >= med_rolls else "lo"
        contrib = "hi" if per_char[cid]["xp"] >= med_xp else "lo"

        fp[cid] = {
            "kill_count": n,
            "kill_pct": t["kill_pct"],
            "xp_pct": t["xp_pct"],
            "distinct_method_count": len(set(methods)),
            "all_kills_one_method": n > 0 and len(set(methods)) == 1,
            "all_distinct_creatures": n > 0 and len(set(creatures)) == n,
            "distinct_type_count": t["kinds_count"],
            "all_distinct_types": n > 0 and t["kinds_count"] == n,
            "biggest_kill_xp": biggest_kills[cid],
            "max_kills_in_one_session": max(by_session.values(), default=0),
            "kill_session_count": len(kill_idxs),
            "longest_drought": drought,
            "kept_d20_avg": f["avg"],
            "is_party_luckiest": cid in avgs and avgs[cid] == max_avg,
            "is_party_unluckiest": cid in avgs and avgs[cid] == min_avg,
            "sd": f["sd"],
            "is_party_steadiest": cid in sds and sds[cid] == min_sd,
            "is_party_swingiest": cid in sds and sds[cid] == max_sd,
            "crits": f["crits"],
            "is_party_most_crits": f["crits"] == max_crits and max_crits > 0,
            "max_crits_in_one_session": max(crits_by_date.values(), default=0),
            "fumbles": f["fumbles"],
            "is_party_most_fumbles": f["fumbles"] == max_fumbles and max_fumbles > 0,
            "heaviest_blow": f["heaviest"]["total"],
            "is_party_heaviest": heaviest[cid] == max_heaviest and max_heaviest > 0,
            "is_party_biggest_kill": biggest_kills[cid] == max_biggest_kill and max_biggest_kill > 0,
            "rolls": fortune_by_char[cid]["rolls_total"],
            "xp": per_char[cid]["xp"],
            "system_size": star.get("system_size", 1),
            "is_constellation_outlier": star.get("system_size", 1) == 1,
            "quadrant": f"{pres}-presence/{contrib}-contribution",
        }
    return fp


_MONTHS_ABBR = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

def _short_date(iso_date: str) -> str:
    """'2026-04-23' -> '23 APR 2026'. Fixed English table — strftime('%b')
    is locale-dependent."""
    from datetime import date
    d = date.fromisoformat(iso_date)
    return f"{d.day:02d} {_MONTHS_ABBR[d.month - 1]} {d.year}"

def compute_sessions_chart(party: dict) -> dict:
    """Per-character kill bars per session date, with tooltip-ready kill lists."""
    members = party.get("members", [])

    # Distinct sorted session dates across the party
    all_dates = sorted({k["date"] for m in members for k in m.get("kills", [])})

    # Per-char per-date counts
    per_char_per_date: dict[str, dict[str, list[dict]]] = {}
    for m in members:
        cid = m["id"]
        bucket: dict[str, list[dict]] = {d: [] for d in all_dates}
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"]) or {}
            bucket[k["date"]].append({
                "creature": k["creature"],
                "method": k["method"],
                "token_url": CUSTOM_CREATURE_TOKENS.get(k["creature"]) or info.get("token_url"),
            })
        per_char_per_date[cid] = bucket

    # Party max per (char,session) count
    party_max = max(
        (len(per_char_per_date[m["id"]][d]) for m in members for d in all_dates),
        default=0,
    )
    scale = max(party_max, 3)

    per_char_bars: dict[str, list[dict]] = {}
    for m in members:
        cid = m["id"]
        bars = []
        for d in all_dates:
            kl = per_char_per_date[cid][d]
            n = len(kl)
            bars.append({
                "date": d,
                "label": _short_date(d),
                "count": n,
                "height_pct": round(n / scale * 100),
                "zero": n == 0,
                "kills": kl,
            })
        per_char_bars[cid] = bars

    return {
        "sessions": [{"date": d, "label": _short_date(d)} for d in all_dates],
        "per_char": per_char_bars,
        "party_max": party_max,
        "scale": scale,
    }

def compute_fortune(events: list) -> dict:
    """Compute fortune stats for one character from their flattened roll events.

    events: list of {"rolls": [die...], "total": N, "notation": str, "date": "YYYY-MM-DD"}.
    Each die is {"type": "d20"/"d6"/..., "value": N, "dropped"?: bool, "isExplosion"?: bool}.
    """
    physical_d20s: list[int] = []
    kept_d20s: list[int] = []
    heaviest = {"total": 0, "notation": ""}

    for ev in events:
        for d in ev.get("rolls", []):
            if d.get("type") == "d20":
                v = int(d["value"])
                physical_d20s.append(v)
                if not d.get("dropped"):
                    kept_d20s.append(v)
        # Heaviest blow: pure damage rolls only. Excludes any event containing a d20
        # (attack rolls, saves, ability checks) or a d100 (percentile rolls in this
        # dice system pair d100 with a d10 for the units digit, so the d10 alone
        # is not a damage signal).
        types_in_event = {d.get("type") for d in ev.get("rolls", [])}
        is_damage = (not (types_in_event & {"d20", "d100"})
                     and bool(types_in_event - {"mod"}))
        if is_damage and ev.get("total", 0) > heaviest["total"]:
            heaviest = {"total": ev["total"], "notation": ev.get("notation", "")}

    avg = round(sum(kept_d20s) / len(kept_d20s), 1) if kept_d20s else 0.0
    sd = round(pstdev(kept_d20s), 1) if len(kept_d20s) >= 2 else 0.0

    return {
        "rolls_total": len(events),
        "physical_d20s_count": len(physical_d20s),
        "kept_d20s_count": len(kept_d20s),
        "avg": avg,
        "sd": sd,
        "crits": sum(1 for v in kept_d20s if v == 20),
        "fumbles": sum(1 for v in kept_d20s if v == 1),
        "heaviest": heaviest,
        "physical_d20s": physical_d20s,  # for histogram
        "events": events,                # for Other Dice and tooltips
    }

def compute_d20_histogram(physical_d20s: list[int], party_max: int) -> list[dict]:
    counts = Counter(physical_d20s)
    scale = max(party_max, 3)
    bars = []
    for v in range(1, 21):
        n = counts.get(v, 0)
        bars.append({
            "value": v,
            "count": n,
            "height_pct": round(n / scale * 100) if scale else 0,
            "zero": n == 0,
        })
    return bars

def compute_party_d20_max(all_physicals_by_player: dict[str, list[int]]) -> int:
    """Per-value max across the party (incl. GM)."""
    party_max = 0
    for v in range(1, 21):
        s = sum(physicals.count(v) for physicals in all_physicals_by_player.values())
        if s > party_max:
            party_max = s
    return party_max

def compute_patron_die(fortune_by_char: dict, party: dict) -> list[dict]:
    """Party-wide d20 histogram, excluding the GM."""
    physicals: list[int] = []
    for m in party.get("members", []):
        if m["id"] == "gm":
            continue
        physicals.extend(fortune_by_char[m["id"]]["physical_d20s"])
    counts = Counter(physicals)
    party_max = max((counts.get(v, 0) for v in range(1, 21)), default=0)
    return compute_d20_histogram(physicals, party_max=party_max)

def compute_other_dice(events: list) -> list[dict]:
    """Per-die-type rows: d4..d12+, with dot positions, avg, and maxed count."""
    by_die: dict[str, list[dict]] = {}
    for ev in events:
        date = ev.get("date", "")
        # Percentile rolls in this dice system pair a d100 with a d10 for the
        # units digit. Drop the units d10 so it doesn't pollute the d10 row.
        types_in_event = {d.get("type") for d in ev.get("rolls", [])}
        skip_units_d10 = "d100" in types_in_event
        for d in ev.get("rolls", []):
            t = d.get("type")
            if t in (None, "d20", "d100", "mod"):
                continue
            if t == "d10" and skip_units_d10:
                continue
            if d.get("dropped"):
                continue
            v = int(d["value"])
            face = int(t.lstrip("d"))
            # d10 quirk: source stores 10 as value: 0
            if face == 10 and v == 0:
                v = 10
            by_die.setdefault(t, []).append({"value": v, "face": face, "date": date})

    rows = []
    for die_type in sorted(by_die.keys(), key=lambda x: int(x.lstrip("d"))):
        entries = by_die[die_type]
        values = [e["value"] for e in entries]
        face = entries[0]["face"]
        N = len(values)
        if N == 1:
            xs = [189]
        else:
            xs = [round(24 + i / (N - 1) * 330) for i in range(N)]
        ys = [round(56 - (v - 1) / (face - 1) * 52) for v in values]
        rows.append({
            "die": die_type,
            "count": N,
            "avg": round(sum(values) / N, 1),
            # Times the die landed on its ceiling. Once ceilings saturate this
            # trends up for everyone, but it still separates the die you cast
            # constantly from the one you've only maxed once.
            "maxed": sum(1 for v in values if v == face),
            "dots": [{"x": x, "y": y, "value": v, "date": e["date"]}
                     for x, y, v, e in zip(xs, ys, values, entries)],
        })
    return rows


# Ascent chart viewBox + plot margins (mirrors the other-dice geometry style:
# coordinates are computed here; the template emits static SVG).
_ASCENT_W, _ASCENT_H = 1000, 440
_ASCENT_ML, _ASCENT_MR, _ASCENT_MT, _ASCENT_MB = 60, 128, 26, 52


def compute_ascent(xp_log: Optional[dict]) -> Optional[dict]:
    """Cumulative-XP climb for the Company tab. Returns None when there are no
    XP entries (template renders an empty state). Geometry is server-side so
    the chart matches the established other-dice/patron-die pattern."""
    entries = (xp_log or {}).get("entries", [])
    if not entries:
        return None

    # Chronological; stable sort preserves the GM's intra-day authoring order
    # (so a closing "rounding error" event stays last within its session).
    ev = sorted(entries, key=lambda e: e.get("date", ""))

    nodes = [{"label": "Where it began", "type": None, "gain": 0, "total": 0,
              "date": "", "source": "Level 1 · the road begins", "session_id": ""}]
    running = 0
    for e in ev:
        running += int(e.get("perPc", 0))
        nodes.append({
            "label": e.get("title", ""),
            "type": e.get("type"),
            "gain": int(e.get("perPc", 0)),
            "total": running,
            "date": _short_date(e["date"]) if e.get("date") else "",
            "source": e.get("source", ""),
            "session_id": e.get("sessionId", ""),
        })

    total = running
    level = _level_for_xp(total)
    nxt = _next_threshold(level)
    ymax = nxt if nxt else max(total, 1)
    to_next = (nxt - total) if nxt else 0

    plot_w = _ASCENT_W - _ASCENT_ML - _ASCENT_MR
    plot_h = _ASCENT_H - _ASCENT_MT - _ASCENT_MB
    n_seg = len(nodes) - 1

    def fx(i):
        return round(_ASCENT_ML + plot_w * (i / n_seg if n_seg else 0), 2)

    def fy(v):
        return round(_ASCENT_MT + plot_h * (1 - v / ymax), 2)

    ybase = fy(0)

    # node coordinates + level-up crossings
    prev = 0
    for i, nd in enumerate(nodes):
        nd["i"] = i
        nd["cx"] = fx(i)
        nd["cy"] = fy(nd["total"])
        up = None
        for l in range(2, 21):
            if prev < LEVEL_XP[l] <= nd["total"]:
                up = _to_roman(l)
        nd["up"] = up
        nd["r"] = 6.5 if up else (3.5 if i == 0 else 5)
        prev = nd["total"]

    # threshold lines visible within (0, ymax]
    thresholds = []
    for l in range(2, 21):
        v = LEVEL_XP[l]
        if v > ymax:
            break
        thresholds.append({"v": v, "lvl": _to_roman(l), "y": fy(v), "top": v == ymax})

    # session date ticks: group consecutive nodes sharing a sessionId
    groups: list[dict] = []
    for nd in nodes[1:]:
        sid = nd["session_id"]
        if groups and groups[-1]["sid"] == sid:
            groups[-1]["xs"].append(nd["cx"])
            groups[-1]["date"] = nd["date"]
        else:
            groups.append({"sid": sid, "xs": [nd["cx"]], "date": nd["date"]})
    ticks = [{
        "x": round(sum(g["xs"]) / len(g["xs"]), 2),
        "x0": g["xs"][0], "x1": g["xs"][-1],
        "label": g["date"], "multi": len(g["xs"]) > 1,
    } for g in groups]

    # path strings
    line_d = "M " + " L ".join(f"{nd['cx']} {nd['cy']}" for nd in nodes)
    area_d = (f"M {nodes[0]['cx']} {ybase} "
              + " ".join(f"L {nd['cx']} {nd['cy']}" for nd in nodes)
              + f" L {nodes[-1]['cx']} {ybase} Z")

    # by-type breakdown for the source bar (descending)
    by_type: dict[str, int] = {}
    for e in ev:
        t = e.get("type") or "other"
        by_type[t] = by_type.get(t, 0) + int(e.get("perPc", 0))
    sources = [{
        "type": t, "label": t.capitalize(), "xp": x,
        "pct": round(x / total * 100) if total else 0,
    } for t, x in sorted(by_type.items(), key=lambda kv: -kv[1])]

    richest = max(ev, key=lambda e: int(e.get("perPc", 0)))

    return {
        "view_w": _ASCENT_W, "view_h": _ASCENT_H,
        "plot_left": _ASCENT_ML, "plot_right": round(_ASCENT_ML + plot_w, 2),
        "ybase": ybase, "ymax": ymax,
        "nodes": nodes, "thresholds": thresholds, "ticks": ticks,
        "line_d": line_d, "area_d": area_d,
        "proj_y": fy(total),
        "road_x": round(_ASCENT_ML + plot_w * 0.52, 2),
        "road_y": fy((total + ymax) / 2),
        "last_cx": nodes[-1]["cx"], "last_cy": nodes[-1]["cy"],
        "sources": sources,
        "total": total, "level": _to_roman(level), "level_num": level,
        "to_next": to_next, "next_threshold": nxt,
        "deeds": len(ev), "sessions": len({e.get("sessionId") for e in ev}),
        "richest_xp": int(richest.get("perPc", 0)),
        "richest_title": richest.get("title", ""),
    }


SKILL_DISPLAY = {
    "acrobatics": "Acrobatics",
    "animalHandling": "Animal Handling",
    "arcana": "Arcana",
    "athletics": "Athletics",
    "deception": "Deception",
    "history": "History",
    "insight": "Insight",
    "intimidation": "Intimidation",
    "investigation": "Investigation",
    "medicine": "Medicine",
    "nature": "Nature",
    "perception": "Perception",
    "performance": "Performance",
    "persuasion": "Persuasion",
    "religion": "Religion",
    "sleightOfHand": "Sleight of Hand",
    "stealth": "Stealth",
    "survival": "Survival",
}

_PROF_RANK = {"expertise": 3, "full": 2, "half": 1, "none": 0}

def compute_best_skill(member: dict) -> dict | None:
    """Return {'name': 'Persuasion', 'mod': 5} for the member's strongest skill.
    Tie-break: higher proficiency rank, then alphabetical skill key."""
    skills = member.get("skills") or {}
    if not skills:
        return None
    best_key, best = min(
        skills.items(),
        key=lambda item: (-item[1].get("mod", 0),
                          -_PROF_RANK.get(item[1].get("prof", "none"), 0),
                          item[0]),
    )
    return {"name": SKILL_DISPLAY.get(best_key, best_key), "mod": best.get("mod", 0)}

# ── Ability radar geometry ──────────────────────────────────────────
# Fixed 240x240 viewBox. Score-based scale: RADAR_FLOOR (center) -> RADAR_CEIL
# (outer ring), one grid ring per RADAR_STEP points. Scores below the floor
# clamp to the center. All coordinates are pre-rounded so the template lays
# them out directly and the client script only animates/links — never recomputes.
RADAR_KEYS = ("str", "dex", "con", "int", "wis", "cha")
RADAR_LABELS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
RADAR_FLOOR = 8
RADAR_CEIL = 20
RADAR_STEP = 2
RADAR_TICKS = (10, 14, 18)
RADAR_CX = 120.0
RADAR_CY = 120.0
RADAR_R = 76.0        # outer-ring radius
RADAR_HIT_R = 112.0   # pie-slice hit radius (beyond the outer ring, inside the viewBox)
RADAR_LABEL_R = 93.0  # label radius (RADAR_R + 17)

def _radar_angle(i: int) -> float:
    """Angle of axis i, with STR (i=0) pointing straight up."""
    return -math.pi / 2 + (i / 6) * 2 * math.pi

def _radar_radius(score: float) -> float:
    """Map an ability score to a pixel radius, clamping to [RADAR_FLOOR, RADAR_CEIL]."""
    clamped = max(RADAR_FLOOR, min(RADAR_CEIL, score))
    return (clamped - RADAR_FLOOR) / (RADAR_CEIL - RADAR_FLOOR) * RADAR_R

def _radar_point(angle: float, radius: float) -> tuple[float, float]:
    return (RADAR_CX + math.cos(angle) * radius, RADAR_CY + math.sin(angle) * radius)

def _radar_xy(p: tuple[float, float]) -> str:
    return f"{p[0]:.1f},{p[1]:.1f}"

def compute_radar(member: dict) -> dict:
    """Geometry for a character's six-axis ability-score radar.

    Returns pre-rounded coordinates for: concentric grid `rings` (point-string
    each), `axes` far-endpoint tips `{x2, y2}` (SVG lines originate at cx, cy),
    `ticks`, the filled `shape` (point-string), vertex
    `dots` (with proficient-save flag), `labels`, and invisible pie-slice
    `sectors` (60-degree hover hit zones tiling the disc). See module constants
    for the scale."""
    abilities = member.get("abilities", {})
    saves = member.get("savingThrows", {})

    rings = []
    for rv in range(RADAR_FLOOR + RADAR_STEP, RADAR_CEIL + 1, RADAR_STEP):
        rr = _radar_radius(rv)
        rings.append(" ".join(_radar_xy(_radar_point(_radar_angle(i), rr)) for i in range(6)))

    axes = []
    for i in range(6):
        p = _radar_point(_radar_angle(i), RADAR_R)
        axes.append({"x2": round(p[0], 1), "y2": round(p[1], 1)})

    ticks = []
    for tv in RADAR_TICKS:
        y = RADAR_CY - _radar_radius(tv)
        # +4 nudges right of the axis; +3 drops to the text baseline
        ticks.append({"x": round(RADAR_CX + 4, 1), "y": round(y + 3, 1), "text": str(tv)})

    shape_pts, dots = [], []
    for i, key in enumerate(RADAR_KEYS):
        score = abilities.get(key, RADAR_FLOOR)
        p = _radar_point(_radar_angle(i), _radar_radius(score))
        shape_pts.append(_radar_xy(p))
        dots.append({
            "i": i, "key": key,
            "x": round(p[0], 1), "y": round(p[1], 1),
            "prof": bool(saves.get(key, {}).get("prof")),
        })
    shape = " ".join(shape_pts)

    labels = []
    for i, lab in enumerate(RADAR_LABELS):
        a = _radar_angle(i)
        p = _radar_point(a, RADAR_LABEL_R)
        cos_a, sin_a = math.cos(a), math.sin(a)
        anchor = "middle"
        if cos_a > 0.4:
            anchor = "start"
        elif cos_a < -0.4:
            anchor = "end"
        dy = 4.0
        if sin_a > 0.5:
            dy = 11.0
        elif sin_a < -0.5:
            dy = -3.0
        labels.append({"i": i, "text": lab, "anchor": anchor,
                       "x": round(p[0], 1), "y": round(p[1] + dy, 1)})

    sectors = []
    for i, key in enumerate(RADAR_KEYS):
        a = _radar_angle(i)
        p0 = _radar_point(a - math.pi / 6, RADAR_HIT_R)
        p1 = _radar_point(a + math.pi / 6, RADAR_HIT_R)
        d = (f"M{RADAR_CX:.0f} {RADAR_CY:.0f} "
             f"L{p0[0]:.1f} {p0[1]:.1f} "
             f"A{RADAR_HIT_R:.0f} {RADAR_HIT_R:.0f} 0 0 1 {p1[0]:.1f} {p1[1]:.1f} Z")
        sectors.append({"i": i, "key": key, "d": d})

    return {"rings": rings, "axes": axes, "ticks": ticks,
            "shape": shape, "dots": dots, "labels": labels, "sectors": sectors}


def compute_constellation(party: dict, fortune_by_char: dict, trials: dict) -> dict:
    """Position each (non-GM) character by (xp, total rolls). Excludes GM.

    When two or more characters round to the same plot coordinate they form
    a 'system': portraits get an orbital offset around the shared center so
    they no longer occlude each other, and a dashed brass ring is drawn
    around the cluster. The constellation polygon connects cluster centers,
    so a system counts as one node in the link sort.
    """
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    party_max_xp = max((trials["per_char"][m["id"]]["xp"] for m in members), default=0)
    party_max_rolls = max(
        (fortune_by_char[m["id"]]["rolls_total"] for m in members), default=0
    )

    raw: list[dict] = []
    for m in members:
        cid = m["id"]
        xp = trials["per_char"][cid]["xp"]
        rolls = fortune_by_char[cid]["rolls_total"]
        left = round(xp / party_max_xp * 92 + 4) if party_max_xp else 4
        top = round(96 - rolls / party_max_rolls * 92) if party_max_rolls else 96
        raw.append({
            "id": cid,
            "left_pct": left,
            "top_pct": top,
            "name": m.get("name") or cid.title(),
            "xp": xp,
            "rolls": rolls,
            "kept_d20s": fortune_by_char[cid]["kept_d20s_count"],
            "kills": trials["per_char"][cid]["kill_count"],
            "avg": fortune_by_char[cid]["avg"],
            "sd": fortune_by_char[cid]["sd"],
            "crits": fortune_by_char[cid]["crits"],
            "fumbles": fortune_by_char[cid]["fumbles"],
        })

    # Cluster stars whose portraits would visually collide on the rendered
    # plot — not just exact coordinate ties, since the chart-space rounding
    # leaves near-ties (e.g. dy=2%) that still overlap by ~80% of a portrait.
    # Threshold = portrait diameter; plot dims approximate the rendered area
    # (.constellation max-width 1100 minus 80px side padding; height 480
    # minus 24+36 vertical padding — see styles.css).
    PLOT_W_PX = 940
    PLOT_H_PX = 420
    COLLISION_THRESHOLD_PX = 72

    # Per-star pixel offset around the cluster center. Tuned to fit shrunken
    # 52px portraits (see .constellation-star.in-system in styles.css) with
    # a small visual gap inside the orbit ring.
    ORBIT_RADIUS_PX = 36

    # Single-linkage clustering via union-find over portrait-overlap pairs.
    parent = list(range(len(raw)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(raw)):
        for j in range(i + 1, len(raw)):
            dx_px = (raw[i]["left_pct"] - raw[j]["left_pct"]) / 100 * PLOT_W_PX
            dy_px = (raw[i]["top_pct"] - raw[j]["top_pct"]) / 100 * PLOT_H_PX
            if math.hypot(dx_px, dy_px) <= COLLISION_THRESHOLD_PX:
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for i, s in enumerate(raw):
        groups.setdefault(find(i), []).append(s)
    # Sort group members by id so a given star always occupies the same
    # orbit slot across runs.
    for group in groups.values():
        group.sort(key=lambda s: s["id"])

    stars: list[dict] = []
    systems: list[dict] = []
    cluster_centers: list[tuple[float, float, int, str]] = []  # (left, top, min_xp, min_id) for link sort

    for group in groups.values():
        n = len(group)
        if n == 1:
            s = group[0]
            s["system_size"] = 1
            s["orbit_x_px"] = 0
            s["orbit_y_px"] = 0
            stars.append(s)
            cluster_centers.append((s["left_pct"], s["top_pct"], s["xp"], s["id"]))
            continue

        # Cluster center = centroid of member coords. Override each star's
        # left_pct/top_pct so portraits anchor at the shared center; the
        # orbit translate then fans them around it.
        center_left = sum(s["left_pct"] for s in group) / n
        center_top = sum(s["top_pct"] for s in group) / n

        # n=2 reads as a true binary: place horizontally on either side.
        # n>=3 fans evenly around the center starting from the top.
        for i, s in enumerate(group):
            if n == 2:
                angle_deg = 180.0 if i == 0 else 0.0
            else:
                angle_deg = -90.0 + (360.0 / n) * i
            angle_rad = math.radians(angle_deg)
            s["left_pct"] = center_left
            s["top_pct"] = center_top
            s["system_size"] = n
            s["orbit_x_px"] = round(ORBIT_RADIUS_PX * math.cos(angle_rad), 2)
            s["orbit_y_px"] = round(ORBIT_RADIUS_PX * math.sin(angle_rad), 2)
            stars.append(s)
        systems.append({
            "left_pct": center_left,
            "top_pct": center_top,
            "size": n,
        })
        cluster_centers.append((
            center_left, center_top,
            min(s["xp"] for s in group),
            min(s["id"] for s in group),
        ))

    # Constellation links: one node per cluster center (so a system is a
    # single vertex), sorted by (min xp, min id) for stability.
    links: list[dict] = []
    if len(cluster_centers) >= 2:
        cluster_centers.sort(key=lambda c: (c[2], c[3]))
        for i in range(len(cluster_centers)):
            a = cluster_centers[i]
            b = cluster_centers[(i + 1) % len(cluster_centers)]
            links.append({
                "x1": a[0] * 10,
                "y1": a[1] * 10,
                "x2": b[0] * 10,
                "y2": b[1] * 10,
            })

    return {
        "stars": stars,
        "systems": systems,
        "links": links,
        "party_max_xp": party_max_xp,
        "party_max_rolls": party_max_rolls,
        "mid_xp": (party_max_xp + 1) // 2,
        "mid_rolls": (party_max_rolls + 1) // 2,
    }

def compute_bestiary(party: dict) -> list[dict]:
    """Group every kill by creature type, then by creature name within type."""
    by_type: dict[str, dict[str, int]] = {}
    token_by_name: dict[str, Optional[str]] = {}
    for m in party.get("members", []):
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"])
            if not info:
                continue
            t = info["type"]
            n = info["name"]
            by_type.setdefault(t, {}).setdefault(n, 0)
            by_type[t][n] += 1
            token_by_name.setdefault(n, info.get("token_url"))

    groups = []
    for t in by_type.keys():
        creatures = sorted(by_type[t].items(), key=lambda kv: (-kv[1], kv[0].lower()))
        groups.append({
            "type": t,
            "total": sum(c for _, c in creatures),
            "creatures": [{"name": n, "count": c, "token_url": token_by_name.get(n)}
                          for n, c in creatures],
        })
    groups.sort(key=lambda g: (-g["total"], g["type"].lower()))
    return groups

def compute_company_ledger(party: dict, session_log: dict, trials: dict, fortune_by_char: dict) -> dict:
    members = [m for m in party.get("members", []) if m["id"] != "gm"]
    total_xp = sum(trials["per_char"][m["id"]]["xp"] for m in members)
    total_kills = sum(trials["per_char"][m["id"]]["kill_count"] for m in members)
    total_rolls = sum(fortune_by_char[m["id"]]["rolls_total"] for m in members)
    total_d20s = sum(fortune_by_char[m["id"]]["kept_d20s_count"] for m in members)
    sessions_kept = len(session_log.get("entries", []))

    return {
        "total_xp": total_xp,
        "total_kills": total_kills,
        "total_rolls": total_rolls,
        "total_d20s": total_d20s,
        "sessions_kept": sessions_kept,
    }

FORGOTTEN_REALMS_MONTHS = [
    "Hammer", "Alturiak", "Ches", "Tarsakh", "Mirtul", "Kythorn",
    "Flamerule", "Eleasis", "Eleint", "Marpenoth", "Uktar", "Nightal",
]

def compute_chronicle(session_log: dict, sessions_authored: list, chapters_authored: list, party: dict) -> dict:
    entries = session_log.get("entries", [])
    auth_session_by_id = {a["session"]: a for a in sessions_authored}
    chapter_by_starts = {a["starts_at_session"]: a for a in chapters_authored if "starts_at_session" in a}

    # Determine chapter spans: every chapter_marker opens a chapter; first session implicitly opens one.
    chapter_starts: list[int] = []
    for e in entries:
        if not chapter_starts or e.get("chapter_marker"):
            chapter_starts.append(e["session"])

    # Map each session to its chapter's starting session
    session_to_chapter: dict[int, int] = {}
    current = None
    for e in entries:
        if e["session"] in chapter_starts:
            current = e["session"]
        session_to_chapter[e["session"]] = current

    # Per-date -> [kill record] for portrait tallies + pip data. Each record carries
    # the killer (id/name/image) and the creature so chronicle pips can render
    # creature tokens with a tooltip naming the killer + method.
    party_kills_by_date: dict[str, list[dict]] = {}
    for m in party.get("members", []):
        for k in m.get("kills", []):
            info = bestiary_lookup(k["creature"]) or {}
            party_kills_by_date.setdefault(k["date"], []).append({
                "killer_id": m["id"],
                "killer_name": m.get("name", m["id"]).split()[0],
                "killer_image": m.get("image", ""),
                "creature": k["creature"],
                "method": k["method"],
                "date": k["date"],
                "date_label": _short_date(k["date"]),
                "token_url": CUSTOM_CREATURE_TOKENS.get(k["creature"]) or info.get("token_url"),
            })

    chapters = []
    for idx, start_id in enumerate(chapter_starts, start=1):
        ch = chapter_by_starts.get(start_id, {})
        sess_in_chapter = [e for e in entries if session_to_chapter[e["session"]] == start_id]
        # Flatten chapter-level kill records in chronological session order.
        chapter_kill_pips: list[dict] = []
        for e in sess_in_chapter:
            chapter_kill_pips.extend(party_kills_by_date.get(e["date"], []))

        chapters.append({
            "label": _to_roman(idx),
            "title": ch.get("title", ""),
            "epigraph": ch.get("epigraph", ""),
            "starts_at": start_id,
            "session_count": len(sess_in_chapter),
            "kill_count": len(chapter_kill_pips),
            "kill_pips": chapter_kill_pips,
            "sessions": [_render_session(e, auth_session_by_id, party_kills_by_date)
                         for e in sess_in_chapter],
        })

    # Regnal rail: (year, month) -> session count, ordered by Forgotten Realms month order.
    months_by_year: dict[str, dict[str, int]] = {}
    for e in entries:
        iu_m = e.get("iu_month") or "Kythorn"
        iu_y = str(e.get("iu_year") or "1494")
        year = f"{iu_y} DR" if not iu_y.endswith("DR") else iu_y
        months_by_year.setdefault(year, {})
        months_by_year[year][iu_m] = months_by_year[year].get(iu_m, 0) + 1
    rail = []
    for year, ms in months_by_year.items():
        ordered = [m for m in FORGOTTEN_REALMS_MONTHS if m in ms]
        for m in ordered:
            rail.append({"month": m, "year": year, "count": ms[m]})

    return {"chapters": chapters, "rail": rail}

def _render_session(entry: dict, auth_by_id: dict, kills_by_date: dict) -> dict:
    sess_id = entry["session"]
    auth = auth_by_id.get(sess_id, {})
    kills = kills_by_date.get(entry["date"], [])
    iu_day = entry.get("iu_day", "")
    iu_month = entry.get("iu_month", "Kythorn")
    return {
        "id": sess_id,
        "label": _to_roman(sess_id),
        "title": auth.get("title", ""),
        "summary": auth.get("summary", ""),
        "silent_roll": auth.get("silent_roll", []),
        "real_date": entry["date"],
        "real_date_label": _short_date(entry["date"]),
        "iu_date": f"{iu_day} {iu_month}".strip(),
        "kills_count": len(kills),
        "kill_pips": kills,
    }

def compute_distinctions(party: dict, characters_authored: list) -> list[dict]:
    """Pair each non-GM character with their authored distinction crown."""
    by_id = {a["id"]: a for a in characters_authored}
    rows = []
    for m in party.get("members", []):
        if m["id"] == "gm":
            continue
        a = by_id.get(m["id"], {})
        rows.append({
            "id": m["id"],
            "name": m["id"].title(),
            "title": a.get("distinction_title", ""),
            "subtitle": a.get("distinction_subtitle", ""),
            "detail": a.get("distinction_detail", ""),
        })
    return rows

# D&D 5e (2024) cumulative XP per level — identical to 2014 at all tiers.
LEVEL_XP = {
    1: 0, 2: 300, 3: 900, 4: 2700, 5: 6500, 6: 14000, 7: 23000,
    8: 34000, 9: 48000, 10: 64000, 11: 85000, 12: 100000, 13: 120000,
    14: 140000, 15: 165000, 16: 195000, 17: 225000, 18: 265000,
    19: 305000, 20: 355000,
}


def _level_for_xp(total: int) -> int:
    """Highest level whose threshold is <= total."""
    lvl = 1
    for l in range(1, 21):
        if total >= LEVEL_XP[l]:
            lvl = l
    return lvl


def _next_threshold(level: int) -> Optional[int]:
    """XP needed for the next level, or None at level 20."""
    return LEVEL_XP.get(level + 1)


_ROMAN_PAIRS = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
                (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]

def _to_roman(n: int) -> str:
    out = ""
    for val, s in _ROMAN_PAIRS:
        while n >= val:
            out += s
            n -= val
    return out

def compute_all(data: dict, authored: dict) -> dict:
    party = data["party"]
    session_log = data["session_log"]
    rolls_by_slug = data.get("rolls_by_slug", {})

    trials = compute_trials(party)
    fortune_ids = [m["id"] for m in party.get("members", [])] + ["gm"]
    fortune_by_char = {cid: compute_fortune(rolls_by_slug.get(cid, []))
                       for cid in fortune_ids}
    sessions_chart = compute_sessions_chart(party)

    # Histograms
    all_physicals_by_player = {cid: f["physical_d20s"] for cid, f in fortune_by_char.items()}
    party_max = compute_party_d20_max(all_physicals_by_player)
    histograms = {cid: compute_d20_histogram(f["physical_d20s"], party_max)
                  for cid, f in fortune_by_char.items()}
    other_dice = {cid: compute_other_dice(f["events"]) for cid, f in fortune_by_char.items()}

    constellation = compute_constellation(party, fortune_by_char, trials)
    bestiary = compute_bestiary(party)
    chronicle = compute_chronicle(session_log, authored["sessions"], authored["chapters"], party)
    ledger = compute_company_ledger(party, session_log, trials, fortune_by_char)
    distinctions = compute_distinctions(party, authored["characters"])
    patron = compute_patron_die(fortune_by_char, party)
    best_skill_by_id = {m["id"]: compute_best_skill(m) for m in party.get("members", [])}
    radar_by_id = {m["id"]: compute_radar(m)
                   for m in party.get("members", []) if m["id"] != "gm"}
    ascent = compute_ascent(data.get("xp_log"))

    char_auth_by_id = {a["id"]: a for a in authored["characters"]}

    inventory_bundle = inventory.load(REPO_ROOT, party=party)

    archetype_ranks: dict[str, int] = {}
    for slug, rec in inventory_bundle["by_id"].items():
        arc = rec.get("archetype")
        if arc:
            archetype_ranks[arc] = 1  # at most one holder per archetype

    inscriptions: dict[str, str] = {}
    for slug, rec in inventory_bundle["by_id"].items():
        authored_badge = char_auth_by_id.get(slug, {}).get("archetype_badge")
        inscriptions[slug] = inventory.resolve_inscription(rec, authored_badge, archetype_ranks)

    site = dict(authored["site"])
    site["header_eyebrow"] = _compute_header_eyebrow(chronicle, ledger)
    site.setdefault(
        "ascent_read",
        "Blade and book in equal measure — the company earns its name as "
        "readily by riddle and road as at the edge of a sword.",
    )

    party_top_xp = _compute_party_top_xp(party, trials, n=3)

    return {
        "site": site,
        "party": party,
        "party_top_xp": party_top_xp,
        "characters_authored": char_auth_by_id,
        "reliquary_by_id": compute_reliquary(party, authored["kills"]),
        "trials": trials,
        "fortune": fortune_by_char,
        "sessions_chart": sessions_chart,
        "histograms": histograms,
        "other_dice": other_dice,
        "constellation": constellation,
        "bestiary": bestiary,
        "chronicle": chronicle,
        "ledger": ledger,
        "distinctions": distinctions,
        "patron_die": patron,
        "ascent": ascent,
        "best_skill_by_id": best_skill_by_id,
        "radar_by_id": radar_by_id,
        "npcs_by_allegiance": _split_npcs(authored["npcs"]),
        "inventory_by_id": inventory_bundle["by_id"],
        "company_strip": inventory_bundle["company_strip"],
        "archetype_inscriptions": inscriptions,
        "skill_display": SKILL_DISPLAY,
        "archetype_labels": {a["slug"]: a["label"] for a in inventory.ARCHETYPE_SLATE},
    }


def _compute_party_top_xp(party: dict, trials: dict, n: int = 3) -> list[dict]:
    """Top-N party members ordered by XP earned, descending. GM excluded.

    Returns a list of member dicts (with their existing fields like image, id, name)
    so the template can iterate them directly. Tiebreaker is alphabetical by id —
    deterministic and stable across runs.
    """
    members = [m for m in party.get("members", []) if m.get("id") != "gm"]
    per = trials.get("per_char", {})
    members_sorted = sorted(
        members,
        key=lambda m: (-int(per.get(m["id"], {}).get("xp", 0)), m.get("id", "")),
    )
    return members_sorted[:n]


def _compute_header_eyebrow(chronicle: dict, ledger: dict) -> list[str]:
    """Three short lines for the upper-left of the page header."""
    lines = ["Volume I"]
    rail = chronicle.get("rail") or []
    if rail:
        latest = rail[-1]
        lines.append(f"{latest.get('month', '')} {latest.get('year', '')}".strip())
    sessions = ledger.get("sessions_kept", 0)
    if sessions:
        word = "Session" if sessions == 1 else "Sessions"
        lines.append(f"{sessions} {word} Kept")
    return [ln for ln in lines if ln]

def _split_npcs(npcs: list) -> dict:
    return {
        "with": [n for n in npcs if n.get("allegiance") == "with"],
        "against": [n for n in npcs if n.get("allegiance") == "against"],
    }

def compute_cr_label(creature: str) -> str:
    info = bestiary_lookup(creature)
    if not info:
        return "?"
    cr = info["cr"]
    if isinstance(cr, dict):
        cr = cr.get("cr")
    cr = str(cr)
    return {"1/8": "&frac18;", "1/4": "&frac14;", "1/2": "&frac12;"}.get(cr, cr)

def compute_reliquary(party: dict, authored_kills: list) -> dict[str, list[dict]]:
    """Per-member, date-sorted kill rows with their authored verse joined in.
    Joining here (via kill_key's casefold) keeps templates free of key
    reconstruction — the template-side `| lower` rebuild diverged from
    casefold on non-ASCII names."""
    by_key = {
        kill_key(k["character"], k["date"], k["creature"], k["method"]): k
        for k in authored_kills
    }
    out: dict[str, list[dict]] = {}
    for m in party.get("members", []):
        rows = []
        for k in sorted(m.get("kills", []), key=lambda k: k["date"]):
            auth = by_key.get(kill_key(m["id"], k["date"], k["creature"], k["method"]), {})
            rows.append({
                "date": k["date"],
                "date_label": _short_date(k["date"]),
                "creature": k["creature"],
                "cr_label": compute_cr_label(k["creature"]),
                "verse": auth.get("verse", ""),
                "annotation": auth.get("annotation", ""),
            })
        out[m["id"]] = rows
    return out
