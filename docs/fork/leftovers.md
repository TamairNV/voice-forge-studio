# Fork leftovers

Things Phase 1 left in place on purpose. Phase 7 works through this list.
One line each: `- <path or name>: <why it stays> (Task N)`.

- backend/engines/omnivoice_gguf/: GPU probe helpers used by gpu_sandbox, health_device, settings_store (Task 21)
- backend/engines/omnivoice_subprocess/: OmniVoice on Apple Silicon runs through it (Task 21)
- diarisation (pyannote, Sortformer): /transcribe speaker hints and model_manager use it (Task 17)
- services/translation_engines.py, services/translation_apis.py: imported by core/prefs.py, system router, performance modules (Task 14)
- config/diagnostics.json: local validation schema read by core/diagnostic_reports.py; contains no upload hosts or tokens (Task 8)
