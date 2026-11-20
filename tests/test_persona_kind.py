"""Persona bundle audio validation tests (marketplace tests removed in Task 10)."""
from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")


@pytest.fixture(scope="module")
def iso(tmp_path_factory):
    """Isolated data dir + reloaded config/db (no main, no torch)."""
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("persona-kind-data")
    mp.setenv("OMNIVOICE_DATA_DIR", str(tmp))
    import core.config as cfg
    importlib.reload(cfg)
    import core.db as db
    importlib.reload(db)
    db.init_db()
    try:
        yield cfg, db
    finally:
        mp.undo()


def _wav_bytes() -> bytes:
    """A small real WAV: bundle import refuses clips that do not decode."""
    import io as _io
    import wave as _wave

    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x10" * 1600)
    return buf.getvalue()


_HTML_PAGE = b"<!doctype html><script>document.title='x'</script>" + b" " * 2000


def _voice_files(cfg) -> set[str]:
    return {p.name for p in Path(cfg.VOICES_DIR).iterdir()} if Path(cfg.VOICES_DIR).exists() else set()


def test_persona_member_ext_is_media_only():
    from services.persona_bundle import _safe_member_ext

    assert _safe_member_ext("ref_audio.html") == ".wav"
    assert _safe_member_ext("ref_audio.svg") == ".wav"
    assert _safe_member_ext("ref_audio.MP3") == ".mp3"


@pytest.mark.parametrize("member", ["ref_audio.html", "ref_audio.wav", "consent_audio.html"])
def test_persona_import_refuses_bundle_audio_that_is_not_audio(iso, member):
    cfg, _ = iso
    from fastapi import HTTPException, UploadFile
    from api.routers import personas

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"bundle_version": 1, "profile_name": "X"}))
        if not member.startswith("ref_audio"):
            zf.writestr("ref_audio.wav", _wav_bytes())
        zf.writestr(member, _HTML_PAGE)
    before = _voice_files(cfg)
    file = UploadFile(filename="evil.ovsvoice", file=io.BytesIO(buf.getvalue()))
    with pytest.raises(HTTPException) as err:
        asyncio.run(personas.import_persona(file))
    assert err.value.status_code == 400, err.value.detail
    assert "could not be read" in err.value.detail
    assert _voice_files(cfg) == before
