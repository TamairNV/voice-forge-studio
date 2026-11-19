"""Titles become filenames; Windows rejects `<>:"|?*` with [Errno 22] (#2376 class)."""
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("How to X: a guide?_en.mp4", "How to X_ a guide__en.mp4"),
        ('a<b>c|d"e*f.srt', "a_b_c_d_e_f.srt"),
        ("clip. .", "clip"),
        ("CON.wav", "_CON.wav"),
        ("lpt1", "_lpt1"),
        ("???", "file"),
        ("", "file"),
        ("tab\there\x00.wav", "tab_here_.wav"),
    ],
)
def test_portable_filename_repairs_windows_hostile_names(raw, expected):
    from core.path_security import portable_filename

    assert portable_filename(raw) == expected


def test_reserved_device_name_exposed_by_truncation_is_still_repaired():
    from core.path_security import portable_filename

    name = portable_filename("CON" + " " * 197 + "x.wav")
    assert name.split(".")[0].upper() != "CON" and name.endswith(".wav")
    assert len(name.encode("utf-8")) <= 200


def test_portable_filename_truncates_by_bytes_and_keeps_extension():
    from core.path_security import portable_filename

    name = portable_filename("日本語" * 60 + ".mp4")
    assert len(name.encode("utf-8")) <= 200
    assert name.endswith(".mp4") and "�" not in name

