"""i18n — locale judges (synthetic) + the localization spec against the real
locale files. Orphan-key + coverage findings are advisory (reported, not gating).
"""

from __future__ import annotations

import json

from .judges import i18n as I


def _write_locales(tmp_path, mapping):
    for name, obj in mapping.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(obj), encoding="utf-8")
    return str(tmp_path)


def test_valid_json_and_orphans_synthetic(tmp_path):
    d = _write_locales(tmp_path, {
        "en": {"a": 1, "b": {"c": 2}},
        "fr": {"a": 1, "b": {"c": 2}},            # clean
        "de": {"a": 1, "b": {"c": 2}, "x": 9},    # orphan key 'x'
    })
    assert I.locale_valid_json(d).passed is True
    res = I.locale_no_orphan_keys(d, "en")
    assert res.passed is False and "de" in res.detail


def test_invalid_json_fails(tmp_path):
    (tmp_path / "en.json").write_text('{"a":1}', encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert I.locale_valid_json(str(tmp_path)).passed is False


def test_coverage_reports_lowest(tmp_path):
    d = _write_locales(tmp_path, {
        "en": {"a": 1, "b": 2, "c": 3, "d": 4},
        "fr": {"a": 1, "b": 2},  # 50%
    })
    res = I.locale_coverage(d, "en")
    assert res.measured == 0.5 and "fr" in res.detail
