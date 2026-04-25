from build import xp_for_cr, compute_trials, compute_sessions_chart, compute_fortune, compute_d20_histogram

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
