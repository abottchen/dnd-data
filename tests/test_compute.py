from build.render import (xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune,
                   compute_d20_histogram, compute_other_dice, compute_best_skill,
                   compute_intro_meta, compute_constellation, compute_fact_pack,
                   _compute_party_top_xp, _compute_header_eyebrow,
                   _creature_token_url, _name_to_token_name,
                   compute_radar)

def test_xp_for_cr_handles_fractions():
    assert xp_for_cr("1/8") == 25
    assert xp_for_cr("1/4") == 50
    assert xp_for_cr("1/2") == 100

def test_xp_for_cr_handles_integers():
    assert xp_for_cr(0) == 10
    assert xp_for_cr(1) == 200
    assert xp_for_cr(5) == 1800

def test_xp_for_cr_handles_dict_form():
    assert xp_for_cr({"cr": "1/4"}) == 50

def test_sessions_chart_uses_party_max_for_scaling():
    party = {"members": [
        {"id": "a", "kills": [
            {"date": "2026-04-01", "creature": "x", "method": "m"},
            {"date": "2026-04-23", "creature": "x", "method": "m"},
            {"date": "2026-04-23", "creature": "x", "method": "m"},
            {"date": "2026-04-23", "creature": "x", "method": "m"},
        ]},
        {"id": "b", "kills": [
            {"date": "2026-04-01", "creature": "x", "method": "m"},
        ]},
    ]}
    result = compute_sessions_chart(party)
    assert [s["date"] for s in result["sessions"]] == ["2026-04-01", "2026-04-23"]
    a_bars = result["per_char"]["a"]
    a_april23 = next(b for b in a_bars if b["date"] == "2026-04-23")
    assert a_april23["count"] == 3
    assert a_april23["height_pct"] == 100
    b_bars = result["per_char"]["b"]
    b_april23 = next(b for b in b_bars if b["date"] == "2026-04-23")
    assert b_april23["count"] == 0
    assert b_april23["zero"] is True

def test_fortune_average_and_sd_use_kept_d20s_only():
    events = [
        {"rolls": [{"type": "d20", "value": 15, "dropped": False}], "total": 15, "notation": "1d20", "date": "2026-04-01"},
        {"rolls": [{"type": "d20", "value": 5, "dropped": True}], "total": 5, "notation": "1d20", "date": "2026-04-01"},
        {"rolls": [{"type": "d20", "value": 17, "dropped": False}], "total": 17, "notation": "1d20", "date": "2026-04-01"},
    ]
    f = compute_fortune(events)
    # Kept: 15, 17. Mean=16.0; population sd = 1.0
    assert f["avg"] == 16.0
    assert f["sd"] == 1.0

def test_fortune_crit_count_excludes_dropped():
    events = [
        {"rolls": [{"type": "d20", "value": 20, "dropped": False}], "total": 20, "notation": "1d20", "date": "x"},
        {"rolls": [{"type": "d20", "value": 20, "dropped": True}], "total": 20, "notation": "1d20", "date": "x"},
    ]
    f = compute_fortune(events)
    assert f["crits"] == 1

def test_fortune_heaviest_blow_excludes_d100_and_d20_events():
    events = [
        # Percentile roll: d100 + d10 pair, total 83. Must NOT be heaviest.
        {"rolls": [{"type": "d100", "value": 80}, {"type": "d10", "value": 3}],
         "total": 83, "notation": "1d100", "date": "x"},
        # Attack + damage rolled together: d20 present. Must NOT be heaviest.
        {"rolls": [{"type": "d20", "value": 18}, {"type": "d6", "value": 5}],
         "total": 23, "notation": "1d20+1d6", "date": "x"},
        # Pure damage: 2d6, total 9. SHOULD be heaviest.
        {"rolls": [{"type": "d6", "value": 5}, {"type": "d6", "value": 4}],
         "total": 9, "notation": "2d6", "date": "x"},
    ]
    f = compute_fortune(events)
    assert f["heaviest"] == {"total": 9, "notation": "2d6"}

def test_other_dice_omits_units_d10_paired_with_d100():
    events = [
        # Percentile: d100 + d10 (units). Both must be skipped.
        {"rolls": [{"type": "d100", "value": 80}, {"type": "d10", "value": 3}],
         "total": 83, "notation": "1d100", "date": "2026-04-01"},
        # Standalone d10 damage roll: must be kept.
        {"rolls": [{"type": "d10", "value": 7}],
         "total": 7, "notation": "1d10", "date": "2026-04-02"},
    ]
    rows = compute_other_dice(events)
    d10_rows = [r for r in rows if r["die"] == "d10"]
    assert len(d10_rows) == 1
    assert d10_rows[0]["count"] == 1
    assert d10_rows[0]["dots"][0]["value"] == 7

def test_best_skill_picks_highest_mod():
    member = {"skills": {
        "perception": {"mod": 2, "prof": "none"},
        "stealth": {"mod": 5, "prof": "full"},
        "persuasion": {"mod": 3, "prof": "full"},
    }}
    assert compute_best_skill(member) == {"name": "Stealth", "mod": 5}

def test_best_skill_tie_broken_by_proficiency_rank():
    # Two skills tied at +5; expertise wins over full.
    member = {"skills": {
        "intimidation": {"mod": 5, "prof": "full"},
        "persuasion": {"mod": 5, "prof": "expertise"},
    }}
    assert compute_best_skill(member) == {"name": "Persuasion", "mod": 5}

def test_best_skill_humanizes_camelcase_keys():
    member = {"skills": {
        "sleightOfHand": {"mod": 4, "prof": "full"},
        "perception": {"mod": 1, "prof": "none"},
    }}
    assert compute_best_skill(member) == {"name": "Sleight of Hand", "mod": 4}

def test_name_to_token_name_strips_diacritics_and_quotes():
    assert _name_to_token_name("Naïve") == "Naive"
    assert _name_to_token_name('Ælf "Foo" Bar') == "AElf Foo Bar"
    assert _name_to_token_name("Sahuagin Warrior") == "Sahuagin Warrior"

def test_creature_token_url_returns_none_when_hasToken_is_false():
    assert _creature_token_url({"name": "Generic", "source": "MM", "hasToken": False}) is None
    assert _creature_token_url({"name": "Generic", "source": "MM"}) is None

def test_creature_token_url_constructs_5etools_path():
    url = _creature_token_url({"name": "Sahuagin Warrior", "source": "XMM", "hasToken": True})
    assert url == "https://5e.tools/img/bestiary/tokens/XMM/Sahuagin%20Warrior.webp"

def test_creature_token_url_honors_token_override():
    # 5etools entries can carry an explicit `token: {name, source}` override.
    url = _creature_token_url({
        "name": "Foo (variant)", "source": "MM", "hasToken": True,
        "token": {"name": "Foo", "source": "VGM"},
    })
    assert url == "https://5e.tools/img/bestiary/tokens/VGM/Foo.webp"

def test_d20_histogram_emits_all_20_bars():
    physicals = [20, 20, 1, 10]
    bars = compute_d20_histogram(physicals, party_max=2)
    assert len(bars) == 20
    assert bars[0]["value"] == 1
    assert bars[19]["value"] == 20
    bar20 = next(b for b in bars if b["value"] == 20)
    assert bar20["count"] == 2
    bar5 = next(b for b in bars if b["value"] == 5)
    assert bar5["count"] == 0
    assert bar5["zero"] is True


def test_compute_intro_meta_typical():
    log = {"entries": [{"iu_month": "Kythorn", "iu_year": 1494}] * 5}
    assert compute_intro_meta(log) == "Five Sessions &middot; Kythorn 1494 DR"

def test_compute_intro_meta_singular():
    log = {"entries": [{"iu_month": "Hammer", "iu_year": 1495}]}
    assert compute_intro_meta(log) == "One Session &middot; Hammer 1495 DR"

def test_compute_intro_meta_uses_latest_entry_month_and_year():
    log = {"entries": [
        {"iu_month": "Kythorn", "iu_year": 1494},
        {"iu_month": "Kythorn", "iu_year": 1494},
        {"iu_month": "Flamerule", "iu_year": 1494},
    ]}
    assert compute_intro_meta(log) == "Three Sessions &middot; Flamerule 1494 DR"

def test_compute_intro_meta_word_form_through_twenty():
    log = {"entries": [{"iu_month": "Kythorn", "iu_year": 1494}] * 20}
    assert compute_intro_meta(log) == "Twenty Sessions &middot; Kythorn 1494 DR"

def test_compute_intro_meta_digit_form_above_twenty():
    log = {"entries": [{"iu_month": "Kythorn", "iu_year": 1494}] * 21}
    assert compute_intro_meta(log) == "21 Sessions &middot; Kythorn 1494 DR"

def test_compute_intro_meta_empty_log():
    assert compute_intro_meta({"entries": []}) == "No Sessions Yet"

def test_compute_intro_meta_missing_entries_key():
    assert compute_intro_meta({}) == "No Sessions Yet"


# ── _compute_party_top_xp ──────────────────────────────────────────────

def _party_with_xp(*pairs):
    """Build a (party, trials) pair from (id, xp) tuples. GM is always added."""
    members = [{"id": cid, "name": cid.title(), "image": f"{cid}.png"}
               for cid, _ in pairs]
    members.append({"id": "gm", "name": "GM", "image": "GM.png"})
    party = {"members": members}
    per = {cid: {"xp": xp, "kill_count": 0} for cid, xp in pairs}
    per["gm"] = {"xp": 9999, "kill_count": 0}  # GM XP must be ignored
    return party, {"per_char": per}


def test_party_top_xp_orders_by_xp_descending():
    party, trials = _party_with_xp(("anton", 100), ("vex", 300), ("urida", 200))
    top = _compute_party_top_xp(party, trials, n=3)
    assert [m["id"] for m in top] == ["vex", "urida", "anton"]


def test_party_top_xp_excludes_gm_even_if_gm_has_highest_xp():
    party, trials = _party_with_xp(("anton", 100), ("vex", 50))
    top = _compute_party_top_xp(party, trials, n=5)
    assert "gm" not in [m["id"] for m in top]
    assert [m["id"] for m in top] == ["anton", "vex"]


def test_party_top_xp_tiebreak_alphabetical_by_id():
    party, trials = _party_with_xp(("vex", 100), ("anton", 100), ("grieg", 100))
    top = _compute_party_top_xp(party, trials, n=3)
    assert [m["id"] for m in top] == ["anton", "grieg", "vex"]


def test_party_top_xp_clamps_to_n():
    party, trials = _party_with_xp(("a", 50), ("b", 40), ("c", 30), ("d", 20), ("e", 10))
    top = _compute_party_top_xp(party, trials, n=3)
    assert [m["id"] for m in top] == ["a", "b", "c"]


def test_party_top_xp_handles_member_missing_from_trials():
    # New party member with no rolls/kills yet — defaults to xp=0, sorts last by id.
    party, trials = _party_with_xp(("vex", 50), ("anton", 50))
    party["members"].insert(0, {"id": "newcomer", "name": "Newcomer", "image": "x.png"})
    top = _compute_party_top_xp(party, trials, n=3)
    assert [m["id"] for m in top] == ["anton", "vex", "newcomer"]


# ── _compute_header_eyebrow ────────────────────────────────────────────

def test_header_eyebrow_typical():
    chronicle = {"rail": [{"month": "Kythorn", "year": "1494 DR"}]}
    ledger = {"sessions_kept": 5}
    assert _compute_header_eyebrow(chronicle, ledger) == [
        "Volume I", "Kythorn 1494 DR", "5 Sessions Kept",
    ]


def test_header_eyebrow_uses_latest_rail_entry():
    chronicle = {"rail": [
        {"month": "Hammer",   "year": "1494 DR"},
        {"month": "Flamerule","year": "1494 DR"},
    ]}
    assert _compute_header_eyebrow(chronicle, {"sessions_kept": 2})[1] == "Flamerule 1494 DR"


def test_header_eyebrow_singular_session_word():
    eyebrow = _compute_header_eyebrow(
        {"rail": [{"month": "Hammer", "year": "1495 DR"}]},
        {"sessions_kept": 1},
    )
    assert eyebrow[-1] == "1 Session Kept"


def test_header_eyebrow_omits_session_line_when_zero():
    eyebrow = _compute_header_eyebrow(
        {"rail": [{"month": "Kythorn", "year": "1494 DR"}]},
        {"sessions_kept": 0},
    )
    assert eyebrow == ["Volume I", "Kythorn 1494 DR"]


def test_header_eyebrow_handles_empty_rail():
    eyebrow = _compute_header_eyebrow({"rail": []}, {"sessions_kept": 3})
    assert eyebrow == ["Volume I", "3 Sessions Kept"]


def test_header_eyebrow_handles_missing_keys():
    # Rail without month/year fields collapses to an empty-string line, which is filtered.
    eyebrow = _compute_header_eyebrow({"rail": [{}]}, {})
    assert eyebrow == ["Volume I"]


# ── compute_constellation links ────────────────────────────────────────

def _consteltation_inputs(*xp_pairs):
    """Build (party, fortune_by_char, trials) for compute_constellation tests."""
    members = [{"id": cid, "name": cid.title()} for cid, _ in xp_pairs]
    party = {"members": members}
    trials = {"per_char": {cid: {"xp": xp, "kill_count": 0}
                            for cid, xp in xp_pairs}}
    fortune_by_char = {cid: {
        "rolls_total": 10, "kept_d20s_count": 8, "avg": 10.0, "sd": 1.0,
        "crits": 0, "fumbles": 0,
    } for cid, _ in xp_pairs}
    return party, fortune_by_char, trials


def test_constellation_links_empty_when_fewer_than_two_stars():
    party, fortune, trials = _consteltation_inputs(("anton", 100))
    result = compute_constellation(party, fortune, trials)
    assert result["links"] == []


def test_constellation_links_empty_when_no_stars():
    result = compute_constellation({"members": []}, {}, {"per_char": {}})
    assert result["links"] == []


def test_constellation_links_form_a_closed_loop():
    party, fortune, trials = _consteltation_inputs(
        ("anton", 100), ("vex", 200), ("urida", 300)
    )
    result = compute_constellation(party, fortune, trials)
    # Closed polygon: N stars → N segments, last connects back to first.
    assert len(result["links"]) == 3
    # Segments chain end-to-end (a→b, b→c, c→a).
    for i in range(3):
        a = result["links"][i]
        b = result["links"][(i + 1) % 3]
        assert (a["x2"], a["y2"]) == (b["x1"], b["y1"])


def test_constellation_links_ordered_by_xp_ascending():
    # Pass members in non-monotonic order to confirm the sort happens inside.
    party, fortune, trials = _consteltation_inputs(
        ("vex", 200), ("anton", 100), ("urida", 300)
    )
    result = compute_constellation(party, fortune, trials)
    star_by_id = {s["id"]: s for s in result["stars"]}
    # First link starts at lowest-xp star (anton), runs to next-lowest (vex).
    first = result["links"][0]
    assert (first["x1"], first["y1"]) == (
        star_by_id["anton"]["left_pct"] * 10, star_by_id["anton"]["top_pct"] * 10,
    )
    assert (first["x2"], first["y2"]) == (
        star_by_id["vex"]["left_pct"] * 10, star_by_id["vex"]["top_pct"] * 10,
    )


# ── compute_radar ──────────────────────────────────────────────────────

def _radar_member(scores, prof=()):
    return {
        "abilities": {k: scores[k] for k in ("str", "dex", "con", "int", "wis", "cha")},
        "savingThrows": {k: {"mod": 0, "prof": k in prof}
                         for k in ("str", "dex", "con", "int", "wis", "cha")},
    }

def test_radar_returns_six_of_each_element():
    r = compute_radar(_radar_member({"str": 12, "dex": 12, "con": 12,
                                     "int": 12, "wis": 12, "cha": 12}))
    assert len(r["axes"]) == 6
    assert len(r["dots"]) == 6
    assert len(r["labels"]) == 6
    assert len(r["sectors"]) == 6
    assert len(r["rings"]) == 6           # rings at 10,12,14,16,18,20
    assert len(r["shape"].split(" ")) == 6

def test_radar_top_axis_vertex_uses_score_scale():
    # STR is index 0 = straight up. score 14 -> radius (14-8)/12*76 = 38 -> y = 120-38 = 82.
    r = compute_radar(_radar_member({"str": 14, "dex": 8, "con": 8,
                                     "int": 8, "wis": 8, "cha": 8}))
    assert r["dots"][0] == {"i": 0, "key": "str", "x": 120.0, "y": 82.0, "prof": False}
    assert r["shape"].split(" ")[0] == "120.0,82.0"

def test_radar_clamps_low_scores_to_center():
    # score 6 (below floor 8) clamps to center (120,120).
    r = compute_radar(_radar_member({"str": 6, "dex": 8, "con": 8,
                                     "int": 8, "wis": 8, "cha": 8}))
    assert r["dots"][0]["x"] == 120.0 and r["dots"][0]["y"] == 120.0
    # score 8 (floor) also sits at center.
    assert r["dots"][1]["x"] == 120.0 and r["dots"][1]["y"] == 120.0

def test_radar_radius_increases_with_score():
    # Distance from center grows monotonically: 8 (center) < 14 < 20 (outer ring).
    def top_y(score):
        return compute_radar(_radar_member({"str": score, "dex": 8, "con": 8,
                                            "int": 8, "wis": 8, "cha": 8}))["dots"][0]["y"]
    assert top_y(20) < top_y(14) < top_y(8)   # smaller y = farther up = bigger radius
    assert top_y(20) == 44.0                  # outer ring: 120 - 76
    assert top_y(22) == top_y(20)   # scores above the ceiling clamp to the outer ring

def test_radar_missing_abilities_defaults_to_center():
    r = compute_radar({"abilities": {}, "savingThrows": {}})
    for dot in r["dots"]:
        assert dot["x"] == 120.0 and dot["y"] == 120.0

def test_radar_marks_proficient_saves():
    r = compute_radar(_radar_member({"str": 10, "dex": 10, "con": 10,
                                     "int": 10, "wis": 10, "cha": 10},
                                    prof=("dex", "cha")))
    by_key = {d["key"]: d["prof"] for d in r["dots"]}
    assert by_key == {"str": False, "dex": True, "con": False,
                      "int": False, "wis": False, "cha": True}

def test_radar_sector_path_is_a_closed_wedge():
    r = compute_radar(_radar_member({"str": 12, "dex": 12, "con": 12,
                                     "int": 12, "wis": 12, "cha": 12}))
    d = r["sectors"][0]["d"]
    assert d.startswith("M120 120 L")   # wedge starts at center
    assert " A112 112 " in d            # arc at the hit radius
    assert d.endswith("Z")              # closed


def test_constellation_links_tiebreak_by_id_when_xp_equal():
    # Identical xp but different rolls → each star is its own cluster, so
    # the (xp, id) tiebreak in the link sort is what matters here.
    party, fortune, trials = _consteltation_inputs(
        ("vex", 100), ("anton", 100), ("grieg", 100)
    )
    fortune["anton"]["rolls_total"] = 30
    fortune["grieg"]["rolls_total"] = 20
    fortune["vex"]["rolls_total"] = 10
    result = compute_constellation(party, fortune, trials)
    # Sort key is (xp, id) ascending → anton, grieg, vex.
    star_by_id = {s["id"]: s for s in result["stars"]}
    expected_order = ["anton", "grieg", "vex"]
    for i, cid in enumerate(expected_order):
        nxt = expected_order[(i + 1) % 3]
        link = result["links"][i]
        assert (link["x1"], link["y1"]) == (
            star_by_id[cid]["left_pct"] * 10, star_by_id[cid]["top_pct"] * 10,
        )
        assert (link["x2"], link["y2"]) == (
            star_by_id[nxt]["left_pct"] * 10, star_by_id[nxt]["top_pct"] * 10,
        )


# ── compute_constellation systems (collision handling) ────────────────

def test_constellation_no_collision_means_no_systems():
    party, fortune, trials = _consteltation_inputs(("anton", 100), ("vex", 200))
    result = compute_constellation(party, fortune, trials)
    assert result["systems"] == []
    for s in result["stars"]:
        assert s["system_size"] == 1
        assert s["orbit_x_px"] == 0
        assert s["orbit_y_px"] == 0


def test_constellation_collision_creates_system():
    # Identical xp + identical rolls → both stars round to the same coord.
    party, fortune, trials = _consteltation_inputs(("vex", 100), ("grieg", 100))
    result = compute_constellation(party, fortune, trials)
    assert len(result["systems"]) == 1
    sys = result["systems"][0]
    assert sys["size"] == 2
    for s in result["stars"]:
        assert s["system_size"] == 2
        assert (s["left_pct"], s["top_pct"]) == (sys["left_pct"], sys["top_pct"])


def test_constellation_binary_orbit_offsets_are_mirrored():
    # n=2 → horizontal pair, offsets sum to zero on x and stay flat on y.
    party, fortune, trials = _consteltation_inputs(("vex", 100), ("grieg", 100))
    result = compute_constellation(party, fortune, trials)
    xs = sorted(s["orbit_x_px"] for s in result["stars"])
    assert xs[0] == -xs[1]
    assert xs[1] > 0
    for s in result["stars"]:
        assert s["orbit_y_px"] == 0


def test_constellation_clusters_near_misses():
    # Stars whose portraits would visibly overlap on the rendered plot
    # cluster even when their rounded coords aren't identical. Here vex and
    # grieg have nearly the same rolls — a 1-vs-2 difference rounds to
    # adjacent (top_pct = 4 vs 6), which puts the 72px portraits ~8px apart
    # on the y-axis and almost fully on top of each other.
    party, fortune, trials = _consteltation_inputs(
        ("vex", 100), ("grieg", 100)
    )
    fortune["vex"]["rolls_total"] = 100
    fortune["grieg"]["rolls_total"] = 98
    result = compute_constellation(party, fortune, trials)
    assert len(result["systems"]) == 1
    assert result["systems"][0]["size"] == 2


def test_constellation_links_dedupe_through_clusters():
    # vex + grieg collide; anton stands alone. Two cluster nodes → two links.
    party, fortune, trials = _consteltation_inputs(
        ("anton", 50), ("vex", 200), ("grieg", 200)
    )
    result = compute_constellation(party, fortune, trials)
    assert len(result["systems"]) == 1
    assert len(result["links"]) == 2  # closed loop of 2 nodes
    sys_center = (result["systems"][0]["left_pct"] * 10,
                  result["systems"][0]["top_pct"] * 10)
    anton = next(s for s in result["stars"] if s["id"] == "anton")
    anton_pos = (anton["left_pct"] * 10, anton["top_pct"] * 10)
    endpoints = set()
    for link in result["links"]:
        endpoints.add((link["x1"], link["y1"]))
        endpoints.add((link["x2"], link["y2"]))
    assert endpoints == {sys_center, anton_pos}


def test_constellation_links_excludes_gm():
    # GM is filtered from the star list; must not appear as a link endpoint.
    members = [
        {"id": "anton", "name": "Anton"},
        {"id": "vex",   "name": "Vex"},
        {"id": "gm",    "name": "GM"},
    ]
    party = {"members": members}
    trials = {"per_char": {
        "anton": {"xp": 100, "kill_count": 0},
        "vex":   {"xp": 200, "kill_count": 0},
        "gm":    {"xp": 9999, "kill_count": 0},
    }}
    fortune_by_char = {cid: {
        "rolls_total": 5, "kept_d20s_count": 4, "avg": 10.0, "sd": 1.0,
        "crits": 0, "fumbles": 0,
    } for cid in ("anton", "vex", "gm")}
    result = compute_constellation(party, fortune_by_char, trials)
    assert {s["id"] for s in result["stars"]} == {"anton", "vex"}
    assert len(result["links"]) == 2  # two stars → closed loop has two segments

# -- Fact pack: kill-derived atoms -------------------------------------------

def _session_log(dates):
    """Build a minimal session log: one entry per date, session ids 1..N."""
    return {"entries": [{"session": i + 1, "date": d, "text": ""} for i, d in enumerate(dates)]}

def test_fact_pack_kill_pattern_atoms():
    party = {"members": [
        {"id": "a", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-08", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-08", "creature": "Goblin", "method": "Longbow"},
        ]},
        {"id": "b", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Dagger"},
            {"date": "2026-04-15", "creature": "Bandit", "method": "Longbow"},
        ]},
    ]}
    trials = compute_trials(party)
    fortune = {"a": compute_fortune([]), "b": compute_fortune([])}
    constellation = compute_constellation(party, fortune, trials)
    log = _session_log(["2026-04-01", "2026-04-08", "2026-04-15"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)

    assert fp["a"]["kill_count"] == 3
    assert fp["a"]["all_kills_one_method"] is True
    assert fp["a"]["distinct_method_count"] == 1
    assert fp["a"]["all_distinct_creatures"] is False     # Goblin thrice
    assert fp["a"]["max_kills_in_one_session"] == 2        # two on 2026-04-08
    assert fp["a"]["kill_session_count"] == 2

    assert fp["b"]["all_kills_one_method"] is False        # Dagger + Longbow
    assert fp["b"]["distinct_method_count"] == 2
    assert fp["b"]["all_distinct_creatures"] is True       # Goblin + Bandit
    assert fp["b"]["max_kills_in_one_session"] == 1

def test_fact_pack_longest_drought_counts_interior_silent_sessions():
    party = {"members": [
        {"id": "a", "kills": [
            {"date": "2026-04-01", "creature": "Goblin", "method": "Longbow"},
            {"date": "2026-04-22", "creature": "Goblin", "method": "Longbow"},
        ]},
    ]}
    trials = compute_trials(party)
    fortune = {"a": compute_fortune([])}
    constellation = compute_constellation(party, fortune, trials)
    # Campaign sessions on 4 dates; PC killed only on the 1st and 4th.
    log = _session_log(["2026-04-01", "2026-04-08", "2026-04-15", "2026-04-22"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)
    assert fp["a"]["longest_drought"] == 2   # two silent sessions between

# -- Fact pack: roll-derived atoms -------------------------------------------

def _d20_events(values, date="2026-04-01"):
    return [{"rolls": [{"type": "d20", "value": v, "dropped": False}],
             "total": v, "notation": "1d20", "date": date} for v in values]

def test_fact_pack_roll_rank_booleans():
    party = {"members": [
        {"id": "a", "kills": []},
        {"id": "b", "kills": []},
    ]}
    trials = compute_trials(party)
    fortune = {
        # a: high average, two crits, both on the same date
        "a": compute_fortune(_d20_events([20, 20, 18, 16])),
        # b: low average, one fumble
        "b": compute_fortune(_d20_events([1, 5, 8, 6])),
    }
    constellation = compute_constellation(party, fortune, trials)
    log = _session_log(["2026-04-01"])
    fp = compute_fact_pack(party, trials, fortune, constellation, log)

    assert fp["a"]["is_party_luckiest"] is True
    assert fp["a"]["is_party_unluckiest"] is False
    assert fp["a"]["crits"] == 2
    assert fp["a"]["is_party_most_crits"] is True
    assert fp["a"]["max_crits_in_one_session"] == 2
    assert fp["b"]["is_party_unluckiest"] is True
    assert fp["b"]["fumbles"] == 1
    assert fp["b"]["is_party_most_fumbles"] is True

def test_fact_pack_heaviest_blow_rank():
    party = {"members": [{"id": "a", "kills": []}, {"id": "b", "kills": []}]}
    trials = compute_trials(party)
    fortune = {
        "a": compute_fortune([{"rolls": [{"type": "d8", "value": 7}], "total": 7,
                               "notation": "1d8", "date": "2026-04-01"}]),
        "b": compute_fortune([{"rolls": [{"type": "d12", "value": 11}], "total": 11,
                               "notation": "1d12", "date": "2026-04-01"}]),
    }
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))
    assert fp["b"]["heaviest_blow"] == 11
    assert fp["b"]["is_party_heaviest"] is True
    assert fp["a"]["is_party_heaviest"] is False

# -- Fact pack: constellation-context atoms ----------------------------------

def test_fact_pack_quadrant_and_system_size():
    party = {"members": [
        {"id": "hi", "kills": [{"date": "2026-04-01", "creature": "Ogre", "method": "Maul"}]},
        {"id": "lo", "kills": []},
    ]}
    trials = compute_trials(party)
    fortune = {
        "hi": compute_fortune(_d20_events([10, 11, 12, 13, 14])),  # more rolls = more presence
        "lo": compute_fortune(_d20_events([9])),
    }
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))

    # hi has more XP (a kill) and more rolls than lo.
    assert fp["hi"]["quadrant"] == "hi-presence/hi-contribution"
    assert fp["lo"]["quadrant"] == "lo-presence/lo-contribution"
    # Two stars far apart → each alone in its own system.
    assert fp["hi"]["system_size"] == 1
    assert fp["hi"]["is_constellation_outlier"] is True

def test_fact_pack_rank_booleans_flag_all_tied_holders():
    party = {"members": [{"id": "a", "kills": []}, {"id": "b", "kills": []}]}
    trials = compute_trials(party)
    fortune = {
        "a": compute_fortune(_d20_events([20, 10])),  # one crit each, equal avg
        "b": compute_fortune(_d20_events([20, 10])),
    }
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))
    assert fp["a"]["is_party_most_crits"] is True
    assert fp["b"]["is_party_most_crits"] is True
    assert fp["a"]["is_party_luckiest"] is True and fp["b"]["is_party_luckiest"] is True

def test_fact_pack_exposes_raw_axis_values():
    # The constellation epithet reasons about real positions on the two axes
    # (rolls cast, experience earned), not the coarse hi/lo split — so the raw
    # values must be in the pack.
    party = {"members": [
        {"id": "a", "kills": [{"date": "2026-04-01", "creature": "Goblin", "method": "Bow"}]},
        {"id": "b", "kills": []},
    ]}
    trials = compute_trials(party)
    fortune = {"a": compute_fortune(_d20_events([10, 12, 14])), "b": compute_fortune(_d20_events([8]))}
    constellation = compute_constellation(party, fortune, trials)
    fp = compute_fact_pack(party, trials, fortune, constellation, _session_log(["2026-04-01"]))
    assert fp["a"]["rolls"] == 3 == fortune["a"]["rolls_total"]
    assert fp["a"]["xp"] == trials["per_char"]["a"]["xp"]
    assert fp["b"]["rolls"] == 1
