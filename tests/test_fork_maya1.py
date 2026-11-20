"""Tests for the ported Maya-1 backend and prompt/audio helpers (Phase 2, Task 2)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_maya1_registered_in_tts_backend():
    from services import tts_backend
    cls = tts_backend.get_backend_class("maya1")
    assert cls.id == "maya1"
    assert cls.sample_rate == 24000
    assert cls.supports_voice_design is True


def test_maya1_snac_pack_unpack_roundtrip():
    from services.maya1_backend import Maya1MLXRunner

    levels = [
        [10, 200],
        [11, 12, 201, 202],
        [13, 14, 15, 16, 203, 204, 205, 206],
    ]
    packed = Maya1MLXRunner.pack_snac_to_7(levels)
    assert len(packed) == 14
    unpacked = Maya1MLXRunner.unpack_snac_from_7(packed)
    assert unpacked == levels


def test_sanitize_dialogue_for_maya1_and_non_maya():
    from services.maya1_backend import sanitize_dialogue_for_model

    clean_maya, tags = sanitize_dialogue_for_model("*laughs* Well, <sighs> let us go.", "maya1")
    assert "<laugh>" in clean_maya
    assert "<sigh>" in clean_maya
    assert tags == ["<laugh>", "<sigh>"]

    clean_other, tags2 = sanitize_dialogue_for_model("<sigh> Keep your coin, *traveller*.", "voxcpm2")
    assert "<sigh>" not in clean_other
    assert "traveller" in clean_other
    assert "*" not in clean_other
    assert tags2 == ["<sigh>"]


def test_compile_voice_instruct_and_optimize_prompts():
    from services.maya1_backend import compile_voice_instruct, optimize_character_prompts

    compiled = compile_voice_instruct("Gruff blacksmith", model_id="maya1")
    assert "Gruff blacksmith" in compiled
    assert "intensity" in compiled

    opt = optimize_character_prompts("Tavern keeper", gender="male", age="50s", accent="Yorkshire")
    assert "Tavern keeper" in opt["instruct_qwen3"]
    assert "Tavern keeper" in opt["instruct_maya"]
    assert opt["golden_sample"]
    assert "<" in opt["golden_sample_maya"]


def test_audio_helpers_normalize_and_analyze():
    from services.maya1_backend import analyze_voice_acoustics, apply_studio_pacing, normalize_studio_loudness

    t = np.linspace(0, 1.0, 24000, endpoint=False, dtype=np.float32)
    wave = 0.05 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    norm = normalize_studio_loudness(wave)
    assert float(np.max(np.abs(norm))) <= 0.92 + 1e-4
    paced = apply_studio_pacing(norm, 24000, speed=1.25)
    assert abs(paced.shape[0] - 19200) <= 2
    metrics = analyze_voice_acoustics(norm, 24000)
    assert metrics["duration_sec"] == 1.0
    assert metrics["clipped_samples"] == 0
