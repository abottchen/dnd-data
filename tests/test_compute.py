from build import (xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune,
                   compute_d20_histogram, compute_other_dice, compute_best_skill,
                   compute_intro_meta,
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
