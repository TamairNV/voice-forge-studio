# Voice Forge Studio

Game-dialogue voice pipeline for Unity. A modified fork of VoiceStudio: see FORK-NOTICE.md.
API only: the backend serves an OpenAI-compatible speech API, an MCP server at /mcp and
Swagger docs at /docs.

## Machines

- Mac M4 Pro, 24 GB: main studio, MLX/Metal. Default engine: VoxCPM2 8-bit via mlx-audio.
- Windows/Linux PC with RTX 3070 8 GB: CUDA render worker (later phase).

## Run

    uv sync
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 3900

Then open http://127.0.0.1:3900/docs.

## Test

    HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test uv run --no-sync pytest tests/ -q -n 6
    HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test uv run --no-sync pytest backend/tests/ -q

## Plans

- Roadmap: docs/superpowers/plans/2026-11-19-roadmap.md
- Phase 1: docs/superpowers/plans/2026-11-19-phase1-fork-and-strip.md

## Licence

AGPL-3.0. See LICENSE, LICENSE-NOTICE.md and FORK-NOTICE.md.
