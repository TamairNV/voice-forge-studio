"""Voice Forge API router and static UI pages.

Preserves Voice Forge's ``/api/*`` endpoint paths and HTML pages so
``voiceforge_mcp.py``, existing agents, and the Voice Forge web UI work
directly on top of Voice Forge Studio's backend.
"""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services import voice_forge_service as svc
from services import voice_forge_store as store
from services.maya1_backend import MAYA1_EMOTION_TAGS, optimize_character_prompts

router = APIRouter(tags=["voice-forge"])

STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "voice_forge"


def mount_voice_forge_static(app) -> None:
    """Mount Voice Forge static assets and audio directories on the FastAPI app."""
    dirs = store.ensure_vf_dirs()
    app.mount("/audio/scenes", StaticFiles(directory=str(dirs["scenes"])), name="vf_scenes")
    app.mount("/audio/takes", StaticFiles(directory=str(dirs["takes"])), name="vf_takes")
    app.mount("/audio/characters", StaticFiles(directory=str(dirs["characters"])), name="vf_characters")
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="vf_static")


def _serve_html(filename: str) -> HTMLResponse:
    p = STATIC_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"UI page not found: {filename}")
    return HTMLResponse(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class LoadModelRequest(BaseModel):
    model_id: str


class SynthesizeRequest(BaseModel):
    model_id: Optional[str] = None
    text: str
    instruct: str = ""
    language: Optional[str] = None
    speed: float = 1.0
    trim_silence: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    seed: Optional[int] = None
    dynamic_temperature: bool = False
    character_id: Optional[str] = None
    prev_take_id: Optional[str] = None
    prev_audio_path: Optional[str] = None
    prev_text: Optional[str] = None
    blend_with: Optional[str] = None
    blend_strength: float = 0.0
    emotion_blend: Optional[float] = None


class DesignAndLockRequest(BaseModel):
    name: str
    instruct: str
    sample_text: str
    design_model_id: Optional[str] = "qwen3_voicedesign"
    speed: float = 1.0
    trim_silence: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    seed: Optional[int] = None


class SaveCharacterFromTakeRequest(BaseModel):
    take_id: str
    name: str
    description: str = ""


class CharacterFromRecordingRequest(BaseModel):
    name: str
    audio_path: str
    ref_text: str = ""
    description: str = ""
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    ref_text: Optional[str] = None
    favorite: Optional[bool] = None
    tags: Optional[List[str]] = None


class OptimizePromptRequest(BaseModel):
    concept: str
    name: str = ""
    model_id: str = "qwen3_voicedesign"
    dialogue_text: str = ""


class SceneLineItem(BaseModel):
    speaker: str
    text: str
    instruct: str = ""
    model_id: Optional[str] = None
    speed: Optional[float] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = None
    seed: Optional[int] = None
    pause_after_ms: Optional[int] = None
    ref_audio_path: Optional[str] = None
    context_reset: bool = False
    continuity_group: Optional[str] = None
    ref_text: Optional[str] = None
    blend_with: Optional[str] = None
    blend_strength: float = 0.0
    emotion: Optional[str] = None
    direction: str = ""
    emotion_blend: Optional[float] = None


class SceneRenderRequest(BaseModel):
    title: str = "Untitled Scene"
    cast: Dict[str, Any] = Field(default_factory=dict)
    lines: Optional[List[SceneLineItem]] = None
    script_text: Optional[str] = None
    default_pause_ms: int = 350
    speed: float = 1.0
    trim_silence: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    seed: Optional[int] = None
    auto_lock_new_characters: bool = True
    context_continuity: bool = False
    natural_pacing: bool = True
    clone_model_id: Optional[str] = None
    chatterbox_takes: int = 1
    takes_per_line: int = 1
    use_profiles: bool = True


class BatchSceneRenderRequest(BaseModel):
    scenes: List[SceneRenderRequest]


class StitchTakesRequest(BaseModel):
    title: str = "Stitched Scene"
    take_ids: List[str]
    pause_ms: int = 350


class RerollSceneLineRequest(BaseModel):
    line_index: int
    text: Optional[str] = None
    instruct: Optional[str] = None
    model_id: Optional[str] = None
    speed: Optional[float] = None
    pause_after_ms: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = None
    seed: Optional[int] = None
    blend_with: Optional[str] = None
    blend_strength: Optional[float] = None
    emotion_blend: Optional[float] = None


class UseTakeRequest(BaseModel):
    line_index: int
    take_id: str


class CastExtractRequest(BaseModel):
    script: str
    model: Optional[str] = None
    use_claude: bool = False


class CastImproveRequest(BaseModel):
    name: str
    description: str = ""
    lines: List[str] = Field(default_factory=list)
    model: Optional[str] = None


class SavedCastRequest(BaseModel):
    name: str
    script: str = ""
    title: str = ""
    mapping: Dict[str, Any] = Field(default_factory=dict)
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    temperature: Optional[float] = None


class CastProduceRequest(BaseModel):
    script: str
    voices: Dict[str, Any] = Field(default_factory=dict)
    use_claude: bool = False
    improve_new_voices: bool = False
    title: str = "Produced Scene"
    temperature: float = 0.7
    takes_per_line: int = 1
    default_pause_ms: int = 350
    natural_pacing: bool = True
    context_continuity: bool = False
    dry_run: bool = False


class ProfileRequest(BaseModel):
    name: str
    description: str = ""


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    engine: Optional[str] = None
    emotion_blend: Optional[float] = None
    shout_blend: Optional[float] = None


class LinkClipRequest(BaseModel):
    emotion: str
    character_id: str


class PromptRequest(BaseModel):
    emotion: str = "neutral"
    context: str = ""


class ProfileClipFromPathRequest(BaseModel):
    emotion: str
    audio_path: str
    script: str = ""


# ---------------------------------------------------------------------------
# Discovery, health, models & prompts
# ---------------------------------------------------------------------------

def _vf_model_catalog() -> List[Dict[str, Any]]:
    from services import tts_backend
    mlx_ok = False
    maya_ok = False
    try:
        mlx_ok, _ = tts_backend.get_backend_class("mlx-audio").is_available()
    except Exception:
        pass
    try:
        maya_ok, _ = tts_backend.get_backend_class("maya1").is_available()
    except Exception:
        pass
    return [
        {
            "id": "voxcpm2",
            "name": "VoxCPM2 8-bit (Default, MLX)",
            "repo": "mlx-community/VoxCPM2-8bit",
            "vram_gb": 3.3,
            "badge": "Default Studio Engine",
            "description": "Default game-dev TTS engine on Apple Silicon (MLX 8-bit).",
            "available": mlx_ok,
        },
        {
            "id": "qwen3_voicedesign",
            "name": "Qwen3-TTS 1.7B Voice Design (MLX)",
            "repo": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit",
            "vram_gb": 2.2,
            "badge": "Best for Inventing Voices",
            "description": "Design brand-new voices from natural-language descriptions.",
            "available": mlx_ok,
        },
        {
            "id": "qwen3_clone",
            "name": "Qwen3-TTS 0.6B Base Clone (MLX)",
            "repo": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
            "vram_gb": 1.2,
            "badge": "Zero-Shot Voice Cloning",
            "description": "Clone locked character voices from reference clips.",
            "available": mlx_ok,
        },
        {
            "id": "maya1",
            "name": "Maya-1 3.3B Expressive Acting (MLX)",
            "repo": "nhe-ai/maya1-mlx-8Bit",
            "vram_gb": 3.6,
            "badge": "Inline Acting Tags",
            "description": "Expressive character acting with <laugh>, <sigh>, <gasp> tags.",
            "available": maya_ok,
        },
        {
            "id": "chatterbox",
            "name": "Chatterbox TTS 4-bit (MLX)",
            "repo": "mlx-community/Chatterbox-TTS-4bit",
            "vram_gb": 0.5,
            "badge": "Fast Cloning",
            "description": "Lightweight 4-bit MLX voice cloning.",
            "available": mlx_ok,
        },
    ]


def _engine_state_payload(status_message: str = "") -> Dict[str, Any]:
    from services import tts_backend
    active = tts_backend.active_backend_id()
    active_mem = 0.0
    cache_mem = 0.0
    peak_mem = 0.0
    try:
        import mlx.core as mx
        active_mem = round(mx.get_active_memory() / 1e9, 2)
        cache_mem = round(mx.get_cache_memory() / 1e9, 2)
        peak_mem = round(mx.get_peak_memory() / 1e9, 2)
    except Exception:
        pass
    return {
        "active": active,
        "active_model_id": active,
        "loading_model_id": None,
        "status_message": status_message or f"Active backend: {active}",
        "active_memory_gb": active_mem,
        "cache_memory_gb": cache_mem,
        "peak_memory_gb": peak_mem,
        "mlx_cache_limit_gb": 2.0,
        "idle_unload_minutes": 15,
        "models": _vf_model_catalog(),
        "engines": tts_backend.list_backends(),
    }


@router.get("/api/llm-guide")
def get_llm_guide():
    p = STATIC_DIR / "LLM_PROMPT_GUIDE.md"
    md = p.read_text(encoding="utf-8") if p.exists() else "Voice Forge Studio LLM Prompt Guide"
    return {"system_prompt_markdown": md, "guide": md}


@router.get("/api/capabilities")
def get_capabilities(request: Request):
    ops: List[Dict[str, str]] = []
    for r in request.app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/"):
            continue
        methods = sorted(m for m in (getattr(r, "methods", None) or set()) if m not in ("HEAD", "OPTIONS"))
        for m in methods:
            ops.append({"method": m, "path": path, "name": getattr(r, "name", "")})
    return {"operations": ops, "count": len(ops)}


@router.post("/api/prompts/optimize")
def optimize_prompt(req: OptimizePromptRequest):
    opt = optimize_character_prompts(req.concept)
    return {
        **opt,
        "instruct_qwen": opt["instruct_qwen3"],
        "golden_sample_qwen": opt["golden_sample"],
    }


@router.get("/api/health")
def vf_health():
    from services import tts_backend
    return {
        "status": "ok",
        "active_engine": tts_backend.active_backend_id(),
        "characters": len(store.list_characters()),
        "profiles": len(store.list_profiles()),
        "scenes": len(store.list_scenes()),
    }


@router.get("/api/status")
def vf_status():
    eng = _engine_state_payload()
    chars = store.list_characters()
    profs = store.list_profiles()
    casts = store.list_casts()
    scenes = store.list_scenes()
    takes = store.list_takes()
    return {
        **eng,
        "status": "ready",
        "loaded_model": eng["active_model_id"],
        "active_engine": eng["active_model_id"],
        "characters": chars,
        "profiles": profs,
        "casts": casts,
        "scenes": scenes,
        "takes": takes,
        "presets": svc.CHARACTER_PRESETS,
        "tags": MAYA1_EMOTION_TAGS,
        "maya1_tags": MAYA1_EMOTION_TAGS,
        "counts": {
            "characters": len(chars),
            "profiles": len(profs),
            "casts": len(casts),
            "scenes": len(scenes),
            "takes": len(takes),
        },
    }


@router.get("/api/models")
def vf_models():
    from services import tts_backend
    return {"models": _vf_model_catalog(), "backends": tts_backend.list_backends(), "active": tts_backend.active_backend_id()}


@router.get("/api/engine")
def vf_engine():
    return _engine_state_payload()


@router.get("/api/tags")
def vf_tags():
    return {"tags": MAYA1_EMOTION_TAGS}


@router.get("/api/presets")
def vf_presets():
    return {"presets": svc.CHARACTER_PRESETS}


@router.post("/api/model/load")
def vf_model_load(req: LoadModelRequest):
    backend, resolved = svc.resolve_vf_backend(req.model_id)
    if hasattr(backend, "_ensure_loaded"):
        backend._ensure_loaded()
    st = _engine_state_payload(status_message=f"Loaded {resolved}")
    st["status"] = "loaded"
    st["model_id"] = resolved
    st["backend_id"] = getattr(backend, "id", resolved)
    return st


@router.post("/api/model/unload")
def vf_model_unload():
    from services import tts_backend
    try:
        tts_backend.unload_active_tts_backend()
    except Exception:
        pass
    st = _engine_state_payload(status_message="Unloaded active TTS model")
    st["status"] = "unloaded"
    return st


# ---------------------------------------------------------------------------
# Synthesis & takes
# ---------------------------------------------------------------------------

@router.post("/api/synthesize")
def vf_synthesize(req: SynthesizeRequest):
    return svc.synthesize_line(
        text=req.text,
        model_id=req.model_id,
        instruct=req.instruct,
        character_id=req.character_id,
        language=req.language,
        speed=req.speed,
        temperature=req.temperature,
        top_p=req.top_p,
        repetition_penalty=req.repetition_penalty,
        seed=req.seed,
        save_take=True,
    )


@router.post("/api/synthesize/wav")
def vf_synthesize_wav(req: SynthesizeRequest):
    take = vf_synthesize(req)
    return FileResponse(path=take["file_path"], media_type="audio/wav", filename=take["filename"])


@router.get("/api/takes")
def vf_list_takes(limit: int = Query(200, ge=1, le=2000)):
    return {"takes": store.list_takes(limit=limit)}


@router.delete("/api/takes/{take_id}")
def vf_delete_take(take_id: str):
    if not store.delete_take(take_id):
        raise HTTPException(status_code=404, detail="Take not found")
    return {"deleted": take_id}


# ---------------------------------------------------------------------------
# Characters & Voice Library
# ---------------------------------------------------------------------------

@router.get("/api/characters")
def vf_list_characters():
    return {"characters": store.list_characters()}


@router.get("/api/voices")
def vf_list_voices():
    import soundfile as sf
    scenes = store.list_scenes()
    usage: Dict[str, int] = {}
    for sc in scenes:
        for seg in sc.get("segments") or []:
            cid = seg.get("character_id")
            if cid:
                usage[cid] = usage.get(cid, 0) + 1
    voices: List[Dict[str, Any]] = []
    for ch in store.list_characters():
        fp = Path(ch.get("file_path") or "")
        exists = fp.exists() and fp.is_file()
        dur = ch.get("duration_sec")
        if exists and dur is None:
            try:
                dur = round(float(sf.info(str(fp)).duration), 2)
            except Exception:
                dur = 0.0
        voices.append({
            **ch,
            "missing_audio": not exists,
            "duration_sec": dur or 0.0,
            "scene_lines": usage.get(ch["id"], 0),
        })
    return {
        "voices": voices,
        "characters": voices,
        "profiles": store.list_profiles(),
    }


@router.post("/api/characters/design-and-lock")
def vf_design_and_lock(req: DesignAndLockRequest):
    take = svc.synthesize_line(
        text=req.sample_text,
        model_id=req.design_model_id,
        instruct=req.instruct,
        speed=req.speed,
        temperature=req.temperature,
        top_p=req.top_p,
        seed=req.seed,
        save_take=True,
    )
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}.wav"
    dst = store.vf_characters_dir() / audio_file
    shutil.copy2(take["file_path"], dst)
    char = store.upsert_character({
        "id": char_id,
        "name": req.name,
        "description": req.instruct,
        "ref_text": req.sample_text,
        "audio_file": audio_file,
        "source_model": take["model_id"],
        "created_at": time.time(),
    })
    return {"character": char, "take": take}


@router.post("/api/characters/from-take")
def vf_character_from_take(req: SaveCharacterFromTakeRequest):
    take = store.get_take(req.take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    src = Path(take["file_path"])
    if not src.exists():
        raise HTTPException(status_code=404, detail="Take audio file missing")
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}.wav"
    shutil.copy2(src, store.vf_characters_dir() / audio_file)
    return store.upsert_character({
        "id": char_id,
        "name": req.name,
        "description": req.description or take.get("instruct") or "",
        "ref_text": take.get("text") or "",
        "audio_file": audio_file,
        "source_model": take.get("model_id") or "",
        "created_at": time.time(),
    })


@router.post("/api/characters/from-recording")
def vf_character_from_recording(req: CharacterFromRecordingRequest):
    src = Path(req.audio_path).expanduser()
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Recording not found: {src}")
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}{src.suffix or '.wav'}"
    dst = store.vf_characters_dir() / audio_file
    shutil.copy2(src, dst)
    ref_text = req.ref_text or svc.transcribe_audio_file(dst)
    return store.upsert_character({
        "id": char_id,
        "name": req.name,
        "description": req.description,
        "ref_text": ref_text,
        "audio_file": audio_file,
        "source_model": "recording",
        "created_at": time.time(),
    })


@router.post("/api/characters/upload")
async def vf_upload_character(
    name: str = Form(...),
    description: str = Form(""),
    ref_text: str = Form(""),
    file: UploadFile = File(...),
):
    ext = Path(file.filename or "clip.wav").suffix or ".wav"
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}{ext}"
    dst = store.vf_characters_dir() / audio_file
    dst.write_bytes(await file.read())
    transcript = ref_text or svc.transcribe_audio_file(dst)
    return store.upsert_character({
        "id": char_id,
        "name": name,
        "description": description,
        "ref_text": transcript,
        "audio_file": audio_file,
        "source_model": "upload",
        "created_at": time.time(),
    })


@router.patch("/api/characters/{char_id}")
def vf_update_character(char_id: str, req: UpdateCharacterRequest):
    updated = store.update_character(char_id, req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Character not found")
    return updated


@router.post("/api/characters/{char_id}/retranscribe")
def vf_retranscribe_character(char_id: str):
    char = store.get_character(char_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    fp = Path(char.get("file_path") or "")
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Character audio file missing")
    transcript = svc.transcribe_audio_file(fp)
    updated = store.update_character(char_id, {"ref_text": transcript})
    return {"character": updated, "ref_text": transcript}


@router.delete("/api/characters/{char_id}")
def vf_delete_character(char_id: str):
    if not store.delete_character(char_id):
        raise HTTPException(status_code=404, detail="Character not found")
    return {"deleted": char_id}


# ---------------------------------------------------------------------------
# Clone Studio Profiles
# ---------------------------------------------------------------------------

@router.get("/api/profiles/emotions")
def vf_profile_emotions():
    return {"emotions": svc.EMOTIONS}


@router.get("/api/profiles")
def vf_list_profiles():
    return {"profiles": store.list_profiles()}


@router.post("/api/profiles")
def vf_create_profile(req: ProfileRequest):
    prof_id = f"prof_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    return store.upsert_profile({
        "id": prof_id,
        "name": req.name,
        "description": req.description,
        "clips": [],
        "created_at": time.time(),
    })


@router.patch("/api/profiles/{profile_id}")
def vf_update_profile(profile_id: str, req: ProfileUpdateRequest):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    patch = req.model_dump(exclude_none=True)
    prof.update(patch)
    prof["updated_at"] = time.time()
    return store.upsert_profile(prof)


@router.delete("/api/profiles/{profile_id}")
def vf_delete_profile(profile_id: str):
    if not store.delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"deleted": profile_id}


def _attach_profile_clip(profile_id: str, emotion: str, char: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    clips = [c for c in (prof.get("clips") or []) if isinstance(c, dict) and c.get("emotion") != emotion]
    clip_entry: Dict[str, Any] = {
        "emotion": emotion,
        "character_id": char["id"],
        "url": char.get("url") or "",
        "ref_text": char.get("ref_text") or "",
    }
    if analysis:
        clip_entry["analysis"] = analysis
    clips.append(clip_entry)
    prof["clips"] = clips
    prof["updated_at"] = time.time()
    return store.upsert_profile(prof)


@router.post("/api/profiles/{profile_id}/clips")
async def vf_add_profile_clip(
    profile_id: str,
    emotion: str = Form(...),
    script: str = Form(""),
    file: UploadFile = File(...),
):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    ext = Path(file.filename or "clip.wav").suffix or ".wav"
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}{ext}"
    dst = store.vf_characters_dir() / audio_file
    dst.write_bytes(await file.read())
    ref_text = script or svc.transcribe_audio_file(dst)
    char = store.upsert_character({
        "id": char_id,
        "name": f"{prof['name']} ({emotion})",
        "description": f"{prof['name']} {emotion} reference clip",
        "ref_text": ref_text,
        "audio_file": audio_file,
        "source_model": "profile_clip",
        "created_at": time.time(),
    })
    analysis = svc.analyze_recording(dst) if dst.suffix.lower() == ".wav" else None
    updated = _attach_profile_clip(profile_id, emotion, char, analysis)
    return {"profile": updated, "character": char, "analysis": analysis}


@router.post("/api/profiles/{profile_id}/clips/from-path")
def vf_add_profile_clip_from_path(profile_id: str, req: ProfileClipFromPathRequest):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    src = Path(req.audio_path).expanduser()
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {src}")
    char_id = f"char_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    audio_file = f"{char_id}{src.suffix or '.wav'}"
    dst = store.vf_characters_dir() / audio_file
    shutil.copy2(src, dst)
    ref_text = req.script or svc.transcribe_audio_file(dst)
    char = store.upsert_character({
        "id": char_id,
        "name": f"{prof['name']} ({req.emotion})",
        "description": f"{prof['name']} {req.emotion} reference clip",
        "ref_text": ref_text,
        "audio_file": audio_file,
        "source_model": "profile_clip",
        "created_at": time.time(),
    })
    analysis = svc.analyze_recording(dst) if dst.suffix.lower() == ".wav" else None
    updated = _attach_profile_clip(profile_id, req.emotion, char, analysis)
    return {"profile": updated, "character": char, "analysis": analysis}


@router.post("/api/profiles/{profile_id}/clips/link")
def vf_link_profile_clip(profile_id: str, req: LinkClipRequest):
    char = store.get_character(req.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    updated = _attach_profile_clip(profile_id, req.emotion, char)
    return {"profile": updated}


@router.delete("/api/profiles/{profile_id}/clips/{emotion}")
def vf_delete_profile_clip(profile_id: str, emotion: str):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    prof["clips"] = [c for c in (prof.get("clips") or []) if isinstance(c, dict) and c.get("emotion") != emotion]
    prof["updated_at"] = time.time()
    return {"profile": store.upsert_profile(prof)}


@router.post("/api/profiles/{profile_id}/repair")
def vf_repair_profile(profile_id: str):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    valid = []
    for c in prof.get("clips") or []:
        if isinstance(c, dict) and store.get_character(c.get("character_id") or ""):
            valid.append(c)
    prof["clips"] = valid
    prof["updated_at"] = time.time()
    return {"profile": store.upsert_profile(prof)}


@router.get("/api/profiles/{profile_id}/pick")
def vf_pick_profile_clip(
    profile_id: str,
    emotion: str = Query(""),
    direction: str = Query(""),
    text: str = Query(""),
):
    prof = store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    target = emotion or svc.emotion_from_text(direction, text)
    clip = svc.pick_profile_clip(prof, target)
    return {"emotion": target, "clip": clip}


@router.post("/api/profiles/prompts")
def vf_profile_prompts(req: PromptRequest):
    meta = next((e for e in svc.EMOTIONS if e["id"] == req.emotion), svc.EMOTIONS[0])
    return {
        "emotion": meta["id"],
        "how": meta["how"],
        "prompts": meta["scripts"],
    }


# ---------------------------------------------------------------------------
# Casts & Casting Desk
# ---------------------------------------------------------------------------

@router.get("/api/cast/claude-status")
def vf_cast_claude_status():
    return svc.claude_cli_status()


@router.post("/api/cast/extract")
def vf_cast_extract(req: CastExtractRequest):
    return svc.extract_cast_from_script(req.script)


@router.post("/api/cast/improve-description")
def vf_cast_improve_description(req: CastImproveRequest):
    opt = optimize_character_prompts(req.description or req.name)
    return {
        "name": req.name,
        "description": opt["instruct_qwen3"],
        "maya_description": opt["instruct_maya"],
    }


@router.post("/api/cast/produce")
def vf_cast_produce(req: CastProduceRequest):
    extracted = svc.extract_cast_from_script(req.script)
    cast: Dict[str, Any] = {}
    for ch in extracted["characters"]:
        sp = ch["name"]
        spec = req.voices.get(sp)
        if isinstance(spec, str):
            if spec.startswith("profile:"):
                prof = store.find_profile_by_name(spec.split(":", 1)[1].strip())
                cast[sp] = {"profile_id": prof["id"]} if prof else {"profile": spec.split(":", 1)[1].strip()}
            else:
                existing = store.get_character(spec) or store.find_character_by_name(spec)
                cast[sp] = {"character_id": existing["id"]} if existing else {"instruct": spec}
        elif isinstance(spec, dict):
            cast[sp] = spec
        elif ch.get("suggested_profile_id"):
            cast[sp] = {"profile_id": ch["suggested_profile_id"]}
        elif ch.get("suggested_character_id"):
            cast[sp] = {"character_id": ch["suggested_character_id"]}
        else:
            cast[sp] = {"instruct": f"{sp}, expressive game character"}

    scene_request = {
        "title": req.title,
        "cast": cast,
        "lines": extracted["lines"],
        "default_pause_ms": req.default_pause_ms,
        "temperature": req.temperature,
        "takes_per_line": req.takes_per_line,
        "natural_pacing": req.natural_pacing,
        "context_continuity": req.context_continuity,
        "use_profiles": True,
    }
    if req.dry_run:
        return {"dry_run": True, "scene_request": scene_request, "extracted": extracted}
    scene = svc.render_scene(scene_request)
    return {"dry_run": False, "scene": scene, "scene_request": scene_request}


@router.get("/api/casts")
def vf_list_casts():
    return {"casts": store.list_casts()}


@router.post("/api/casts")
def vf_save_cast(req: SavedCastRequest):
    existing = store.find_cast_by_name(req.name)
    cast_id = existing["id"] if existing else f"cast_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    return store.upsert_cast({
        "id": cast_id,
        "name": req.name,
        "title": req.title or req.name,
        "script": req.script,
        "mapping": req.mapping,
        "lines": req.lines,
        "temperature": req.temperature,
        "updated_at": time.time(),
    })


@router.delete("/api/casts/{cast_id}")
def vf_delete_cast(cast_id: str):
    if not store.delete_cast(cast_id):
        raise HTTPException(status_code=404, detail="Cast not found")
    return {"deleted": cast_id}


@router.post("/api/casts/{cast_id}/render")
def vf_render_saved_cast(cast_id: str):
    cast_rec = store.get_cast(cast_id) or store.find_cast_by_name(cast_id)
    if not cast_rec:
        raise HTTPException(status_code=404, detail="Saved cast not found")
    payload = {
        "title": cast_rec.get("title") or cast_rec.get("name") or "Saved Cast Scene",
        "cast": cast_rec.get("mapping") or {},
        "lines": cast_rec.get("lines") or None,
        "script_text": cast_rec.get("script") or None,
        "temperature": cast_rec.get("temperature") or 0.7,
    }
    return svc.render_scene(payload)


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

@router.get("/api/scenes")
def vf_list_scenes():
    return {"scenes": store.list_scenes()}


@router.delete("/api/scenes/{scene_id}")
def vf_delete_scene(scene_id: str):
    if not store.delete_scene(scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")
    return {"deleted": scene_id}


@router.post("/api/scenes/render")
def vf_render_scene(req: SceneRenderRequest):
    try:
        scene = svc.render_scene(req.model_dump())
        return {**scene, "scene": scene}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/scenes/render/wav")
def vf_render_scene_wav(req: SceneRenderRequest):
    scene = vf_render_scene(req)
    return FileResponse(path=scene["file_path"], media_type="audio/wav", filename=scene["filename"])


@router.post("/api/scenes/batch")
def vf_render_scene_batch(req: BatchSceneRenderRequest):
    results = [vf_render_scene(s) for s in req.scenes]
    return {"scenes": results, "count": len(results)}


@router.post("/api/scenes/stitch")
def vf_stitch_takes(req: StitchTakesRequest):
    try:
        return svc.stitch_takes(req.title, req.take_ids, pause_ms=req.pause_ms)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenes/{scene_id}/reroll-line")
def vf_reroll_scene_line(scene_id: str, req: RerollSceneLineRequest):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    segments = list(scene.get("segments") or [])
    if req.line_index < 0 or req.line_index >= len(segments):
        raise HTTPException(status_code=400, detail="line_index out of range")
    seg = dict(segments[req.line_index])
    take = svc.synthesize_line(
        text=req.text or seg.get("text") or "",
        model_id=req.model_id or seg.get("model_id"),
        instruct=req.instruct or "",
        character_id=seg.get("character_id") or None,
        speed=req.speed or 1.0,
        temperature=req.temperature or 0.7,
        top_p=req.top_p or 0.9,
        repetition_penalty=req.repetition_penalty or 1.1,
        seed=req.seed,
        save_take=True,
    )
    seg.update({
        "text": req.text or seg.get("text") or "",
        "take_id": take["id"],
        "file_path": take["file_path"],
        "url": take["url"],
        "duration_sec": take["duration_sec"],
    })
    if req.pause_after_ms is not None:
        seg["pause_after_ms"] = req.pause_after_ms
    segments[req.line_index] = seg
    wav_items = [
        (Path(s["file_path"]), int(s.get("pause_after_ms") or 350) if i < len(segments) - 1 else 0)
        for i, s in enumerate(segments)
        if s.get("file_path") and Path(s["file_path"]).exists()
    ]
    if wav_items:
        out_path = Path(scene["file_path"])
        duration, spans = svc._stitch_wav_paths(wav_items, out_path)
        for s, (st, en) in zip(segments, spans):
            s["start_sec"] = st
            s["end_sec"] = en
        scene["duration_sec"] = duration
    scene["segments"] = segments
    updated = store.upsert_scene(scene)
    svc.write_scene_sidecars(updated)
    return updated


@router.post("/api/scenes/{scene_id}/use-take")
def vf_use_scene_take(scene_id: str, req: UseTakeRequest):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    take = store.get_take(req.take_id)
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    segments = list(scene.get("segments") or [])
    if req.line_index < 0 or req.line_index >= len(segments):
        raise HTTPException(status_code=400, detail="line_index out of range")
    seg = dict(segments[req.line_index])
    seg.update({
        "take_id": take["id"],
        "file_path": take["file_path"],
        "url": take["url"],
        "duration_sec": take["duration_sec"],
    })
    segments[req.line_index] = seg
    wav_items = [
        (Path(s["file_path"]), int(s.get("pause_after_ms") or 350) if i < len(segments) - 1 else 0)
        for i, s in enumerate(segments)
        if s.get("file_path") and Path(s["file_path"]).exists()
    ]
    if wav_items:
        duration, spans = svc._stitch_wav_paths(wav_items, Path(scene["file_path"]))
        for s, (st, en) in zip(segments, spans):
            s["start_sec"] = st
            s["end_sec"] = en
        scene["duration_sec"] = duration
    scene["segments"] = segments
    updated = store.upsert_scene(scene)
    svc.write_scene_sidecars(updated)
    return updated


@router.post("/api/scenes/{scene_id}/check")
def vf_check_scene(scene_id: str):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return svc.check_scene_with_asr(scene)


@router.get("/api/scenes/{scene_id}/subtitles.srt")
def vf_scene_srt(scene_id: str):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    srt_path, _ = svc.write_scene_sidecars(scene)
    return FileResponse(path=str(srt_path), media_type="text/plain; charset=utf-8", filename=f"{scene_id}.srt")


@router.get("/api/scenes/{scene_id}/manifest.json")
def vf_scene_manifest(scene_id: str):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    _, manifest_path = svc.write_scene_sidecars(scene)
    return FileResponse(path=str(manifest_path), media_type="application/json", filename=f"{scene_id}_manifest.json")


@router.get("/api/scenes/{scene_id}/export.zip")
def vf_scene_export_zip(scene_id: str):
    scene = store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    payload = svc.build_scene_export_zip(scene)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{scene_id}.zip"'},
    )


# ---------------------------------------------------------------------------
# Web UI HTML pages
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui_home():
    return _serve_html("home.html")


@router.get("/cast", response_class=HTMLResponse, include_in_schema=False)
def ui_cast():
    return _serve_html("cast.html")


@router.get("/voices", response_class=HTMLResponse, include_in_schema=False)
def ui_voices():
    return _serve_html("voices.html")


@router.get("/clone", response_class=HTMLResponse, include_in_schema=False)
def ui_clone():
    return _serve_html("clone.html")


@router.get("/studio", response_class=HTMLResponse, include_in_schema=False)
def ui_studio():
    return _serve_html("studio.html")


@router.get("/scenes", response_class=HTMLResponse, include_in_schema=False)
def ui_scenes():
    return _serve_html("scenes.html")


@router.get("/takes", response_class=HTMLResponse, include_in_schema=False)
def ui_history():
    return _serve_html("history.html")


@router.get("/ui/engines", response_class=HTMLResponse, include_in_schema=False)
def ui_engines():
    return _serve_html("engines.html")
