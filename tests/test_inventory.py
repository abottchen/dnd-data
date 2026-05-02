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
