"""URL imports only fetch public destinations (core.url_safety).

Covers the up-front 400s on both import routes, option-like input never
reaching yt-dlp, the connect-time guard (which is what stops redirects and
discovered URLs), the opt-in, and the restricted upload extensions.
"""
import os
import socket
import subprocess
import sys

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import pytest

from core import url_safety
from core.url_safety import ALLOW_PRIVATE_ENV, UnsafeURLError, check_public_url, is_public_address

PUBLIC_IP = "93.184.215.14"


def _answers(*ips):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))
            for ip in ips
        ]

    return fake_getaddrinfo


@pytest.fixture(autouse=True)
def _no_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_PRIVATE_ENV, raising=False)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254",
        "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "::",
        "fe80::1", "fc00::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254",
        "2002:c0a8:0101::1", "64:ff9b::a9fe:a9fe", "fe80::1%eth0", "not-an-ip",
    ],
)
def test_non_public_addresses_are_refused(ip):
    assert not is_public_address(ip)


@pytest.mark.parametrize("ip", [PUBLIC_IP, "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(ip):
    assert is_public_address(ip)


@pytest.mark.parametrize(
    "url",
    ["--config-locations=/tmp/x.conf", "-o/tmp/x", "file:///etc/passwd", "ytsearch:x", "ftp://h/x", "http://", ""],
)
def test_only_http_urls_are_accepted(url):
    with pytest.raises(UnsafeURLError, match="http"):
        check_public_url(url)


def test_private_answers_are_refused_and_public_allowed(monkeypatch):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers("192.168.1.10"))
    with pytest.raises(UnsafeURLError, match=ALLOW_PRIVATE_ENV):
        check_public_url("http://media.lan:9000/x")
    # One private answer among public ones is enough to refuse.
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers(PUBLIC_IP, "127.0.0.1"))
    with pytest.raises(UnsafeURLError):
        check_public_url("https://mixed.example/v")
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers(PUBLIC_IP))
    assert check_public_url(" https://www.youtube.com/watch?v=x ") == "https://www.youtube.com/watch?v=x"


def test_fake_ip_answers_stay_refused_and_the_message_says_what_to_do(monkeypatch):
    """Clash, Surge and sing-box in TUN/fake-IP mode answer every lookup with
    198.18.0.0/15. The range stays refused; the message names the cause, the
    fix, and where a desktop user sets the variable."""
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers("198.18.0.7"))
    with pytest.raises(UnsafeURLError) as refused:
        check_public_url("https://www.youtube.com/watch?v=x")
    detail = str(refused.value)
    assert f"{ALLOW_PRIVATE_ENV}=1" in detail
    assert "198.18." in detail and "fake-IP" in detail and "real-IP DNS" in detail
    assert "~/.config/omnivoice/env" in detail
    assert "%USERPROFILE%\\.config\\omnivoice\\env" in detail


def test_opt_in_allows_private_destinations(monkeypatch):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers("192.168.1.10"))
    monkeypatch.setenv(ALLOW_PRIVATE_ENV, "1")
    assert check_public_url("http://media.lan:9000/x") == "http://media.lan:9000/x"


def test_resolved_media_urls_are_checked(monkeypatch):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _answers("169.254.169.254"))
    with pytest.raises(UnsafeURLError):
        url_safety.check_resolved_media_urls({"requested_formats": [{"url": "http://meta/x"}]})
    with pytest.raises(UnsafeURLError):
        url_safety.check_resolved_media_urls({"url": "rtmp://public.example/live"})


# ── Routes ───────────────────────────────────────────────────────────────


def _client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, client=("127.0.0.1", 1))


@pytest.mark.parametrize("name", ["evil.conf", "cfg.txt", "run.sh", "x.wav:stream", "clip.m\\..\\x"])
def test_profile_uploads_enforce_the_media_policy(name):
    client = _client()
    payload = b"--exec touch /tmp/x\n"
    profile = client.post(
        "/profiles",
        data={"name": "x"},
        files={"ref_audio": (name, payload, "application/octet-stream")},
    )
    assert profile.status_code == 415


@pytest.mark.parametrize(
    "name", ["book.m4b", "a.mka", "a.ac3", "a.mp2", "a.asf", "a.f4v", "a.mxf", "A.M4B"]
)
def test_real_media_extensions_are_accepted(name):
    from core.media_types import MEDIA_EXTS, media_extension, media_upload_suffix

    assert media_extension(name, MEDIA_EXTS, ".wav") == os.path.splitext(name)[1].lower()
    assert media_upload_suffix(name) == os.path.splitext(name)[1].lower()


def test_media_extensions_are_plain_and_exclude_config_or_script_types():
    import re

    from core.media_types import AUDIO_EXTS, MEDIA_EXTS, VIDEO_EXTS, media_upload_suffix

    assert MEDIA_EXTS == AUDIO_EXTS | VIDEO_EXTS
    assert all(re.fullmatch(r"\.[a-z0-9]{1,8}", ext) for ext in MEDIA_EXTS)
    for ext in (".conf", ".cfg", ".ini", ".env", ".txt", ".json", ".yaml", ".toml",
                ".sh", ".bat", ".cmd", ".ps1", ".py", ".js", ".html", ".svg", ".ps",
                ".exe", ".dll", ".so", ".lnk", ".pth"):
        assert ext not in MEDIA_EXTS, ext
    assert media_upload_suffix("recording") == ""
    assert media_upload_suffix(None, ".mp4") == ".mp4"
    assert media_upload_suffix("evil.conf") is None


def test_ws_tts_emotion_clip_must_live_in_app_folders(tmp_path, monkeypatch):
    from api.routers import tts_stream
    from core import config

    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "calm.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(config, "VOICES_DIR", str(voices))
    monkeypatch.setattr(config, "OUTPUTS_DIR", str(tmp_path / "outputs"))
    assert tts_stream.resolve_emotion_clip("calm.wav") == str((voices / "calm.wav").resolve())
    assert tts_stream.resolve_emotion_clip(str(voices / "calm.wav")).endswith("calm.wav")
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"RIFF")
    for value in (str(outside), "../secret.wav", "/etc/passwd", "", None):
        with pytest.raises(ValueError):
            tts_stream.resolve_emotion_clip(value)


# ── Connect-time guard ───────────────────────────────────────────────────


def test_guard_is_scoped_to_the_guarded_thread():
    with url_safety.guard_outbound_connections():
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("127.0.0.1", 80)
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_guard_recovers_after_a_predecessor_restores_the_resolver():
    """A fresh interpreter reproduces first use inside a DNS test double.

    The dub download test can install the hook while monkeypatch owns the
    global resolver; its teardown then restores that resolver independently.
    """
    script = """
import socket
from unittest.mock import patch
from core import url_safety

def require_refusal():
    with url_safety.guard_outbound_connections():
        try:
            socket.getaddrinfo('127.0.0.1', 80)
        except socket.gaierror:
            return
        raise AssertionError('the guarded resolver allowed loopback')

with patch.object(socket, 'getaddrinfo', socket.getaddrinfo):
    require_refusal()
require_refusal()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_reinstall_keeps_nested_guards_idempotent_and_other_threads_unrestricted(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(socket, "getaddrinfo", url_safety._real_getaddrinfo)
    with ThreadPoolExecutor(max_workers=1) as worker:
        with url_safety.guard_outbound_connections():
            installed = socket.getaddrinfo
            with url_safety.guard_outbound_connections():
                assert socket.getaddrinfo is installed
                with pytest.raises(socket.gaierror):
                    socket.getaddrinfo("127.0.0.1", 80)
            with pytest.raises(socket.gaierror):
                socket.getaddrinfo("127.0.0.1", 80)
            assert worker.submit(socket.getaddrinfo, "127.0.0.1", 80).result(timeout=5)
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_policy_check_sees_private_answers_inside_the_connect_guard(monkeypatch):
    """Inside the guard, ``socket.getaddrinfo`` hides private answers; the policy
    check must still see them and give the clear refusal, not pass the URL on."""
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", url_safety.socket.getaddrinfo)
    for answers in (("192.168.1.10",), (PUBLIC_IP, "192.168.1.10")):
        monkeypatch.setattr(url_safety, "_real_getaddrinfo", _answers(*answers))
        with url_safety.guard_outbound_connections():
            with pytest.raises(UnsafeURLError, match=ALLOW_PRIVATE_ENV):
                check_public_url("http://media.lan:9000/x")
