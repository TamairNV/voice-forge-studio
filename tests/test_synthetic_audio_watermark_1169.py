"""Every public synthetic-audio route carries the invisible provenance mark (#1169).

`/v1/audio/speech` returned synthetic audio WITHOUT the AudioSeal watermark
while `/generate` marked the same text — the provenance mark depended on which
door the audio came out of. EU AI Act Art. 50(2) (applicable 2026-08-02, and
expressly carved out of the open-source exemption in Art. 2(12)) requires
synthetic audio to be machine-readably marked, so a per-door coverage gap is a
compliance bug, not a cosmetic one.

The fix routes every producer through ONE chokepoint —
``services.watermark.mark_synthetic`` — and these tests pin, per public route,
that the audio actually leaving the app detects as watermarked (via the real
``services.watermark`` code: real ``mark_synthetic`` → ``embed_watermark``
chunking → ``detect_watermark``), with the watermark setting ON. Only the two
neural AudioSeal models are faked (deterministic marker, no weight download),
plus the usual fake TTS engine idiom from test_generate_engine.py /
test_text_normalization_routes.py.

Fail-before/pass-after: on pre-#1169 code the openai_compat / ws-tts /
stream-preview / batch / audiobook / dub-preview / archetype cases below all
fail (no mark embedded); structural recurrence-proofing lives in
tests/test_watermark_route_coverage.py.
"""
from __future__ import annotations

import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import asyncio
import base64
import importlib
import io
import json
import zlib

import pytest
import torch

SR = 24000


def _wm():
    """Resolve services.watermark at RUN time (test_generate_engine.py idiom):
    tests/backend/** and tests/smoke/** purge + re-import the services tree
    mid-suite, so a module-level binding here can be a stale copy the routes'
    request-time imports no longer see — the monkeypatches would land on a
    dead module and every detection assert would fail full-suite-only."""
    return importlib.import_module("services.watermark")

# ── Deterministic fake AudioSeal (marker survives 16-bit PCM round trips) ────
#
# The generator plants wide comb pulses that survive resampling; the detector measures their centers. Both
# sit BEHIND the real embed_watermark/detect_watermark code (shape handling,
# pref gate, #1045 chunking all real), so the tests exercise the actual
# service seam every route calls — only the neural nets are substituted.

_STRIDE = 977          # prime → never collides with test-audio structure
_AMP = 0.9375          # survives int16 (30719/32767 ≈ 0.93750) and stays > 0.9


class _MarkerGenerator:
    def __call__(self, audio, sample_rate, message=None):
        out = audio.clone()
        for offset in range(16):
            out[..., offset::_STRIDE] = _AMP
        return out


class _MarkerDetector:
    """Gain-invariant, like AudioSeal: a level change (normalization, a
    peak-safe encode) keeps the mark, while clipping or dropping it does not.
    Marked = the comb centers agree with each other (within 10% of their
    median) and stand well clear of the clip's own level. An absolute
    threshold here once made a legitimate loudness change in the DSP chain
    (#3429) read as a lost mark."""

    def detect_watermark(self, audio, sample_rate, message_threshold=0.5):
        probes = audio[..., 8::_STRIDE].flatten()
        if not probes.numel():
            return (0.0, torch.zeros(16))
        level = float(probes.median())
        rms = float(audio.pow(2).mean().sqrt())
        if level <= 0 or level < 2.5 * rms:
            conf = 0.0
        else:
            conf = float(((probes - level).abs() <= 0.1 * level).float().mean())
        if conf > 0.5:
            msg = torch.tensor(_wm().OMNI_MESSAGE, dtype=torch.float32)
        else:
            msg = torch.zeros(16)
        return (conf, msg)


@pytest.fixture()
def marking_on(monkeypatch):
    """Watermark setting ON + fake AudioSeal models installed."""
    monkeypatch.setattr(_wm(), "_generator", _MarkerGenerator())
    monkeypatch.setattr(_wm(), "_detector", _MarkerDetector())
    monkeypatch.setattr(_wm(), "_audioseal_available", True)
    monkeypatch.setattr(_wm(), "is_enabled", lambda: True)


def _assert_marked(wav: torch.Tensor, sr: int, where: str):
    res = _wm().detect_watermark(wav, sr)
    assert res["is_watermarked"] is True, (
        f"{where}: synthetic audio left the app WITHOUT the provenance "
        f"watermark (EU AI Act Art. 50(2), #1169): {res}"
    )
    assert res["is_omnivoice"] is True, f"{where}: mark present but wrong message: {res}"


def _assert_unmarked(wav: torch.Tensor, sr: int, where: str):
    res = _wm().detect_watermark(wav, sr)
    assert res["is_watermarked"] is False, f"{where}: false positive: {res}"


def _wav_from_bytes(data: bytes):
    from services.audio_io import load_audio
    return load_audio(io.BytesIO(data))


def _pcm16_to_tensor(data: bytes) -> torch.Tensor:
    import numpy as np
    return torch.from_numpy(
        np.frombuffer(data, dtype="<i2").astype("float32") / 32767.0
    ).unsqueeze(0)


# ── Fake TTS engine (registry idiom from test_generate_engine.py) ────────────


def _tts_mod():
    return importlib.import_module("services.tts_backend")


def _speechy(n: int = SR, seed: int = 7) -> torch.Tensor:
    """Deterministic noise burst: speech-like enough for the blank/buzz guards,
    every sample < 0.9 even after peak normalization → the marker comb is the
    only thing the fake detector can ever see."""
    g = torch.Generator().manual_seed(seed)
    return (torch.randn(1, n, generator=g) * 0.25).clamp(-0.79, 0.79)


def _make_fake_engine(engine_id: str):
    class _FakeEngine(_tts_mod().TTSBackend):
        id = engine_id
        display_name = f"{engine_id} (test)"
        supports_cloning = True
        gpu_compat = ("cpu",)
        calls: list = []

        @property
        def sample_rate(self) -> int:
            return SR

        @property
        def supported_languages(self) -> list[str]:
            return ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw) -> torch.Tensor:
            type(self).calls.append((text, kw))
            return _speechy(seed=zlib.crc32(text.encode("utf-8")) & 0xFFFF)

    return _FakeEngine


@pytest.fixture()
def fake_engine(monkeypatch):
    tb = _tts_mod()
    tb.reset_active_backend()
    fake = _make_fake_engine("fake-wm-1169")
    monkeypatch.setitem(tb._REGISTRY, "fake-wm-1169", fake)
    monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)
    yield fake
    tb.reset_active_backend()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, client=("127.0.0.1", 50000))


# ── Sanity: the harness itself can't fake a pass ─────────────────────────────


def test_unmarked_engine_output_is_not_detected(marking_on):
    _assert_unmarked(_speechy(), SR, "raw engine output")


# ── POST /v1/audio/speech (the reported gap) ─────────────────────────────────


def test_openai_speech_wav_response_is_watermarked(client, fake_engine, marking_on):
    res = client.post("/v1/audio/speech", json={
        "model": "fake-wm-1169", "input": "Hello there",
        "response_format": "wav",
    })
    assert res.status_code == 200, res.text
    wav, sr = _wav_from_bytes(res.content)
    _assert_marked(wav, sr, "POST /v1/audio/speech (wav)")


def test_openai_speech_pcm_response_is_watermarked(client, fake_engine, marking_on):
    """The raw-PCM branch bypasses the container encoder — it must not bypass
    the mark (tensor-stage marking covers every response_format uniformly)."""
    res = client.post("/v1/audio/speech", json={
        "model": "fake-wm-1169", "input": "Hello there",
        "response_format": "pcm",
    })
    assert res.status_code == 200, res.text
    _assert_marked(_pcm16_to_tensor(res.content), SR, "POST /v1/audio/speech (pcm)")


# ── WS /ws/tts (streaming TTS) ───────────────────────────────────────────────


def test_ws_tts_streamed_pcm_is_watermarked(client, fake_engine, marking_on):
    pcm = bytearray()
    with client.websocket_connect("/ws/tts") as ws:
        # Single sentence → one generate → the stream is one marked tensor
        # (multi-sentence requests are marked per sentence; the 16-bit message
        # repeats, so detection over any sentence still works).
        ws.send_json({"text": "Hello there", "engine": "fake-wm-1169"})
        while True:
            msg = ws.receive()
            if msg.get("bytes") is not None:
                pcm.extend(msg["bytes"])
                continue
            frame = json.loads(msg["text"])
            if frame.get("type") in ("done", "error"):
                assert frame["type"] == "done", frame
                break
    assert pcm, "no audio frames received"
    _assert_marked(_pcm16_to_tensor(bytes(pcm)), SR, "WS /ws/tts")


# ── POST /generate — classic response and streamed preview chunks ────────────


@pytest.fixture()
def hermetic_outputs(tmp_path, monkeypatch):
    import core.config as cfg
    import api.routers.generation as gen_mod

    outdir = tmp_path / "outputs"
    outdir.mkdir()
    monkeypatch.setattr(cfg, "OUTPUTS_DIR", str(outdir))
    monkeypatch.setattr(gen_mod, "OUTPUTS_DIR", str(outdir))
    return outdir


def test_generate_classic_response_is_watermarked(
    client, fake_engine, marking_on, hermetic_outputs,
):
    res = client.post("/generate", data={
        "text": "Hello there", "engine": "fake-wm-1169",
    })
    assert res.status_code == 200, res.text
    wav, sr = _wav_from_bytes(res.content)
    _assert_marked(wav, sr, "POST /generate")


def _stream_chunks(client, data):
    chunks, done = [], None
    with client.stream("POST", "/generate", data={**data, "stream": "true"}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if not line.strip():
                continue
            ev = json.loads(line)
            assert ev.get("type") != "error", ev
            if ev["type"] == "chunk":
                chunks.append(_pcm16_to_tensor(base64.b64decode(ev["pcm"])))
            elif ev["type"] == "done":
                done = ev
    assert done is not None, "stream ended without done"
    return chunks


def test_generate_stream_single_chunk_preview_is_watermarked(
    client, fake_engine, marking_on, hermetic_outputs,
):
    chunks = _stream_chunks(client, {"text": "Hello there", "engine": "fake-wm-1169"})
    assert len(chunks) == 1
    _assert_marked(chunks[0], SR, "POST /generate stream=true (single chunk)")


def test_generate_stream_multi_chunk_previews_are_watermarked(
    client, fake_engine, marking_on, hermetic_outputs,
):
    chunks = _stream_chunks(client, {
        "text": "First sentence here. Second sentence follows now.",
        "engine": "fake-wm-1169", "max_chunk_chars": "25",
    })
    assert len(chunks) >= 2, "expected the multi-chunk streaming path"
    for i, ch in enumerate(chunks):
        _assert_marked(ch, SR, f"POST /generate stream=true (chunk {i})")


# ── Archetypes: preview clip + materialized profile reference ────────────────


def test_archetype_render_is_watermarked(tmp_path, monkeypatch, marking_on):
    import api.routers.archetypes as arch
    import api.routers.generation as gen_mod
    from services.audio_io import load_audio

    class _Model:
        sampling_rate = SR

    async def _fake_get_model():
        return _Model()

    monkeypatch.setattr(gen_mod, "get_model", _fake_get_model)
    monkeypatch.setattr(gen_mod, "_run_inference", lambda *a, **k: _speechy())

    out = tmp_path / "arch.wav"
    a = {"id": "t", "name": "T", "language": "en",
         "sample_script": "Hello there.", "instruct": "warm narrator"}
    asyncio.run(arch._render_archetype_wav(a, out))
    wav, sr = load_audio(str(out))
    _assert_marked(wav, sr, "archetype render (served preview + profile reference WAV)")
