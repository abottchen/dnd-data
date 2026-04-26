"""Authored store load/write.

Six JSON files under build/authored/: five list-shaped (kills, sessions,
chapters, npcs, characters) and one dict-shaped (site). Cold-start safe —
missing files default to empty containers so the orchestrator can run on a
fresh repo.
"""
import json

from .paths import authored_dir

LIST_STEMS = ("kills", "sessions", "chapters", "npcs", "characters")
SITE_STEM = "site"


def load_authored() -> dict:
    """Load every authored/*.json. Missing files → empty containers."""
    auth = authored_dir()
    out: dict = {}
    for stem in LIST_STEMS:
        p = auth / f"{stem}.json"
        out[stem] = json.loads(p.read_text()) if p.exists() else []
    site_path = auth / f"{SITE_STEM}.json"
    out[SITE_STEM] = json.loads(site_path.read_text()) if site_path.exists() else {}
    return out


def write_section(stem: str, value) -> None:
    """Write one authored section back to disk.

    `ensure_ascii=False` preserves literal Unicode (σ, em-dashes, etc.) rather
    than escaping to `\\u...` — keeps diffs minimal vs hand-authored files.
    """
    auth = authored_dir()
    auth.mkdir(parents=True, exist_ok=True)
    path = auth / f"{stem}.json"
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def persist(authored: dict) -> None:
    """Write every section in `authored` back to disk."""
    for stem in LIST_STEMS:
        write_section(stem, authored[stem])
    write_section(SITE_STEM, authored[SITE_STEM])


def bump_marker(authored: dict, latest_session: int) -> None:
    """Set site.refreshed_through_session and persist the site section."""
    authored[SITE_STEM]["refreshed_through_session"] = latest_session
    write_section(SITE_STEM, authored[SITE_STEM])
