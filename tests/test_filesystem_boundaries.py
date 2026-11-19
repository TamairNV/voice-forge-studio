"""Regression tests for host-filesystem and persisted-path trust boundaries."""

from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _request(host: str | None):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host else None)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_native_filesystem_capabilities_allow_true_loopback(host):
    from api.dependencies import require_native_access
    require_native_access(_request(host))


@pytest.mark.parametrize("host", ["172.17.0.1", "192.168.1.4", None])
def test_native_filesystem_capabilities_reject_remote_even_in_server_mode(monkeypatch, host):
    from api.dependencies import require_native_access
    monkeypatch.setenv("OMNIVOICE_SERVER_MODE", "1")
    monkeypatch.setenv("OMNIVOICE_API_KEY", "operator-secret")
    with pytest.raises(HTTPException) as exc:
        require_native_access(_request(host))
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "name",
    ["../secret.wav", "folder/voice.wav", r"folder\voice.wav", r"C:\secret.wav", ".", "..", ""],
)
def test_safe_filename_rejects_posix_and_windows_escapes(name):
    from core.path_security import UnsafePath, safe_filename
    with pytest.raises(UnsafePath):
        safe_filename(name)


def test_resolve_within_accepts_relative_and_existing_absolute_paths(tmp_path):
    from core.path_security import resolve_within
    root = tmp_path / "root"
    root.mkdir()
    item = root / "voice.wav"
    assert resolve_within(root, "voice.wav") == item
    assert resolve_within(root, item) == item


def test_stored_subpaths_split_on_both_separator_families():
    """The component split is host-independent.

    Asserted on the splitter itself, not through ``resolve_within``: the
    Python suite runs on Linux only, where ``os.sep`` splitting already
    handled ``/``. A behavioural test would pass here whether or not the
    Windows path is fixed, so it would not guard the regression.
    """
    from core.path_security import _PATH_SEPARATORS
    assert _PATH_SEPARATORS.split("sub/voice.wav") == ["sub", "voice.wav"]
    assert _PATH_SEPARATORS.split(r"sub\voice.wav") == ["sub", "voice.wav"]


@pytest.mark.parametrize("stored_path", ["sub/voice.wav", r"sub\voice.wav"])
def test_resolve_within_reads_a_stored_subpath(tmp_path, stored_path):
    """A persisted sub-path resolves to the same file on Windows and POSIX.

    Rows written on Windows, POSIX, or Docker must resolve identically after
    the same data directory is opened on another supported host.
    """
    from core.path_security import resolve_within
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    assert resolve_within(root, stored_path) == root / "sub" / "voice.wav"


def test_resolve_within_rejects_traversal_through_either_separator(tmp_path):
    """Splitting on both separators must not open a traversal path."""
    from core.path_security import UnsafePath, resolve_within
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    with pytest.raises(UnsafePath):
        resolve_within(root, "sub/../../secret.wav")


def test_resolve_within_rejects_parent_and_absolute_escape(tmp_path):
    from core.path_security import UnsafePath, resolve_within
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(UnsafePath):
        resolve_within(root, "../secret.wav")
    with pytest.raises(UnsafePath):
        resolve_within(root, tmp_path / "secret.wav")
    with pytest.raises(UnsafePath):
        resolve_within(root, r"..\secret.wav")
    with pytest.raises(UnsafePath):
        resolve_within(root, r"C:\secret.wav")


def test_resolve_within_rejects_symlink_escape(tmp_path):
    from core.path_security import UnsafePath, resolve_within
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    # Match the reason, not just the type: when ``/`` was not treated as a
    # separator on Windows this call failed at component validation instead,
    # so the containment check below it was never exercised there.
    with pytest.raises(UnsafePath, match="escapes its allowed root"):
        resolve_within(root, "link/secret.wav")


def test_duration_probe_rejects_absolute_traversal_and_symlink_escapes(tmp_path, monkeypatch):
    from services import ffmpeg_utils

    root = tmp_path / "dub"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    secret = outside / "secret.mp4"
    secret.write_bytes(b"not media")
    monkeypatch.setattr(ffmpeg_utils, "find_ffprobe", lambda: "/should/not/run")
    spawned = []

    async def forbidden_spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("rejected media path reached ffprobe")

    monkeypatch.setattr(ffmpeg_utils, "spawn_subprocess", forbidden_spawn)
    for value in (secret, "../outside/secret.mp4", r"..\outside\secret.mp4"):
        assert asyncio.run(ffmpeg_utils.probe_duration(str(value), allowed_root=str(root))) is None
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        return
    assert asyncio.run(
        ffmpeg_utils.probe_duration(str(root / "link" / "secret.mp4"), allowed_root=str(root))
    ) is None
    assert spawned == []


def test_profile_lock_rejects_history_path_outside_outputs(tmp_path, monkeypatch):
    from api.routers import profiles

    outputs = tmp_path / "outputs"
    voices = tmp_path / "voices"
    outputs.mkdir()
    voices.mkdir()
    secret = tmp_path / "secret.wav"
    secret.write_bytes(b"secret")

    class FakeConnection:
        def execute(self, query, _params):
            if "voice_profiles" in query:
                return SimpleNamespace(fetchone=lambda: {"id": "profile"})
            return SimpleNamespace(
                fetchone=lambda: {"audio_path": str(secret), "text": "private"}
            )

    @contextmanager
    def fake_db_conn():
        yield FakeConnection()

    monkeypatch.setattr(profiles, "OUTPUTS_DIR", str(outputs))
    monkeypatch.setattr(profiles, "VOICES_DIR", str(voices))
    monkeypatch.setattr(profiles, "db_conn", fake_db_conn)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(profiles.lock_profile("profile", history_id="history"))
    assert exc.value.status_code == 400
    assert not any(voices.iterdir())
