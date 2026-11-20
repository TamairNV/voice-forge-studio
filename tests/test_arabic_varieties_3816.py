"""#3816: Arabic varieties on engines that declare a single ``ar``.

The pickers name Arabic varieties ("Standard Arabic" = ``arb``, "Egyptian
Arabic" = ``arz``) while finite engines such as VoxCPM2 declare the
macrolanguage ``ar``. The synthesis check, the picker inventory and the
sidecar request must agree: a variety is spoken as the declared ``ar``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def stub():
    from services.tts_backend import TTSBackend

    class Stub(TTSBackend):
        def __init__(self, supported):
            self._supported = list(supported)

        id = "stub"
        display_name = "Stub"
        sample_rate = 24000

        @property
        def supported_languages(self):  # type: ignore[override]
            return self._supported

        @classmethod
        def is_available(cls):  # type: ignore[override]
            return True, "ready"

        def generate(self, text, **kw):  # type: ignore[override]
            raise AssertionError("not used")

    return Stub


@pytest.mark.parametrize("language", [
    "Standard Arabic", "Egyptian Arabic", "Saidi Arabic", "Najdi Arabic",
    "arb", "arz", "aec", "Arabic", "ar", "ar-EG",
])
def test_arabic_varieties_are_spoken_as_the_declared_macrolanguage(stub, language):
    assert stub(["ar", "en"])._check_language(language) == "ar"


def test_an_engine_that_declares_the_variety_keeps_it(stub):
    assert stub(["arz", "en"])._check_language("Egyptian Arabic") == "arz"


@pytest.mark.parametrize("language", ["Standard Arabic", "arb", "Judeo-Moroccan Arabic"])
def test_no_arabic_or_a_non_member_is_still_refused(stub, language):
    # Judeo-Moroccan Arabic belongs to the Judeo-Arabic macrolanguage, not "ar".
    supported = ["en"] if language != "Judeo-Moroccan Arabic" else ["ar", "en"]
    with pytest.raises(ValueError, match="doesn't support"):
        stub(supported)._check_language(language)


def test_finite_engine_inventory_lists_the_varieties_it_accepts():
    from services import tts_backend

    options = tts_backend.language_options("voxcpm2")
    for name in ("arabic", "standard arabic", "egyptian arabic", "najdi arabic"):
        assert name in options, name
    assert "judeo-moroccan arabic" not in options


def test_indextts_speaks_a_variety_as_its_declared_arabic(monkeypatch):
    from services.subprocess_backend import SubprocessBackend
    from engines.indextts import IndexTTS2Backend

    sent = []
    monkeypatch.setattr(SubprocessBackend, "generate", lambda self, text, **kw: sent.append(kw))
    monkeypatch.delenv("OMNIVOICE_INDEXTTS_DIR", raising=False)
    backend = object.__new__(IndexTTS2Backend)
    # Latin text: without the checked code, script detection would pick English.
    backend.generate("marhaban", ref_audio="/tmp/ref.wav", language="Standard Arabic")
    assert sent[0]["lang"] == "ar"


