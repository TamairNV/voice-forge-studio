"""Unknown native ASR language must not become an English translation source."""
import asyncio
from types import SimpleNamespace

import pytest

pytest_plugins = ["whisper_cpp_fixtures"]


@pytest.mark.parametrize('data', [{}, {'result': {}}, {'result': {'language': None}}])
def test_missing_language_stays_unknown(data):
    from engines.whisper_cpp.output import parse_transcript
    assert parse_transcript(data, word_timestamps=True)['language'] is None


@pytest.mark.parametrize('result', ['nl', ['nl'], True, 1, None, '', []])
def test_non_mapping_result_keeps_transcript_and_unknown_language(result):
    from engines.whisper_cpp.output import parse_transcript

    data = {'result': result, 'transcription': [
        {'text': ' Goedemorgen', 'offsets': {'from': 0, 'to': 2000}},
    ]}
    transcript = parse_transcript(data, word_timestamps=False)
    assert transcript['language'] is None
    assert transcript['text'] == 'Goedemorgen'
    assert transcript['chunks'] == [{'text': ' Goedemorgen', 'timestamp': (0.0, 2.0)}]


def test_mapping_result_language_is_preserved():
    from collections import UserDict

    from engines.whisper_cpp.output import parse_transcript

    assert parse_transcript({'result': UserDict(language='nl')}, False)['language'] == 'nl'




def test_reported_language_is_preserved():
    from engines.whisper_cpp.output import parse_transcript
    assert parse_transcript({'result': {'language': 'nl'}}, word_timestamps=False)['language'] == 'nl'














