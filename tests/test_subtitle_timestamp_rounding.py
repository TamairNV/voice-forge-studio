"""Exported subtitle cue times keep their milliseconds.

The SRT/VTT formatters truncated ``(seconds % 1) * 1000``. Most decimal times
are not exact in binary (2.3 is 2.29999…), so a cue imported as
``00:00:02,300`` exported as ``00:00:02,299`` — every such cue moved a
millisecond early in the dub SRT/VTT downloads, the burned-in subtitles and
the OpenAI-compatible transcription's srt/vtt formats.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("OMNIVOICE_MODEL", "test")

# (seconds, SRT form). 2.3 / 4.1 / 70.7 are the binary-inexact values an SRT
# import produces; 59.9996 must carry into the next second, never ",1000".
_CASES = [
    (0.0, "00:00:00,000"),
    (2.3, "00:00:02,300"),
    (4.1, "00:00:04,100"),
    (70.7, "00:01:10,700"),
    (3661.123, "01:01:01,123"),
    (59.9996, "00:01:00,000"),
]




@pytest.mark.parametrize("seconds,expected", _CASES)
def test_openai_compat_srt_and_vtt_times_round_to_the_millisecond(seconds, expected):
    from api.routers.openai_compat import _format_ts_srt, _format_ts_vtt

    assert _format_ts_srt(seconds) == expected
    assert _format_ts_vtt(seconds) == expected.replace(",", ".")


@pytest.fixture()
def imported_job():
    """A dub job carrying the cue times an imported .srt produces."""
    from services.dub_pipeline import _dub_jobs
    from services.srt_parser import parse_srt

    segments = parse_srt(
        "1\n00:00:02,300 --> 00:00:04,100\nFirst\n\n"
        "2\n00:01:10,700 --> 00:01:12,900\nSecond\n"
    ).segments
    job_id = str(uuid.uuid4())[:8]
    _dub_jobs[job_id] = {
        "video_path": "/nonexistent/original.mp4",
        "duration": 80.0,
        "filename": "imported.mp4",
        "segments": segments,
    }
    yield job_id, _dub_jobs[job_id]
    _dub_jobs.pop(job_id, None)


_SRT_TIMINGS = ["00:00:02,300 --> 00:00:04,100", "00:01:10,700 --> 00:01:12,900"]




