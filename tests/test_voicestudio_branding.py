"""VoiceStudio release-brand and source-launch contracts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def test_current_version_is_in_lockstep_everywhere() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == CURRENT_VERSION

    mirrors = {
        "pyproject.toml": r'(?m)^version = "([^"]+)"',
        "backend/core/version.py": r'(?m)^_FALLBACK_VERSION = "([^"]+)"',
    }
    for path, pattern in mirrors.items():
        match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
        assert match and match.group(1) == CURRENT_VERSION, path

    lock_contracts = {"uv.lock": r'name = "omnivoice"\s+version = "([^"]+)"'}
    for path, pattern in lock_contracts.items():
        match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
        # uv writes the PEP 440 form of a beta (0.5.9b1 for 0.5.9-beta.1).
        assert match and Version(match.group(1)) == Version(CURRENT_VERSION), path


def test_waveform_stroke_is_never_filled() -> None:
    # An SVG path fills black unless told otherwise; without fill="none" the
    # waveform's closed curves painted a black band across every icon.
    signature = "M6 34c4 0 5-7 9-7"
    tracked = subprocess.run(["git", "ls-files", "*.svg"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    svgs = [ROOT / name for name in tracked if signature in (ROOT / name).read_text(encoding="utf-8")]
    assert len(svgs) >= 3
    for svg in svgs:
        stroke = re.search(rf'<path d="{re.escape(signature)}[^>]*>', svg.read_text(encoding="utf-8"))
        assert stroke and 'fill="none"' in stroke.group(0), svg


def test_python_package_metadata_points_to_voicestudio() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'Homepage = "https://github.com/debpalash/VoiceStudio"' in pyproject
    assert 'Repository = "https://github.com/debpalash/VoiceStudio"' in pyproject
    assert '"Upstream TTS Model" = "https://github.com/k2-fsa/OmniVoice"' in pyproject


def test_engine_help_names_the_app_not_the_upstream_model() -> None:
    paths = (
        "backend/engines/dots_tts/__init__.py",
        "backend/engines/dots_tts/bootstrap.py",
        "backend/engines/indextts/__init__.py",
        "backend/engines/indextts/bootstrap.py",
        "backend/engines/moss_tts_v15/__init__.py",
        "backend/engines/moss_tts_v15/bootstrap.py",
    )
    stale_help = re.compile(r"(?:restart|reinstall|re-launch|Run) OmniVoice")
    for path in paths:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert not stale_help.search(text), path


def test_compatibility_identifiers_stay_stable() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "voice-forge-studio"
    assert 'name = "omnivoice"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app_config = json.loads((ROOT / "config/app.json").read_text(encoding="utf-8"))
    assert app_config["appId"] == "com.voicestudio.desktop"
