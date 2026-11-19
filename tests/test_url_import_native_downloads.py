"""URL imports download natively, under the connect-time guard (core.url_safety).

ffmpeg resolves hosts and follows redirects in its own process, outside the
socket guard, so no URL-import path may hand it a URL: downloads use yt-dlp's
native downloaders, live streams are refused, clips are cut from the local
file, and a "media" download that is really a playlist is refused before
ffmpeg could follow the URLs inside it.
"""
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import numpy as np
import pytest
import soundfile as sf

from core import url_safety
from core.url_safety import (
    ALLOW_PRIVATE_ENV,
    UNSUPPORTED_DOWNLOAD_DETAIL,
    UnsafeURLError,
)


@pytest.fixture(autouse=True)
def _no_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_PRIVATE_ENV, raising=False)


def _mp3_bytes():
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 512


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


@pytest.mark.parametrize("protocol", ["rtmp", "rtsp", "mms", "websocket_frag", "https+rtmp"])
def test_protocols_needing_an_external_program_are_rejected(protocol):
    with pytest.raises(UnsafeURLError) as excinfo:
        url_safety.check_ytdlp_source({"protocol": protocol, "url": "https://cdn.example/x"})
    assert str(excinfo.value) == UNSUPPORTED_DOWNLOAD_DETAIL
