"""No-ASR-installed preflight (TTS-only installs).

Only the TTS model is required (models.yaml): a fresh install has NO ASR
model on disk. Every whisper-family backend auto-downloads its weights from
HF on first load, so before this preflight an ASR-less install that hit
dub / batch / dictation either silently pulled a multi-GB model or 500'd.
These tests pin the contract: each consumer answers with a typed 409 (or SSE
error) carrying ``{"error": "asr_model_missing", "recommended": {...}}``
BEFORE any backend is constructed — and stays silent when a model IS
installed (mocked via the same ``is_cached`` helper the model store uses).
"""
from __future__ import annotations

import contextlib
import os
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_installed_repo_memo():
    """_repo_installed memoizes positives module-globally and never
    invalidates, and test_installed_positive_is_memoized writes the very repo
    the missing-model tests probe — so run order decided what these tests saw
    (CodeRabbit on #1610). Deterministic now: empty before, empty after."""
    from services import asr_backend

    asr_backend._INSTALLED_REPO_MEMO.clear()
    yield
    asr_backend._INSTALLED_REPO_MEMO.clear()


@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app, client=("127.0.0.1", 50000))


_KEPT_FASTER_WHISPER_REPO = "deepdml/faster-whisper-large-v3-turbo-ct2"


@contextlib.contextmanager
def _offline_asr_missing(cached: bool):
    """Deterministic offline selection: catalogued faster-whisper turbo,
    with the HF cache reporting installed/not-installed per ``cached``."""
    from api.routers.setup import models as setup_models
    from services import asr_backend
    with patch.dict(os.environ, {"ASR_MODEL_FASTER": _KEPT_FASTER_WHISPER_REPO}), \
         patch.object(asr_backend, "active_backend_id", return_value="faster-whisper"), \
         patch.object(setup_models, "is_cached", return_value=cached), \
         patch.object(setup_models, "cache_is_complete", return_value=True):
        yield


@contextlib.contextmanager
def _dictation_whisper_missing():
    """Deterministic dictation selection: no sherpa pref, MLX unavailable,
    faster-whisper package available, model NOT cached."""
    from api.routers.setup import models as setup_models
    from services import asr_backend
    with patch.dict(os.environ, {"ASR_MODEL_FASTER": _KEPT_FASTER_WHISPER_REPO}), \
         patch.object(asr_backend, "dictation_model_id", return_value=None), \
         patch.object(asr_backend.MLXWhisperBackend, "is_available",
                      return_value=(False, "not apple silicon")), \
         patch.object(asr_backend.FasterWhisperBackend, "is_available",
                      return_value=(True, "ready")), \
         patch.object(asr_backend.SherpaDictationBackend, "is_available",
                      return_value=(False, "sherpa-onnx not installed")), \
         patch.object(setup_models, "is_cached", return_value=False), \
         patch.object(setup_models, "cache_is_complete", return_value=True):
        yield


# ── Helper contract ─────────────────────────────────────────────────────────

class TestHelper:
    def test_none_when_model_installed(self):
        from services.asr_backend import asr_model_missing_error
        with _offline_asr_missing(cached=True):
            assert asr_model_missing_error() is None

    def test_typed_payload_when_missing(self):
        from services.asr_backend import asr_model_missing_error
        with _offline_asr_missing(cached=False):
            payload = asr_model_missing_error()
        assert payload is not None
        assert payload["error"] == "asr_model_missing"
        assert payload["missing_repo_id"] == _KEPT_FASTER_WHISPER_REPO
        rec = payload["recommended"]
        # The missing repo is itself in the catalog -> recommend exactly it,
        # so the one-click download makes a retry succeed.
        assert rec["repo_id"] == _KEPT_FASTER_WHISPER_REPO
        assert rec["label"] and rec["size_gb"] > 0

    def test_opt_in_engines_are_not_gated(self):
        # NeMo is an explicit opt-in we can't preflight — never block.
        from services import asr_backend
        with patch.object(asr_backend, "active_backend_id", return_value="nemo-parakeet"):
            assert asr_backend.asr_model_missing_error() is None

    def test_dictation_sherpa_installed_is_fine(self):
        from services import asr_backend
        from services import sherpa_dictation as sd
        with patch.object(asr_backend, "dictation_model_id",
                          return_value="sherpa-parakeet-tdt-v3"), \
             patch.object(asr_backend.SherpaDictationBackend, "is_available",
                          return_value=(True, "ready")), \
             patch.object(sd, "is_installed", return_value=True):
            assert asr_backend.asr_model_missing_error(purpose="dictation") is None

    def test_demoted_default_never_recommends_itself(self):
        """Installing the CTA recommendation must escape, not clear, a demotion loop."""
        from api.routers.setup import models as setup_models
        from services import asr_backend
        from services import sherpa_dictation as sd

        fallback_repo = _KEPT_FASTER_WHISPER_REPO
        with patch.object(asr_backend.SherpaDictationBackend, "is_available",
                          return_value=(True, "ready")), \
             patch.object(sd, "is_demoted",
                          side_effect=lambda mid: mid == "sherpa-whisper-tiny"), \
             patch.object(asr_backend, "_capture_whisper_repo",
                          return_value=fallback_repo), \
             patch.object(setup_models, "is_cached", return_value=False), \
             patch.object(setup_models, "cache_is_complete", return_value=True):
            payload = asr_backend.asr_model_missing_error(
                purpose="dictation",
                sherpa_model_id="sherpa-whisper-tiny",
            )

        assert payload is not None
        assert payload["missing_repo_id"] == fallback_repo
        assert payload["recommended"]["repo_id"] == fallback_repo
        assert "dictation_id" not in payload["recommended"]

    def test_never_raises(self):
        from services import asr_backend
        with patch.object(asr_backend, "active_backend_id",
                          side_effect=RuntimeError("boom")):
            assert asr_backend.asr_model_missing_error() is None

    def test_custom_pin_outside_catalog_fails_open(self):
        """A repo the model store can't install (custom ASR_MODEL_* pin) must
        FAIL OPEN — the download CTA could never fix that state, so blocking
        would trap the user in an un-installable loop."""
        from services import asr_backend
        with patch.object(asr_backend, "active_backend_id",
                          return_value="faster-whisper"), \
             patch.dict(os.environ, {"ASR_MODEL_FASTER": "someorg/custom-whisper"}):
            assert asr_backend.asr_model_missing_error() is None

    def test_silent_recovery_requires_even_a_custom_fallback_to_be_installed(self):
        """The recovery path never turns fail-open into an implicit download."""
        from api.routers.setup import models as setup_models
        from services import asr_backend

        with patch.object(asr_backend, "_capture_whisper_repo",
                          return_value="someorg/custom-whisper"), \
             patch.object(setup_models, "is_cached", return_value=False), \
             patch.object(setup_models, "cache_is_complete", return_value=False):
            payload = asr_backend.asr_model_missing_error(
                purpose="dictation",
                skip_sherpa=True,
                require_installed=True,
            )

        assert payload is not None
        assert payload["missing_repo_id"] == "someorg/custom-whisper"

    def test_pytorch_whisper_default_repo_fails_open(self):
        """openai/whisper-large-v3-turbo (the pytorch-whisper default) is not
        a catalog entry — the preflight stays out of the way (auto-download,
        the pre-preflight behaviour)."""
        from services import asr_backend
        with patch.object(asr_backend, "active_backend_id",
                          return_value="pytorch-whisper"):
            assert asr_backend.asr_model_missing_error() is None

    def test_unknown_faster_whisper_alias_fails_open(self):
        """An alias our table doesn't know (but faster_whisper may resolve)
        must not be coerced to the default repo's CTA."""
        from services import asr_backend
        with patch.object(asr_backend, "active_backend_id",
                          return_value="faster-whisper"), \
             patch.dict(os.environ, {"ASR_MODEL_FASTER": "large-v3-turbo-exotic"}):
            assert asr_backend.asr_model_missing_error() is None

    def test_isolated_faster_whisper_is_preflighted(self):
        """The crash-isolated sidecar loads the same CT2 weights as in-process
        faster-whisper — it gets the same preflight, not a silent download."""
        from api.routers.setup import models as setup_models
        from services import asr_backend
        with patch.dict(os.environ, {"ASR_MODEL_FASTER": _KEPT_FASTER_WHISPER_REPO}), \
             patch.object(asr_backend, "active_backend_id",
                          return_value="faster-whisper-isolated"), \
             patch.object(setup_models, "is_cached", return_value=False), \
             patch.object(setup_models, "cache_is_complete", return_value=True):
            payload = asr_backend.asr_model_missing_error()
        assert payload is not None
        assert payload["missing_repo_id"] == _KEPT_FASTER_WHISPER_REPO

    def test_installed_positive_is_memoized(self):
        """Once a repo is confirmed installed, later preflights skip the
        scan_cache_dir walk (installs only add — no invalidation needed)."""
        from api.routers.setup import models as setup_models
        from services import asr_backend
        calls = {"n": 0}

        def counting_is_cached(repo_id):
            calls["n"] += 1
            return True

        with patch.dict(os.environ, {"ASR_MODEL_FASTER": _KEPT_FASTER_WHISPER_REPO}), \
             patch.object(asr_backend, "active_backend_id",
                          return_value="faster-whisper"), \
             patch.object(setup_models, "is_cached", side_effect=counting_is_cached), \
             patch.object(setup_models, "cache_is_complete", return_value=True):
            assert asr_backend.asr_model_missing_error() is None
            assert asr_backend.asr_model_missing_error() is None
        assert calls["n"] == 1

    def test_transcribe_reference_skips_without_backend_construction(self, tmp_path):
        """Clone-ref transcription degrades to None — it must never trigger a
        silent multi-GB download (it is best-effort by contract)."""
        from services import asr_backend
        wav = tmp_path / "ref.wav"
        wav.write_bytes(b"RIFF0000WAVE")
        with _offline_asr_missing(cached=False), \
             patch.object(asr_backend, "get_active_asr_backend",
                          side_effect=AssertionError("backend must not be built")):
            assert asr_backend.transcribe_reference(str(wav)) is None


# ── Consumer wiring (typed 409, not 500, not a download) ────────────────────

def _assert_409(r):
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "asr_model_missing"
    assert detail["recommended"]["repo_id"]
    assert detail["message"]


class TestEndpoints:


    def test_capture_transcribe_409(self, client):
        with _dictation_whisper_missing():
            r = client.post(
                "/transcribe",
                files={"audio": ("t.wav", b"RIFF0000WAVE", "audio/wav")},
            )
        _assert_409(r)

    def test_reference_transcript_uses_installed_model_when_selection_missing(self, client):
        """#2929/#2678: the selected engine's weights are absent but another
        speech-to-text model is installed. generate transcribes through it, so
        the clone preview must not answer asr_model_missing."""
        from services import asr_backend

        with _offline_asr_missing(cached=False), \
             patch.object(asr_backend, "asr_model_missing_error",
                          side_effect=lambda **kw: {"error": "asr_model_missing"}), \
             patch.object(asr_backend, "_installed_reference_fallbacks",
                          return_value=[object()]), \
             patch.object(asr_backend, "transcribe_reference",
                          return_value="hello there"):
            r = client.post(
                "/transcribe",
                data={"mode": "reference"},
                files={"audio": ("t.wav", b"RIFF0000WAVE", "audio/wav")},
            )
        assert r.status_code == 200, r.text
        assert r.json()["text"].strip().lower().startswith("hello")

    def test_reference_transcript_409_when_nothing_installed(self, client):
        from services import asr_backend

        with _offline_asr_missing(cached=False), \
             patch.object(asr_backend, "_installed_reference_fallbacks", return_value=[]), \
             patch.object(asr_backend, "dictation_model_id", return_value=None):
            r = client.post(
                "/transcribe",
                data={"mode": "reference"},
                files={"audio": ("t.wav", b"RIFF0000WAVE", "audio/wav")},
            )
        _assert_409(r)




    def test_openai_compat_transcriptions_409(self, client):
        # #1175 review: the shared typed contract, not a string-only detail —
        # clients must be able to render the download CTA from the payload.
        with _offline_asr_missing(cached=False):
            r = client.post(
                "/v1/audio/transcriptions",
                files={"file": ("t.wav", b"RIFF0000WAVE", "audio/wav")},
            )
        _assert_409(r)


class TestFallbackPreflight:
    """#1189 review: load_active_asr_backend re-selects after a broken import
    chain — the fallback candidate must pass the same no-download preflight
    before ensure_loaded() can auto-download multi-GB weights."""

    class _Broken:
        display_name = "WhisperX"
        id = "whisperx"

        def ensure_loaded(self):
            raise ImportError("No module named 'lightning_fabric'",
                              name="lightning_fabric")

    def _payload(self):
        return {"error": "asr_model_missing", "missing_repo_id": "x/y",
                "recommended": {"repo_id": "x/y", "label": "L", "size_gb": 1}}

    def test_uncached_fallback_raises_typed_error_before_load(self):
        from services import asr_backend as ab

        class _Fallback:
            display_name = "Faster-Whisper"
            id = "faster-whisper"

            def ensure_loaded(self):
                raise AssertionError(
                    "fallback must not load (= auto-download) before its "
                    "own preflight")

        payload = self._payload()
        with patch.dict(ab._DEEP_IMPORT_BROKEN, clear=True), \
             patch.dict(ab._LAST_ERRORS, clear=True), \
             patch.object(ab, "get_active_asr_backend",
                          side_effect=[self._Broken(), _Fallback()]), \
             patch.object(ab, "_asr_backend_pinned", return_value=False), \
             patch.object(ab, "asr_model_missing_error", return_value=payload):
            with pytest.raises(ab.ASRModelMissingError) as ei:
                ab.load_active_asr_backend()
        assert ei.value.payload == payload

    def test_cached_fallback_still_loads(self):
        from services import asr_backend as ab

        loaded = []

        class _Fallback:
            display_name = "Faster-Whisper"
            id = "faster-whisper"

            def ensure_loaded(self):
                loaded.append(True)

        with patch.dict(ab._DEEP_IMPORT_BROKEN, clear=True), \
             patch.dict(ab._LAST_ERRORS, clear=True), \
             patch.object(ab, "get_active_asr_backend",
                          side_effect=[self._Broken(), _Fallback()]), \
             patch.object(ab, "_asr_backend_pinned", return_value=False), \
             patch.object(ab, "asr_model_missing_error", return_value=None):
            backend = ab.load_active_asr_backend()
        assert loaded == [True]
        assert backend.id == "faster-whisper"
