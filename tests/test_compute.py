from build import xp_for_cr, compute_trials

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
