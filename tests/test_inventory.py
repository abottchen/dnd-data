"""Tests for build/inventory.py — the inventory loader/classifier/scorer."""
import json
from pathlib import Path

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


def test_parse_inventories_scrubs_parenthetical_player_tag():
    """Anton's upstream entry is named 'Anton(<player>)' — character name plus
    a real player tag in parens. The character-name key resolves the slug; the
    parenthetical real name is discarded with the rest of the upstream `name`
    field and must never reach the output."""
    raw = {
        "inventories": {
            "uuid-1": {
                "name": "Anton(Redacted)",
                "items": [{"id": "a", "count": 1, "name": "Rope"}],
            },
        },
    }
    mapping = {"Anton": "anton"}

    parsed = inventory._parse_inventories(raw, mapping)

    assert set(parsed.keys()) == {"anton"}
    assert "Redacted" not in str(parsed)  # parenthetical player tag scrubbed


def test_parse_inventories_empty_duplicate_does_not_clobber_populated():
    """An Owlbear export can carry two inventories that resolve to the same
    slug — e.g. a player's real token plus a stale, empty duplicate token.
    Iteration order must not let the empty duplicate overwrite the populated
    inventory (which would zero the character's items); the inventory with
    more items wins regardless of order."""
    populated = {"name": "ScorpioTHK",
                 "items": [{"id": "a", "count": 1, "name": "Spellbook"}]}
    empty = {"name": "ScorpioTHK", "items": []}
    mapping = {"ScorpioTHK": "urida"}

    # Populated first, empty second (the order that triggers last-write-wins).
    parsed = inventory._parse_inventories(
        {"inventories": {"u1": populated, "u2": empty}}, mapping)
    assert set(parsed.keys()) == {"urida"}
    assert [it["name"] for it in parsed["urida"]["items"]] == ["Spellbook"]

    # Empty first, populated second — must also keep the populated one.
    parsed = inventory._parse_inventories(
        {"inventories": {"u1": empty, "u2": populated}}, mapping)
    assert [it["name"] for it in parsed["urida"]["items"]] == ["Spellbook"]


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


def test_archetype_slate_contains_all_sixteen():
    slugs = [a["slug"] for a in inventory.ARCHETYPE_SLATE]
    assert slugs == [
        "pack-mule", "armorer", "glaive-hand", "quiver",
        "curio-keeper", "naturalist", "scholar", "tongues",
        "lamplighter", "pathfinder", "apothecary", "cellarer", "trapper",
        "costume-master",
        "quartermaster", "featherfoot",
    ]


def test_each_archetype_has_label_and_scorer():
    for a in inventory.ARCHETYPE_SLATE:
        assert isinstance(a["slug"], str)
        assert a["label"].startswith("THE ")
        assert callable(a["score"])
        assert isinstance(a.get("min_lead", 0), (int, float))


def test_assign_archetypes_picks_top_scorer_per_metric():
    # Two characters, two metrics. Each character should get the metric
    # they decisively dominate.
    chars = {
        "alice": {"items": [{"id": "rope", "name": "Rope", "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"id": "book", "name": "Book", "count": 5}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "scholar", "label": "THE SCHOLAR",
         "score": inventory.score_scholar, "min_lead": 0},
        {"slug": "pathfinder", "label": "THE PATHFINDER",
         "score": inventory.score_pathfinder, "min_lead": 0},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {"alice": "pathfinder", "bob": "scholar"}


def test_assign_archetypes_largest_lead_wins_when_one_char_tops_two():
    # Alice tops both archetypes. Her larger lead is on Pack-Mule (lead=10
    # vs Quartermaster lead=1), so Alice keeps Pack-Mule and Quartermaster
    # falls through to Bob.
    chars = {
        "alice": {"items": [{"id": "x", "weight": 100, "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"id": "x", "weight": 90, "count": 1},
                          {"id": "y", "weight": 0, "count": 1}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "pack-mule", "label": "THE PACK-MULE",
         "score": inventory.score_pack_mule, "min_lead": 0},
        {"slug": "quartermaster", "label": "THE QUARTERMASTER",
         "score": inventory.score_quartermaster, "min_lead": 0},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {"alice": "pack-mule", "bob": "quartermaster"}


def test_assign_archetypes_unawarded_when_min_lead_unmet():
    # Both characters tie on Featherfoot (lead = 0). min_lead = 5 means it
    # goes unawarded.
    chars = {
        "alice": {"items": [{"weight": 0, "count": 1}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"weight": 0, "count": 1}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "featherfoot", "label": "THE FEATHERFOOT",
         "score": inventory.score_featherfoot, "min_lead": 5},
    )

    assignments = inventory._assign_archetypes(chars, slate)

    assert assignments == {}


def test_assign_archetypes_unawarded_when_top_score_zero():
    # Nobody has any books → score_scholar returns 0 for both.
    # No award.
    chars = {
        "alice": {"items": [{"name": "Sword"}],
                  "member": {"abilities": {"str": 10}}},
        "bob": {"items": [{"name": "Hat"}],
                "member": {"abilities": {"str": 10}}},
    }
    slate = (
        {"slug": "scholar", "label": "THE SCHOLAR",
         "score": inventory.score_scholar, "min_lead": 0},
    )

    assert inventory._assign_archetypes(chars, slate) == {}


def test_build_bundle_classifies_totals_and_assigns():
    # Three characters so that cellarer is the largest-lead win for grieg:
    # vex (0 lb) takes featherfoot, anton (100 lb ladder) takes pack-mule,
    # leaving grieg with cellarer as the largest of his remaining leads.
    parsed = {
        "grieg": {"items": [
            {"id": "wh", "name": "Warhammer", "category": "Weapon",
             "weight": 5, "count": 1, "rarity": "common", "icon": "", "description": ""},
            {"id": "rations", "name": "Rations (x9)",
             "category": "Adventuring Gear - Camping & Travel",
             "weight": 2, "count": 9, "rarity": "common", "icon": "", "description": ""},
        ]},
        "vex": {"items": []},
        "anton": {"items": [
            {"id": "ladder", "name": "Ladder",
             "category": "Adventuring Gear - Utility & Equipment",
             "weight": 100, "count": 1, "rarity": "common", "icon": "", "description": ""},
        ]},
    }
    party = {"members": [
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "vex", "name": "Vex", "abilities": {"str": 17}},
        {"id": "anton", "name": "Anton", "abilities": {"str": 17}},
    ]}

    bundle = inventory._build_bundle(parsed, party)

    g = bundle["by_id"]["grieg"]
    assert {it["name"] for it in g["rack"]} == {"Warhammer"}
    assert {it["name"] for it in g["manifest"]} == {"Rations (x9)"}
    assert g["total_weight"] == 23  # 5 + 2*9
    assert g["capacity"] == 255
    # Cellarer keyword "ration" matches Rations.
    assert g["archetype"] == "cellarer"


def test_company_strip_includes_placeholders_for_missing_inventories():
    parsed = {"grieg": {"items": []}}
    party = {"members": [
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "lilac", "name": "Lilac Mist", "abilities": {"str": 8}},
    ]}

    bundle = inventory._build_bundle(parsed, party)
    strip = bundle["company_strip"]

    assert [s["slug"] for s in strip] == ["grieg", "lilac"]
    assert strip[0]["status"] == "ok"
    assert strip[1]["status"] == "awaiting_manifest"
    assert strip[1]["shortname"] == "Lilac"


def test_company_strip_excludes_gm_member():
    parsed = {}
    party = {"members": [
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "gm", "name": "GM", "abilities": {"str": 10}},
    ]}

    strip = inventory._build_bundle(parsed, party)["company_strip"]

    assert [s["slug"] for s in strip] == ["grieg"]


def test_load_returns_empty_bundle_when_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_DATA_DIR", str(tmp_path))
    bundle = inventory.load(tmp_path.parent)
    assert bundle == {"by_id": {}, "company_strip": []}


def test_load_full_pipeline_with_fixture(tmp_path, monkeypatch):
    fixture_dir = tmp_path / "data"
    fixture_dir.mkdir()
    src = (
        Path(__file__).parent / "fixtures" / "inventory"
        / "obr-inv-backup-2026-05-02T04-21-16-825Z.json"
    )
    (fixture_dir / "inventory").mkdir()
    (fixture_dir / "inventory" / src.name).write_text(src.read_text())
    (fixture_dir / "party.json").write_text(json.dumps([
        {"id": "grieg", "name": "Grieg", "abilities": {"str": 17}},
        {"id": "vex",   "name": "Vex",   "abilities": {"str": 12}},
    ]))
    monkeypatch.setenv("BUILD_DATA_DIR", str(fixture_dir))

    bundle = inventory.load(fixture_dir.parent)

    assert set(bundle["by_id"].keys()) == {"grieg", "vex"}
    assert bundle["by_id"]["grieg"]["total_weight"] == 5
    assert "Weil" not in json.dumps(bundle)  # surname scrubbed
    assert [s["slug"] for s in bundle["company_strip"]] == ["grieg", "vex"]


def test_math_inscription_for_pack_mule_uses_total_weight():
    rec = {
        "archetype": "pack-mule",
        "archetype_items": [{"weight": 100, "count": 1}, {"weight": 5, "count": 11}],
        "total_weight": 155.5,
    }
    line = inventory.math_inscription(rec, ranks={"pack-mule": 1})
    assert "155 lb" in line  # 100*1 + 5*11 = 155
    assert "heaviest load" in line


def test_math_inscription_for_cellarer_names_the_provisions():
    rec = {
        "archetype": "cellarer",
        "archetype_items": [
            {"name": "Rations", "count": 9, "weight": 2},
            {"name": "Waterskin", "count": 1, "weight": 5},
        ],
    }
    line = inventory.math_inscription(rec, ranks={"cellarer": 1})
    assert "10" in line  # 9 + 1
    assert "rations and provisions" in line
    assert "most provisions" in line


def test_math_inscription_for_quartermaster_counts_distinct():
    rec = {
        "archetype": "quartermaster",
        "archetype_items": [
            {"id": "a", "count": 1}, {"id": "b", "count": 4}, {"id": "c", "count": 1},
        ],
    }
    line = inventory.math_inscription(rec, ranks={"quartermaster": 1})
    assert "3 distinct items" in line


def test_math_inscription_returns_empty_for_no_archetype():
    rec = {"archetype": None, "total_weight": 0, "item_count": 0}
    assert inventory.math_inscription(rec, ranks={}) == ""


def test_math_inscription_for_featherfoot():
    rec = {"archetype": "featherfoot", "total_weight": 10,
           "capacity": 90, "item_count": 3}
    line = inventory.math_inscription(rec, ranks={"featherfoot": 1})
    assert "11%" in line  # 10/90
    assert "lightest" in line


def test_resolve_inscription_uses_authored_when_archetype_matches():
    rec = {"archetype": "pack-mule", "total_weight": 100, "item_count": 10}
    authored = {"archetype": "pack-mule",
                "inscription": "Hauls a smithy on her shoulders."}
    assert (inventory.resolve_inscription(rec, authored, ranks={"pack-mule": 1})
            == "Hauls a smithy on her shoulders.")


def test_resolve_inscription_falls_back_when_archetype_stale():
    rec = {
        "archetype": "scholar",
        "archetype_items": [{"name": "Spellbook", "count": 3}],
    }
    authored = {"archetype": "pack-mule",  # stale!
                "inscription": "old prose for the wrong archetype"}
    out = inventory.resolve_inscription(rec, authored, ranks={"scholar": 1})
    assert "Hauls" not in out
    assert "books, scrolls" in out


def test_resolve_inscription_falls_back_when_authored_missing():
    rec = {
        "archetype": "scholar",
        "archetype_items": [{"name": "Parchment", "count": 5}],
    }
    out = inventory.resolve_inscription(rec, None, ranks={"scholar": 1})
    assert "books, scrolls" in out


def test_resolve_inscription_empty_when_no_archetype():
    rec = {"archetype": None, "total_weight": 0, "item_count": 0}
    assert inventory.resolve_inscription(rec, None, ranks={}) == ""
