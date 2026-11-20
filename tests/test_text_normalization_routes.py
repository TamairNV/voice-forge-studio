"""Text-normalization coverage for the three remaining TTS entry points.

Sibling of tests/test_text_normalization.py (which pins the pass itself and
the /generate + audiobook integrations). These routes hand text to
`backend.generate` directly — none funnels through /generate or the dub /
audiobook call sites — so each needs its own wiring, pinned here with the
same applied-EXACTLY-once spy + toggle-off contract:

  - POST /v1/audio/speech (OpenAI-compatible API) — normalized once, with the
    request's `language`, before the generate dispatch.
  - WS /ws/tts (streaming TTS) — normalized once on the WHOLE request text,
    BEFORE the sentence chunker fans it out (multi-sentence requests must not
    re-normalize per sentence).
  - batch dub queue — normalized once per segment inside `_gen`, with the
    job's target language (same shape as dub_generate's `_gen`).

Fake-engine/client harness from tests/test_text_normalization.py; the batch
pipeline harness is the hermetic stub set from
tests/test_dub_batch_engine_selection.py.
"""
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import asyncio
import importlib
import json

import pytest
import torch

from services import text_normalization


def _tts_mod():
    """Resolve services.tts_backend at RUN time (same rationale as
    test_generate_engine.py — collection-time bindings can go stale)."""
    return importlib.import_module("services.tts_backend")


def _make_fake_engine():
    class _FakeEngine(_tts_mod().TTSBackend):
        id = "fake-norm-route"
        display_name = "Fake Norm Route Engine (test)"
        supports_cloning = True
        gpu_compat = ("cpu",)
        calls: list = []

        @property
        def sample_rate(self) -> int:
            return 24000

        @property
        def supported_languages(self) -> list[str]:
            return ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw) -> torch.Tensor:
            type(self).calls.append((text, kw))
            return torch.zeros(1, 24000)

    return _FakeEngine


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture()
def fake_engine(monkeypatch):
    """Register a fresh fake engine in the REAL registry; reset the MM2-01
    active-backend cache so batch's resolve_generation_backend re-resolves."""
    tb = _tts_mod()
    tb.reset_active_backend()
    fake = _make_fake_engine()
    monkeypatch.setitem(tb._REGISTRY, "fake-norm-route", fake)
    monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)
    yield fake
    tb.reset_active_backend()


@pytest.fixture()
def norm_spy(monkeypatch):
    """Count normalize_for_tts calls (patched on the module object the routes
    import per-request) while keeping the real behavior."""
    monkeypatch.delenv(text_normalization.ENV_VAR, raising=False)
    norm_mod = importlib.import_module("services.text_normalization")
    calls = []
    real = norm_mod.normalize_for_tts

    def spy(text, language=None):
        calls.append((text, language))
        return real(text, language)

    monkeypatch.setattr(norm_mod, "normalize_for_tts", spy)
    return calls


# ── POST /v1/audio/speech (OpenAI-compatible API) ────────────────────────────


def test_openai_speech_applies_normalization_exactly_once(client, fake_engine, norm_spy):
    res = client.post("/v1/audio/speech", json={
        "model": "fake-norm-route", "input": "Dr. Smith has 2 cats",
        "language": "en", "response_format": "wav",
    })
    assert res.status_code == 200, res.text
    assert len(norm_spy) == 1  # exactly once, at the choke point
    assert norm_spy[0] == ("Dr. Smith has 2 cats", "en")
    assert len(fake_engine.calls) == 1
    assert fake_engine.calls[0][0] == "Doctor Smith has two cats"


def test_openai_speech_toggle_off_sends_raw_text(client, fake_engine, monkeypatch):
    monkeypatch.setenv(text_normalization.ENV_VAR, "0")
    res = client.post("/v1/audio/speech", json={
        "model": "fake-norm-route", "input": "Dr. Smith has 2 cats",
        "language": "en", "response_format": "wav",
    })
    assert res.status_code == 200, res.text
    assert fake_engine.calls[-1][0] == "Dr. Smith has 2 cats"


@pytest.fixture()
def saved_pronunciations(monkeypatch, tmp_path):
    """Real saved rows; do not replace the pronunciation implementation."""
    db = importlib.import_module("core.db")
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "pronunciation.db"))
    with db.db_conn() as conn:
        conn.executescript(db._BASE_SCHEMA)
        conn.execute("INSERT INTO voice_profiles (id, name) VALUES (?, ?)",
                     ("pron-voice", "Pronunciation Voice"))
        for index, (term, replacement, profile) in enumerate([
            ("Doctor", "Professor", ""),
            ("cats", "kittens", ""),
            ("kittens", "should not be applied twice", ""),
            ("cats", "felines", "pron-voice"),
        ]):
            conn.execute(
                "INSERT INTO pronunciation_entries "
                "(id,term,replacement,type,language,enabled,created_at,profile_id) "
                "VALUES (?,?,?,'respelling','en',1,?,?)",
                (str(index), term, replacement, index, profile),
            )
    monkeypatch.delenv("OMNIVOICE_PRONUNCIATION", raising=False)
    monkeypatch.delenv(text_normalization.ENV_VAR, raising=False)


@pytest.mark.parametrize("voice,spoken", [
    ("alloy", "kittens"),
    ("pron-voice", "felines"),
    ("Pronunciation Voice", "felines"),
])
def test_openai_uses_saved_pronunciations_and_inline_choice(
    client, fake_engine, saved_pronunciations, voice, spoken,
):
    res = client.post("/v1/audio/speech", json={
        "model": "fake-norm-route", "voice": voice,
        "input": "Dr. Smith has 2 cats. [[cats|cats]]",
        "language": "en", "response_format": "wav",
    })
    assert res.status_code == 200, res.text
    assert fake_engine.calls[-1][0] == f"Professor Smith has two {spoken}. cats"


def test_ws_uses_saved_voice_pronunciations_before_sentence_split(
    client, fake_engine, saved_pronunciations,
):
    frames = _run_ws_request(client, {
        "text": "Dr. Smith has 2 cats. [[cats|cats]]",
        "language": "en", "voice": "pron-voice", "engine": "fake-norm-route",
    })
    assert frames[-1]["type"] == "done", frames
    spoken = " ".join(text.strip() for text, _ in fake_engine.calls)
    assert spoken == "Professor Smith has two felines. cats"


# ── WS /ws/tts (streaming TTS) ───────────────────────────────────────────────


def _run_ws_request(client, payload):
    """Send one /ws/tts request; drain frames until done/error. Returns the
    JSON frames (binary PCM chunks are skipped)."""
    frames = []
    with client.websocket_connect("/ws/tts") as ws:
        ws.send_json(payload)
        while True:
            msg = ws.receive()
            text = msg.get("text")
            if text is None:
                continue  # binary PCM chunk
            frame = json.loads(text)
            frames.append(frame)
            if frame.get("type") in ("done", "error"):
                return frames


def test_ws_tts_applies_normalization_exactly_once(client, fake_engine, norm_spy):
    # Two sentences: the chunker fans the request out into per-sentence
    # generates, but normalization must run ONCE, on the whole text, before
    # the split — never once per sentence.
    frames = _run_ws_request(client, {
        "text": "Dr. Smith has 2 cats. He is 40.",
        "language": "en", "engine": "fake-norm-route",
    })
    assert frames[-1]["type"] == "done", frames
    assert len(norm_spy) == 1
    assert norm_spy[0] == ("Dr. Smith has 2 cats. He is 40.", "en")
    assert fake_engine.calls, "engine never ran"
    joined = " ".join(t.strip() for t, _ in fake_engine.calls)
    assert joined == "Doctor Smith has two cats. He is forty."


def test_ws_tts_toggle_off_sends_raw_text(client, fake_engine, monkeypatch):
    monkeypatch.setenv(text_normalization.ENV_VAR, "0")
    frames = _run_ws_request(client, {
        "text": "Dr. Smith has 2 cats",
        "language": "en", "engine": "fake-norm-route",
    })
    assert frames[-1]["type"] == "done", frames
    assert fake_engine.calls[-1][0] == "Dr. Smith has 2 cats"


def test_ws_tts_reports_true_first_audio_latency(client, fake_engine, monkeypatch):
    """TTFA ends at the first binary chunk, not when the whole render ends."""
    import api.routers.tts_stream as stream
    from services import watermark

    # t0, synth start, synth end, first audio byte, finish.
    # Synthesis takes 0.20s; the remaining 0.30s of wall clock is delivery.
    ticks = iter((100.0, 100.0, 100.20, 100.125, 100.5))
    monkeypatch.setattr(stream, "_perf_counter", lambda: next(ticks), raising=False)
    monkeypatch.setattr(watermark, "mark_synthetic", lambda wav, _sr, **_kw: wav)

    frames = _run_ws_request(client, {
        "text": "One sentence.",
        "language": "en",
        "engine": "fake-norm-route",
    })
    done = frames[-1]

    assert done["type"] == "done", frames
    assert done["ttfa_ms"] == pytest.approx(125.0)
    assert done["gen_time_s"] == pytest.approx(0.5)   # end-to-end, incl. delivery
    assert done["duration_s"] == pytest.approx(1.0)
    # RTF is a RENDER metric: 0.20s of synthesis per 1.0s of audio. Deriving it
    # from the 0.5s wall clock would report 0.5 and blame the engine for a slow
    # consumer (#1620 review).
    assert done["rtf"] == pytest.approx(0.2)
