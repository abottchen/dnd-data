"""render.py invocation.

Currently a thin wrapper that runs build/render.py in the project's venv and
returns the result. Targeted MISSING/MALFORMED retry — the loop that
re-dispatches a single transformer for the offending entity — is a future
extension; first-cut just surfaces the render error.
"""
import subprocess
import sys
from pathlib import Path

from .paths import REPO_ROOT, data_dir


def run_render() -> dict:
    """Run build/render.py once.

    Passes --data-dir explicitly so the render resolves the same upstream
    data the orchestrator did (honoring BUILD_DATA_DIR via paths.data_dir()
    rather than render.py's own default of REPO_ROOT/data).

    Returns {"ok": bool, "stdout": str, "stderr": str, "returncode": int}.
    """
    render_py = REPO_ROOT / "build" / "render.py"
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    interpreter = venv_python if venv_python.exists() else Path(sys.executable)

    result = subprocess.run(
        [str(interpreter), str(render_py), "--data-dir", str(data_dir())],
        capture_output=True,
        text=True,
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
