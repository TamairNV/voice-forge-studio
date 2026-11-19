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
