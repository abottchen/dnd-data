from build import xp_for_cr, compute_trials, compute_sessions_chart

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
