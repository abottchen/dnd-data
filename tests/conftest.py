import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def pytest_sessionstart(session):
    """The forbidden-names hooks only run when core.hooksPath is set — a
    fresh clone is silently unguarded. Warn loudly rather than fail."""
    repo = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath"],
            capture_output=True, text=True)
        hooks_path = out.stdout.strip()
    except OSError:
        return
    if hooks_path != ".githooks":
        warnings.warn(
            "core.hooksPath is not '.githooks' — the forbidden-name guard "
            "is INACTIVE in this clone. Run: git config core.hooksPath .githooks",
            stacklevel=1)


@pytest.fixture
def staged_env(tmp_path, monkeypatch):
    """Materialize fixture data + authored store + run root under tmp_path
    and point the BUILD_* env vars at them. Returns tmp_path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    (data_dir / "dice").mkdir()
    shutil.copy(FIXTURES / "sample_dicex_rolls.json",
                data_dir / "dice" / "dicex-rolls-2026-04-23.json")
    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)
    run_root = tmp_path / "runs"
    run_root.mkdir()
    monkeypatch.setenv("BUILD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUILD_AUTHORED_DIR", str(authored_dir))
    monkeypatch.setenv("BUILD_RUN_ROOT", str(run_root))
    return tmp_path
