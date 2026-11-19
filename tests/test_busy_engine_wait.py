"""A busy engine never becomes a missing or silent piece of an assembled output.

A native PCM stream can hold the shared engine, so a buffered generation raises
``GpuPoolBusyError`` at once. Every caller that assembles an artifact (audiobook
chapter, dub segment, batch segment) waits through ``await_free_engine`` inside
its own timeout budget, off the GPU worker: it either succeeds once the engine
frees up or the job fails clearly. Interactive single requests keep the route's
503/429 + Retry-After convention. No models / GPU: every engine is a fake.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os

os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import pytest
import torch

from schemas.requests import DubRequest, DubSegment


def _busy():
    from services.model_manager import GpuPoolBusyError
    return GpuPoolBusyError("busy", retry_after=1)


@pytest.fixture
def fast_sleep(monkeypatch):
    real = asyncio.sleep
    slept = []

    async def sleep(delay, *a, **k):
        slept.append(delay)
        await real(0.005)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return slept


# ── shared helper ──────────────────────────────────────────────────────────


def test_helper_retries_until_free(fast_sleep):
    from services.model_manager import await_free_engine
    calls = []

    async def call():
        calls.append(1)
        if len(calls) < 3:
            raise _busy()
        return "ok"

    assert asyncio.run(await_free_engine(call, budget_s=30)) == "ok"
    assert len(calls) == 3 and len(fast_sleep) == 2


def test_helper_raises_busy_past_budget(fast_sleep):
    from services.model_manager import GpuPoolBusyError, await_free_engine

    async def call():
        raise _busy()

    with pytest.raises(GpuPoolBusyError):
        asyncio.run(await_free_engine(call, budget_s=0))


def test_helper_stops_when_cancelled(fast_sleep):
    from services.model_manager import GpuPoolBusyError, await_free_engine
    state = {"cancelled": False, "calls": 0}

    async def call():
        state["calls"] += 1
        state["cancelled"] = True
        raise _busy()

    with pytest.raises(GpuPoolBusyError):
        asyncio.run(await_free_engine(call, budget_s=30,
                                      is_cancelled=lambda: state["cancelled"]))
    assert state["calls"] == 1


def test_helper_does_not_swallow_other_errors(fast_sleep):
    from services.model_manager import await_free_engine

    async def call():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(await_free_engine(call, budget_s=30))


# ── dub ────────────────────────────────────────────────────────────────────


@pytest.fixture
def dub_env(monkeypatch, tmp_path):
    import api.routers.dub_generate as dg

    tb = importlib.import_module("services.tts_backend")
    tb.reset_active_backend()
    job = {"duration": 2.0, "dubbed_tracks": {}, "speaker_clones": {}}
    job_dir = tmp_path / "jobX"
    job_dir.mkdir()
    monkeypatch.setattr(dg, "_get_job", lambda job_id: job)
    monkeypatch.setattr(dg, "_save_job", lambda job_id, j: None)
    monkeypatch.setattr(dg, "DUB_DIR", str(tmp_path))
    monkeypatch.setattr(dg, "dub_seg_path",
                        lambda job_id, seg_id: str(job_dir / f"seg_{seg_id}.wav"))
    monkeypatch.setattr(dg, "rvc_is_enabled", lambda: False)
    monkeypatch.setattr(dg, "mark_synthetic", lambda wav, sr, **kw: wav)
    monkeypatch.setattr(dg, "apply_mastering", lambda a, sample_rate=None: a)
    monkeypatch.setattr(dg, "get_effect_chain", lambda preset: None)
    monkeypatch.setattr(dg, "apply_effects_chain", lambda a, **k: a)
    monkeypatch.setattr(dg, "normalize_audio", lambda a, target_dBFS=None: a)

    class _Engine(tb.TTSBackend):
        id = "fake-busy"
        display_name = "Fake busy"
        supports_cloning = True
        gpu_compat = ("cpu",)
        calls = 0
        busy_times = 0

        @property
        def sample_rate(self):
            return 24000

        @property
        def supported_languages(self):
            return ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw):
            type(self).calls += 1
            if type(self).calls <= type(self).busy_times:
                raise _busy()
            return torch.full((1, 24000), 0.25)

    tb._REGISTRY["fake-busy"] = _Engine
    monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "fake-busy")
    yield dg, job, _Engine
    tb.reset_active_backend()
    tb._REGISTRY.pop("fake-busy", None)


def _dub_events(dg, monkeypatch, *, cancelled=lambda: False):
    events = []

    class _TM:
        def is_cancelled(self, _id):
            return cancelled()

        async def add_task(self, _id, _type, func, *args, **_kw):
            async for e in func(*args):
                events.append(e)

    monkeypatch.setattr(dg, "task_manager", _TM())
    req = DubRequest(segments=[DubSegment(start=0.0, end=1.0, text="hola")],
                     segment_ids=["0"], language="Auto", language_code="es", num_step=4)
    asyncio.run(dg.dub_generate("jobX", req))
    return "".join(events)






