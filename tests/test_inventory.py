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
