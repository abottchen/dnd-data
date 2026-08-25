from pathlib import Path
import pytest
from build.render import bestiary_lookup, BESTIARY_GLOB, CUSTOM_NPC_STATBLOCKS

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

def test_custom_npc_borrows_statblock_but_keeps_name(bestiary_dir):
    # Named NPCs in CUSTOM_NPC_STATBLOCKS resolve via their stat block for
    # type/CR/token, while the entry keeps the NPC's own display name so the
    # bestiary and chronicle still read the NPC, not the stat block.
    for npc, statblock in CUSTOM_NPC_STATBLOCKS.items():
        base = bestiary_lookup(statblock)
        assert base is not None, f"stat block {statblock!r} missing from bestiary"
        info = bestiary_lookup(npc)
        assert info is not None
        assert info["name"] == npc           # display name preserved
        assert info["type"] == base["type"]  # type borrowed (e.g. humanoid)
        assert info["cr"] == base["cr"]
        assert info["token_url"] == base["token_url"]

def test_custom_creature_is_first_class_entry(bestiary_dir):
    # Fully custom creatures in CUSTOM_CREATURES resolve as complete bestiary
    # records — own type, CR, and token image — without borrowing a stat block,
    # so they enter the Kinds Slain tally and earn CR-appropriate XP instead of
    # falling through to CR 0 / 10 XP.
    from build.render import CUSTOM_CREATURES
    from build.bestiary import _kill_xp
    for name, entry in CUSTOM_CREATURES.items():
        info = bestiary_lookup(name)
        assert info is not None
        assert info["name"] == name
        assert info["type"]
        assert info["cr"] is not None
        assert info["token_url"]

def test_aspect_of_imix_cr6(bestiary_dir):
    # Shilku companion-module boss: custom CR 6 elemental with 3e phoenix art.
    from build.bestiary import _kill_xp
    info = bestiary_lookup("Aspect of Imix")
    assert info["type"] == "elemental"
    assert info["cr"] == "6"
    assert _kill_xp("Aspect of Imix") == 2300
