"""Maya-1 3.3B MLX backend and Voice Forge prompt/audio utilities.

Ported from Voice Forge (`engine.py`) onto Voice Forge Studio's ``TTSBackend``
interface. Uses ``mlx-audio`` (Llama + SNAC 24 kHz) on Apple Silicon.
"""
from __future__ import annotations

import gc
import importlib.util
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

from services.tts_backend import TTSBackend

# Maya-1 token constants
CODE_START_TOKEN_ID = 128257
CODE_END_TOKEN_ID = 128258
CODE_TOKEN_OFFSET = 128266
SNAC_MIN_ID = 128266
SNAC_MAX_ID = 156937
SNAC_TOKENS_PER_FRAME = 7

SOH_ID = 128259
EOH_ID = 128260
SOA_ID = 128261
BOS_ID = 128000
TEXT_EOT_ID = 128009

MAYA1_REPO_ID = "nhe-ai/maya1-mlx-8Bit"
MAYA1_SNAC_REPO_ID = "mlx-community/snac_24khz"

MAYA1_EMOTION_TAGS = [
    {"tag": "<laugh>", "label": "Laugh", "category": "Vocal"},
    {"tag": "<laugh_harder>", "label": "Hard Laugh", "category": "Vocal"},
    {"tag": "<chuckle>", "label": "Chuckle", "category": "Vocal"},
    {"tag": "<giggle>", "label": "Giggle", "category": "Vocal"},
    {"tag": "<sigh>", "label": "Sigh", "category": "Breath"},
    {"tag": "<exhale>", "label": "Exhale", "category": "Breath"},
    {"tag": "<gasp>", "label": "Gasp", "category": "Breath"},
    {"tag": "<gulp>", "label": "Gulp", "category": "Breath"},
    {"tag": "<snort>", "label": "Snort", "category": "Vocal"},
    {"tag": "<whisper>", "label": "Whisper", "category": "Style"},
    {"tag": "<angry>", "label": "Angry", "category": "Emotion"},
    {"tag": "<sarcastic>", "label": "Sarcastic", "category": "Emotion"},
    {"tag": "<mischievous>", "label": "Mischievous", "category": "Emotion"},
    {"tag": "<excited>", "label": "Excited", "category": "Emotion"},
    {"tag": "<curious>", "label": "Curious", "category": "Emotion"},
    {"tag": "<disappointed>", "label": "Disappointed", "category": "Emotion"},
    {"tag": "<appalled>", "label": "Appalled", "category": "Emotion"},
    {"tag": "<cry>", "label": "Cry", "category": "Emotion"},
    {"tag": "<scream>", "label": "Scream", "category": "Style"},
    {"tag": "<sing>", "label": "Sing", "category": "Style"},
]

VALID_MAYA1_TAG_SET = {t["tag"] for t in MAYA1_EMOTION_TAGS}

MAYA1_TAG_ALIASES = {
    "laughs": "<laugh>",
    "laughing": "<laugh>",
    "chuckles": "<chuckle>",
    "chuckling": "<chuckle>",
    "giggles": "<giggle>",
    "giggling": "<giggle>",
    "sighs": "<sigh>",
    "sighing": "<sigh>",
    "exhales": "<exhale>",
    "gasps": "<gasp>",
    "gasping": "<gasp>",
    "gulps": "<gulp>",
    "snorts": "<snort>",
    "whispers": "<whisper>",
    "whispering": "<whisper>",
    "cries": "<cry>",
    "crying": "<cry>",
    "screams": "<scream>",
    "screaming": "<scream>",
    "sings": "<sing>",
    "singing": "<sing>",
}

TAG_TO_INSTRUCT = {
    "<whisper>": "hushed intimate whisper delivery",
    "<angry>": "fierce angry intense tone",
    "<sarcastic>": "dry sarcastic biting tone",
    "<mischievous>": "playful mischievous tone",
    "<excited>": "high-energy excited enthusiastic tone",
    "<curious>": "inquisitive curious inflections",
    "<disappointed>": "weary disappointed tone",
    "<appalled>": "shocked appalled tone",
    "<cry>": "emotional trembling tearful delivery",
    "<scream>": "urgent raised shouting delivery",
    "<laugh>": "warm amused chuckling delivery",
    "<chuckle>": "warm amused chuckling delivery",
    "<giggle>": "lighthearted giggly delivery",
    "<sigh>": "weary breathy sighing cadence",
}


def sanitize_dialogue_for_model(text: str, model_id: str) -> Tuple[str, List[str]]:
    """Format dialogue text for the target model family.

    Normalises markdown asterisks and angle-bracket tags into canonical Maya-1
    SNAC tags for ``maya1``, or strips them cleanly for non-Maya engines while
    returning the extracted tag list so callers can enrich delivery instructions.
    """
    s = (text or "").strip()
    if not s:
        return "", []

    extracted_tags: List[str] = []

    def _replace_asterisk_action(match: re.Match) -> str:
        word = match.group(1).strip().lower()
        if word in MAYA1_TAG_ALIASES:
            return f" {MAYA1_TAG_ALIASES[word]} "
        if f"<{word}>" in VALID_MAYA1_TAG_SET:
            return f" <{word}> "
        return match.group(1)

    s = re.sub(r"\*+([^*]+)\*+", _replace_asterisk_action, s)

    def _normalize_angle_tag(match: re.Match) -> str:
        raw_inner = match.group(1).strip().lower()
        canonical = MAYA1_TAG_ALIASES.get(raw_inner, f"<{raw_inner}>")
        if canonical in VALID_MAYA1_TAG_SET:
            extracted_tags.append(canonical)
            return canonical
        return ""

    s = re.sub(r"<([a-zA-Z_]+)>", _normalize_angle_tag, s)

    if model_id != "maya1":
        for breath_tag in ("<sigh>", "<exhale>", "<gasp>", "<gulp>"):
            s = s.replace(breath_tag, "... ")
        for tag in VALID_MAYA1_TAG_SET:
            s = s.replace(tag, " ")

    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.!?])", r"\1", s)
    return s, extracted_tags


def compile_voice_instruct(
    raw_instruct: str,
    model_id: str = "qwen3_voicedesign",
    extracted_tags: Optional[List[str]] = None,
) -> str:
    """Compile a voice description with acoustic anchors for Maya-1 or Qwen3/VoxCPM2."""
    base = (raw_instruct or "").strip().rstrip(".")
    lower = base.lower()
    tags = extracted_tags or []

    tag_cues: List[str] = []
    if model_id != "maya1" and tags:
        for t in tags:
            cue = TAG_TO_INSTRUCT.get(t)
            if cue and cue not in tag_cues and cue not in lower:
                tag_cues.append(cue)

    if not base:
        if model_id == "maya1":
            return (
                "Expressive game character, voice in their 30s with a clear accent, "
                "medium pitch, warm resonant timbre, brisk conversational pacing, "
                "engaging tone at medium intensity."
            )
        return (
            "A clear, expressive game character voice in their 30s, medium resonant pitch, "
            "warm articulate vocal texture, natural brisk conversational pacing, "
            "engaging studio dialogue delivery."
        )

    has_pitch = any(
        w in lower
        for w in ("pitch", "baritone", "bass", "tenor", "alto", "soprano", "deep", "high", "low", "mid-range")
    )
    has_texture = any(
        w in lower
        for w in (
            "timbre", "texture", "raspy", "gravelly", "smooth", "warm", "crisp",
            "husky", "breathy", "resonant", "silky", "hoarse", "clear", "smoky",
        )
    )
    has_pace = any(
        w in lower
        for w in (
            "pace", "pacing", "cadence", "rhythm", "fast", "brisk", "snappy",
            "steady", "measured", "deliberate", "slow", "rapid", "conversational",
        )
    )
    has_intensity = "intensity" in lower

    additions: List[str] = list(tag_cues)
    if model_id == "maya1":
        if not has_pitch:
            additions.append("natural well-defined pitch")
        if not has_texture:
            additions.append("expressive studio vocal timbre")
        if not has_pace:
            additions.append("brisk conversational pacing")
        if not has_intensity:
            additions.append("expressive tone at medium-high intensity")
    else:
        if not has_pitch:
            additions.append("well-anchored natural pitch")
        if not has_texture:
            additions.append("articulate studio vocal timbre")
        if not has_pace:
            additions.append("natural conversational pacing")
        if "studio" not in lower and "dialogue" not in lower and "mic" not in lower:
            additions.append("close-mic studio game dialogue presence")

    if additions:
        return f"{base}, {', '.join(additions)}."
    return f"{base}."


def optimize_character_prompts(
    concept: str,
    gender: str = "",
    age: str = "",
    accent: str = "",
    timbre: str = "",
    pacing: str = "",
    emotion: str = "",
    intensity: str = "medium-high",
) -> Dict[str, str]:
    """Build ready-to-use prompts for VoiceDesign and Maya-1 from structured character fields."""
    parts = [p.strip() for p in (concept, gender, age, accent, timbre, pacing, emotion) if p and p.strip()]
    raw = ", ".join(parts) if parts else "expressive game character"
    if intensity and "intensity" not in raw.lower():
        raw_maya = f"{raw} at {intensity} intensity"
    else:
        raw_maya = raw

    qwen_prompt = compile_voice_instruct(raw, model_id="qwen3_voicedesign")
    maya_prompt = compile_voice_instruct(raw_maya, model_id="maya1")
    golden_sample = (
        "Listen closely, because I will only say this once. "
        "The road north is washed out, the guards are doubled, and half the town is watching our doors."
    )
    golden_sample_maya = (
        "<sigh> Listen closely, because I will only say this once. "
        "<chuckle> Half the town thinks we are bluffing, and the other half is already packing."
    )
    return {
        "instruct_qwen3": qwen_prompt,
        "instruct_maya": maya_prompt,
        "golden_sample": golden_sample,
        "golden_sample_maya": golden_sample_maya,
    }


def normalize_studio_loudness(
    audio_np: np.ndarray,
    target_rms: float = 0.14,
    peak_ceiling: float = 0.92,
) -> np.ndarray:
    """Normalise active speech RMS with a soft peak ceiling."""
    if audio_np.size == 0:
        return audio_np
    x = audio_np.astype(np.float32, copy=True)
    x = x - float(np.mean(x))
    abs_x = np.abs(x)
    active = x[abs_x > 0.015]
    rms = float(np.sqrt(np.mean(active ** 2))) if active.size > 128 else float(np.sqrt(np.mean(x ** 2)))
    if rms > 1e-5:
        gain = min(target_rms / rms, 4.0)
        x *= gain
    peak = float(np.max(np.abs(x)))
    if peak > peak_ceiling:
        x *= peak_ceiling / peak
    return x


def apply_studio_pacing(
    audio_np: np.ndarray,
    sr: int,
    speed: float = 1.0,
) -> np.ndarray:
    """Return raw audio when speed is 1.0, otherwise resample lightly for pacing."""
    if audio_np.size == 0 or abs(speed - 1.0) < 0.01:
        return audio_np
    speed = max(0.5, min(2.0, float(speed)))
    target_len = max(1, int(round(audio_np.shape[0] / speed)))
    return np.interp(
        np.linspace(0.0, 1.0, target_len, endpoint=False),
        np.linspace(0.0, 1.0, audio_np.shape[0], endpoint=False),
        audio_np,
    ).astype(np.float32)


def analyze_voice_acoustics(audio_np: np.ndarray, sr: int) -> Dict[str, Any]:
    """Compute lightweight studio metrics (duration, RMS, peak, clipping, silence ratio)."""
    if audio_np.size == 0 or sr <= 0:
        return {
            "duration_sec": 0.0,
            "rms_dbfs": -96.0,
            "peak_dbfs": -96.0,
            "clipped_samples": 0,
            "silence_ratio": 1.0,
        }
    x = audio_np.astype(np.float32)
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(np.max(np.abs(x)))
    rms_db = round(20.0 * float(np.log10(max(rms, 1e-6))), 2)
    peak_db = round(20.0 * float(np.log10(max(peak, 1e-6))), 2)
    clipped = int(np.sum(np.abs(x) >= 0.995))
    silence_ratio = round(float(np.mean(np.abs(x) < 0.01)), 3)
    return {
        "duration_sec": round(x.shape[0] / float(sr), 2),
        "rms_dbfs": rms_db,
        "peak_dbfs": peak_db,
        "clipped_samples": clipped,
        "silence_ratio": silence_ratio,
    }


class Maya1MLXRunner:
    """Native Apple Silicon MLX runner for Maya-1 (3.3B Llama + SNAC 24 kHz)."""

    def __init__(self, repo_id: str = MAYA1_REPO_ID):
        import mlx.core as mx
        from mlx_audio.codec.models.snac import SNAC
        from mlx_audio.lm.models.llama import Model as LlamaModel, ModelArgs as LlamaModelConfig
        from mlx_audio.utils import (
            apply_quantization,
            from_dict,
            get_model_path,
            load_config,
            load_weights,
        )
        from transformers import AutoTokenizer

        self.repo_id = repo_id
        self.sample_rate = 24000
        model_path = get_model_path(repo_id)
        config_dict = load_config(model_path)

        llama_args = from_dict(LlamaModelConfig, config_dict)
        self.model = LlamaModel(llama_args)

        weights = load_weights(model_path)
        if hasattr(self.model, "sanitize"):
            weights = self.model.sanitize(weights)

        apply_quantization(self.model, config_dict, weights)
        self.model.load_weights(list(weights.items()), strict=False)
        mx.eval(self.model.parameters())
        self.model.eval()

        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
        self.snac = SNAC.from_pretrained(MAYA1_SNAC_REPO_ID)
        self.snac.eval()

    def build_prompt(self, description: str, text: str) -> str:
        soh_token = self.tokenizer.decode([SOH_ID])
        eoh_token = self.tokenizer.decode([EOH_ID])
        soa_token = self.tokenizer.decode([SOA_ID])
        sos_token = self.tokenizer.decode([CODE_START_TOKEN_ID])
        eot_token = self.tokenizer.decode([TEXT_EOT_ID])
        bos_token = self.tokenizer.bos_token or "<|begin_of_text|>"

        clean_desc = description.replace('"', "'").strip()
        formatted_text = f'<description="{clean_desc}"> {text.strip()}'
        return soh_token + bos_token + formatted_text + eot_token + eoh_token + soa_token + sos_token

    @staticmethod
    def extract_snac_codes(token_ids: List[int]) -> List[int]:
        try:
            eos_idx = token_ids.index(CODE_END_TOKEN_ID)
        except ValueError:
            eos_idx = len(token_ids)
        return [
            tid for tid in token_ids[:eos_idx]
            if SNAC_MIN_ID <= tid <= SNAC_MAX_ID
        ]

    @staticmethod
    def unpack_snac_from_7(snac_tokens: List[int]) -> List[List[int]]:
        if snac_tokens and snac_tokens[-1] == CODE_END_TOKEN_ID:
            snac_tokens = snac_tokens[:-1]

        frames = len(snac_tokens) // SNAC_TOKENS_PER_FRAME
        snac_tokens = snac_tokens[: frames * SNAC_TOKENS_PER_FRAME]
        if frames == 0:
            return [[], [], []]

        l1, l2, l3 = [], [], []
        for i in range(frames):
            slots = snac_tokens[i * 7 : (i + 1) * 7]
            l1.append((slots[0] - CODE_TOKEN_OFFSET) % 4096)
            l2.extend([
                (slots[1] - CODE_TOKEN_OFFSET) % 4096,
                (slots[4] - CODE_TOKEN_OFFSET) % 4096,
            ])
            l3.extend([
                (slots[2] - CODE_TOKEN_OFFSET) % 4096,
                (slots[3] - CODE_TOKEN_OFFSET) % 4096,
                (slots[5] - CODE_TOKEN_OFFSET) % 4096,
                (slots[6] - CODE_TOKEN_OFFSET) % 4096,
            ])
        return [l1, l2, l3]

    @staticmethod
    def pack_snac_to_7(levels: List[List[int]]) -> List[int]:
        """Inverse of ``unpack_snac_from_7`` for SNAC audio-prefix voice locking."""
        l1, l2, l3 = levels[0], levels[1], levels[2]
        frames = min(len(l1), len(l2) // 2, len(l3) // 4)
        packed: List[int] = []
        for i in range(frames):
            s0 = CODE_TOKEN_OFFSET + 0 * 4096 + int(l1[i])
            s1 = CODE_TOKEN_OFFSET + 1 * 4096 + int(l2[2 * i])
            s2 = CODE_TOKEN_OFFSET + 2 * 4096 + int(l3[4 * i])
            s3 = CODE_TOKEN_OFFSET + 3 * 4096 + int(l3[4 * i + 1])
            s4 = CODE_TOKEN_OFFSET + 4 * 4096 + int(l2[2 * i + 1])
            s5 = CODE_TOKEN_OFFSET + 5 * 4096 + int(l3[4 * i + 2])
            s6 = CODE_TOKEN_OFFSET + 6 * 4096 + int(l3[4 * i + 3])
            packed.extend([s0, s1, s2, s3, s4, s5, s6])
        return packed

    def encode_reference_audio_tokens(self, ref_audio_source: Any, max_ref_sec: float = 5.5) -> List[int]:
        import mlx.core as mx

        if isinstance(ref_audio_source, np.ndarray):
            audio_np = ref_audio_source.astype(np.float32)
            sr = self.sample_rate
        else:
            audio_np, sr = sf.read(str(ref_audio_source), dtype="float32")
        if audio_np.ndim > 1:
            audio_np = audio_np.mean(axis=1)
        if sr != self.sample_rate and audio_np.size > 0:
            duration = audio_np.shape[0] / sr
            target_len = int(duration * self.sample_rate)
            audio_np = np.interp(
                np.linspace(0.0, 1.0, target_len, endpoint=False),
                np.linspace(0.0, 1.0, audio_np.shape[0], endpoint=False),
                audio_np,
            ).astype(np.float32)
        max_samples = int(max_ref_sec * self.sample_rate)
        if audio_np.shape[0] > max_samples:
            audio_np = audio_np[-max_samples:]
        audio_mx = mx.array(audio_np, dtype=mx.float32)[None, None, :]
        codes = self.snac.encode(audio_mx)
        mx.eval(codes)
        levels = [np.array(c.squeeze(0), dtype=np.int32).tolist() for c in codes]
        return self.pack_snac_to_7(levels)

    def generate(
        self,
        text: str,
        instruct: str,
        temperature: float = 0.45,
        top_p: float = 0.9,
        repetition_penalty: float = 1.15,
        max_tokens: int = 2048,
        ref_audio_path: Optional[Any] = None,
        ref_text: Optional[str] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        import mlx.core as mx
        from mlx_audio.lm.generate import stream_generate
        from mlx_audio.lm.sample_utils import make_logits_processors, make_sampler

        t0 = time.perf_counter()
        ref_snac_tokens: List[int] = []
        ref_frames = 0

        has_valid_ref = (
            ref_audio_path is not None
            and ref_text
            and (isinstance(ref_audio_path, np.ndarray) or Path(str(ref_audio_path)).exists())
        )
        if has_valid_ref:
            ref_dur = (
                ref_audio_path.shape[0] / self.sample_rate
                if isinstance(ref_audio_path, np.ndarray)
                else sf.info(str(ref_audio_path)).duration
            )
            if ref_dur <= 6.5:
                raw_snac = self.encode_reference_audio_tokens(ref_audio_path, max_ref_sec=6.5)
                if len(raw_snac) > 28:
                    raw_snac = raw_snac[:-14]
                ref_snac_tokens = raw_snac
                ref_frames = len(ref_snac_tokens) // SNAC_TOKENS_PER_FRAME
                combined_text = f"{ref_text.strip().rstrip('.!?')}, {text.strip()}"
                prompt_str = self.build_prompt(instruct, combined_text)
            else:
                prompt_str = self.build_prompt(instruct, text)
        else:
            prompt_str = self.build_prompt(instruct, text)

        encoded = self.tokenizer.encode(prompt_str, add_special_tokens=False)
        if ref_snac_tokens:
            encoded = encoded + ref_snac_tokens
        prompt_ids = mx.array(encoded, dtype=mx.int32)

        sampler = make_sampler(temperature, top_p, top_k=50)
        logits_processors = make_logits_processors(
            logit_bias=None,
            repetition_penalty=repetition_penalty,
            repetition_context_size=64,
        )

        generated_ids: List[int] = []
        for resp in stream_generate(
            self.model,
            tokenizer=self.tokenizer,
            prompt=prompt_ids,
            max_tokens=max_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
        ):
            tok = int(resp.token)
            if tok == CODE_END_TOKEN_ID:
                if len(generated_ids) >= 28:
                    break
                continue
            generated_ids.append(tok)
            if len(generated_ids) % 100 == 0:
                mx.clear_cache()

        snac_tokens = self.extract_snac_codes(generated_ids)
        if ref_snac_tokens:
            full_levels = self.unpack_snac_from_7(ref_snac_tokens + snac_tokens)
            gen_levels = self.unpack_snac_from_7(snac_tokens)
            if not gen_levels[0]:
                raise RuntimeError("Maya-1 did not produce enough acoustic tokens.")
            codes_mx = [mx.array(level, dtype=mx.int32)[None, :] for level in full_levels]
            audio_hat = self.snac.decode(codes_mx).squeeze()
            mx.eval(audio_hat)
            full_audio_np = np.array(audio_hat, dtype=np.float32)
            slice_sample = ref_frames * 2048
            audio_np = (
                full_audio_np[slice_sample:]
                if full_audio_np.shape[0] > slice_sample
                else full_audio_np
            )
            levels = gen_levels
        else:
            levels = self.unpack_snac_from_7(snac_tokens)
            if not levels[0]:
                raise RuntimeError(
                    "Maya-1 did not produce enough acoustic tokens. "
                    "Try adjusting temperature or description."
                )
            codes_mx = [mx.array(level, dtype=mx.int32)[None, :] for level in levels]
            audio_hat = self.snac.decode(codes_mx).squeeze()
            mx.eval(audio_hat)
            audio_np = np.array(audio_hat, dtype=np.float32)
            if audio_np.shape[0] > 4096:
                audio_np = audio_np[2048:]

        elapsed = time.perf_counter() - t0
        duration = audio_np.shape[0] / self.sample_rate
        mx.clear_cache()

        return audio_np, {
            "duration_sec": round(duration, 2),
            "elapsed_sec": round(elapsed, 2),
            "rtf": round(duration / elapsed, 2) if elapsed > 0 else 0,
            "tokens": len(generated_ids),
            "frames": len(levels[0]),
            "snac_voice_locked": bool(ref_snac_tokens),
            "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 2),
        }


class Maya1Backend(TTSBackend):
    """Maya-1 3.3B MLX backend with inline acting tags (<laugh>, <sigh>, etc.)."""

    id = "maya1"
    display_name = "Maya-1 3.3B (MLX, inline acting tags)"
    sample_rate = 24000
    gpu_compat = ("mps",)
    supports_cloning = True
    supports_voice_design = True
    supports_generation_seed = True
    supported_languages = ("en",)

    def __init__(self, repo_id: str = MAYA1_REPO_ID):
        super().__init__()
        self.repo_id = repo_id
        self._runner: Optional[Maya1MLXRunner] = None

    @classmethod
    def is_available(cls) -> Tuple[bool, str]:
        if sys.platform != "darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
            return False, "Maya-1 MLX requires Apple Silicon (macOS arm64)."
        if importlib.util.find_spec("mlx") is None or importlib.util.find_spec("mlx_audio") is None:
            return False, "mlx and mlx-audio packages are required for Maya-1."
        return True, ""

    def _ensure_loaded(self) -> Maya1MLXRunner:
        if self._runner is None:
            self._runner = Maya1MLXRunner(self.repo_id)
        return self._runner

    def unload(self) -> None:
        if self._runner is not None:
            self._runner = None
            gc.collect()
            try:
                import mlx.core as mx
                mx.clear_cache()
            except Exception:
                pass

    def generate(
        self,
        text: str,
        *,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        language: Optional[str] = None,
        duration: Optional[float] = None,
        description: Optional[str] = None,
        num_step: int = 16,
        guidance_scale: float = 2.0,
        speed: float = 1.0,
        **extras,
    ):
        import torch

        runner = self._ensure_loaded()
        clean_text, tags = sanitize_dialogue_for_model(text, "maya1")
        raw_desc = description or instruct or ""
        compiled_desc = compile_voice_instruct(raw_desc, model_id="maya1", extracted_tags=tags)

        seed = extras.get("seed")
        if seed is not None:
            try:
                import mlx.core as mx
                mx.random.seed(int(seed))
            except Exception:
                pass

        audio_np, _meta = runner.generate(
            text=clean_text,
            instruct=compiled_desc,
            temperature=float(extras.get("temperature", 0.45)),
            top_p=float(extras.get("top_p", 0.9)),
            repetition_penalty=float(extras.get("repetition_penalty", 1.15)),
            max_tokens=int(extras.get("max_tokens", 2048)),
            ref_audio_path=ref_audio,
            ref_text=ref_text,
        )
        audio_np = apply_studio_pacing(audio_np, self.sample_rate, speed=speed)
        audio_np = normalize_studio_loudness(audio_np)
        return torch.from_numpy(audio_np.astype(np.float32)).unsqueeze(0)
