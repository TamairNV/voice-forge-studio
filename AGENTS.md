# Agent guide

## Layout

- backend/main.py: FastAPI app; routers are registered in `_phase_a_build` and `_phase_a_finalize`.
- backend/api/routers/: one file per API area.
- backend/services/: engine adapters (tts_backend.py, asr_backend.py) and feature logic.
- backend/engines/: engines that run in their own process or venv.
- backend/config/models.yaml and model_licenses.json: model catalogue and licence records.
- backend/mcp_server.py: MCP tools, mounted at /mcp.
- tests/ and backend/tests/: pytest suites. tests/fixtures/api_routes.txt is the route snapshot.

## Plans

- docs/superpowers/plans/2026-11-19-roadmap.md: decisions, engine table, phases.
- docs/superpowers/plans/: one plan file per phase.
- docs/fork/: baselines and the leftovers list.

## Commands

- Route snapshot: `HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test uv run --no-sync python scripts/dump_api_routes.py`
- Tests: see README.md.
