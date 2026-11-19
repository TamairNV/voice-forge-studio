KEPT_TTS = {"omnivoice", "mlx-audio", "voxcpm2", "cosyvoice", "cosyvoice-gguf", "indextts2",
            "dots-tts", "audiocpp-dots", "moss-tts-v15", "qwen3-tts", "gpt-sovits", "pockettts"}
KEPT_ASR = {"mlx-whisper", "faster-whisper", "faster-whisper-isolated", "whisperx",
            "parakeet-mlx", "nemo-parakeet"}


def test_tts_registry_is_exactly_kept():
    from services import tts_backend
    assert set(tts_backend._REGISTRY) == KEPT_TTS


def test_every_kept_tts_engine_resolves():
    from services import tts_backend
    for engine_id in KEPT_TTS:
        assert tts_backend._REGISTRY[engine_id] is not None


import platform
import sys

import pytest


def test_omnivoice_hidden_from_default_listing():
    from services import tts_backend
    assert "omnivoice" not in {b["id"] for b in tts_backend.list_backends()}
    assert "omnivoice" in {b["id"] for b in tts_backend.list_backends(include_hidden=True)}


@pytest.mark.parametrize("plat,machine,expected", [
    ("darwin", "arm64", "mlx-audio"),
    ("darwin", "x86_64", "voxcpm2"),
    ("linux", "x86_64", "voxcpm2"),
    ("win32", "AMD64", "voxcpm2"),
])
def test_default_engine_by_platform(monkeypatch, plat, machine, expected):
    from services import tts_backend
    monkeypatch.setattr(sys, "platform", plat)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert tts_backend.default_tts_backend_id() == expected


def _with_saved_engine(monkeypatch, value):
    from core import prefs
    real_get = prefs.get
    monkeypatch.setattr(prefs, "get",
                        lambda key, default=None: value if key == "tts_backend" else real_get(key, default))
    monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)


def test_saved_removed_engine_falls_back_to_default(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "kittentts")
    assert tts_backend.active_backend_id() == tts_backend.default_tts_backend_id()


def test_nothing_saved_uses_default(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, None)
    assert tts_backend.active_backend_id() == tts_backend.default_tts_backend_id()


def test_saved_valid_engine_is_kept(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "cosyvoice")
    assert tts_backend.active_backend_id() == "cosyvoice"


def test_env_override_wins(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "cosyvoice")
    monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "voxcpm2")
    assert tts_backend.active_backend_id() == "voxcpm2"


def test_mlx_audio_defaults_to_voxcpm2():
    from services.tts_backend import MLXAudioBackend, _MLX_AUDIO_MODEL_LABELS
    assert MLXAudioBackend.DEFAULT_MODEL_KEY == "voxcpm2"
    assert MLXAudioBackend.CURATED_MODELS["voxcpm2"] == "mlx-community/VoxCPM2-8bit"
    for key in ("melotts", "outetts"):
        assert key not in MLXAudioBackend.CURATED_MODELS
        assert key not in MLXAudioBackend.CURATED_MODEL_LANGUAGES
        assert key not in _MLX_AUDIO_MODEL_LABELS


def test_asr_registry_is_exactly_kept():
    from services import asr_backend
    assert set(asr_backend._REGISTRY) == KEPT_ASR


def test_saved_removed_asr_engine_falls_back_to_default(monkeypatch):
    from core import prefs
    from services import asr_backend

    real_get = prefs.get
    monkeypatch.setattr(
        prefs,
        "get",
        lambda key, default=None: "moonshine" if key == "asr_backend" else real_get(key, default),
    )
    monkeypatch.delenv("OMNIVOICE_ASR_BACKEND", raising=False)
    assert asr_backend.active_backend_id() == asr_backend._auto_detect()
