# Mac M4 Pro Smoke Test (Phase 1, Task 30)

- **Date:** 2026-11-19
- **Machine:** Apple M4 Pro, 24 GB unified memory (`darwin-arm64`)
- **Commit:** `9c5e2282c` (`game-dev`)
- **Python / MLX:** Python 3.11.15, `mlx==0.32.4`, `mlx-audio==0.5.0`
- **Model:** `mlx-community/VoxCPM2-8bit` (pre-fetched into Hugging Face cache)

## Checks

1. **Server startup:** `uv run --no-sync uvicorn backend.main:app --host 127.0.0.1 --port 3900`
   started cleanly, mounted `/mcp`, and skipped native TTS preload because `mlx-audio` is the
   selected TTS engine.
2. **Voices (`GET /v1/audio/voices`):** returned 200 OK with 13 OpenAI voice aliases plus
   `demo0001` (`Demo Voice`).
3. **Speech render (`POST /v1/audio/speech` with `model: "mlx-audio"`, `voice: "demo0001"`):**
   - Cold render (load + synthesis): `14.75 s`
   - Warm render (synthesis only): `2.28 s`
   - Estimated model load time: `~12.5 s`
   - Output (`afinfo /tmp/vf.wav`): 1 ch, 24000 Hz, Int16, `1.60 s` (`76852` bytes)
   - Warm real-time factor (RTF): `1.43x` (`2.28 s` wall / `1.60 s` audio)
   - Peak memory (`footprint`): `9017 MB` `phys_footprint_peak` (`8924 MB` steady, `715728 KB` RSS)
   - Note: passing `"model": "voxcpm2"` directly routes to the PyTorch `voxcpm2` backend; on
     `darwin-arm64`, OpenAI-compat callers should pass `"model": "mlx-audio"` (or `"tts-1"`).
4. **OpenAPI routes (`GET /openapi.json`):** `179` paths total; `0` paths under `/dub`, `/batch`,
   `/audiobook`, `/dictation`, `/calls`, `/gallery`, or `/marketplace`.
5. **MCP (`/mcp`):** Streamable HTTP session listed `9` tools (`generate_speech`, `list_voices`,
   `list_personalities`, `list_languages`, `transcribe`, `check_health`, `clone_voice`,
   `describe_voice`, `design_voice`).
