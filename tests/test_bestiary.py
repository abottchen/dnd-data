from pathlib import Path
import pytest
from build.render import bestiary_lookup, BESTIARY_GLOB

@pytest.fixture
def bestiary_dir():
    p = Path(".claude/ext/5etools-src/data/bestiary")
    if not p.exists():
        pytest.skip("5etools data not present")
    return p

def test_bestiary_lookup_returns_type_for_known_creature(bestiary_dir):
    info = bestiary_lookup("Goblin")
    assert info is not None
    assert info["type"]  # string
    assert info["cr"] is not None

def test_bestiary_lookup_caches(bestiary_dir):
    info1 = bestiary_lookup("Goblin")
    info2 = bestiary_lookup("Goblin")
    assert info1 is info2  # same object from cache

def test_bestiary_lookup_returns_none_for_unknown_creature(bestiary_dir):
    assert bestiary_lookup("Definitely Not A Real Creature 9000") is None
