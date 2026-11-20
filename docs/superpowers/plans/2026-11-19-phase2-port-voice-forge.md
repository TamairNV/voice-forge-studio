# Phase 2: Port Voice Forge

Port Voice Forge (`~/voice_forge`) onto the Phase 1 Voice Forge Studio backend (`game-dev` branch).

## Goals

1. Store characters, emotion profiles, casts, scenes and takes in the backend's SQLite database
   (via `core/db.py` and an additive Alembic migration `0019_voice_forge_tables.py`).
2. Port the Maya-1 3.3B MLX engine (`nhe-ai/maya1-mlx-8Bit`) as a first-class `TTSBackend` with
   catalogue and licence entries.
3. Serve Voice Forge's `static/` HTML/CSS/JS pages as the web UI (`/`, `/cast`, `/voices`,
   `/clone`, `/studio`, `/scenes`, `/history`, `/engines`) and keep all Voice Forge `/api/*`
   endpoint paths so `voiceforge_mcp.py` and existing agents continue to work.
4. Provide an idempotent importer for `~/voice_forge/data/` (JSON records and WAV/SRT/manifest
   assets) and import the existing library.

## Route Collision Note

`POST /v1/audio/speech` is already provided by `backend/api/routers/openai_compat.py` and stays
there. All other 60 routes in `voice_forge/server.py` live under `/api/*` or HTML page paths and
have zero collisions with existing Voice Forge Studio routes.

## Tasks

1. **Database schema and store**
   - Add `vf_characters`, `vf_profiles`, `vf_casts`, `vf_scenes`, `vf_takes` to `_BASE_SCHEMA` in
     `backend/core/db.py` and migration `backend/migrations/versions/0019_voice_forge_tables.py`.
   - Create `backend/services/voice_forge_store.py` for CRUD and asset path management under
     `DATA_DIR / "voice_forge"`.
   - Test with `tests/test_fork_voice_forge_store.py`.

2. **Port Maya-1 engine**
   - Create `backend/services/maya1_backend.py` containing `Maya1MLXRunner`, `Maya1Backend`,
     `MAYA1_EMOTION_TAGS`, `MAYA1_TAG_ALIASES`, prompt compiler, tag sanitizer, and studio audio
     helpers (`normalize_studio_loudness`, `apply_studio_pacing`, `analyze_voice_acoustics`).
   - Register `Maya1Backend` (`id = "maya1"`) in `backend/services/tts_backend.py`.
   - Add `nhe-ai/maya1-mlx-8Bit` to `backend/config/models.yaml` and
     `backend/config/model_licenses.json`, and regenerate `docs/licensing/model-license-data.json`.
   - Update `tests/test_fork_engines.py` for the added `maya1` engine and add
     `tests/test_fork_maya1.py`.

3. **Voice Forge domain services**
   - Create `backend/services/voice_forge_service.py` implementing emotion slots and profile clip
     picking, script parsing (with optional `claude` CLI fallback), casting (`cast_produce`),
     line synthesis mapped to `tts_backend` engines, scene stitching, SRT/manifest/ZIP export,
     and Whisper scene verification.

4. **Voice Forge API router and static UI**
   - Copy `voice_forge/static/*` and `LLM_PROMPT_GUIDE.md` into `backend/static/voice_forge/`.
   - Create `backend/api/routers/voice_forge.py` exposing all Voice Forge `/api/*` endpoints and
     HTML page routes, plus mounts for `/static` and `/audio/{characters,scenes,takes}`.
   - Wire into `backend/main.py` (`_phase_a_build_inner` and `_phase_a_finalize`).
   - Update `tests/fixtures/api_routes.txt` and add `tests/test_fork_voice_forge_api.py`.

5. **Data importer**
   - Create `scripts/import_voice_forge_data.py` to import `characters.json`, `profiles.json`,
     `casts.json`, `scenes.json`, `takes.json` and audio files idempotently.
   - Test with `tests/test_fork_voice_forge_import.py`.
   - Run the importer against `/Users/tamair/voice_forge/data/`.

6. **Verification**
   - Run offline fork guard suite (`HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test uv run --no-sync pytest
     tests/test_fork_*.py`), licence checks, and live HTTP smoke checks against the UI and
     imported data.
