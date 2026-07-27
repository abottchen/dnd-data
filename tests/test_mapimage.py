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


def test_skips_when_source_is_unchanged(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    stamp = out.stat().st_mtime_ns
    result = prepare_map(src=src, out=out, record=rec)
    assert result["status"] == STATUS_SKIPPED
    assert out.stat().st_mtime_ns == stamp    # untouched


def test_rebuilds_when_source_content_changes(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    make_source(src, size=(128, 96))          # a different map dropped in
    result = prepare_map(src=src, out=out, record=rec)
    assert result["status"] == STATUS_REBUILT
    with Image.open(out) as im:
        assert im.size == (128, 96)


def test_rebuilds_stale_derivative_that_mtime_calls_current(tmp_path):
    """The git-checkout trap: a stale derivative whose mtime is newer than the
    source. Git stamps working-tree files at checkout time, so any checkout,
    pull, or stash after dropping in a new map made the old mtime guard skip
    forever and silently serve the previous map."""
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)

    make_source(src, size=(128, 96))          # new map dropped in ...
    os.utime(src, (1_000_000, 1_000_000))     # ... then git touches the
    os.utime(out, (2_000_000, 2_000_000))     # derivative, making it "newer"

    result = prepare_map(src=src, out=out, record=rec)
    assert result["status"] == STATUS_REBUILT
    with Image.open(out) as im:
        assert im.size == (128, 96)


def test_rebuilds_when_record_is_missing(tmp_path):
    """A fresh clone, or the first run after this guard landed, has no record.
    Rebuilding once is cheap and self-healing; skipping would serve stale art."""
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    rec.unlink()
    assert prepare_map(src=src, out=out, record=rec)["status"] == STATUS_REBUILT


def test_rebuilds_when_record_is_corrupt(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    rec.write_text("{ not json")
    assert prepare_map(src=src, out=out, record=rec)["status"] == STATUS_REBUILT


def test_record_holds_the_source_digest(tmp_path):
    import hashlib
    import json

    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    saved = json.loads(rec.read_text())
    assert saved["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert saved["output_bytes"] == out.stat().st_size


def test_missing_source_leaves_the_record_alone(tmp_path):
    src = make_source(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    rec = tmp_path / "record.json"
    prepare_map(src=src, out=out, record=rec)
    before = rec.read_text()
    src.unlink()
    assert prepare_map(src=src, out=out, record=rec)["status"] == STATUS_NO_SOURCE
    assert rec.read_text() == before


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
