"""URL imports download natively, under the connect-time guard (core.url_safety).

ffmpeg resolves hosts and follows redirects in its own process, outside the
socket guard, so no URL-import path may hand it a URL: downloads use yt-dlp's
native downloaders, live streams are refused, clips are cut from the local
file, and a "media" download that is really a playlist is refused before
ffmpeg could follow the URLs inside it.
"""
import http.server
import os
import sqlite3
import subprocess
import threading

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import numpy as np
import pytest
import soundfile as sf

from core import url_safety
from core.url_safety import (
    ALLOW_PRIVATE_ENV,
    LIVE_SOURCE_DETAIL,
    NOT_MEDIA_DETAIL,
    UNSUPPORTED_DOWNLOAD_DETAIL,
    UnsafeURLError,
)


@pytest.fixture(autouse=True)
def _no_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_PRIVATE_ENV, raising=False)


# ── Local servers: 127.0.0.1 plays "public", 127.0.0.2 the private target ──


class _Routes(http.server.BaseHTTPRequestHandler):
    routes: dict
    hits: list

    def do_GET(self):  # noqa: N802 - stdlib hook name
        self.hits.append(self.path)
        route = self.routes.get(self.path.split("?")[0])
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        status, headers, body = route(len(self.hits)) if callable(route) else route
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(host, routes=None):
    hits = []
    handler = type("H", (_Routes,), {"routes": routes or {}, "hits": hits})
    try:
        server = http.server.ThreadingHTTPServer((host, 0), handler)
    except OSError:
        pytest.skip(f"cannot bind {host}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hits, f"http://{host}:{server.server_address[1]}"


@pytest.fixture
def servers(monkeypatch):
    started = []

    def start(host, routes=None):
        server, hits, base = _serve(host, routes)
        started.append(server)
        return hits, base

    monkeypatch.setattr(url_safety, "is_public_address", lambda ip: ip == "127.0.0.1")
    monkeypatch.setattr(url_safety, "_proxy_hosts", lambda: frozenset())
    yield start
    for server in started:
        server.shutdown()


def _mp3_bytes():
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 512


def _ytdlp_download(url, tmp_path):
    import yt_dlp

    opts = url_safety.harden_ytdlp_options({
        "quiet": True, "no_warnings": True, "retries": 0, "extractor_retries": 0,
        "fragment_retries": 0, "proxy": "", "outtmpl": str(tmp_path / "original.%(ext)s"),
    })
    with url_safety.guard_outbound_connections(), yt_dlp.YoutubeDL(opts) as ydl:
        ydl.add_post_processor(url_safety.ytdlp_url_guard_postprocessor(), when="before_dl")
        return ydl.extract_info(url, download=True)


def test_media_redirect_to_a_private_host_is_refused(servers, tmp_path):
    import yt_dlp

    target_hits, target = servers("127.0.0.2", {"/secret": (200, {"Content-Type": "audio/mpeg"}, _mp3_bytes())})
    media = {"Content-Type": "audio/mpeg"}

    def clip(hit):
        # Extraction sees real media; the download is redirected to the LAN.
        if hit == 1:
            return 200, media, _mp3_bytes()
        return 302, {"Location": f"{target}/secret"}, b""

    entry_hits, entry = servers("127.0.0.1", {"/clip.mp3": clip})
    with pytest.raises(yt_dlp.utils.DownloadError):
        _ytdlp_download(f"{entry}/clip.mp3", tmp_path)
    assert len(entry_hits) >= 2  # the download itself was attempted
    assert target_hits == []


def test_hls_segments_on_a_private_host_are_refused(servers, tmp_path):
    import yt_dlp

    target_hits, target = servers("127.0.0.2", {"/seg0.ts": (200, {}, b"\x47" * 188)})
    playlist = (
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:4.0,\n{target}/seg0.ts\n#EXT-X-ENDLIST\n"
    ).encode()
    _, entry = servers("127.0.0.1", {"/index.m3u8": (200, {"Content-Type": "application/vnd.apple.mpegurl"}, playlist)})
    with pytest.raises(yt_dlp.utils.DownloadError):
        _ytdlp_download(f"{entry}/index.m3u8", tmp_path)
    assert target_hits == []


def test_a_playlist_served_as_media_is_refused_before_ffmpeg_sees_it(servers, tmp_path):
    import yt_dlp

    target_hits, target = servers("127.0.0.2", {"/x.ts": (200, {}, b"\x47" * 188)})
    smuggled = f"#EXTM3U\n#EXTINF:4.0,\n{target}/x.ts\n#EXT-X-ENDLIST\n".encode()

    def clip(hit):
        # Extraction sees an audio file; the download body is a playlist.
        if hit == 1:
            return 200, {"Content-Type": "audio/mpeg"}, _mp3_bytes()
        return 200, {"Content-Type": "audio/mpeg"}, smuggled

    _, entry = servers("127.0.0.1", {"/clip.mp3": clip})
    with pytest.raises(yt_dlp.utils.DownloadError, match="playlist or web page"):
        _ytdlp_download(f"{entry}/clip.mp3", tmp_path)
    assert not list(tmp_path.glob("original.*"))
    assert target_hits == []


@pytest.mark.parametrize(
    "head", [b"#EXTM3U\n", b"\xef\xbb\xbf  #EXTM3U", b"ffconcat version 1.0", b'<?xml version="1.0"?><MPD', b"v=0\r\n"],
)
def test_manifest_content_is_not_media(tmp_path, head):
    path = tmp_path / "original.m4a"
    path.write_bytes(head + b"\nhttp://192.168.1.1/x\n")
    with pytest.raises(UnsafeURLError, match="playlist"):
        url_safety.check_downloaded_media(str(path))


def test_real_media_passes_the_content_check(tmp_path):
    path = tmp_path / "clip.wav"
    sf.write(path, np.zeros(1600, dtype=np.float32), 16000)
    url_safety.check_downloaded_media(str(path))
    path.write_bytes(_mp3_bytes())
    url_safety.check_downloaded_media(str(path))


# ── Downloader selection: never ffmpeg (or another external program) ─────


@pytest.mark.parametrize(
    "protocol", ["https", "m3u8", "m3u8_native", "http_dash_segments"],
)
def test_hardened_options_select_native_downloaders(protocol):
    from yt_dlp.downloader import get_suitable_downloader
    from yt_dlp.downloader.external import ExternalFD

    params = url_safety.harden_ytdlp_options({})
    info = {"url": "https://cdn.example/x", "protocol": protocol, "ext": "m4a"}
    with url_safety.guard_outbound_connections():
        downloader = get_suitable_downloader(info, params)
    assert not issubclass(downloader, ExternalFD)


def test_external_downloaders_are_refused_under_the_guard(tmp_path, monkeypatch):
    import yt_dlp
    from yt_dlp.downloader.external import FFmpegFD

    url_safety.harden_ytdlp_options({})
    calls = []
    monkeypatch.setattr(FFmpegFD, "_call_downloader", lambda *a, **k: calls.append(a) or 0)
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl, url_safety.guard_outbound_connections():
        assert FFmpegFD.available() is False  # HLS decrypts natively instead of delegating
        with pytest.raises(yt_dlp.utils.DownloadError, match="external downloader"):
            FFmpegFD(ydl, ydl.params).real_download(
                str(tmp_path / "x.m4a"), {"url": "http://192.168.1.1/x", "protocol": "m3u8", "id": "x"}
            )
    assert calls == []


@pytest.mark.parametrize(
    "info",
    [
        {"is_live": True},
        {"live_status": "is_live"},
        {"live_status": "is_upcoming"},
    ],
)
def test_live_sources_are_rejected(info):
    import yt_dlp

    with pytest.raises(yt_dlp.utils.DownloadError, match="live stream"):
        url_safety.ytdlp_url_guard_postprocessor().run({"url": "https://cdn.example/x", **info})


@pytest.mark.parametrize("protocol", ["rtmp", "rtsp", "mms", "websocket_frag", "https+rtmp"])
def test_protocols_needing_an_external_program_are_rejected(protocol):
    with pytest.raises(UnsafeURLError) as excinfo:
        url_safety.check_ytdlp_source({"protocol": protocol, "url": "https://cdn.example/x"})
    assert str(excinfo.value) == UNSUPPORTED_DOWNLOAD_DETAIL


def test_dub_download_uses_hardened_options_and_the_source_guard(tmp_path, monkeypatch):
    import yt_dlp
    from services import dub_pipeline

    seen = {}

    class _FakeYDL:
        def __init__(self, opts):
            seen.setdefault("opts", opts)
            self.pps = []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def add_post_processor(self, pp, when=None):
            self.pps.append((when, pp))

        def extract_info(self, url, download=True):
            ((when, pp),) = self.pps
            assert when == "before_dl"
            pp.run({"is_live": True, "url": url})

        def prepare_filename(self, info):
            raise AssertionError("unreachable")

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.215.14", 443))])
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)
    with pytest.raises(Exception, match="live stream"):
        dub_pipeline.yt_download_sync("https://www.youtube.com/watch?v=live", str(tmp_path))
    opts = seen["opts"]
    assert opts["external_downloader"] == {"default": "native"}
    assert opts["hls_prefer_native"] is True
    assert url_safety._media_file_hook in opts["progress_hooks"]


def test_guarded_ytdlp_subprocess_applies_the_hardening(tmp_path):
    """The gallery's subprocess entry point refuses a playlist served as media."""
    from services.media_tools import guarded_ytdlp_invocation

    smuggled = b"#EXTM3U\n#EXTINF:4.0,\nhttp://192.168.1.1/x.ts\n#EXT-X-ENDLIST\n"
    hits = []

    def clip(hit):
        hits.append(hit)
        body = _mp3_bytes() if hit == 1 else smuggled
        return 200, {"Content-Type": "audio/mpeg"}, body

    server, _, base = _serve("127.0.0.1", {"/clip.mp3": clip})
    argv, env = guarded_ytdlp_invocation()
    env = dict(env or os.environ)
    # Loopback must be reachable for the local test server.
    env[ALLOW_PRIVATE_ENV] = "1"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(name, None)
    try:
        result = subprocess.run(
            [*argv, "--retries", "0", "-o", str(tmp_path / "clip.%(ext)s"), "--", f"{base}/clip.mp3"],
            capture_output=True, text=True, timeout=120, env=env, cwd=tmp_path,
        )
    finally:
        server.shutdown()
    assert result.returncode != 0
    assert NOT_MEDIA_DETAIL in result.stderr
    assert not list(tmp_path.glob("clip.*"))
