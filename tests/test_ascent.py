"""Tests for the XP-threshold helpers and compute_ascent geometry."""
from build import render


def test_level_for_xp_boundaries():
    assert render._level_for_xp(0) == 1
    assert render._level_for_xp(299) == 1
    assert render._level_for_xp(300) == 2
    assert render._level_for_xp(899) == 2
    assert render._level_for_xp(900) == 3      # party sits exactly here
    assert render._level_for_xp(2699) == 3
    assert render._level_for_xp(2700) == 4


def test_next_threshold():
    assert render._next_threshold(2) == 900
    assert render._next_threshold(3) == 2700
    assert render._next_threshold(20) is None  # capped
