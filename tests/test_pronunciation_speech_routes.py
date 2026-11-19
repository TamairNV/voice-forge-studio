"""Saved pronunciation rows reach actual speech dispatch, once per input.

These fixtures come from maintained route suites; only inference/ASR are fake.
The dictionary is persisted in SQLite and its precedence runs unmodified.
"""
import asyncio
import importlib
import sqlite3
import threading

import httpx
import pytest
import torch

from test_text_normalization_routes import (  # noqa: F401
    client, fake_engine, saved_pronunciations, _run_ws_request,
)


@pytest.fixture
def dictionary_read_threads(saved_pronunciations, monkeypatch):
    pronunciation = importlib.import_module("services.pronunciation")
    load = pronunciation.load_entries_from_db
    reads_on_event_loop = []

    def load_rows():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            reads_on_event_loop.append(False)
        else:
            reads_on_event_loop.append(True)
        return load()

    monkeypatch.setattr(pronunciation, "load_entries_from_db", load_rows)
    return reads_on_event_loop


@pytest.mark.parametrize("route", ["openai", "websocket"])
def test_native_streams_prepare_the_whole_saved_voice_text_once(
    client, fake_engine, saved_pronunciations, monkeypatch, dictionary_read_threads, route,
):
    streamed = []

    def stream_audio(_self, text, **kwargs):
        streamed.append((text, kwargs))
        yield torch.ones(1, 240) * 0.1
        yield torch.ones(1, 240) * 0.2

    monkeypatch.setattr(fake_engine, "can_stream", lambda _self, **_kw: True, raising=False)
    monkeypatch.setattr(fake_engine, "stream_audio", stream_audio, raising=False)
    payload = dict(text="Dr. Smith has 2 cats. [[cats|cats]]", language="en",
                   voice="pron-voice", engine="fake-norm-route")
    if route == "websocket":
        frames = _run_ws_request(client, payload)
        assert frames[-1]["type"] == "done", frames
    else:
        response = client.post("/v1/audio/speech", json={
            "model": payload["engine"], "input": payload["text"],
            "voice": "Pronunciation Voice", "language": "en", "response_format": "pcm",
            "stream_format": "audio",
        })
        assert response.status_code == 200 and response.content, response.text
    assert len(streamed) == 1
    assert streamed[0][0] == "Professor Smith has two felines. cats"
    assert not fake_engine.calls
    assert dictionary_read_threads == [False]


def test_voice_conversion_uses_saved_voice_entries_after_asr(
    client, fake_engine, saved_pronunciations, monkeypatch, tmp_path, dictionary_read_threads,
):
    from test_voice_convert import _wire_stubs, _FakeASR, _post_convert

    db = importlib.import_module("core.db")
    with db.db_conn() as conn:
        conn.execute("UPDATE voice_profiles SET ref_audio_path='convert-ref.wav', "
                     "ref_text='reference words', language='en' WHERE id='pron-voice'")
    generated = tmp_path / "converted"
    generated.mkdir()
    monkeypatch.setattr("api.routers.generation.OUTPUTS_DIR", str(generated))
    _wire_stubs(monkeypatch, engine_cls=fake_engine, asr=_FakeASR({
        "text": "Dr. Smith has 2 cats. [[cats|cats]]", "segments": [],
    }))
    response = _post_convert(client, "pron-voice", match_duration="0")
    assert response.status_code == 200, response.text
    assert fake_engine.calls[-1][0] == "Professor Smith has two felines. cats."
    assert dictionary_read_threads == [False]


@pytest.mark.parametrize("route", ["openai", "websocket"])
@pytest.mark.parametrize("control", ["disabled", "unreadable"])
def test_unavailable_saved_dictionary_still_normalizes_and_honors_inline(
    client, fake_engine, saved_pronunciations, monkeypatch, route, control,
):
    pronunciation = importlib.import_module("services.pronunciation")
    loads = []

    def unavailable():
        loads.append(True)
        raise sqlite3.OperationalError("controlled dictionary read failure")

    monkeypatch.setattr(pronunciation, "load_entries_from_db", unavailable)
    if control == "disabled":
        monkeypatch.setenv("OMNIVOICE_PRONUNCIATION", "0")
    payload = dict(text="Dr. Smith has 2 cats. [[cats|felines]]", language="en",
                   voice="pron-voice", engine="fake-norm-route")
    if route == "websocket":
        frames = _run_ws_request(client, payload)
        assert frames[-1]["type"] == "done", frames
    else:
        response = client.post("/v1/audio/speech", json={
            "model": payload["engine"], "input": payload["text"],
            "voice": payload["voice"], "language": "en", "response_format": "wav",
        })
        assert response.status_code == 200, response.text
    assert " ".join(text.strip() for text, _ in fake_engine.calls) == "Doctor Smith has two cats. felines"
    assert bool(loads) is (control == "unreadable")


@pytest.mark.parametrize("pronounce,spoken", [("0", "cats"), ("1", "felines")])
def test_generate_request_switch_keeps_inline_choices(
    client, fake_engine, saved_pronunciations, monkeypatch, tmp_path, dictionary_read_threads,
    pronounce, spoken,
):
    generated = tmp_path / "generated"
    generated.mkdir()
    monkeypatch.setattr("api.routers.generation.OUTPUTS_DIR", str(generated))
    response = client.post("/generate", data={
        "engine": "fake-norm-route", "profile_id": "pron-voice", "language": "English",
        "text": "Dr. Smith has 2 cats. [[cats|cats]]", "pronounce": pronounce, "seed": "42",
    })
    assert response.status_code == 200, response.text
    title = "Doctor" if pronounce == "0" else "Professor"
    assert fake_engine.calls[-1][0] == f"{title} Smith has two {spoken}. cats"
    assert dictionary_read_threads == ([False] if pronounce == "1" else [])


@pytest.mark.parametrize("route", ["openai", "websocket"])
def test_sentence_stream_dictionary_reads_run_off_the_event_loop(
    client, fake_engine, saved_pronunciations, dictionary_read_threads, route,
):
    payload = dict(text="Dr. Smith has 2 cats. [[cats|cats]]", language="en",
                   voice="pron-voice", engine="fake-norm-route")
    if route == "websocket":
        frames = _run_ws_request(client, payload)
        assert frames[-1]["type"] == "done", frames
    else:
        response = client.post("/v1/audio/speech", json={
            "model": payload["engine"], "input": payload["text"],
            "voice": payload["voice"], "language": "en", "response_format": "pcm",
            "stream_format": "audio",
        })
        assert response.status_code == 200 and response.content, response.text
    assert dictionary_read_threads == [False]
    assert " ".join(text.strip() for text, _kw in fake_engine.calls) == "Professor Smith has two felines. cats"


def test_public_sentence_stream_reads_one_dictionary_snapshot_off_loop(
    fake_engine, saved_pronunciations, dictionary_read_threads,
):
    from api.routers.tts_stream import synthesize_stream

    async def render():
        return [chunk async for chunk in synthesize_stream(
            "Dr. Smith has 2 cats. [[cats|cats]]", language="en",
            voice="pron-voice", engine="fake-norm-route",
        )]

    assert asyncio.run(render())
    assert dictionary_read_threads == [False]
    assert " ".join(text.strip() for text, _kw in fake_engine.calls) == "Professor Smith has two felines. cats"


def test_openai_dictionary_read_keeps_the_request_loop_responsive(
    fake_engine, saved_pronunciations, monkeypatch,
):
    from main import app
    pronunciation = importlib.import_module("services.pronunciation")
    load = pronunciation.load_entries_from_db
    started, release = threading.Event(), threading.Event()
    released_while_reading = []

    def load_rows():
        started.set()
        released_while_reading.append(release.wait(timeout=3))
        return load()

    monkeypatch.setattr(pronunciation, "load_entries_from_db", load_rows)

    async def render():
        async def observe():
            assert await asyncio.to_thread(started.wait, 3), "request never reached dictionary loading"
            release.set()  # unrelated event-loop work can run during the read

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://localhost") as api:
            response, _ = await asyncio.gather(api.post("/v1/audio/speech", json={
                "model": "fake-norm-route", "input": "cats", "voice": "pron-voice",
                "language": "en", "response_format": "wav",
            }), observe())
            assert response.status_code == 200, response.text

    asyncio.run(render())
    assert released_while_reading == [True]


def test_disabling_normalization_does_not_disable_saved_pronunciations(
    client, fake_engine, saved_pronunciations, monkeypatch,
):
    monkeypatch.setenv("OMNIVOICE_TEXT_NORMALIZATION", "0")
    response = client.post("/v1/audio/speech", json={
        "model": "fake-norm-route", "voice": "pron-voice", "language": "en",
        "input": "Dr. Smith has 2 cats. [[cats|cats]]", "response_format": "wav",
    })
    assert response.status_code == 200, response.text
    assert fake_engine.calls[-1][0] == "Dr. Smith has 2 felines. cats"
