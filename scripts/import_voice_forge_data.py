#!/usr/bin/env python3
"""Import Voice Forge JSON records and audio assets into Voice Forge Studio.

Idempotent: safe to re-run. Copies audio files into ``<DATA_DIR>/voice_forge/``
(skipping identical existing files) and upserts characters, emotion profiles,
casts, scenes and takes into the SQLite ``vf_*`` tables.

Usage:
    uv run --no-sync python scripts/import_voice_forge_data.py --source ~/voice_forge/data
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import voice_forge_store as store  # noqa: E402


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [v for v in raw.values() if isinstance(v, dict)]
    return []


def _copy_if_needed(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_dir_files(src_dir: Path, dst_dir: Path) -> int:
    if not src_dir.exists() or not src_dir.is_dir():
        return 0
    copied = 0
    for item in src_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            if _copy_if_needed(item, dst_dir / item.name):
                copied += 1
    return copied


def import_voice_forge_data(source_dir: Path, copy_media: bool = True) -> Dict[str, int]:
    """Import all Voice Forge JSON tables and audio artefacts from ``source_dir``."""
    src = Path(source_dir).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Voice Forge data directory not found: {src}")

    dirs = store.ensure_vf_dirs()
    counts = {
        "characters": 0,
        "profiles": 0,
        "casts": 0,
        "scenes": 0,
        "takes": 0,
        "files_copied": 0,
    }

    if copy_media:
        counts["files_copied"] += _copy_dir_files(src / "characters", dirs["characters"])
        counts["files_copied"] += _copy_dir_files(src / "scenes", dirs["scenes"])
        counts["files_copied"] += _copy_dir_files(src / "takes", dirs["takes"])

    # Characters
    for rec in _load_json_list(src / "characters.json"):
        if not rec.get("id"):
            continue
        item = dict(rec)
        audio_file = item.get("audio_file") or (
            Path(str(item["file_path"])).name if item.get("file_path") else ""
        )
        if audio_file:
            item["audio_file"] = audio_file
            item["file_path"] = str(dirs["characters"] / audio_file)
            item["url"] = f"/audio/characters/{audio_file}"
        store.upsert_character(item)
        counts["characters"] += 1

    # Emotion profiles
    for rec in _load_json_list(src / "profiles.json"):
        if not rec.get("id"):
            continue
        store.upsert_profile(dict(rec))
        counts["profiles"] += 1

    # Saved casts
    for rec in _load_json_list(src / "casts.json"):
        if not rec.get("id"):
            continue
        store.upsert_cast(dict(rec))
        counts["casts"] += 1

    # Takes
    for rec in _load_json_list(src / "takes.json"):
        if not rec.get("id"):
            continue
        item = dict(rec)
        metrics = item.get("metrics") or {}
        if "duration_sec" not in item and "duration_sec" in metrics:
            item["duration_sec"] = metrics["duration_sec"]
        if "elapsed_sec" not in item and "elapsed_sec" in metrics:
            item["elapsed_sec"] = metrics["elapsed_sec"]
        filename = item.get("filename") or (
            Path(str(item["file_path"])).name if item.get("file_path") else ""
        )
        if filename:
            item["filename"] = filename
            item["file_path"] = str(dirs["takes"] / filename)
            item["url"] = f"/audio/takes/{filename}"
        store.upsert_take(item)
        counts["takes"] += 1

    # Scenes (rewrite segment audio paths to new vf_takes_dir)
    for rec in _load_json_list(src / "scenes.json"):
        if not rec.get("id"):
            continue
        item = dict(rec)
        filename = item.get("filename") or (
            Path(str(item["file_path"])).name if item.get("file_path") else ""
        )
        if filename:
            item["filename"] = filename
            item["file_path"] = str(dirs["scenes"] / filename)
            item["url"] = f"/audio/scenes/{filename}"
        rewritten_segs: List[Dict[str, Any]] = []
        for seg in item.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            s = dict(seg)
            for key in ("file_path", "take_path"):
                val = s.get(key)
                if val:
                    fname = Path(str(val)).name
                    s[key] = str(dirs["takes"] / fname)
            if not s.get("take_url") and s.get("url"):
                s["take_url"] = s["url"]
            rewritten_segs.append(s)
        item["segments"] = rewritten_segs
        store.upsert_scene(item)
        counts["scenes"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Voice Forge data into Voice Forge Studio.")
    parser.add_argument(
        "--source",
        default=str(Path.home() / "voice_forge" / "data"),
        help="Path to the legacy voice_forge/data directory.",
    )
    parser.add_argument(
        "--no-copy-media",
        action="store_true",
        help="Import SQLite records only without copying WAV/SRT/manifest files.",
    )
    args = parser.parse_args()
    counts = import_voice_forge_data(Path(args.source), copy_media=not args.no_copy_media)
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
