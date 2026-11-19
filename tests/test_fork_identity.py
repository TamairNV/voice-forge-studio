import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_name():
    assert json.loads((ROOT / "config" / "app.json").read_text())["productName"] == "Voice Forge Studio"


def test_fork_notice_present():
    text = (ROOT / "FORK-NOTICE.md").read_text()
    for needle in ("debpalash/VoiceStudio", "8f6c11343", "AGPL-3.0", "2026-11-19", "Tamair"):
        assert needle in text
