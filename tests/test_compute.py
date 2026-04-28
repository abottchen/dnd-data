from build.render import (xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune,
                   compute_d20_histogram, compute_other_dice, compute_best_skill,
                   compute_intro_meta, compute_constellation,
                   _compute_party_top_xp, _compute_header_eyebrow,
                   _creature_token_url, _name_to_token_name)

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
