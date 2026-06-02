"""Tests for the transformer registry — the single source of truth that
wires transformer names to slice builders and apply functions."""
from build import registry, slices, apply


def test_registry_lists_every_transformer():
    names = {entry.name for entry in registry.ALL}
    assert names == {
        "refresh-known-npcs",
        "append-kills", "append-sessions", "append-chapters",
        "append-npcs", "append-characters",
        "refresh-chapters", "refresh-npcs", "refresh-characters",
        "refresh-road-ahead", "refresh-intro-epithet",
        "refresh-archetype-inscription",
        "refresh-ascent-read",
    }


def test_registry_pass_assignment():
    by_name = {e.name: e for e in registry.ALL}
    assert by_name["refresh-known-npcs"].pass_name == "discovery"
    assert by_name["append-kills"].pass_name == "append"
    assert by_name["refresh-chapters"].pass_name == "refresh"


def test_registry_slice_and_apply_callables_wire_through():
    by_name = {e.name: e for e in registry.ALL}
    assert by_name["append-kills"].slice_builder is slices.append_kills
    assert by_name["append-kills"].apply_fn is apply.apply_append_kills
    assert by_name["refresh-known-npcs"].slice_builder is slices.refresh_known_npcs
    assert by_name["refresh-known-npcs"].apply_fn is apply.apply_refresh_known_npcs


def test_lookup_by_name():
    entry = registry.by_name("append-kills")
    assert entry.name == "append-kills"
    assert entry.pass_name == "append"


def test_every_pass_name_is_valid():
    valid = {"discovery", "append", "refresh"}
    for entry in registry.ALL:
        assert entry.pass_name in valid, f"{entry.name}: invalid pass_name {entry.pass_name!r}"
