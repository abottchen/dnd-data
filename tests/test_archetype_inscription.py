"""Tests for the archetype-inscription transformer wiring."""
import pytest

from build import slices


def _party(*members):
    return {"members": list(members)}


def test_slice_contains_only_items_that_earned_archetype(monkeypatch):
    party = _party(
        {"id": "grieg", "name": "Grieg", "race": "Wulven", "class": "Fighter",
         "background": "Beast Hunter", "abilities": {"str": 17}},
    )
    inv_by_id = {
        "grieg": {
            "rack": [{"name": "Warhammer", "count": 1, "weight": 5, "description": ""}],
            "spotlight": [],
            "manifest": [
                {"name": "Rations (x9)", "count": 9, "weight": 2, "description": ""},
                {"name": "Waterskin", "count": 1, "weight": 5, "description": ""},
                {"name": "Sword", "count": 1, "weight": 3, "description": ""},
            ],
            "archetype": "cellarer",
            "total_weight": 23,
            "item_count": 12,
            "capacity": 255,
        },
    }
    authored_chars = [{
        "id": "grieg",
        "epithet": "the wulven who never sleeps cold",
    }]

    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": authored_chars, "inventory_by_id": inv_by_id},
    )

    assert len(out) == 1
    key, slice_data = out[0]
    assert key == "grieg"
    item_names = {it["name"] for it in slice_data["items"]}
    # Only food items should be in the slice (Cellarer's matched set).
    assert item_names == {"Rations (x9)", "Waterskin"}
    assert slice_data["archetype"]["slug"] == "cellarer"
    assert slice_data["archetype"]["label"] == "THE CELLARER"
    assert slice_data["character"]["id"] == "grieg"
    assert slice_data["existing"] is None  # no archetype_badge yet


def test_slice_skips_characters_with_no_inventory():
    party = _party(
        {"id": "anton", "name": "Anton Truebranch", "abilities": {"str": 9}},
    )
    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": [{"id": "anton"}], "inventory_by_id": {}},
    )
    assert out == []


def test_slice_skips_characters_with_no_archetype():
    party = _party(
        {"id": "vex", "name": "Vex", "abilities": {"str": 12}},
    )
    inv_by_id = {"vex": {"archetype": None, "rack": [], "spotlight": [],
                          "manifest": [], "item_count": 0, "total_weight": 0,
                          "capacity": 180}}
    out = slices.refresh_archetype_inscription(
        {"party": party},
        {"characters": [{"id": "vex"}], "inventory_by_id": inv_by_id},
    )
    assert out == []


from build import apply


def test_apply_writes_archetype_badge_on_rewrite():
    authored = {"characters": [{"id": "grieg", "epithet": "..."}]}
    slice_data = {
        "character": {"id": "grieg"},
        "archetype": {"slug": "pack-mule", "label": "THE PACK-MULE"},
        "items": [],
        "existing": None,
    }
    output = {
        "decision": "rewrite",
        "fields": {"inscription": "Hauls a smithy on her shoulders."},
        "reason": "no existing inscription",
    }

    apply.apply_refresh_archetype_inscription(authored, "grieg", slice_data, output)

    badge = authored["characters"][0]["archetype_badge"]
    assert badge["archetype"] == "pack-mule"
    assert badge["inscription"] == "Hauls a smithy on her shoulders."


def test_apply_no_change_leaves_existing_alone():
    authored = {"characters": [{
        "id": "grieg",
        "epithet": "...",
        "archetype_badge": {
            "archetype": "pack-mule",
            "inscription": "old, but fits",
        },
    }]}
    slice_data = {
        "character": {"id": "grieg"},
        "archetype": {"slug": "pack-mule"},
        "items": [],
        "existing": authored["characters"][0]["archetype_badge"],
    }
    output = {"decision": "no_change", "fields": None, "reason": "still fits"}

    apply.apply_refresh_archetype_inscription(authored, "grieg", slice_data, output)

    assert authored["characters"][0]["archetype_badge"]["inscription"] == "old, but fits"


def test_apply_raises_for_missing_character():
    authored = {"characters": []}
    slice_data = {
        "character": {"id": "ghost"},
        "archetype": {"slug": "scholar"},
        "items": [], "existing": None,
    }
    output = {"decision": "rewrite",
              "fields": {"inscription": "x"},
              "reason": "."}
    with pytest.raises(ValueError, match="ghost"):
        apply.apply_refresh_archetype_inscription(authored, "ghost", slice_data, output)
