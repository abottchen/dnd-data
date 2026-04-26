"""build.py invocation.

Currently a thin wrapper that runs build/build.py in the project's venv and
returns the result. Targeted MISSING/MALFORMED retry — the loop that
re-dispatches a single transformer for the offending entity — is a future
extension; first-cut hydrate just surfaces the build error.
"""
import subprocess
import sys
from pathlib import Path

from .paths import REPO_ROOT, data_dir


def run_build() -> dict:
    """Run build/build.py once.

    Passes --data-dir explicitly so the build resolves the same upstream data
    the hydrator did (honoring HYDRATE_DATA_DIR via paths.data_dir() rather
    than build.py's own default of REPO_ROOT/data).

    Returns {"ok": bool, "stdout": str, "stderr": str, "returncode": int}.
    """
    build_py = REPO_ROOT / "build" / "build.py"
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    interpreter = venv_python if venv_python.exists() else Path(sys.executable)

    result = subprocess.run(
        [str(interpreter), str(build_py), "--data-dir", str(data_dir())],
        capture_output=True,
        text=True,
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
