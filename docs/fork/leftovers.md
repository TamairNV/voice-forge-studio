# Fork leftovers

Things Phase 1 left in place on purpose. Phase 7 works through this list.
One line each: `- <path or name>: <why it stays> (Task N)`.

- backend/engines/omnivoice_gguf/: GPU probe helpers used by gpu_sandbox, health_device, settings_store (Task 21)
- backend/engines/omnivoice_subprocess/: OmniVoice on Apple Silicon runs through it (Task 21)
- diarisation (pyannote, Sortformer): /transcribe speaker hints and model_manager use it (Task 17)
- services/translation_engines.py, services/translation_apis.py: imported by core/prefs.py, system router, performance modules (Task 14)
- config/diagnostics.json: local validation schema read by core/diagnostic_reports.py; contains no upload hosts or tokens (Task 8)
- backend/core/db.py (cloud_sync tables): kept to avoid a schema migration; migrations 0014 and 0015 stay (Task 9)
- gallery tables in SQLite: stay in the database to avoid a schema migration (Task 10)
- backend/services/dub_qc.py: services/pronunciation.py imports _NO_SPACE_SCRIPT from it (Task 15)
- backend/core/failure.py, backend/core/url_safety.py: yt-dlp error text and guard helpers kept out of scope for Phase 1 (Task 16)
