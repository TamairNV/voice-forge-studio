"""Caption markup is styling, not dialogue.

YouTube auto-captions write karaoke timestamps and <c> spans into the cue.
Fansub and player SRTs prefix a line with {\\an8} or {\\i1}. Downloaded
WebVTT already dropped those before seeding a dub; a pasted or picked file
went through parse_srt and kept them, so the editor and the voice read
"c everyone" or "an8 hello".
"""
from __future__ import annotations

import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")

YOUTUBE_KARAOKE = """WEBVTT

00:00:00.160 --> 00:00:02.310 align:start position:0%
hey<00:00:00.480><c> everyone</c><00:00:00.640><c> welcome</c>
"""

MARKUP_VTT = """WEBVTT

00:00:01.000 --> 00:00:02.000
<i>Hello</i> <v Roger>there</v>
"""

ASS_SRT = """1
00:00:01,000 --> 00:00:02,000
{\\an8}{\\i1}Hello{\\i0}
"""


def test_pasted_youtube_karaoke_is_spoken_words_only():
    from services.srt_parser import parse_srt

    assert [cue["text"] for cue in parse_srt(YOUTUBE_KARAOKE).segments] == [
        "hey everyone welcome",
    ]






def test_imported_srt_alignment_tags_are_not_dialogue():
    from services.srt_parser import parse_srt

    assert [cue["text"] for cue in parse_srt(ASS_SRT).segments] == ["Hello"]


def test_literal_less_than_in_srt_is_not_a_tag():
    from services.srt_parser import parse_srt

    srt = "1\n00:00:01,000 --> 00:00:02,000\nI <3 you\n"
    assert parse_srt(srt).segments[0]["text"] == "I <3 you"




def test_escaped_tags_stay_literal_in_spoken_text():
    from services.srt_parser import parse_srt

    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n&lt;i&gt;literal&lt;/i&gt; <i>real</i>\n"
    assert parse_srt(vtt).segments[0]["text"] == "<i>literal</i> real"


def test_srt_dialogue_with_angle_brackets_is_kept():
    from services.srt_parser import parse_srt

    for line in ("2 < 3 and 4 > 1", "<laughter> okay", "if a<b and c>d", "x <= y >= z"):
        srt = f"1\n00:00:01,000 --> 00:00:02,000\n{line}\n"
        assert parse_srt(srt).segments[0]["text"] == line


def test_srt_player_tags_are_not_dialogue():
    from services.srt_parser import parse_srt

    srt = (
        "1\n00:00:01,000 --> 00:00:02,000\n"
        '<font color="#ffff00"><b>Hi</b></font> <u>there</u> <I>you</I>\n'
    )
    assert parse_srt(srt).segments[0]["text"] == "Hi there you"


def test_line_break_tags_separate_words():
    from services.srt_parser import parse_srt

    srt = "1\n00:00:01,000 --> 00:00:02,000\nHello<br>big<BR />world\n"
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello<br/>world\n"
    assert parse_srt(srt).segments[0]["text"] == "Hello big world"
    assert parse_srt(vtt).segments[0]["text"] == "Hello world"


def test_webvtt_escaped_math_reads_as_written():
    from services.srt_parser import parse_srt

    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<i>x &lt; y</i> &amp;&amp; y &gt; z\n"
    assert parse_srt(vtt).segments[0]["text"] == "x < y && y > z"


def test_cjk_and_rtl_text_survive_markup_stripping():
    from services.srt_parser import parse_srt

    words = "\u4f60\u597d \u05e9\u05dc\u05d5\u05dd \u0645\u0631\u062d\u0628\u0627"
    srt = f"1\n00:00:01,000 --> 00:00:02,000\n{{\\an8}}<i>{words}</i>\n"
    vtt = f"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v A>{words}</v>\n"
    assert parse_srt(srt).segments[0]["text"] == words
    assert parse_srt(vtt).segments[0]["text"] == words


def test_malformed_markup_prefixes_parse_in_linear_time():
    import time

    from services.srt_parser import spoken_cue_text

    for junk in ("<" * 50_000, "{\\" * 50_000, "<i" * 50_000, "{{\\" * 50_000, "<br " * 50_000):
        for webvtt in (False, True):
            started = time.perf_counter()
            spoken_cue_text(junk, webvtt=webvtt)
            assert time.perf_counter() - started < 1.0, (junk[:4], webvtt)


def _export(kind, segments):
    from services.dub_pipeline import _dub_jobs
    from fastapi.testclient import TestClient
    from main import app
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _dub_jobs[job_id] = {
        "video_path": "/nonexistent/original.mp4",
        "duration": 10.0,
        "filename": "clip.mp4",
        "segments": segments,
    }
    try:
        client = TestClient(app, client=("127.0.0.1", 50000))
        response = client.get(f"/dub/{kind}/{job_id}")
    finally:
        _dub_jobs.pop(job_id, None)
    assert response.status_code == 200
    return response.text








def _generate(job, texts, lang, cue_ids=None):
    from api.routers.dub_generate import _sync_job_segments
    from schemas.requests import DubRequest, DubSegment

    ids = [str(s["id"]) for s in job["segments"]]
    segs = [
        DubSegment(start=s["start"], end=s["end"], text=t,
                   cue_source_id=(cue_ids or [None] * len(texts))[i])
        for i, (s, t) in enumerate(zip(job["segments"], texts))
    ]
    _sync_job_segments(job, DubRequest(segments=segs, segment_ids=ids, language_code=lang))






