"""Inline ``[[…]]`` pronunciation overrides survive dictionaries and chapters.

An explicit ``[[route|route]]`` was rewritten by a saved ``route -> root``
entry before its brackets resolved, and the longform chapter path applied
only the lexicon, so the engine read ``root [[root|root]]`` aloud. Chapters
and segments rendered that way are re-keyed; everything else keeps its key.
"""
from __future__ import annotations

import pytest

ROWS = [{"term": "route", "replacement": "root", "type": "respelling",
         "language": "*", "enabled": 1}]
LEXICON = {"route": "root"}
SR = 24000


@pytest.mark.parametrize(("text", "expected"), [
    ("route [[route|route]]", "root route"),
    ("route [[route]]", "root route"),
    ("[[Route|ROUTE]] then route.", "ROUTE then root."),
    ("no override, route", "no override, root"),
])
def test_dictionary_never_rewrites_inside_an_inline_override(text, expected):
    from services.pronunciation import apply_lexicon_and_overrides, apply_pronunciation

    assert apply_pronunciation(text, ROWS, "en") == expected
    assert apply_lexicon_and_overrides(text, LEXICON) == expected
