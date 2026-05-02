"""Tests for build/inventory.py — the inventory loader/classifier/scorer."""
import pytest

from build import inventory


def test_module_exposes_load():
    assert hasattr(inventory, "load")
    assert callable(inventory.load)
