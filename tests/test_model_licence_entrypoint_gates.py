"""Use-time licence gates at every TTS / dictation / translation entry point (#2689).

Each entry point must refuse an unaccepted gated engine BEFORE it constructs an
engine, loads weights, routes to a worker or touches the network, and must let
an accepted gated engine and a commercial-category engine through. The engines
are tiny fakes; nothing heavy loads. Every gate here is also reachable through
a deeper choke point, so each probe is shaped to reach only its own gate.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

pytestmark = pytest.mark.model_licence_gate  # real enforcement, see conftest

GATED_ENGINE, GATED_REPO = "indextts2", "IndexTeam/IndexTTS-2.5"  # unknown category
COMMERCIAL_ENGINE = "voxcpm2"  # Apache-2.0


def _mod(name):
    return importlib.import_module(name)


@pytest.fixture
def ma():
    return _mod("services.model_acceptance")


@pytest.fixture
def tb():
    return _mod("services.tts_backend")


@pytest.fixture
def store(monkeypatch):
    settings_store = _mod("services.settings_store")
    data: dict[str, str] = {}
    monkeypatch.setattr(settings_store, "get_text", lambda key, default=None: data.get(key, default))
    monkeypatch.setattr(settings_store, "set_text", lambda key, value: data.__setitem__(key, value))
    monkeypatch.setattr(settings_store, "get_license_accepted", lambda engine: False)
    return data


def _accept(ma, repo_id):
    ma.accept(repo_id, ma.status(repo_id)["fingerprint"])


def _fake(engine_id):
    class FakeEngine:
        id = engine_id
        built = 0
        sample_rate = 24000

        def __init__(self):
            type(self).built += 1

        @classmethod
        def configured_identity(cls):
            return None

        def built_identity(self):
            return None

        @classmethod
        def is_available(cls):
            return False, "sentinel-not-available"  # first thing after the gate

        def unload(self):
            pass

    return FakeEngine


@pytest.fixture
def engine(monkeypatch, tb):
    """Make ``cls`` the active/registered engine everywhere an id is resolved."""
    saved = (tb._active_instance, tb._active_instance_id, tb._active_mlx_model_key)

    def install(engine_id):
        cls = _fake(engine_id)
        monkeypatch.setattr(tb, "active_backend_id", lambda: engine_id)
        monkeypatch.setattr(tb, "get_backend_class", lambda _id: cls)
        for name in ("api.routers.batch", "api.routers.dub_generate"):
            mod = sys.modules.get(name)
            if mod is not None and hasattr(mod, "active_backend_id"):
                monkeypatch.setattr(mod, "active_backend_id", lambda: engine_id)
        tb._active_instance = tb._active_instance_id = None
        return cls

    yield install
    tb._active_instance, tb._active_instance_id, tb._active_mlx_model_key = saved
    for cls in [c for c in tb._ENGINE_INSTANCES if c.__name__ == "FakeEngine"]:
        tb._ENGINE_INSTANCES.pop(cls, None)
        tb._ENGINE_LAST_USED.pop(cls, None)


# Each probe returns True when the call got PAST the licence gate and False when
# it was refused with ModelLicenceNotAccepted. Any other outcome is a test bug.
def _outcome(fn, ma):
    try:
        fn()
    except ma.ModelLicenceNotAccepted:
        return False
    return True


def _probe_resolve_generation_backend(cls, tb, ma, monkeypatch):
    def run():
        try:
            asyncio.run(tb.resolve_generation_backend())
        except ValueError as exc:  # is_available() sentinel: the gate let it in
            assert "sentinel-not-available" in str(exc)
    return _outcome(run, ma)


def _probe_generation_route(cls, tb, ma, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    gen = _mod("api.routers.generation")
    monkeypatch.setattr(gen, "_conditioning_refusal", lambda *a, **k: "gate-passed")
    app = FastAPI()
    app.include_router(gen.router)

    @app.exception_handler(ma.ModelLicenceNotAccepted)
    async def _h(request, exc):
        return JSONResponse(status_code=403, content={"detail": exc.detail()})

    resp = TestClient(app, client=("127.0.0.1", 50000)).post("/generate", data={"text": "hello", "engine": cls.id})
    if resp.status_code == 403:
        assert resp.json()["detail"]["code"] == "model_licence_required"
        return False
    assert resp.status_code == 422 and resp.json()["detail"] == "gate-passed", resp.text
    return True


def _probe_stream_cached_instance(cls, tb, ma, monkeypatch):
    """Explicit engine override that matches the already-built active instance."""
    stream = _mod("api.routers.tts_stream")
    tb._active_instance, tb._active_instance_id = cls(), cls.id
    cls.built = 0

    def run():
        assert asyncio.run(stream._resolve_stream_backend(cls.id)) is tb._active_instance
    return _outcome(run, ma)


def _probe_stream_omnivoice_override(cls, tb, ma, monkeypatch):
    """The explicit OmniVoice override constructs the class directly."""
    stream = _mod("api.routers.tts_stream")
    monkeypatch.setattr(tb, "OmniVoiceBackend", cls)

    def run():
        assert isinstance(asyncio.run(stream._resolve_stream_backend(cls.id)), cls)
    return _outcome(run, ma)


PROBES = {
    "resolve_generation_backend": _probe_resolve_generation_backend,
    "generation_route": _probe_generation_route,
    "tts_stream_cached_instance": _probe_stream_cached_instance,
    "tts_stream_omnivoice_override": _probe_stream_omnivoice_override,
}
# Probes that build the engine themselves when the gate lets them through.
_BUILDS_WHEN_PASSED = {"tts_stream_omnivoice_override"}


@pytest.mark.parametrize("name", PROBES)
def test_unaccepted_gated_engine_is_refused_before_construction(name, store, engine, tb, ma, monkeypatch):
    cls = engine(GATED_ENGINE)
    assert PROBES[name](cls, tb, ma, monkeypatch) is False
    assert cls.built == 0


@pytest.mark.parametrize("name", PROBES)
def test_accepted_gated_engine_passes_the_gate(name, store, engine, tb, ma, monkeypatch):
    cls = engine(GATED_ENGINE)
    _accept(ma, GATED_REPO)
    assert PROBES[name](cls, tb, ma, monkeypatch) is True
    if name in _BUILDS_WHEN_PASSED:
        assert cls.built == 1


@pytest.mark.parametrize("name", PROBES)
def test_commercial_engine_needs_no_acceptance(name, store, engine, tb, ma, monkeypatch):
    cls = engine(COMMERCIAL_ENGINE)
    assert PROBES[name](cls, tb, ma, monkeypatch) is True


@pytest.mark.parametrize("name", ["tts_stream_cached_instance"])
def test_revocation_applies_to_already_built_engines(name, store, engine, tb, ma, monkeypatch):
    cls = engine(GATED_ENGINE)
    _accept(ma, GATED_REPO)
    assert PROBES[name](cls, tb, ma, monkeypatch) is True
    ma.revoke(GATED_REPO)
    assert PROBES[name](cls, tb, ma, monkeypatch) is False


# ── OpenAI-compatible speech (typed error propagation) ───

def test_openai_speech_returns_403_with_the_typed_licence_code(store, engine, tb, ma, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    oc = _mod("api.routers.openai_compat")
    cls = engine(GATED_ENGINE)
    cls.is_available = classmethod(lambda c: (True, ""))
    app = FastAPI()
    app.include_router(oc.router)
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    body = {"model": GATED_ENGINE, "input": "hello", "voice": "alloy"}

    resp = client.post("/v1/audio/speech", json=body)
    assert resp.status_code == 403 and cls.built == 0
    assert resp.json()["error"]["code"] == "model_licence_required"

    _accept(ma, GATED_REPO)
    assert client.post("/v1/audio/speech", json=body).status_code != 403
