"""Voice profile lock-retirement and lease checks (#2535)."""
import os

import pytest

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")


@pytest.fixture
def locked_profile(tmp_path, monkeypatch):
    from api.routers import profiles
    from core import config, db

    voices = tmp_path / "voices"
    outputs = tmp_path / "outputs"
    voices.mkdir()
    outputs.mkdir()
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(profiles, "VOICES_DIR", str(voices))
    monkeypatch.setattr(profiles, "OUTPUTS_DIR", str(outputs))
    monkeypatch.setattr(config, "VOICES_DIR", str(voices))
    db.init_db()
    with db.db_conn() as conn:
        conn.execute("INSERT INTO voice_profiles(id,name) VALUES('voice','V')")
        for name, body in (("take1.wav", b"first-take"), ("take2.wav", b"second-take")):
            (outputs / name).write_bytes(body)
            conn.execute(
                "INSERT INTO generation_history(id, text, audio_path) VALUES(?, 'same text', ?)",
                (name[:5], name),
            )
    return voices


def test_sweep_keeps_a_retired_file_a_profile_references_again(locked_profile):
    from api.routers import profiles
    from core import db

    (locked_profile / "voice_locked.wav").write_bytes(b"legacy")  # pre-#2535 name
    with db.db_conn() as conn:
        conn.execute(
            "UPDATE voice_profiles SET locked_audio_path='voice_locked.wav', is_locked=1"
        )
    profiles._retire_voice_file("voice_locked.wav")
    assert profiles.sweep_retired_voice_files(grace_s=0) == 0
    assert (locked_profile / "voice_locked.wav").read_bytes() == b"legacy"
    assert os.listdir(locked_profile / ".retired") == []


def test_voice_leases_count_each_holder_and_release_once(tmp_path):
    from core import voice_leases

    path = str(tmp_path / "take.wav")
    a, b = voice_leases.VoiceFileLease(), voice_leases.VoiceFileLease()
    a.hold(path)
    a.hold(path)  # one lease holds a path once
    b.hold(path)
    a.release()
    a.release()
    assert voice_leases.in_use(path)
    b.release()
    assert not voice_leases.in_use(path)
    a.hold(path)  # a released lease cannot pin a file again
    assert not voice_leases.in_use(path)
