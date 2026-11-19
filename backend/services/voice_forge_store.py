"""SQLite-backed store and asset paths for Voice Forge domain objects.

Stores characters, emotion profiles, saved casts, rendered scenes and single-line
takes in the shared Voice Forge Studio SQLite database (`vf_*` tables), with audio
and sidecar artefacts kept under ``<DATA_DIR>/voice_forge/{characters,scenes,takes}``.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_app_data_dir
from core.db import db_conn, ensure_schema


def vf_data_dir() -> Path:
    """Return the root directory for Voice Forge media artefacts."""
    root = Path(get_app_data_dir()) / "voice_forge"
    root.mkdir(parents=True, exist_ok=True)
    return root


def vf_characters_dir() -> Path:
    d = vf_data_dir() / "characters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vf_scenes_dir() -> Path:
    d = vf_data_dir() / "scenes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vf_takes_dir() -> Path:
    d = vf_data_dir() / "takes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_vf_dirs() -> Dict[str, Path]:
    return {
        "root": vf_data_dir(),
        "characters": vf_characters_dir(),
        "scenes": vf_scenes_dir(),
        "takes": vf_takes_dir(),
    }


def _loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _dumps(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

_CHAR_COLS = {
    "id", "name", "description", "ref_text", "audio_file", "source_model",
    "favorite", "tags", "created_at", "updated_at", "file_path", "url",
}


def _row_to_character(row: Any) -> Dict[str, Any]:
    extra = _loads(row["extra_json"], {})
    audio_file = row["audio_file"] or ""
    out: Dict[str, Any] = dict(extra)
    out.update({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "ref_text": row["ref_text"] or "",
        "audio_file": audio_file,
        "source_model": row["source_model"] or "",
        "favorite": bool(row["favorite"]),
        "tags": _loads(row["tags_json"], []),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    })
    if audio_file:
        out["file_path"] = str(vf_characters_dir() / audio_file)
        out["url"] = f"/audio/characters/{audio_file}"
    else:
        out.setdefault("file_path", "")
        out.setdefault("url", "")
    return out


def list_characters() -> List[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vf_characters ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_character(r) for r in rows]


def get_character(char_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM vf_characters WHERE id = ?", (char_id,)
        ).fetchone()
    return _row_to_character(row) if row else None


def find_character_by_name(name: str) -> Optional[Dict[str, Any]]:
    target = (name or "").strip().lower()
    if not target:
        return None
    for c in list_characters():
        if (c.get("name") or "").strip().lower() == target:
            return c
    return None


def upsert_character(record: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    now = time.time()
    char_id = str(record["id"])
    created_at = float(record.get("created_at") or now)
    updated_at = float(record.get("updated_at") or now)
    audio_file = str(record.get("audio_file") or "")
    if not audio_file and record.get("file_path"):
        audio_file = Path(str(record["file_path"])).name
    tags = record.get("tags") or []
    extra = {k: v for k, v in record.items() if k not in _CHAR_COLS}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO vf_characters (
                id, name, description, ref_text, audio_file, source_model,
                favorite, tags_json, extra_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                ref_text = excluded.ref_text,
                audio_file = excluded.audio_file,
                source_model = excluded.source_model,
                favorite = excluded.favorite,
                tags_json = excluded.tags_json,
                extra_json = excluded.extra_json,
                updated_at = excluded.updated_at
            """,
            (
                char_id,
                str(record.get("name") or ""),
                str(record.get("description") or ""),
                str(record.get("ref_text") or ""),
                audio_file,
                str(record.get("source_model") or ""),
                1 if record.get("favorite") else 0,
                _dumps(list(tags)),
                _dumps(extra),
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    return get_character(char_id) or record


def update_character(char_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_character(char_id)
    if not existing:
        return None
    merged = dict(existing)
    for k, v in patch.items():
        if v is not None:
            merged[k] = v
    merged["id"] = char_id
    merged["updated_at"] = time.time()
    return upsert_character(merged)


def delete_character(char_id: str, delete_file: bool = True) -> bool:
    existing = get_character(char_id)
    if not existing:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM vf_characters WHERE id = ?", (char_id,))
        conn.commit()
    if delete_file and existing.get("audio_file"):
        p = vf_characters_dir() / existing["audio_file"]
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return True


# ---------------------------------------------------------------------------
# Emotion profiles (Clone Studio)
# ---------------------------------------------------------------------------

_PROF_COLS = {"id", "name", "description", "clips", "created_at", "updated_at"}


def _row_to_profile(row: Any) -> Dict[str, Any]:
    extra = _loads(row["extra_json"], {})
    out: Dict[str, Any] = dict(extra)
    out.update({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "clips": _loads(row["clips_json"], {}),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    })
    return out


def list_profiles() -> List[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vf_profiles ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_profile(r) for r in rows]


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM vf_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    return _row_to_profile(row) if row else None


def find_profile_by_name(name: str) -> Optional[Dict[str, Any]]:
    target = (name or "").strip().lower()
    if not target:
        return None
    for p in list_profiles():
        if (p.get("name") or "").strip().lower() == target:
            return p
    return None


def upsert_profile(record: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    now = time.time()
    prof_id = str(record["id"])
    created_at = float(record.get("created_at") or now)
    updated_at = float(record.get("updated_at") or now)
    clips = record.get("clips") or {}
    extra = {k: v for k, v in record.items() if k not in _PROF_COLS}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO vf_profiles (
                id, name, description, clips_json, extra_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                clips_json = excluded.clips_json,
                extra_json = excluded.extra_json,
                updated_at = excluded.updated_at
            """,
            (
                prof_id,
                str(record.get("name") or ""),
                str(record.get("description") or ""),
                _dumps(clips),
                _dumps(extra),
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    return get_profile(prof_id) or record


def delete_profile(profile_id: str) -> bool:
    existing = get_profile(profile_id)
    if not existing:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM vf_profiles WHERE id = ?", (profile_id,))
        conn.commit()
    return True


# ---------------------------------------------------------------------------
# Saved casts
# ---------------------------------------------------------------------------

_CAST_COLS = {
    "id", "name", "title", "script", "mapping", "lines", "temperature",
    "created_at", "updated_at",
}


def _row_to_cast(row: Any) -> Dict[str, Any]:
    extra = _loads(row["extra_json"], {})
    out: Dict[str, Any] = dict(extra)
    out.update({
        "id": row["id"],
        "name": row["name"],
        "title": row["title"] or "",
        "script": row["script"] or "",
        "mapping": _loads(row["mapping_json"], {}),
        "lines": _loads(row["lines_json"], []),
        "temperature": row["temperature"],
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    })
    return out


def list_casts() -> List[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vf_casts ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [_row_to_cast(r) for r in rows]


def get_cast(cast_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM vf_casts WHERE id = ?", (cast_id,)
        ).fetchone()
    return _row_to_cast(row) if row else None


def find_cast_by_name(name: str) -> Optional[Dict[str, Any]]:
    target = (name or "").strip().lower()
    if not target:
        return None
    for c in list_casts():
        if (c.get("name") or "").strip().lower() == target:
            return c
    return None


def upsert_cast(record: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    now = time.time()
    cast_id = str(record["id"])
    created_at = float(record.get("created_at") or now)
    updated_at = float(record.get("updated_at") or now)
    extra = {k: v for k, v in record.items() if k not in _CAST_COLS}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO vf_casts (
                id, name, title, script, mapping_json, lines_json,
                temperature, extra_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                title = excluded.title,
                script = excluded.script,
                mapping_json = excluded.mapping_json,
                lines_json = excluded.lines_json,
                temperature = excluded.temperature,
                extra_json = excluded.extra_json,
                updated_at = excluded.updated_at
            """,
            (
                cast_id,
                str(record.get("name") or ""),
                str(record.get("title") or ""),
                str(record.get("script") or ""),
                _dumps(record.get("mapping") or {}),
                _dumps(record.get("lines") or []),
                record.get("temperature"),
                _dumps(extra),
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    return get_cast(cast_id) or record


def delete_cast(cast_id: str) -> bool:
    existing = get_cast(cast_id)
    if not existing:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM vf_casts WHERE id = ?", (cast_id,))
        conn.commit()
    return True


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

_SCENE_COLS = {
    "id", "title", "filename", "duration_sec", "elapsed_sec", "model_swaps",
    "line_count", "cast", "segments", "created_at", "file_path", "url",
    "srt_url", "manifest_url", "bundle_zip_url",
}


def _row_to_scene(row: Any) -> Dict[str, Any]:
    extra = _loads(row["extra_json"], {})
    scene_id = row["id"]
    filename = row["filename"] or ""
    out: Dict[str, Any] = dict(extra)
    out.update({
        "id": scene_id,
        "title": row["title"] or "",
        "filename": filename,
        "duration_sec": float(row["duration_sec"] or 0),
        "elapsed_sec": float(row["elapsed_sec"] or 0),
        "model_swaps": int(row["model_swaps"] or 0),
        "line_count": int(row["line_count"] or 0),
        "cast": _loads(row["cast_json"], {}),
        "segments": _loads(row["segments_json"], []),
        "created_at": float(row["created_at"] or 0),
        "srt_url": f"/api/scenes/{scene_id}/subtitles.srt",
        "manifest_url": f"/api/scenes/{scene_id}/manifest.json",
        "bundle_zip_url": f"/api/scenes/{scene_id}/export.zip",
    })
    if filename:
        out["file_path"] = str(vf_scenes_dir() / filename)
        out["url"] = f"/audio/scenes/{filename}"
    else:
        out.setdefault("file_path", "")
        out.setdefault("url", "")
    return out


def list_scenes() -> List[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vf_scenes ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_scene(r) for r in rows]


def get_scene(scene_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM vf_scenes WHERE id = ?", (scene_id,)
        ).fetchone()
    return _row_to_scene(row) if row else None


def upsert_scene(record: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    now = time.time()
    scene_id = str(record["id"])
    filename = str(record.get("filename") or "")
    if not filename and record.get("file_path"):
        filename = Path(str(record["file_path"])).name
    extra = {k: v for k, v in record.items() if k not in _SCENE_COLS}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO vf_scenes (
                id, title, filename, duration_sec, elapsed_sec, model_swaps,
                line_count, cast_json, segments_json, extra_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                filename = excluded.filename,
                duration_sec = excluded.duration_sec,
                elapsed_sec = excluded.elapsed_sec,
                model_swaps = excluded.model_swaps,
                line_count = excluded.line_count,
                cast_json = excluded.cast_json,
                segments_json = excluded.segments_json,
                extra_json = excluded.extra_json
            """,
            (
                scene_id,
                str(record.get("title") or ""),
                filename,
                float(record.get("duration_sec") or 0),
                float(record.get("elapsed_sec") or 0),
                int(record.get("model_swaps") or 0),
                int(record.get("line_count") or len(record.get("segments") or [])),
                _dumps(record.get("cast") or {}),
                _dumps(record.get("segments") or []),
                _dumps(extra),
                float(record.get("created_at") or now),
            ),
        )
        conn.commit()
    return get_scene(scene_id) or record


def delete_scene(scene_id: str, delete_files: bool = True) -> bool:
    existing = get_scene(scene_id)
    if not existing:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM vf_scenes WHERE id = ?", (scene_id,))
        conn.commit()
    if delete_files:
        sdir = vf_scenes_dir()
        for name in (
            existing.get("filename") or "",
            f"{scene_id}.srt",
            f"{scene_id}_manifest.json",
        ):
            if name:
                p = sdir / name
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
    return True


# ---------------------------------------------------------------------------
# Takes
# ---------------------------------------------------------------------------

_TAKE_COLS = {
    "id", "text", "model_id", "character_id", "filename", "duration_sec",
    "elapsed_sec", "created_at", "file_path", "url",
}


def _row_to_take(row: Any) -> Dict[str, Any]:
    extra = _loads(row["extra_json"], {})
    filename = row["filename"] or ""
    out: Dict[str, Any] = dict(extra)
    out.update({
        "id": row["id"],
        "text": row["text"] or "",
        "model_id": row["model_id"] or "",
        "character_id": row["character_id"] or "",
        "filename": filename,
        "duration_sec": float(row["duration_sec"] or 0),
        "elapsed_sec": float(row["elapsed_sec"] or 0),
        "created_at": float(row["created_at"] or 0),
    })
    if filename:
        out["file_path"] = str(vf_takes_dir() / filename)
        out["url"] = f"/audio/takes/{filename}"
    else:
        out.setdefault("file_path", "")
        out.setdefault("url", "")
    return out


def list_takes(limit: int = 200) -> List[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vf_takes ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_row_to_take(r) for r in rows]


def get_take(take_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM vf_takes WHERE id = ?", (take_id,)
        ).fetchone()
    return _row_to_take(row) if row else None


def upsert_take(record: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    now = time.time()
    take_id = str(record["id"])
    filename = str(record.get("filename") or "")
    if not filename and record.get("file_path"):
        filename = Path(str(record["file_path"])).name
    extra = {k: v for k, v in record.items() if k not in _TAKE_COLS}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO vf_takes (
                id, text, model_id, character_id, filename, duration_sec,
                elapsed_sec, extra_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text = excluded.text,
                model_id = excluded.model_id,
                character_id = excluded.character_id,
                filename = excluded.filename,
                duration_sec = excluded.duration_sec,
                elapsed_sec = excluded.elapsed_sec,
                extra_json = excluded.extra_json
            """,
            (
                take_id,
                str(record.get("text") or ""),
                str(record.get("model_id") or record.get("model") or ""),
                str(record.get("character_id") or ""),
                filename,
                float(record.get("duration_sec") or 0),
                float(record.get("elapsed_sec") or 0),
                _dumps(extra),
                float(record.get("created_at") or now),
            ),
        )
        conn.commit()
    return get_take(take_id) or record


def delete_take(take_id: str, delete_file: bool = True) -> bool:
    existing = get_take(take_id)
    if not existing:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM vf_takes WHERE id = ?", (take_id,))
        conn.commit()
    if delete_file and existing.get("filename"):
        p = vf_takes_dir() / existing["filename"]
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return True
