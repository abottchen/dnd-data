"""Path resolution for the build package.

Every path resolves from REPO_ROOT (the repo this package lives in). Test
isolation overrides via env vars: BUILD_DATA_DIR, BUILD_AUTHORED_DIR,
BUILD_RUN_ROOT, BUILD_PROMPTS_DIR (and BUILD_TOA_ADVENTURE / BUILD_TOA_DOCS
for the module text).
"""
import datetime as _dt
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / ".claude" / "prompts"


def prompts_dir() -> Path:
    """Where prepare reads prompts, schemas and their includes. Override via
    BUILD_PROMPTS_DIR: the session briefs include publisher-notes.md, which is
    gitignored and exists only on the publisher's machine, so the test suite
    points this at a copy of the prompts carrying a stand-in for it."""
    return Path(os.environ.get("BUILD_PROMPTS_DIR", PROMPTS_DIR))


def data_dir() -> Path:
    return Path(os.environ.get("BUILD_DATA_DIR", REPO_ROOT / "data"))


def authored_dir() -> Path:
    return Path(os.environ.get("BUILD_AUTHORED_DIR", REPO_ROOT / "build" / "authored"))


def toa_adventure_path() -> Path:
    """The Tomb of Annihilation module text as 5etools JSON, reached through
    the machine-local `.claude/ext/dnd-toa` link (see .claude/ext/README.md).
    Override via BUILD_TOA_ADVENTURE. Missing is tolerated: the session
    writer then gets no module text, and prepare says so once."""
    override = os.environ.get("BUILD_TOA_ADVENTURE")
    if override:
        return Path(override)
    return REPO_ROOT / ".claude" / "ext" / "dnd-toa" / "data" / "5etools" / "adventure-toa.json"


def toa_docs_glob() -> str:
    """Module text kept as markdown transcriptions in the `dnd-toa` checkout
    (the Lost City of Mezro trilogy lives in `docs/`), read beside the 5etools
    JSON. Override via BUILD_TOA_DOCS, a glob. Missing is tolerated."""
    override = os.environ.get("BUILD_TOA_DOCS")
    if override:
        return override
    return str(REPO_ROOT / ".claude" / "ext" / "dnd-toa" / "docs" / "*.md")


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
