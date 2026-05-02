"""Tests for build/inventory.py — the inventory loader/classifier/scorer."""
import pytest

from build import inventory


def test_module_exposes_load():
    assert hasattr(inventory, "load")
    assert callable(inventory.load)


def test_resolve_snapshot_path_picks_latest(tmp_path):
    (tmp_path / "obr-inv-backup-2026-04-01T00-00-00-000Z.json").write_text("{}")
    (tmp_path / "obr-inv-backup-2026-05-02T04-21-16-825Z.json").write_text("{}")
    (tmp_path / "obr-inv-backup-2026-04-15T12-00-00-000Z.json").write_text("{}")
    (tmp_path / "unrelated.json").write_text("{}")

    path = inventory._resolve_snapshot_path(tmp_path)

    assert path is not None
    assert path.name == "obr-inv-backup-2026-05-02T04-21-16-825Z.json"


def test_resolve_snapshot_path_returns_none_when_missing(tmp_path):
    assert inventory._resolve_snapshot_path(tmp_path) is None


def test_parse_inventories_drops_gm_and_resolves_names():
    raw = {
        "inventories": {
            "uuid-1": {
                "name": "Simon Weil",
                "items": [{"id": "x", "count": 1, "name": "Sword",
                           "category": "Weapon", "weight": 3, "rarity": "common",
                           "icon": "https://example/sword.svg",
                           "description": ""}],
            },
            "uuid-2": {
                "name": "GM",
                "items": [{"id": "y", "count": 1, "name": "Junk",
                           "category": "Adventuring Gear - Utility & Equipment",
                           "weight": 1, "rarity": "common", "icon": "",
                           "description": ""}],
            },
            "uuid-3": {
                "name": "Vex",
                "items": [],
            },
        },
    }
    mapping = {"Simon": "grieg", "Vex": "vex", "GM": "gm"}

    parsed = inventory._parse_inventories(raw, mapping)

    assert set(parsed.keys()) == {"grieg", "vex"}
    assert "gm" not in parsed  # GM dropped before resolution
    assert "Weil" not in str(parsed)  # surname scrubbed
    assert parsed["grieg"]["items"][0]["name"] == "Sword"


def test_parse_inventories_skips_unresolved_name():
    raw = {
        "inventories": {
            "uuid-1": {"name": "Stranger", "items": []},
            "uuid-2": {"name": "Vex", "items": []},
        },
    }
    mapping = {"Vex": "vex"}

    parsed = inventory._parse_inventories(raw, mapping)

    assert set(parsed.keys()) == {"vex"}


def _item(name, category, rarity="common", weight=1, count=1):
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "category": category,
        "rarity": rarity,
        "weight": weight,
        "count": count,
        "icon": "",
        "description": "",
    }


def test_classify_separates_rack_spotlight_manifest():
    items = [
        _item("Warhammer", "Weapon"),
        _item("Scale Mail", "Armor", weight=45),
        _item("Crossbow Bolts", "Ammunition", count=20),
        _item("Sending Stones", "Wondrous Item", rarity="uncommon"),
        _item("Staff", "Spellcasting Focus"),
        _item("Rations", "Adventuring Gear - Camping & Travel", count=5),
        _item("Backpack", "Adventuring Gear - Containers & Storage"),
        _item("Costume", "Clothing"),
    ]

    rack, spotlight, manifest = inventory._classify(items)

    rack_names = {it["name"] for it in rack}
    spotlight_names = {it["name"] for it in spotlight}
    manifest_names = {it["name"] for it in manifest}

    assert rack_names == {"Warhammer", "Scale Mail", "Crossbow Bolts"}
    assert spotlight_names == {"Sending Stones", "Staff"}
    assert manifest_names == {"Rations", "Backpack", "Costume"}


def test_classify_caps_spotlight_at_three():
    items = [_item(f"Curio {i}", "Wondrous Item", rarity="rare") for i in range(5)]

    rack, spotlight, manifest = inventory._classify(items)

    assert len(spotlight) == 3
    assert len(manifest) == 2  # spillover lands in Manifest
    assert rack == []


def test_classify_spotlight_ranks_higher_rarity_first():
    items = [
        _item("Bauble", "Wondrous Item", rarity="common"),
        _item("Greater Curio", "Wondrous Item", rarity="rare"),
        _item("Lesser Curio", "Wondrous Item", rarity="uncommon"),
        _item("Marvel", "Wondrous Item", rarity="legendary"),
    ]

    _, spotlight, _ = inventory._classify(items)

    spotlight_names = [it["name"] for it in spotlight]
    assert spotlight_names == ["Marvel", "Greater Curio", "Lesser Curio"]


def test_total_weight_sums_count_times_weight_with_null_as_zero():
    items = [
        {"weight": 4, "count": 1},
        {"weight": 2, "count": 5},
        {"weight": None, "count": 1},
        {"weight": 0, "count": 3},
    ]
    assert inventory._total_weight(items) == 14


def test_carrying_capacity_is_15_times_str():
    member = {"abilities": {"str": 17}}
    assert inventory._carrying_capacity(member) == 255


def test_zone_breakdown_matches_total():
    rack = [{"weight": 4, "count": 2}]            # 8
    spotlight = [{"weight": None, "count": 1}]     # 0
    manifest = [{"weight": 1, "count": 5},         # 5
                {"weight": 2, "count": 3}]         # 6

    breakdown = inventory._zone_breakdown(rack, spotlight, manifest)

    assert breakdown == {"rack": 8, "spotlight": 0, "manifest": 11}
    assert sum(breakdown.values()) == 19


def test_pack_mule_score_is_total_weight():
    items = [{"weight": 4, "count": 2}, {"weight": 1, "count": 3}]
    assert inventory.score_pack_mule(items, member={}) == 11.0


def test_armorer_sums_weapons_and_armor_only():
    items = [
        {"category": "Weapon", "weight": 5, "count": 1},
        {"category": "Armor", "weight": 45, "count": 1},
        {"category": "Adventuring Gear - Camping & Travel", "weight": 10, "count": 1},
        {"category": "Ammunition", "weight": 1, "count": 20},  # not in armorer
    ]
    assert inventory.score_armorer(items, member={}) == 50.0


def test_glaive_hand_counts_distinct_weapon_ids():
    items = [
        {"category": "Weapon", "id": "a", "count": 1},
        {"category": "Weapon", "id": "b", "count": 1},
        {"category": "Weapon", "id": "a", "count": 1},  # same id; not distinct
        {"category": "Armor", "id": "c", "count": 1},
    ]
    assert inventory.score_glaive_hand(items, member={}) == 2


def test_quiver_sums_ammunition_counts():
    items = [
        {"category": "Ammunition", "count": 20},
        {"category": "Ammunition", "count": 12},
        {"category": "Weapon", "count": 1},
    ]
    assert inventory.score_quiver(items, member={}) == 32


def test_curio_keeper_counts_non_common_or_wondrous():
    items = [
        {"rarity": "rare", "category": "Weapon"},
        {"rarity": "common", "category": "Wondrous Item"},
        {"rarity": "common", "category": "Weapon"},
        {"rarity": "uncommon", "category": "Adventuring Gear - Utility & Equipment"},
    ]
    assert inventory.score_curio_keeper(items, member={}) == 3


def test_scholar_substring_match_on_lore_keywords():
    items = [
        {"name": "Spellbook", "count": 1},
        {"name": "Parchment (x10)", "count": 10},
        {"name": "Ink Pen", "count": 1},
        {"name": "Sword", "count": 1},  # no match
    ]
    # spellbook + parchment + ink → 3 matches; counts summed
    assert inventory.score_scholar(items, member={}) == 12


def test_naturalist_substring_match():
    items = [
        {"name": "Sprig of Mistletoe (Druidic Focus)", "count": 1},
        {"name": "Yew Wand", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_naturalist(items, member={}) == 2


def test_tongues_substring_match():
    items = [
        {"name": "Sending Stone (Azlund)", "count": 1},
        {"name": "Whisper Charm", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_tongues(items, member={}) == 2


def test_lamplighter_sums_light_items():
    items = [
        {"name": "Oil (x10)", "count": 10},
        {"name": "Torch", "count": 5},
        {"name": "Lantern", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_lamplighter(items, member={}) == 16


def test_pathfinder_sums_explore_items():
    items = [
        {"name": "Rope (50 ft)", "count": 1},
        {"name": "Crowbar", "count": 1},
        {"name": "Iron Spike", "count": 8},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_pathfinder(items, member={}) == 10


def test_apothecary_counts_consumables():
    items = [
        {"category": "Consumable", "count": 2},
        {"category": "Consumable", "count": 1},
        {"category": "Weapon", "count": 1},
    ]
    assert inventory.score_apothecary(items, member={}) == 3


def test_cellarer_sums_food_items():
    items = [
        {"name": "Rations (x9)", "count": 9},
        {"name": "Waterskin", "count": 1},
        {"name": "Wineskin", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_cellarer(items, member={}) == 11


def test_trapper_sums_traps():
    items = [
        {"name": "Caltrops (x20)", "count": 20},
        {"name": "Hunting Trap", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_trapper(items, member={}) == 21


def test_costume_master_sums_persona_items():
    items = [
        {"name": "Costume (x3)", "count": 3},
        {"name": "Perfume", "count": 1},
        {"name": "Fine Clothes", "count": 1},
        {"name": "Sword", "count": 1},
    ]
    assert inventory.score_costume_master(items, member={}) == 5


def test_quartermaster_counts_distinct_ids():
    items = [
        {"id": "a", "count": 1},
        {"id": "b", "count": 5},
        {"id": "c", "count": 1},
    ]
    assert inventory.score_quartermaster(items, member={}) == 3


def test_featherfoot_is_carry_ratio_inverted():
    member = {"abilities": {"str": 6}}  # capacity 90
    items = [{"weight": 9, "count": 1}]   # 9 lb → 10% utilization
    # Score is inverted utilization (so higher = more decisively unburdened).
    # 10% utilization → score 90.0
    assert inventory.score_featherfoot(items, member) == pytest.approx(90.0)
