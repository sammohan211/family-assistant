"""Regression guard: importing the app must not require a populated `.env`.

Settings are loaded lazily by `db.get_engine` / `db.get_sessionmaker`, so
importing `family_assistant.main` succeeds even when no config is present.
Configuration errors only surface when the engine is actually used.
"""

import os
import subprocess
import sys
from pathlib import Path


def test_main_imports_with_no_env_vars_and_no_dotenv(tmp_path: Path) -> None:
    """Bug #6: collection used to fail before this — Settings validated at import."""
    repo_root = Path(__file__).resolve().parent.parent
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(repo_root / "src"),
    }
    result = subprocess.run(
        [sys.executable, "-c", "from family_assistant.main import app; assert app is not None"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Importing family_assistant.main failed without .env.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
