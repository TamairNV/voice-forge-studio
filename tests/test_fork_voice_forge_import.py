"""Tests for the idempotent Voice Forge data importer (Phase 2, Task 5)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BACKEND = Path(__file__).resolve().parents[1] / "backend"
for p in (str(SCRIPTS), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_import_voice_forge_data_idempotent(tmp_path, monkeypatch):
    # Target Voice Forge Studio data dir
    dest = tmp_path / "dest"
    dest.mkdir()
    monkeypatch.setenv("OMNIVOICE_DATA_DIR", str(dest))
    import core.config as cfg
    import core.db as db_mod
    monkeypatch.setattr(cfg, "DATA_DIR", str(dest))
    monkeypatch.setattr(cfg, "DB_PATH", str(dest / "omnivoice.db"))
    monkeypatch.setattr(db_mod, "DB_PATH", str(dest / "omnivoice.db"))
    db_mod.ensure_schema()

    # Fake legacy voice_forge/data directory
    src = tmp_path / "legacy_data"
    (src / "characters").mkdir(parents=True)
    (src / "scenes").mkdir(parents=True)
    (src / "takes").mkdir(parents=True)
    (src / "characters" / "char_1.wav").write_bytes(b"RIFFdemo")
    (src / "scenes" / "scene_1.wav").write_bytes(b"RIFFscene")
    (src / "takes" / "take_1.wav").write_bytes(b"RIFFtake")

    (src / "characters.json").write_text(json.dumps([
        {
            "id": "char_1",
            "name": "Nyx",
            "description": "Rogue",
            "ref_text": "Watch out.",
            "audio_file": "char_1.wav",
            "created_at": "2026-11-12 20:25",
        }
    ]), encoding="utf-8")
    (src / "profiles.json").write_text(json.dumps([
        {"id": "prof_1", "name": "Lana", "description": "", "clips": [], "created_at": "2026-11-12 20:25"}
    ]), encoding="utf-8")
    (src / "casts.json").write_text(json.dumps([
        {"id": "cast_1", "name": "Demo Cast", "script": "Nyx: Hi", "mapping": {}, "lines": []}
    ]), encoding="utf-8")
    (src / "takes.json").write_text(json.dumps([
        {
            "id": "take_1",
            "filename": "take_1.wav",
            "model_id": "qwen3_clone",
            "text": "Hi",
            "character_id": "char_1",
            "metrics": {"duration_sec": 1.2, "elapsed_sec": 2.3},
        }
    ]), encoding="utf-8")
    (src / "scenes.json").write_text(json.dumps([
        {
            "id": "scene_1",
            "title": "Intro",
            "filename": "scene_1.wav",
            "duration_sec": 1.2,
            "line_count": 1,
            "cast": [{"speaker": "Nyx", "character_id": "char_1"}],
            "segments": [{"index": 0, "speaker": "Nyx", "text": "Hi", "file_path": "/old/takes/take_1.wav"}],
        }
    ]), encoding="utf-8")

    from import_voice_forge_data import import_voice_forge_data
    from services import voice_forge_store as store

    c1 = import_voice_forge_data(src)
    assert c1 == {
        "characters": 1,
        "profiles": 1,
        "casts": 1,
        "scenes": 1,
        "takes": 1,
        "files_copied": 3,
    }
    assert (dest / "voice_forge" / "characters" / "char_1.wav").exists()
    sc = store.get_scene("scene_1")
    assert sc["segments"][0]["file_path"].endswith("voice_forge/takes/take_1.wav")
    assert store.get_take("take_1")["duration_sec"] == 1.2

    # Second run is idempotent and skips copying unchanged files
    c2 = import_voice_forge_data(src)
    assert c2["files_copied"] == 0
    assert len(store.list_characters()) == 1
