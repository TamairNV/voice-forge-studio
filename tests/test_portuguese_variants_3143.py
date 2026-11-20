"""#3143 / #2752: Brazilian and European Portuguese as separate choices.

The pickers offer "Portuguese (Brazil)" and "Portuguese (Portugal)". Every
engine and the bundled vocabulary know a single Portuguese, so the variant
must resolve to that base language at the engine boundary while the dialect
still reaches what can use it (number words, translation prompts), and a
saved plain "Portuguese"/"pt" keeps working as Brazilian Portuguese.
"""
from __future__ import annotations

import asyncio

import pytest


# ── the shared table ────────────────────────────────────────────────────────


@pytest.mark.parametrize(("language", "dialect"), [
    ("Portuguese (Brazil)", "pt-BR"),
    ("Portuguese (Portugal)", "pt-PT"),
    ("portuguese  (portugal)", "pt-PT"),
    ("pt-PT", "pt-PT"),
    ("pt_pt", "pt-PT"),
    ("pt-br", "pt-BR"),
    # Saved settings from before the split mean Brazilian Portuguese.
    ("Portuguese", "pt-BR"),
    ("pt", "pt-BR"),
    # Languages without a variant split carry no dialect here.
    ("en-US", None),
    ("Spanish", None),
    ("Auto", None),
    (None, None),
])
def test_dialect_for(language, dialect):
    from core.language_variants import dialect_for
    assert dialect_for(language) == dialect


def test_base_language_only_rewrites_variant_names():
    from core.language_variants import base_language
    assert base_language("Portuguese (Portugal)") == "Portuguese"
    assert base_language("Portuguese (Brazil)") == "Portuguese"
    for unchanged in ("Portuguese", "pt-PT", "English", None, "Auto"):
        assert base_language(unchanged) == unchanged


def test_base_language_converts_native_batch_lists():
    from core.language_variants import base_language
    assert base_language(["Portuguese (Portugal)", "English", None]) == [
        "Portuguese", "English", None,
    ]
    assert base_language(("Portuguese (Brazil)",)) == ("Portuguese",)


def test_regional_target_splits_into_base_and_dialect():
    from core.language_variants import split_target
    assert split_target("pt-PT") == ("pt", "pt-PT")
    assert split_target("pt") == ("pt", None)
    assert split_target("es-AR") == ("es-AR", None)  # no picker split for Spanish


# ── TTS engine boundary ─────────────────────────────────────────────────────


@pytest.fixture
def recording_backend():
    from services.tts_backend import TTSBackend

    class Recording(TTSBackend):
        id = "recording"
        display_name = "Recording"

        def __init__(self, supported=("multi",)):
            self._supported = list(supported)
            self.calls: list[dict] = []

        @property
        def sample_rate(self) -> int:  # type: ignore[override]
            return 24000

        @property
        def supported_languages(self) -> list[str]:  # type: ignore[override]
            return self._supported

        @classmethod
        def is_available(cls):  # type: ignore[override]
            return True, "ready"

        def generate(self, text, **kw):  # type: ignore[override]
            self.calls.append(kw)
            import torch
            return torch.zeros(1, 1)

    return Recording


@pytest.mark.parametrize(("picked", "engine_sees"), [
    ("Portuguese (Portugal)", "Portuguese"),
    ("Portuguese (Brazil)", "Portuguese"),
    ("Portuguese", "Portuguese"),
    ("pt-PT", "pt-PT"),
])
def test_engines_receive_the_language_they_know(recording_backend, picked, engine_sees):
    backend = recording_backend()
    backend.generate("Olá", language=picked)
    assert backend.calls[-1]["language"] == engine_sees


def test_native_batch_engines_receive_base_languages(recording_backend):
    class Batching(recording_backend):
        def generate_batch(self, texts, **kw):  # type: ignore[override]
            self.calls.append(kw)
            return []

    backend = Batching()
    backend.generate_batch(["a", "b"], language=["Portuguese (Portugal)", "Portuguese (Brazil)"])
    assert backend.calls[-1]["language"] == ["Portuguese", "Portuguese"]


def test_kokoro_resolves_portuguese_variants(monkeypatch):
    import sys
    import types

    from services import tts_backend

    pipeline = types.ModuleType("mlx_audio.tts.models.kokoro.pipeline")
    pipeline.ALIASES = {"pt": "p", "pt-br": "p"}
    pipeline.LANG_CODES = {"p": "pt-br"}
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.models.kokoro.pipeline", pipeline)
    for picked in ("Portuguese (Portugal)", "Portuguese (Brazil)", "pt-PT", "pt-BR", "Portuguese"):
        assert tts_backend.resolve_kokoro_lang_code(picked) == "p"


def test_finite_engine_accepts_both_variants(recording_backend):
    backend = recording_backend(["en", "pt"])
    for picked in ("Portuguese (Brazil)", "Portuguese (Portugal)", "Portuguese", "pt"):
        assert backend._check_language(picked) == "pt"
    with pytest.raises(ValueError, match="doesn't support"):
        recording_backend(["en"])._check_language("Portuguese (Portugal)")


def test_language_options_list_variants_only_with_portuguese(monkeypatch):
    from services import tts_backend
    options = tts_backend.language_options("omnivoice")
    assert {"portuguese", "portuguese (brazil)", "portuguese (portugal)"} <= set(options)

    class _EnOnly(tts_backend.TTSBackend):
        id = "stub-en-pt-test"
        display_name = "Stub EN"
        sample_rate = 24000
        supported_languages = ["en"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw):
            raise AssertionError("not used")

    monkeypatch.setitem(tts_backend._REGISTRY, "stub-en-pt-test", _EnOnly)
    english_only = tts_backend.language_options("stub-en-pt-test")
    assert "portuguese (brazil)" not in english_only


def test_bundled_engines_render_no_regional_accent():
    from services import tts_backend
    assert tts_backend.rendered_dialects("omnivoice") == []
    assert tts_backend.rendered_dialects("no-such-engine") == []


# ── text normalization ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("language", "sixteen"), [
    ("Portuguese (Brazil)", "dezesseis"),
    ("Portuguese (Portugal)", "dezasseis"),
    ("pt-PT", "dezasseis"),
    ("pt-BR", "dezesseis"),  # was European before #3143
    ("Portuguese", "dezesseis"),
    ("pt", "dezesseis"),
])
def test_number_words_follow_the_dialect(language, sixteen):
    from services.text_normalization import normalize_text
    assert normalize_text("Tenho 16 anos, 50%", language) == f"Tenho {sixteen} anos, cinquenta por cento"


def test_pronunciation_scopes_resolve_variants_to_portuguese():
    from services.pronunciation import language_scope_key
    assert language_scope_key("Portuguese (Portugal)") == "pt"
    assert language_scope_key("Portuguese (Brazil)") == "pt"


# ── dub translation ─────────────────────────────────────────────────────────


def _request(**fields):
    from schemas.requests import TranslateRequest
    return TranslateRequest(segments=[], **fields)












