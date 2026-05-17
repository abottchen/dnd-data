"""Tests for build/paths.py run-dir resolution."""
import os
from pathlib import Path

from build import paths


def test_run_dir_creates_directory(monkeypatch, tmp_path):
    """run_dir(run_id) creates the dir under run_root()."""
    monkeypatch.setenv("BUILD_RUN_ROOT", str(tmp_path))
    p = paths.run_dir("2026-05-17T14-32-08")
    assert p == tmp_path / "2026-05-17T14-32-08"
    assert p.exists()
    assert p.is_dir()


def test_run_dir_env_override(monkeypatch, tmp_path):
    """BUILD_RUN_ROOT relocates the root of all run dirs (for tests)."""
    monkeypatch.setenv("BUILD_RUN_ROOT", str(tmp_path))
    p = paths.run_dir("custom-id")
    assert p == tmp_path / "custom-id"
    assert p.exists()


def test_new_run_id_is_iso_timestamp():
    run_id = paths.new_run_id()
    assert len(run_id) == 19
    assert run_id[4] == "-"
    assert run_id[10] == "T"


def test_run_root_returns_repo_default(monkeypatch):
    monkeypatch.delenv("BUILD_RUN_ROOT", raising=False)
    assert paths.run_root() == paths.REPO_ROOT / "build" / ".run"
