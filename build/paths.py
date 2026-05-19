"""Path resolution for the build package.

Every path resolves from REPO_ROOT (the repo this package lives in). Test
isolation overrides via env vars: BUILD_DATA_DIR, BUILD_AUTHORED_DIR,
BUILD_RUN_ROOT.
"""
import datetime as _dt
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / ".claude" / "prompts"


def data_dir() -> Path:
    return Path(os.environ.get("BUILD_DATA_DIR", REPO_ROOT / "data"))


def authored_dir() -> Path:
    return Path(os.environ.get("BUILD_AUTHORED_DIR", REPO_ROOT / "build" / "authored"))


def run_root() -> Path:
    """Parent of all run dirs. Override via BUILD_RUN_ROOT."""
    override = os.environ.get("BUILD_RUN_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT / "build" / ".run"


def run_dir(run_id: str) -> Path:
    """Return (and create) the directory for one build run."""
    p = run_root() / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_run_id() -> str:
    """Filesystem-safe ISO-ish timestamp: 2026-05-17T14-32-08 (no colons)."""
    now = _dt.datetime.now().replace(microsecond=0)
    return now.isoformat().replace(":", "-")
