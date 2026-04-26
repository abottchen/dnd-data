"""Path resolution for the hydrate package.

Every path resolves from REPO_ROOT (the repo this package lives in). Test
isolation overrides via env vars: HYDRATE_DATA_DIR, HYDRATE_AUTHORED_DIR,
HYDRATE_TEMP_DIR.
"""
import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / ".claude" / "prompts"


def data_dir() -> Path:
    return Path(os.environ.get("HYDRATE_DATA_DIR", REPO_ROOT / "data"))


def authored_dir() -> Path:
    return Path(os.environ.get("HYDRATE_AUTHORED_DIR", REPO_ROOT / "build" / "authored"))


def temp_dir() -> Path:
    """Allocate (or honor override of) the per-run temp dir.

    The dir is preserved on failure and cleaned only on full-run success.
    Cleaning is the orchestrator's responsibility, not this function's.
    """
    override = os.environ.get("HYDRATE_TEMP_DIR")
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.mkdtemp(prefix="hydrate-"))
