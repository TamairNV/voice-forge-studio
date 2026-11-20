"""Offline API and UI tests for the ported Voice Forge router (Phase 2, Task 4)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIVOICE_MODEL", "test")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    import core.config as cfg
    import core.db as db_mod
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "omnivoice.db"))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "omnivoice.db"))
    db_mod.ensure_schema()

    import main as main_mod
    main_mod._phase_a_build()
    main_mod._phase_a_finalize()
    return TestClient(main_mod.app)


def test_voice_forge_ui_pages_and_discovery(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    for page in ("/", "/cast", "/voices", "/clone", "/studio", "/scenes", "/takes", "/ui/engines"):
        resp = client.get(page)
        assert resp.status_code == 200, f"{page} returned {resp.status_code}"
        assert "<!DOCTYPE" in resp.text or "<html" in resp.text.lower()

    assert client.get("/api/health").status_code == 200
    st = client.get("/api/status").json()
    assert "characters" in st and "maya1_tags" in st and "models" in st
    eng = client.get("/api/engine").json()
    assert "active_model_id" in eng and len(eng["models"]) >= 4
    assert client.get("/api/presets").json()["presets"]
    assert client.get("/api/tags").json()["tags"]
    assert client.get("/api/profiles/emotions").json()["emotions"]
    assert client.get("/api/capabilities").json()["count"] >= 40
    guide = client.get("/api/llm-guide").json()
    assert "Voice" in guide["system_prompt_markdown"]
    assert "voices" in client.get("/api/voices").json()


def test_voice_forge_crud_and_cast_extract_dry_run(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    # Create profile
    prof = client.post("/api/profiles", json={"name": "Tamair", "description": "Lead"}).json()
    assert prof["name"] == "Tamair"

    # Upload a reference WAV as character
    wav_path = tmp_path / "sample.wav"
    t = np.linspace(0, 1.0, 24000, endpoint=False, dtype=np.float32)
    sf.write(str(wav_path), 0.1 * np.sin(2 * np.pi * 220 * t), 24000)

    ch = client.post(
        "/api/characters/from-recording",
        json={"name": "Torvin", "audio_path": str(wav_path), "ref_text": "Keep your coin."},
    ).json()
    assert ch["name"] == "Torvin"

    # Link clip to profile and pick it
    linked = client.post(
        f"/api/profiles/{prof['id']}/clips/link",
        json={"emotion": "angry", "character_id": ch["id"]},
    ).json()
    assert len(linked["profile"]["clips"]) == 1

    picked = client.get(
        f"/api/profiles/{prof['id']}/pick",
        params={"direction": "furious", "text": "Enough!"},
    ).json()
    assert picked["emotion"] == "angry"
    assert picked["clip"]["character_id"] == ch["id"]

    # Cast extract and dry-run produce
    script = "Tamair (furious): Where are my keys?!\nTorvin (deadpan): In your hand."
    ext = client.post("/api/cast/extract", json={"script": script}).json()
    assert len(ext["characters"]) == 2
    assert len(ext["lines"]) == 2

    prod = client.post(
        "/api/cast/produce",
        json={"script": script, "dry_run": True},
    ).json()
    assert prod["dry_run"] is True
    assert prod["scene_request"]["cast"]["Tamair"]["profile_id"] == prof["id"]
    assert prod["scene_request"]["cast"]["Torvin"]["character_id"] == ch["id"]

    # Save & list cast
    saved = client.post(
        "/api/casts",
        json={"name": "Keys", "script": script, "mapping": prod["scene_request"]["cast"]},
    ).json()
    assert saved["name"] == "Keys"
    assert any(c["id"] == saved["id"] for c in client.get("/api/casts").json()["casts"])
