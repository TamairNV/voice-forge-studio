import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOVED_APP_DIRS = ["electron", "mobile", "native", "frontend", "store", "fastlane", "snap", "packaging", "cli", "skills"]


def test_app_dirs_gone():
    assert [d for d in REMOVED_APP_DIRS if (ROOT / d).exists()] == []


def test_backend_imports_in_a_fresh_interpreter():
    # Must work on Linux without mlx and on the Mac without CUDA.
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "OMNIVOICE_MODEL": "test"}
    result = subprocess.run([sys.executable, "-c", "import main"], cwd=ROOT / "backend",
                            env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
