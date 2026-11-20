# VoiceStudio documentation

## Use the app

| Need | Guide |
| --- | --- |
| Install and troubleshoot | [Platform downloads](../README.md) · [Troubleshooting](install/troubleshooting.md) · Upgrade from Tauri |
| Phone apps | [iOS and Android](mobile.md) |
| Models and hardware | [Engine guides](engines/README.md) · [Model downloads](downloading-models.md) |
| Speech and cloning | [Voice design](voice-design.md) · [Expressive speech](expressive-speech.md) · [Audio quality](audio-quality.md) |
| Dubbing | Multi-speaker guide · Translation · Exports |
| Stories and audiobooks | Longform guide · Projects |
| Voices and sharing | Gallery · [Persona format](persona-format.md) · [Network sharing](sharing.md) |
| Dictation and transcription | [Dictation](features/dictation.md) · Transcriptions |
| Automation | [Local API](speech-platform.md) · [MCP](mcp.md) · Workflows and calls |

## Develop and maintain

| Need | Reference |
| --- | --- |
| Contribute | [Contributing](../.github/CONTRIBUTING.md) · Electron development |
| Repository layout | [Project structure](STRUCTURE.md) |
| Shipping capabilities | [Feature catalog](feature-catalog.md) · Electron parity |
| Planned work | [Live roadmap](ROADMAP.md) |
| Release and distribution | Release checklist · Store publishing |
| Model licensing | [Inventory](licensing/model-inventory.md) · [Review workflow](licensing/model-review-workflow.md) |
| Designs and decisions | [Design references](specs/README.md) · [Architecture decisions](adr/) |

## Documentation maintenance

Keep current behavior in the topic guide and update it in the same PR as the
implementation. Link to that guide rather than keeping a second status report.
The live issue tracker owns pending work; dated plans describe their original
snapshot, not current feature availability or repository policy.

Retain migration guidance, format/security contracts, licensing evidence and
useful investigation results. Remove superseded implementation checklists after
checking incoming references; git history keeps the original text. For example:

```sh
git log --all -- docs/maintenance-pages-modularization.md
git show <commit>:docs/maintenance-pages-modularization.md
```

Validate relative links with:

```sh
uv run pytest -q tests/test_docs_links.py
```
