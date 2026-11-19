"""Tests for the SQLite-backed Voice Forge store (Phase 2, Task 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_voice_forge_store_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_DATA_DIR", str(tmp_path))
    import core.config as cfg
    import core.db as db_mod
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "omnivoice.db"))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "omnivoice.db"))
    db_mod.ensure_schema()

    from services import voice_forge_store as store

    # Characters
    ch = store.upsert_character({
        "id": "char_torvin",
        "name": "Torvin",
        "description": "Gruff blacksmith",
        "ref_text": "Keep your coin, traveller.",
        "audio_file": "char_torvin.wav",
        "source_model": "voxcpm2",
        "tags": ["npc", "blacksmith"],
    })
    assert ch["id"] == "char_torvin"
    assert ch["url"] == "/audio/characters/char_torvin.wav"
    assert store.find_character_by_name("torvin")["id"] == "char_torvin"
    updated = store.update_character("char_torvin", {"favorite": True, "name": "Torvin Ironhand"})
    assert updated["favorite"] is True
    assert updated["name"] == "Torvin Ironhand"

    # Profiles
    prof = store.upsert_profile({
        "id": "prof_tamair",
        "name": "Tamair",
        "description": "Main cast",
        "clips": {"neutral": {"char_id": "char_torvin"}},
    })
    assert prof["clips"]["neutral"]["char_id"] == "char_torvin"
    assert store.find_profile_by_name("TAMAIR")["id"] == "prof_tamair"

    # Casts
    cast = store.upsert_cast({
        "id": "cast_001",
        "name": "Tavern",
        "title": "Tavern Intro",
        "script": "Torvin: Welcome.",
        "mapping": {"Torvin": {"char_id": "char_torvin"}},
        "lines": [{"speaker": "Torvin", "text": "Welcome."}],
        "temperature": 0.7,
    })
    assert cast["temperature"] == pytest.approx(0.7)
    assert store.find_cast_by_name("tavern")["id"] == "cast_001"

    # Scenes
    scene = store.upsert_scene({
        "id": "scene_001",
        "title": "Tavern Intro",
        "filename": "scene_001.wav",
        "duration_sec": 3.5,
        "elapsed_sec": 5.1,
        "line_count": 1,
        "cast": {"Torvin": {"char_id": "char_torvin"}},
        "segments": [{"index": 0, "speaker": "Torvin", "text": "Welcome."}],
    })
    assert scene["url"] == "/audio/scenes/scene_001.wav"
    assert scene["srt_url"] == "/api/scenes/scene_001/subtitles.srt"

    # Takes
    take = store.upsert_take({
        "id": "take_001",
        "text": "Welcome.",
        "model_id": "maya1",
        "character_id": "char_torvin",
        "filename": "take_001.wav",
        "duration_sec": 1.2,
    })
    assert take["url"] == "/audio/takes/take_001.wav"
    assert len(store.list_takes()) == 1

    # Deletes
    assert store.delete_take("take_001") is True
    assert store.delete_scene("scene_001") is True
    assert store.delete_cast("cast_001") is True
    assert store.delete_profile("prof_tamair") is True
    assert store.delete_character("char_torvin") is True
    assert store.list_characters() == []
