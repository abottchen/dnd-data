"""mapimage.py — the web derivative of the party's annotated map of Chult.

The source under data/ is a ~17 MB, 55-megapixel export and is gitignored
like everything else in that directory; the committed artifact is a
re-encoded, full-resolution JPEG in site/images/. Full resolution is the
point — the viewer zooms past native pixel density so the handwritten
annotations stay legible.

Re-encoding 55 megapixels takes seconds, and most builds carry no new map,
so this is a no-op unless the source is newer than the derivative.
"""
from __future__ import annotations

from pathlib import Path

from .paths import REPO_ROOT, data_dir

SOURCE_NAME = "chult-player-map.jpg"
OUTPUT_NAME = "chult-map.jpg"

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
                out: Path | None = None) -> dict:
    """Re-encode the map source into site/images/, unless it is already current.

    Returns {"status", "src_bytes", "out_bytes"}. A missing source is not an
    error: a clone without data/ still has the committed derivative, and a
    missing derivative is caught by validate_map at render time.
    """
    src = src or source_path()
    out = out or output_path()

    if not src.exists():
        return {"status": STATUS_NO_SOURCE, "src_bytes": None,
                "out_bytes": _size_or_none(out)}

    if not force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return {"status": STATUS_SKIPPED, "src_bytes": src.stat().st_size,
                "out_bytes": out.stat().st_size}

    from PIL import Image

    with Image.open(src) as im:
        rgb = im.convert("RGB")   # loads the pixels; safe to use after close
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out, format="JPEG", quality=QUALITY, optimize=True,
             progressive=True, subsampling=SUBSAMPLING)

    return {"status": STATUS_REBUILT, "src_bytes": src.stat().st_size,
            "out_bytes": out.stat().st_size}
