"""Voice Forge domain services: emotion slots, casting, synthesis and scenes.

Bridges Voice Forge's game-dev workflow (characters, emotion profiles, casts,
multi-speaker scenes, SRT/manifest/ZIP bundles) onto Voice Forge Studio's
``tts_backend``, ``asr_backend`` and ``voice_forge_store``.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf

from services import voice_forge_store as store
from services.maya1_backend import (
    MAYA1_EMOTION_TAGS,
    analyze_voice_acoustics,
    compile_voice_instruct,
    normalize_studio_loudness,
    optimize_character_prompts,
    sanitize_dialogue_for_model,
)

CHARACTER_PRESETS: List[Dict[str, str]] = [
    {
        "id": "preset_dwarf_blacksmith",
        "name": "Torvin the Ironwright (Dwarven Blacksmith)",
        "category": "Fantasy NPC",
        "instruct_qwen": (
            "An elderly, weathered male dwarven blacksmith in his 60s with a deep, gravelly "
            "baritone voice, rough raspy texture, natural conversational pacing, and a cynical "
            "Scottish-tinged accent."
        ),
        "instruct_maya": (
            "Rough fantasy dwarf character, Male voice in their 60s with a Scottish accent, "
            "very low pitch, gravelly raspy timbre, natural conversational pacing, grumpy tone "
            "at medium intensity."
        ),
        "sample_text_qwen": (
            "Keep your coin, traveler. That blade was forged in the old fires, and nothing "
            "in these mountains is for sale anymore."
        ),
        "sample_text_maya": (
            "Keep your coin, traveler <snort> that blade was forged in the old fires <sigh> "
            "and nothing in these mountains is for sale anymore."
        ),
    },
    {
        "id": "preset_cyber_rogue",
        "name": "Nyx (Cyberpunk Netrunner / Rogue)",
        "category": "Sci-Fi / Action",
        "instruct_qwen": (
            "A sharp, witty 28-year-old female rogue with a sleek British accent, medium-low "
            "husky pitch, confident and sarcastic tone, brisk conversational pacing."
        ),
        "instruct_maya": (
            "Sarcastic female rogue character, Female voice in her late 20s with a British "
            "accent, slightly husky timbre, brisk pacing, sarcastic and mischievous tone."
        ),
        "sample_text_qwen": (
            "Oh, brilliant plan! Let's just walk right through the main security grid. I'm "
            "sure the automated turrets won't mind at all."
        ),
        "sample_text_maya": (
            "Oh, brilliant plan! <laugh> Let's just walk right through the main security grid "
            "<sigh> I'm sure the automated turrets won't mind at all."
        ),
    },
    {
        "id": "preset_dark_villain",
        "name": "Malakor (Ancient Lich / Main Villain)",
        "category": "Boss / Antagonist",
        "instruct_qwen": (
            "A sinister, ancient male villain in his 50s with a resonant, aristocratic British "
            "accent, cold menacing whispery baritone, dramatic cadence, and dark authority."
        ),
        "instruct_maya": (
            "Dark villain character, Male voice in their 40s with a British accent, low pitch, "
            "gravelly timbre, dramatic pacing, angry menacing tone at high intensity."
        ),
        "sample_text_qwen": (
            "You dare step into my sanctum, mortal? Every hero before you has knelt in ashes, "
            "and you shall be no different."
        ),
        "sample_text_maya": (
            "You dare step into my sanctum, mortal? <chuckle> How amusing. <whisper> Every "
            "hero before you has knelt in ashes."
        ),
    },
    {
        "id": "preset_energetic_companion",
        "name": "Pip (Excitable Alchemist Companion)",
        "category": "Companion",
        "instruct_qwen": (
            "A cheerful, energetic young female alchemist in her early 20s with a bright, clear "
            "American voice, slightly high pitch, fast excited pacing, and bubbly enthusiasm."
        ),
        "instruct_maya": (
            "Energetic young female companion in her 20s with an American accent, bright clear "
            "timbre, fast excited pacing, curious and cheerful tone."
        ),
        "sample_text_qwen": (
            "Wait, wait, don't touch that vial! It's either going to heal all your wounds or "
            "turn your boots into frogs!"
        ),
        "sample_text_maya": (
            "<gasp> Wait, wait, don't touch that vial! <giggle> It's either going to heal all "
            "your wounds or turn your boots into frogs!"
        ),
    },
    {
        "id": "preset_noir_detective",
        "name": "Detective Cole (Gritty Noir Narrator)",
        "category": "Narrator / Noir",
        "instruct_qwen": (
            "A tired 45-year-old male noir detective, late-night smoky baritone voice, neutral "
            "American accent, hushed studio microphone presence, steady conversational pacing."
        ),
        "instruct_maya": (
            "Tired male detective in his 40s with an American accent, low smoky baritone, "
            "steady conversational pacing, calm exhausted delivery."
        ),
        "sample_text_qwen": (
            "Rain was hammering the neon glass outside my office when she walked in. In this "
            "city, a knock after midnight never brings good news."
        ),
        "sample_text_maya": (
            "<exhale> Rain was hammering the neon glass outside my office when she walked in. "
            "<sigh> In this city, a knock after midnight never brings good news."
        ),
    },
]

EMOTIONS: List[Dict[str, Any]] = [
    {
        "id": "neutral", "label": "Neutral", "icon": "neutral", "fallback": [],
        "how": "Relaxed and conversational, like telling a mate about your day.",
        "scripts": [
            "So I got to the station about ten minutes early, which never happens, and of course the train was already sitting there waiting for me.",
            "Honestly, the best bit of the whole weekend was just sitting outside with a coffee and doing absolutely nothing for an hour.",
            "Right, so the plan is we meet at the corner around seven, grab some food, and then see how everyone's feeling after that.",
        ],
    },
    {
        "id": "happy", "label": "Happy", "icon": "happy", "fallback": ["excited", "neutral"],
        "how": "Smile while you speak; warm, bright, a little laugh in the voice.",
        "scripts": [
            "No way, you actually remembered? That's so nice of you. Honestly, you've made my whole week.",
            "Oh, this is brilliant. Look at it! It's exactly what I wanted.",
            "Ha, okay, that's genuinely the funniest thing I've heard all day. Tell it again.",
        ],
    },
    {
        "id": "excited", "label": "Excited", "icon": "excited", "fallback": ["happy", "neutral"],
        "how": "Fast, high energy, words tumbling out.",
        "scripts": [
            "Wait, wait, wait, are you serious? We got the tickets? Front row? This is actually happening!",
            "Guess what, guess what! They said yes! I start on Monday!",
            "Okay, listen to this idea, because it's genius. We take the van, we drive to the coast, and we don't come back until Sunday!",
        ],
    },
    {
        "id": "angry", "label": "Angry", "icon": "angry", "fallback": ["annoyed", "shouting", "neutral"],
        "how": "Controlled fury: tight, clipped and forceful, hitting consonants hard.",
        "scripts": [
            "No. Don't you dare tell me to calm down. I asked you three times, and you looked me in the eye and said it was done.",
            "You know what, I'm done being polite about it. You took it without asking, you broke it, and now you're blaming me?",
            "Every single time. Every single time I trust you with something, this happens.",
        ],
    },
    {
        "id": "annoyed", "label": "Annoyed", "icon": "annoyed", "fallback": ["angry", "sarcastic", "neutral"],
        "how": "Exasperated and fed up, lots of sighing energy.",
        "scripts": [
            "Oh, brilliant. Fantastic. So the one day I actually need the printer to work, it decides to have a little breakdown.",
            "Can you just not tap the table like that? I've asked you nicely about four times now.",
            "Right, so we're doing this again. Same argument, same ending.",
        ],
    },
    {
        "id": "sad", "label": "Sad", "icon": "sad", "fallback": ["tired", "neutral"],
        "how": "Slower and softer, voice dropping at the end of sentences.",
        "scripts": [
            "I just thought it would be different this time, you know? I kept looking at the door all night.",
            "It's fine. Honestly, it's fine. I just wish someone had told me before I found out like that.",
            "We used to sit right here every Sunday. It feels really strange coming back now.",
        ],
    },
    {
        "id": "scared", "label": "Scared", "icon": "scared", "fallback": ["pleading", "excited", "neutral"],
        "how": "Breathy, fast and shaky, a bit hushed.",
        "scripts": [
            "Did you hear that? Listen, there's something outside. Please tell me you locked the back door.",
            "Okay, don't panic. The lights just went off. Why is the door open? I closed that door.",
            "Stop the car! There's someone standing in the road, right there!",
        ],
    },
    {
        "id": "sarcastic", "label": "Sarcastic", "icon": "sarcastic", "fallback": ["annoyed", "neutral"],
        "how": "Dry and deadpan with exaggerated emphasis on the nice words.",
        "scripts": [
            "Oh wow, what an amazing surprise, you're late again.",
            "No, please, take the last slice. You clearly need it more than me.",
            "Yeah, great plan. Really solid. Nothing could possibly go wrong.",
        ],
    },
    {
        "id": "confused", "label": "Confused", "icon": "confused", "fallback": ["neutral"],
        "how": "Puzzled and hesitant, questions rising at the end.",
        "scripts": [
            "Sorry, what? Hang on. So you're saying the meeting was yesterday?",
            "Wait, I don't get it. Why would you put the milk in the cupboard?",
            "Hold on, who's Dave? Is that the same Dave from before?",
        ],
    },
    {
        "id": "pleading", "label": "Pleading", "icon": "pleading", "fallback": ["sad", "scared", "neutral"],
        "how": "Desperate and earnest, voice pushing upward.",
        "scripts": [
            "Please, just give me five minutes. Five minutes and I'll explain everything, I promise.",
            "Come on, don't do this. I'm begging you.",
            "I know I messed up. But please don't leave like this. Just stay and talk to me.",
        ],
    },
    {
        "id": "tired", "label": "Tired", "icon": "tired", "fallback": ["sad", "neutral"],
        "how": "Low energy and breathy, slow, letting words drag.",
        "scripts": [
            "I've been up since five. I haven't eaten. I just want to lie down on the floor.",
            "Give me a second. Why are there so many stairs? Okay, I'm fine.",
            "Mm, yeah, sounds good. Wake me up when we get there.",
        ],
    },
    {
        "id": "whispering", "label": "Whispering", "icon": "whispering", "fallback": ["scared", "neutral"],
        "how": "Hushed stage whisper with a little voice in it, not pure air.",
        "scripts": [
            "Shh, keep your voice down. She's in the next room.",
            "Okay, on three we run for the door. Don't step on the creaky floorboard.",
            "Psst. Are you awake? I think I heard something downstairs.",
        ],
    },
    {
        "id": "shouting", "label": "Shouting", "icon": "shouting", "fallback": ["angry", "excited", "neutral"],
        "how": "Projecting across a room; step back from the mic so it does not clip.",
        "scripts": [
            "Oi! Get off the grass! Can you not read the sign? Off! Now!",
            "Everyone out! The kitchen's on fire! Leave your bags and get out!",
            "I'm over here! Can you hear me? Throw the rope!",
        ],
    },
]
EMOTION_IDS = [e["id"] for e in EMOTIONS]

EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "shouting": ["shout", "yell", "scream", "bellow", "roar", "caps"],
    "whispering": ["whisper", "hushed", "under breath", "murmur", "sotto voce"],
    "angry": ["angry", "furious", "rage", "livid", "losing it", "seething", "fuming"],
    "annoyed": ["annoyed", "irritated", "exasperat", "frustrat", "fed up", "impatient", "grumpy"],
    "scared": ["scared", "afraid", "panic", "terrified", "nervous", "anxious", "fear", "frightened", "shaky"],
    "sad": ["sad", "upset", "crying", "tearful", "defeated", "hurt", "heartbroken", "gloomy", "devastated"],
    "pleading": ["plead", "beg", "desperate", "imploring"],
    "sarcastic": ["sarcas", "deadpan", "dry", "mocking", "ironic", "snide"],
    "confused": ["confus", "puzzled", "baffled", "bewildered", "unsure", "lost"],
    "excited": ["excited", "thrilled", "ecstatic", "enthusias", "hyped", "elated"],
    "happy": ["happy", "cheerful", "warm", "delighted", "laugh", "amused", "joyful", "pleased", "smiling"],
    "tired": ["tired", "exhausted", "weary", "sleepy", "winded", "out of breath", "panting", "yawn"],
}


def emotion_from_text(direction: str, text: str = "") -> str:
    d = (direction or "").lower()
    for emo, words in EMOTION_KEYWORDS.items():
        if any(w in d for w in words):
            return emo
    letters = [c for c in (text or "") if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7 and len(letters) > 6:
        return "shouting"
    return "neutral"


def pick_profile_clip(profile: Dict[str, Any], emotion: str) -> Optional[Dict[str, Any]]:
    """Pick best clip for an emotion: exact slot, fallback chain, neutral, or first clip."""
    raw_clips = profile.get("clips") or []
    if isinstance(raw_clips, dict):
        clips = raw_clips
    else:
        clips = {c["emotion"]: c for c in raw_clips if isinstance(c, dict) and c.get("emotion")}
    if not clips:
        return None
    meta = next((e for e in EMOTIONS if e["id"] == emotion), None)
    for emo in [emotion] + (meta["fallback"] if meta else []) + ["neutral"]:
        if emo in clips:
            return clips[emo]
    return next(iter(clips.values()))


def analyze_recording(path: Union[str, Path]) -> Dict[str, Any]:
    """Level, noise and clipping check for a reference recording."""
    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    duration = audio.shape[0] / float(sr) if sr else 0.0
    eps = 1e-9
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    hop = max(1, int(sr * 0.02))
    n = audio.shape[0] // hop
    frames = audio[: n * hop].reshape(n, hop) if n else np.zeros((1, hop), dtype=np.float32)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    speech_db = 20.0 * float(np.log10(float(np.percentile(rms, 90)) + eps))
    noise_db = 20.0 * float(np.log10(float(np.percentile(rms, 10)) + eps))
    clipped = float(np.mean(np.abs(audio) > 0.985)) if audio.size else 0.0
    tips: List[str] = []
    if clipped > 0.0005 or peak > 0.995:
        tips.append("Recording clipped (too loud). Lower input gain or step back from the mic.")
    elif speech_db < -32:
        tips.append("Quite quiet. Move closer to the mic or raise input gain.")
    if noise_db > -50:
        tips.append("Noticeable background noise between words.")
    if speech_db - noise_db < 25:
        tips.append("Low signal-to-noise ratio; clone may pick up room hiss.")
    if duration < 5:
        tips.append("Short clip. 8-12 seconds gives the clone more to learn from.")
    elif duration > 20:
        tips.append("Long clip; 6-12 seconds is usually ideal.")
    score = 100
    score -= 35 if (clipped > 0.0005 or peak > 0.995) else 0
    score -= 20 if speech_db < -32 else 0
    score -= 20 if noise_db > -50 else 0
    score -= 15 if speech_db - noise_db < 25 else 0
    score -= 10 if duration < 5 else 0
    return {
        "duration_sec": round(duration, 2),
        "peak_dbfs": round(20.0 * float(np.log10(peak + eps)), 1),
        "speech_dbfs": round(speech_db, 1),
        "noise_dbfs": round(noise_db, 1),
        "snr_db": round(speech_db - noise_db, 1),
        "score": max(0, score),
        "tips": tips,
    }


# ---------------------------------------------------------------------------
# Script parsing & Casting
# ---------------------------------------------------------------------------

_SCRIPT_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9_ .-]{1,40}?)(?:\s*\(([^)]+)\))?\s*:\s*(.+?)\s*$"
)


def parse_script_text(script_text: str) -> List[Dict[str, Any]]:
    """Parse ``Speaker (direction): line`` script text into structured lines."""
    lines: List[Dict[str, Any]] = []
    for raw in (script_text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        m = _SCRIPT_LINE_RE.match(s)
        if m:
            speaker = m.group(1).strip()
            direction = (m.group(2) or "").strip()
            text = m.group(3).strip()
            emo = emotion_from_text(direction, text)
            lines.append({
                "speaker": speaker,
                "direction": direction,
                "emotion": emo,
                "text": text,
            })
        elif lines:
            lines[-1]["text"] = f"{lines[-1]['text']} {s}"
    return lines


def extract_cast_from_script(script_text: str) -> Dict[str, Any]:
    """Extract speakers, sample lines and suggested library/profile matches."""
    lines = parse_script_text(script_text)
    speakers_order: List[str] = []
    speaker_lines: Dict[str, List[str]] = {}
    for item in lines:
        sp = item["speaker"]
        if sp not in speaker_lines:
            speakers_order.append(sp)
            speaker_lines[sp] = []
        speaker_lines[sp].append(item["text"])

    characters_out: List[Dict[str, Any]] = []
    for sp in speakers_order:
        prof = store.find_profile_by_name(sp)
        char = store.find_character_by_name(sp)
        entry: Dict[str, Any] = {
            "name": sp,
            "line_count": len(speaker_lines[sp]),
            "sample_lines": speaker_lines[sp][:3],
            "suggested_profile_id": prof["id"] if prof else None,
            "suggested_character_id": char["id"] if char else None,
            "description": (char or prof or {}).get("description", ""),
        }
        characters_out.append(entry)
    return {
        "characters": characters_out,
        "lines": lines,
        "used_claude": False,
    }


def claude_cli_status() -> Dict[str, Any]:
    path = shutil.which("claude")
    return {
        "available": bool(path),
        "via": "claude-cli" if path else "",
        "path": path or "",
        "detail": f"Found at {path}" if path else "claude CLI not on PATH",
    }


# ---------------------------------------------------------------------------
# Engine mapping & Synthesis
# ---------------------------------------------------------------------------

_VF_MODEL_TO_BACKEND = {
    "maya1": ("maya1", None),
    "qwen3_voicedesign": ("mlx-audio", "qwen3-tts"),
    "qwen3_clone": ("mlx-audio", "qwen3-tts-base"),
    "chatterbox": ("mlx-audio", "chatterbox"),
    "voxcpm2": ("mlx-audio", "voxcpm2"),
}


def resolve_vf_backend(model_id: Optional[str]):
    """Resolve a Voice Forge model_id onto a Voice Forge Studio TTSBackend."""
    from services import tts_backend

    mid = (model_id or "").strip() or tts_backend.active_backend_id()
    if mid in _VF_MODEL_TO_BACKEND:
        backend_id, mlx_key = _VF_MODEL_TO_BACKEND[mid]
        if backend_id == "mlx-audio":
            cls = tts_backend.get_backend_class("mlx-audio")
            ok, _ = cls.is_available()
            if not ok:
                backend_id = tts_backend.active_backend_id()
                mlx_key = None
        inst = tts_backend.get_engine_instance_for(backend_id)
        if mlx_key and hasattr(inst, "set_model"):
            try:
                inst.set_model(mlx_key)
            except Exception:
                pass
        return inst, mid

    try:
        return tts_backend.get_engine_instance_for(mid), mid
    except ValueError:
        return tts_backend.get_active_tts_backend(), tts_backend.active_backend_id()


def synthesize_line(
    *,
    text: str,
    model_id: Optional[str] = None,
    instruct: str = "",
    character_id: Optional[str] = None,
    ref_audio_path: Optional[str] = None,
    ref_text: Optional[str] = None,
    language: Optional[str] = None,
    speed: float = 1.0,
    temperature: float = 0.7,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
    seed: Optional[int] = None,
    save_take: bool = True,
) -> Dict[str, Any]:
    """Synthesize a single dialogue line and persist it as a Voice Forge take."""
    t0 = time.perf_counter()
    char = store.get_character(character_id) if character_id else None
    if char:
        ref_audio_path = ref_audio_path or char.get("file_path") or None
        ref_text = ref_text or char.get("ref_text") or None
        if not instruct:
            instruct = char.get("description") or ""

    backend, resolved_model = resolve_vf_backend(model_id)
    clean_text, tags = sanitize_dialogue_for_model(text, resolved_model)
    compiled_instruct = compile_voice_instruct(instruct, model_id=resolved_model, extracted_tags=tags) if instruct else ""

    tensor = backend.generate(
        clean_text or text,
        ref_audio=ref_audio_path if ref_audio_path and Path(ref_audio_path).exists() else None,
        ref_text=ref_text,
        instruct=compiled_instruct or None,
        description=compiled_instruct or None,
        language=language,
        speed=speed,
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
        seed=seed,
    )
    sr = int(getattr(backend, "sample_rate", 24000) or 24000)
    if hasattr(tensor, "detach"):
        audio_np = tensor.detach().cpu().numpy().squeeze().astype(np.float32)
    else:
        audio_np = np.asarray(tensor, dtype=np.float32).squeeze()
    audio_np = normalize_studio_loudness(audio_np)

    elapsed = round(time.perf_counter() - t0, 2)
    duration = round(audio_np.shape[0] / float(sr), 2) if sr else 0.0
    take_id = f"take_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    filename = f"{take_id}.wav"
    out_path = store.vf_takes_dir() / filename
    sf.write(str(out_path), audio_np, sr, subtype="PCM_16")

    record: Dict[str, Any] = {
        "id": take_id,
        "text": text,
        "cleaned_text": clean_text,
        "model_id": resolved_model,
        "character_id": character_id or "",
        "filename": filename,
        "file_path": str(out_path),
        "url": f"/audio/takes/{filename}",
        "sample_rate": sr,
        "duration_sec": duration,
        "elapsed_sec": elapsed,
        "instruct": compiled_instruct,
        "acoustics": analyze_voice_acoustics(audio_np, sr),
        "created_at": time.time(),
    }
    if save_take:
        return store.upsert_take(record)
    return record


# ---------------------------------------------------------------------------
# Scene rendering, stitching, SRT, manifest, ZIP, ASR check
# ---------------------------------------------------------------------------

def _fmt_srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_scene_sidecars(scene: Dict[str, Any]) -> Tuple[Path, Path]:
    """Write ``<scene_id>.srt`` and ``<scene_id>_manifest.json`` into ``vf_scenes_dir``."""
    sdir = store.vf_scenes_dir()
    scene_id = scene["id"]
    srt_path = sdir / f"{scene_id}.srt"
    manifest_path = sdir / f"{scene_id}_manifest.json"

    srt_blocks: List[str] = []
    for idx, seg in enumerate(scene.get("segments") or [], 1):
        start = float(seg.get("start_sec") or 0.0)
        end = float(seg.get("end_sec") or (start + float(seg.get("duration_sec") or 0.0)))
        speaker = seg.get("speaker") or "Speaker"
        text = seg.get("text") or ""
        srt_blocks.append(f"{idx}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{speaker}: {text}\n")
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    manifest_path.write_text(json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8")
    return srt_path, manifest_path


def build_scene_export_zip(scene: Dict[str, Any]) -> bytes:
    """Package the scene WAV, SRT, manifest and segment WAVs into an in-memory ZIP."""
    srt_path, manifest_path = write_scene_sidecars(scene)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        wav_path = Path(scene.get("file_path") or "")
        if wav_path.exists():
            zf.write(wav_path, arcname=wav_path.name)
        if srt_path.exists():
            zf.write(srt_path, arcname=srt_path.name)
        if manifest_path.exists():
            zf.write(manifest_path, arcname=manifest_path.name)
        for idx, seg in enumerate(scene.get("segments") or []):
            tp = Path(seg.get("file_path") or "")
            if tp.exists():
                sp = re.sub(r"[^A-Za-z0-9_-]+", "_", seg.get("speaker") or "line")
                zf.write(tp, arcname=f"lines/{idx:03d}_{sp}.wav")
    return buf.getvalue()


def _stitch_wav_paths(
    items: List[Tuple[Path, int]],
    out_path: Path,
    target_sr: int = 24000,
) -> Tuple[float, List[Tuple[float, float]]]:
    """Concatenate WAV files with per-item trailing pauses (negative = overlap)."""
    chunks: List[np.ndarray] = []
    spans: List[Tuple[float, float]] = []
    cursor = 0
    for path, pause_ms in items:
        audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != target_sr and audio.size > 0:
            new_len = max(1, int(round(audio.shape[0] * target_sr / float(sr))))
            audio = np.interp(
                np.linspace(0.0, 1.0, new_len, endpoint=False),
                np.linspace(0.0, 1.0, audio.shape[0], endpoint=False),
                audio,
            ).astype(np.float32)
        start_sec = cursor / float(target_sr)
        chunks.append(audio)
        cursor += audio.shape[0]
        end_sec = cursor / float(target_sr)
        spans.append((round(start_sec, 3), round(end_sec, 3)))
        if pause_ms > 0:
            sil = np.zeros(int(target_sr * (pause_ms / 1000.0)), dtype=np.float32)
            chunks.append(sil)
            cursor += sil.shape[0]

    combined = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    sf.write(str(out_path), combined, target_sr, subtype="PCM_16")
    return round(combined.shape[0] / float(target_sr), 2), spans


def stitch_takes(title: str, take_ids: List[str], pause_ms: int = 350) -> Dict[str, Any]:
    """Stitch existing takes into a saved scene."""
    items: List[Tuple[Path, int]] = []
    segments: List[Dict[str, Any]] = []
    for idx, tid in enumerate(take_ids):
        take = store.get_take(tid)
        if not take:
            raise KeyError(f"Take not found: {tid}")
        tp = Path(take["file_path"])
        if not tp.exists():
            raise FileNotFoundError(f"Audio file missing for take {tid}")
        items.append((tp, pause_ms if idx < len(take_ids) - 1 else 0))
        segments.append({
            "index": idx,
            "speaker": take.get("character_id") or "Speaker",
            "text": take.get("text") or "",
            "take_id": tid,
            "file_path": str(tp),
            "url": take.get("url") or "",
            "duration_sec": take.get("duration_sec") or 0.0,
        })

    scene_id = f"scene_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    filename = f"{scene_id}.wav"
    out_path = store.vf_scenes_dir() / filename
    duration, spans = _stitch_wav_paths(items, out_path)
    for seg, (s, e) in zip(segments, spans):
        seg["start_sec"] = s
        seg["end_sec"] = e

    scene = store.upsert_scene({
        "id": scene_id,
        "title": title or "Stitched Scene",
        "filename": filename,
        "duration_sec": duration,
        "elapsed_sec": 0.0,
        "model_swaps": 0,
        "line_count": len(segments),
        "cast": {},
        "segments": segments,
        "created_at": time.time(),
    })
    write_scene_sidecars(scene)
    return scene


def render_scene(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Render a multi-speaker scene from ``lines`` or ``script_text`` + ``cast``."""
    t0 = time.perf_counter()
    cast: Dict[str, Any] = dict(payload.get("cast") or {})
    lines = payload.get("lines")
    if not lines and payload.get("script_text"):
        lines = parse_script_text(payload["script_text"])
    lines = list(lines or [])
    if not lines:
        raise ValueError("Scene render requires non-empty lines or script_text.")

    default_pause_ms = int(payload.get("default_pause_ms") or 350)
    use_profiles = payload.get("use_profiles", True)
    segments: List[Dict[str, Any]] = []
    wav_items: List[Tuple[Path, int]] = []

    for idx, line in enumerate(lines):
        speaker = str(line.get("speaker") or "Narrator")
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        spec = cast.get(speaker) or {}
        if isinstance(spec, str):
            spec = {"instruct": spec}

        char_id = spec.get("character_id") or spec.get("char_id")
        instruct = line.get("instruct") or spec.get("instruct") or ""
        model_id = line.get("model_id") or spec.get("model_id") or payload.get("clone_model_id")
        ref_audio = line.get("ref_audio_path") or spec.get("ref_audio_path")
        ref_text = line.get("ref_text") or spec.get("ref_text")

        # Profile emotion clip selection
        if use_profiles and not char_id:
            prof = None
            if spec.get("profile_id"):
                prof = store.get_profile(spec["profile_id"])
            elif spec.get("profile"):
                prof = store.find_profile_by_name(spec["profile"])
            else:
                prof = store.find_profile_by_name(speaker)
            if prof:
                emo = line.get("emotion") or emotion_from_text(line.get("direction") or "", text)
                clip = pick_profile_clip(prof, emo)
                if clip and clip.get("character_id"):
                    char_id = clip["character_id"]

        if not char_id:
            by_name = store.find_character_by_name(speaker)
            if by_name:
                char_id = by_name["id"]

        take = synthesize_line(
            text=text,
            model_id=model_id,
            instruct=instruct,
            character_id=char_id,
            ref_audio_path=ref_audio,
            ref_text=ref_text,
            speed=float(line.get("speed") or payload.get("speed") or 1.0),
            temperature=float(line.get("temperature") or payload.get("temperature") or 0.7),
            top_p=float(line.get("top_p") or payload.get("top_p") or 0.9),
            repetition_penalty=float(line.get("repetition_penalty") or payload.get("repetition_penalty") or 1.1),
            seed=line.get("seed") if line.get("seed") is not None else payload.get("seed"),
            save_take=True,
        )
        pause_ms = int(line.get("pause_after_ms") if line.get("pause_after_ms") is not None else default_pause_ms)
        wav_items.append((Path(take["file_path"]), pause_ms if idx < len(lines) - 1 else 0))
        segments.append({
            "index": len(segments),
            "speaker": speaker,
            "text": text,
            "emotion": line.get("emotion") or emotion_from_text(line.get("direction") or "", text),
            "direction": line.get("direction") or "",
            "character_id": char_id or "",
            "model_id": take["model_id"],
            "take_id": take["id"],
            "file_path": take["file_path"],
            "url": take["url"],
            "take_url": take["url"],
            "duration_sec": take["duration_sec"],
            "pause_after_ms": pause_ms,
        })

    scene_id = f"scene_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    filename = f"{scene_id}.wav"
    out_path = store.vf_scenes_dir() / filename
    duration, spans = _stitch_wav_paths(wav_items, out_path)
    for seg, (s, e) in zip(segments, spans):
        seg["start_sec"] = s
        seg["end_sec"] = e

    scene = store.upsert_scene({
        "id": scene_id,
        "title": payload.get("title") or "Untitled Scene",
        "filename": filename,
        "duration_sec": duration,
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "model_swaps": 0,
        "line_count": len(segments),
        "cast": cast,
        "segments": segments,
        "created_at": time.time(),
    })
    write_scene_sidecars(scene)
    return scene


def transcribe_audio_file(path: Union[str, Path]) -> str:
    """Transcribe an audio file using Voice Forge Studio's active ASR backend."""
    try:
        from services import asr_backend
        asr = asr_backend.get_active_asr_backend()
        res = asr.transcribe(str(path))
        if isinstance(res, dict):
            return str(res.get("text") or "").strip()
        return str(res or "").strip()
    except Exception:
        return ""


def check_scene_with_asr(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Run ASR across each segment in a scene and flag mismatches."""
    results: List[Dict[str, Any]] = []
    flagged: List[int] = []
    for seg in scene.get("segments") or []:
        fp = Path(seg.get("file_path") or "")
        expected = (seg.get("text") or "").strip()
        heard = transcribe_audio_file(fp) if fp.exists() else ""
        exp_words = set(re.findall(r"[a-z0-9]+", expected.lower()))
        heard_words = set(re.findall(r"[a-z0-9]+", heard.lower()))
        overlap = len(exp_words & heard_words) / max(1, len(exp_words)) if heard_words else 0.0
        ok = bool(heard) and overlap >= 0.65
        if not ok:
            flagged.append(int(seg.get("index", 0)))
        results.append({
            "index": seg.get("index", 0),
            "speaker": seg.get("speaker", ""),
            "expected": expected,
            "heard": heard,
            "word_overlap": round(overlap, 3),
            "ok": ok,
        })
    return {
        "scene_id": scene["id"],
        "lines": results,
        "flagged": flagged,
    }
