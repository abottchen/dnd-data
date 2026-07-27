"""mapimage.py — the web derivative of the party's annotated map of Chult.

The source under data/ is a ~17 MB, 55-megapixel export and is gitignored
like everything else in that directory; the committed artifact is a
re-encoded, full-resolution JPEG in site/images/. Full resolution is the
point — the viewer zooms past native pixel density so the handwritten
annotations stay legible.

Re-encoding 55 megapixels takes seconds, and most builds carry no new map,
so this is a no-op unless the source has actually changed. Staleness is keyed
on a SHA-256 of the source recorded in build/map-source.json, not on mtimes:
the derivative is git-tracked, and git stamps working-tree files with the
checkout time, so a pull or stash after dropping in a new map would leave the
old derivative looking newer than its own source and skip forever.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import REPO_ROOT, data_dir

SOURCE_NAME = "chult-player-map.jpg"
OUTPUT_NAME = "chult-map.jpg"
RECORD_NAME = "map-source.json"

# 4:4:4 chroma (subsampling=0) costs a little size and buys crisp edges on the
# colored annotation strokes, which is the whole reason to keep full res.
QUALITY = 80
SUBSAMPLING = 0

STATUS_REBUILT = "rebuilt"
STATUS_SKIPPED = "skipped"
STATUS_NO_SOURCE = "no-source"


def source_path() -> Path:
    return data_dir() / SOURCE_NAME


def output_path() -> Path:
    return REPO_ROOT / "site" / "images" / OUTPUT_NAME


def record_path() -> Path:
    """Committed alongside the derivative it describes, so a fresh clone whose
    source matches skips the rebuild instead of re-encoding on first build."""
    return Path(__file__).resolve().parent / RECORD_NAME


def _digest(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _recorded_digest(record: Path) -> str | None:
    """The source digest the derivative was last built from, or None when the
    record is absent or unreadable. Either way the caller rebuilds: a wasted
    re-encode costs seconds, a skipped one publishes the wrong map."""
    try:
        return json.loads(record.read_text()).get("source_sha256")
    except (OSError, ValueError, AttributeError):
        return None


def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    size = float(n)
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


def _size_or_none(p: Path) -> int | None:
    return p.stat().st_size if p.exists() else None


def prepare_map(force: bool = False, *, src: Path | None = None,
                out: Path | None = None, record: Path | None = None) -> dict:
    """Re-encode the map source into site/images/, unless it is already current.

    Current means the source hashes to what the record says the derivative was
    built from. Returns {"status", "src_bytes", "out_bytes"}. A missing source
    is not an error: a clone without data/ still has the committed derivative,
    and a missing derivative is caught by validate_map at render time.
    """
    src = src or source_path()
    out = out or output_path()
    record = record or record_path()

    if not src.exists():
        return {"status": STATUS_NO_SOURCE, "src_bytes": None,
                "out_bytes": _size_or_none(out)}

    digest = _digest(src)
    if not force and out.exists() and _recorded_digest(record) == digest:
        return {"status": STATUS_SKIPPED, "src_bytes": src.stat().st_size,
                "out_bytes": out.stat().st_size}

    from PIL import Image

    with Image.open(src) as im:
        rgb = im.convert("RGB")   # loads the pixels; safe to use after close
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out, format="JPEG", quality=QUALITY, optimize=True,
             progressive=True, subsampling=SUBSAMPLING)

    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(
        {"source_sha256": digest, "output_bytes": out.stat().st_size},
        indent=2) + "\n")

    return {"status": STATUS_REBUILT, "src_bytes": src.stat().st_size,
            "out_bytes": out.stat().st_size}
