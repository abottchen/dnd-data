"""Tests for build/mapimage.py — the web derivative of the player map."""
import os

import pytest
from PIL import Image

from build.mapimage import (
    prepare_map, fmt_bytes,
    STATUS_REBUILT, STATUS_SKIPPED, STATUS_NO_SOURCE,
)


def make_source(path, size=(64, 48)):
    """A tiny stand-in for the 55 MP map — the code path is identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 90, 40)).save(path, format="JPEG")
    return path


def test_rebuilds_when_derivative_missing(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "images" / "out.jpg"
    result = prepare_map(src=src, out=out)
    assert result["status"] == STATUS_REBUILT
    assert out.exists()
    assert result["out_bytes"] == out.stat().st_size
    assert result["src_bytes"] == src.stat().st_size


def test_output_keeps_full_resolution(tmp_path):
    src = make_source(tmp_path / "src.jpg", size=(300, 200))
    out = tmp_path / "out.jpg"
    prepare_map(src=src, out=out)
    with Image.open(out) as im:
        assert im.size == (300, 200)


def test_skips_when_derivative_is_newer(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    prepare_map(src=src, out=out)
    os.utime(src, (1_000_000, 1_000_000))     # source now much older
    stamp = out.stat().st_mtime_ns
    result = prepare_map(src=src, out=out)
    assert result["status"] == STATUS_SKIPPED
    assert out.stat().st_mtime_ns == stamp    # untouched


def test_rebuilds_when_source_is_newer(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    prepare_map(src=src, out=out)
    os.utime(out, (1_000_000, 1_000_000))     # derivative now stale
    result = prepare_map(src=src, out=out)
    assert result["status"] == STATUS_REBUILT


def test_force_rebuilds_a_current_derivative(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    prepare_map(src=src, out=out)
    result = prepare_map(force=True, src=src, out=out)
    assert result["status"] == STATUS_REBUILT


def test_no_source_leaves_existing_derivative_alone(tmp_path):
    out = tmp_path / "out.jpg"
    out.write_bytes(b"committed artifact")
    result = prepare_map(src=tmp_path / "absent.jpg", out=out)
    assert result["status"] == STATUS_NO_SOURCE
    assert result["src_bytes"] is None
    assert out.read_bytes() == b"committed artifact"


def test_no_source_and_no_derivative(tmp_path):
    result = prepare_map(src=tmp_path / "absent.jpg", out=tmp_path / "gone.jpg")
    assert result["status"] == STATUS_NO_SOURCE
    assert result["out_bytes"] is None


@pytest.mark.parametrize("n,expected", [(512, "512 B"), (2048, "2.0 KB"), (17_238_587, "16.4 MB")])
def test_fmt_bytes(n, expected):
    assert fmt_bytes(n) == expected
