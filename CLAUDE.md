# Voice Forge Studio: rules for agents

- Read AGENTS.md and the roadmap before changing code.
- The server binds 127.0.0.1 by default. Remote access uses the Tailscale address plus an API key.
- Keep the Python package name `omnivoice`, the `OMNIVOICE_*` env prefix and `omnivoice_data/`.
- Licence stays AGPL-3.0. Keep LICENSE, LICENSE-NOTICE.md and FORK-NOTICE.md.
- Run tests offline: prefix with `HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test`.
- Comments and docs: British English, ASCII only, wrapped at 100 columns.
- Never delete files under backend/migrations/.
- Conventional commit messages. No AI co-author trailers.

@AGENTS.md
