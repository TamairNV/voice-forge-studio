# Phase 1: Fork and Strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the VoiceStudio checkout into an API-only "Voice Forge Studio" backend: no desktop, mobile, store, cloud, telemetry, dubbing, dictation or long-form code. It keeps only the game-dev engine set, uses VoxCPM2 as the default engine, and passes its tests.

**Architecture:** Strip leaves-first. Each task deletes one feature area (router, then the services only that area imports, then their tests), removes it from `backend/main.py`'s `_router_modules`, and runs the test suite. New `tests/test_fork_*.py` files pin what must be gone and what must stay. No new features in this phase.

**Tech Stack:** Python 3.11+, FastAPI, uv, pytest (`-n` via xdist), mlx-audio (Mac), torch (Linux/CUDA).

**Spec:** `docs/superpowers/plans/2026-11-19-roadmap.md` (decisions, engine table, phases).

## Global Constraints

- Base: upstream `8f6c11343`, branch `game-dev`, upstream remote named `upstream`.
- Keep the Python package name `omnivoice`, the `OMNIVOICE_*` env var prefix and the `omnivoice_data/` layout. Renaming them is churn with no gain.
- Licence stays AGPL-3.0. Keep `LICENSE` and `LICENSE-NOTICE.md`, and add a modification notice (Task 2).
- The server binds `127.0.0.1` by default. Never document `0.0.0.0`. Remote access (Phase 5) uses the Tailscale IP plus an API key.
- Engine registry after this phase is exactly: `omnivoice` (hidden, non-default), `mlx-audio`, `voxcpm2`, `cosyvoice`, `cosyvoice-gguf`, `indextts2`, `dots-tts`, `audiocpp-dots`, `qwen3-tts`, `gpt-sovits`, `pockettts`.
- Default TTS engine: `mlx-audio` with model `mlx-community/VoxCPM2-8bit` on darwin-arm64, and `voxcpm2` elsewhere. `OMNIVOICE_TTS_BACKEND` still overrides it.
- ASR kept: `mlx-whisper` (large-v3-turbo, tiny), `faster-whisper` (large-v3-turbo, base), `whisperx`, `parakeet-mlx` v3, `nemo-parakeet` v3.
- Tests run with `HF_HUB_OFFLINE=1`, as upstream CI does, so nothing is downloaded.
- Upstream's `CLAUDE.md`/`AGENTS.md` rules (Electron only, release channels, no AI co-author trailers) stop applying once Task 2 replaces those files.

## Review Focus

1. A saved preference naming a removed engine (`tts_backend: "kittentts"`) must fall back to the default, not crash at startup. The test is in Task 7.
2. MCP tools in `backend/mcp_server.py` that call removed routers (dubbing and others) must be gone, not left to fail when called. The test is in Task 5.
3. The backend must import and start on Linux with no `mlx*` packages, and on the Mac with no CUDA. The test is in Task 3, run again in Tasks 8 and 9.
4. Setup and recommendation endpoints (`/setup/recommendations`) must not list models whose engine was removed. The test is in Task 7.
5. A `models.yaml` entry without a `model_licenses.json` record (or the reverse) must fail tests. The upstream consistency test stays, and Task 7 keeps it green.

---

### Task 1: Baseline

**Files:**
- Create: `docs/fork/baseline-tests.txt`, `docs/fork/routes-baseline.txt`

- [ ] **Step 1:** `uv sync` (Linux: CPU or CUDA torch; Mac: arm64 extras).
- [ ] **Step 2:** Run `HF_HUB_OFFLINE=1 uv run --no-sync pytest tests/ -q --tb=no -n 6 -p no:randomly | tail -40 > docs/fork/baseline-tests.txt`, then do the same for `backend/tests/` (append). Expected: a pass/fail summary. Pre-existing failures are recorded, not fixed.
- [ ] **Step 3:** Dump every route with `cd backend && uv run --no-sync python -c "import main; print('\n'.join(sorted({r.path for r in main.app.routes})))"` (after the app's deferred router registration runs; call the module's finalize helper if routes come back empty) into `docs/fork/routes-baseline.txt`.
- [ ] **Step 4:** Commit: `chore(fork): record upstream test and route baseline`.

### Task 2: Fork identity and notices

**Files:**
- Create: `FORK-NOTICE.md`
- Modify: `backend/core/app_config.py` (`PRODUCT_NAME`), `README.md`
- Replace: `CLAUDE.md`, `AGENTS.md`

- [ ] **Step 1: Write the failing test** `tests/test_fork_identity.py`:

```python
def test_product_name():
    from backend.core.app_config import PRODUCT_NAME  # match the repo's import style
    assert PRODUCT_NAME == "Voice Forge Studio"

def test_fork_notice_present():
    text = Path("FORK-NOTICE.md").read_text()
    assert "debpalash/VoiceStudio" in text and "AGPL-3.0" in text and "2026-11-19" in text
```

- [ ] **Step 2:** Run it and expect FAIL.
- [ ] **Step 3:** Set `PRODUCT_NAME`. Write `FORK-NOTICE.md`: it says this is a modified fork of debpalash/VoiceStudio at `8f6c11343`, modified from 2026-11-19 by Tamair, under AGPL-3.0 §5(a), and summarises what was removed. Rewrite `README.md` as a short page covering what it is, the machines, how to run it, and links to the roadmap. Replace `CLAUDE.md` with fork rules (this plan's Global Constraints, `@AGENTS.md`). Make `AGENTS.md` a short agent guide pointing at the roadmap.
- [ ] **Step 4:** Run it and expect PASS.
- [ ] **Step 5:** Commit: `chore(fork): Voice Forge Studio identity and AGPL modification notice`.

### Task 3: Remove desktop, mobile and packaging surfaces

**Files:**
- Delete: `electron/`, `mobile/`, `store/`, `fastlane/`, `snap/`, `native/`, `packaging/`, `notebooks/`, `omnivoice-gallery/`, `flake.nix`, `flake.lock`, `dagger.json`, `greptile.json`, `funding.json`, `SPONSORS.md`, `.coderabbit.yaml`, `bun.lock`, `.agents/` and `skills-lock.json` (upstream agent skills), and every `.github/workflows/*` (Task 8 adds one back).
- Modify: root `package.json`, reduced to `name` and `version` only (it stays the version source for `tests/test_app_version.py`).
- Delete or trim: tests whose subject was deleted (find them with `grep -rlE "electron/|mobile/|fastlane|snap/|store/|ios|android|testflight|packaging" tests backend/tests`). Delete a test file only if everything it tests is gone. Otherwise remove just the affected cases.
- Test: `tests/test_fork_startup.py`

- [ ] **Step 1: Write the failing test** `tests/test_fork_startup.py`:

```python
REMOVED_DIRS = ["electron", "mobile", "store", "fastlane", "snap", "native", "packaging"]

def test_removed_surfaces_gone():
    assert [d for d in REMOVED_DIRS if Path(d).exists()] == []

def test_backend_imports_without_platform_extras():
    # Fresh interpreter: main must import even when mlx (Linux) or CUDA (Mac) is absent.
    r = subprocess.run([sys.executable, "-c", "import main"], cwd="backend",
                       env={**os.environ, "HF_HUB_OFFLINE": "1"}, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
```

- [ ] **Step 2:** Run it and expect `test_removed_surfaces_gone` to FAIL.
- [ ] **Step 3:** Delete the listed paths and the tests that only covered them. Check `backend/main.py` and `backend/core/*` for code that serves the Electron web build (`StaticFiles` mount of a renderer `dist`). If the directory is missing, the mount must be skipped and the server must not fail. `/docs` (Swagger) stays as the only UI in this phase.
- [ ] **Step 4:** Run `HF_HUB_OFFLINE=1 uv run --no-sync pytest tests/ backend/tests/ -q -n 6`. Expected: the new tests PASS, and the only failures are ones already in `baseline-tests.txt`.
- [ ] **Step 5:** Commit: `chore(fork): remove desktop, mobile, store and packaging`.

### Task 4: Remove cloud, Pro, analytics and phone-home

**Files:**
- Delete: `backend/services/cloud_account*`, `backend/services/cloud_sync/`, `backend/api/routers/cloud_sync.py`, `backend/core/analytics.py`, `backend/core/analytics_transport.py`, `backend/core/diagnostic_app_transport.py`, `backend/api/routers/{community,gallery,marketplace,telephony_twilio,calls}.py` and the services only they import, `config/analytics.json`, `config/diagnostics.json`.
- Modify: `backend/main.py` (drop the `importlib.import_module("services.cloud_account")` near line 161, the router imports, and the `_router_modules` entries), the settings router (remove the analytics consent endpoints).
- Test: `tests/test_fork_no_phone_home.py`

- [ ] **Step 1: Write the failing test:**

```python
BANNED_HOSTS = ["voicestudio.sh", "supermetry.com", "posthog", "jsdelivr.net", "twilio.com"]

def test_no_phone_home_hosts_in_backend():
    hits = [(str(p), h) for p in Path("backend").rglob("*.py") for h in BANNED_HOSTS
            if h in p.read_text(errors="ignore")]
    assert hits == []
```

- [ ] **Step 2:** Run it and expect FAIL with a list of hits.
- [ ] **Step 3:** Remove the listed code. For every remaining hit, cut the call site rather than adding the file to an allowlist. Hugging Face, PyPI, download.pytorch.org and GitHub engine-source downloads stay (they're needed for model and engine installs).
- [ ] **Step 4:** Run the full suite as in Task 3 Step 4. Expected: PASS apart from the baseline failures.
- [ ] **Step 5:** Commit: `chore(fork): remove cloud, Pro, analytics and remote galleries`.

### Task 5: Remove dubbing, translation and video

**Files:**
- Delete: `backend/api/routers/{dub_core,dub_generate,dub_export,dub_translate,glossary,batch,sonitranslate}.py` and every service only they import (find them with `grep -rl "services\.<name>"` across the remaining code). Remove NLLB and pyannote usage, and the yt-dlp parts of `media_tools` (keep ffmpeg and ffprobe).
- Modify: `backend/main.py`, `backend/mcp_server.py` (drop tools that use dubbing or translation), `pyproject.toml` (drop dependencies that nothing imports any more; run `uv lock`).
- Test: `tests/test_fork_routes.py`

- [ ] **Step 1: Write the failing test:**

```python
REMOVED_PREFIXES = ["/dub", "/batch", "/glossary", "/sonitranslate", "/translate"]  # confirm exact
# prefixes against docs/fork/routes-baseline.txt and adjust this list once, here.
KEPT = ["/v1/audio/speech", "/docs", "/openapi.json"]

def test_removed_routes_gone(app_routes):        # fixture: paths of the fully started app
    assert [p for p in app_routes if p.startswith(tuple(REMOVED_PREFIXES))] == []

def test_kept_routes_present(app_routes):
    assert all(k in app_routes for k in KEPT)

def test_mcp_tools_only_reference_live_routes():
    # Every tool in mcp_server's tool list must map to a route that still exists.
    ...  # assert set(tool_route_paths) <= set(app_routes)
```

Put the `app_routes` fixture in `tests/conftest.py`. It builds the app the same way as Task 1 Step 3.

- [ ] **Step 2:** Run it and expect FAIL.
- [ ] **Step 3:** Delete the listed code, leaves first. After each deletion run `cd backend && python -c "import main"` until it imports cleanly.
- [ ] **Step 4:** Run the full suite. Expected: PASS apart from the baseline failures.
- [ ] **Step 5:** Commit: `chore(fork): remove dubbing, translation and video pipeline`.

### Task 6: Remove dictation, capture and long-form

**Files:**
- Delete: `backend/api/routers/{dictation,capture,capture_ws,speech_platform,audiobook,stories,longform_jobs}.py`, `backend/speech_client/`, and the services only they import. Remove `sherpa-onnx` ASR, moonshine, funasr and pytorch-whisper ASR backends.
- Modify: `backend/main.py`, `backend/mcp_server.py`, `pyproject.toml` + `uv lock`, `tests/test_fork_routes.py` (add `/dictation`, `/capture`, `/audiobook`, `/stories`, `/longform`, `/speech-platform` to `REMOVED_PREFIXES`, after checking the exact paths against the baseline).

- [ ] **Step 1:** Add the prefixes to the test. Run it and expect FAIL.
- [ ] **Step 2:** Delete the code, leaves first, as in Task 5 Step 3.
- [ ] **Step 3:** Run the full suite. Expected: PASS apart from the baseline failures.
- [ ] **Step 4:** Commit: `chore(fork): remove dictation, capture and long-form`.

### Task 7: Engine set, model catalogue and default engine

**Files:**
- Modify: `backend/services/tts_backend.py` (`_LAZY_REGISTRY` around line 4111, `_REGISTRY` around line 4225, `_INSTALL_HINTS`, and the default in the `prefs.resolve("tts_backend", …, default="omnivoice")` call around line 4903), `backend/config/models.yaml`, `backend/config/model_licenses.json`, the ASR backend registry (whichever module lists `whisperx`/`mlx-whisper`).
- Delete: `backend/engines/{kittentts*,moss_tts_nano_subprocess,supertonic3,confucius4,ming_tts,omnivoice_gguf,omnivoice_subprocess,moss_tts_v15,moss_sfx}`, the in-file backend classes of removed engines (`KittenTTSBackend`, `MossTTSNanoBackend`, `SherpaOnnxBackend`), and their tests and docs in `docs/engines/`.
- Modify: `backend/engines/audiocpp/` (keep `AudioCPPDotsBackend`, remove the registry key `audiocpp` and its Breeze bundle).
- Test: `tests/test_fork_engines.py`

**Interfaces:**
- Produces: `default_tts_backend_id() -> str` in `backend/services/tts_backend.py`. It returns `"mlx-audio"` on darwin-arm64 and `"voxcpm2"` otherwise, and the `prefs.resolve` default uses it. Phase 2 and 3 code calls it.
- Produces: `KEPT_TTS = {...}`, exported from `tests/test_fork_engines.py`. It is the authoritative list for this phase and equals the Global Constraints registry.

- [ ] **Step 1: Write the failing tests:**

```python
KEPT_TTS = {"omnivoice", "mlx-audio", "voxcpm2", "cosyvoice", "cosyvoice-gguf", "indextts2",
            "dots-tts", "audiocpp-dots", "qwen3-tts", "gpt-sovits", "pockettts"}

def test_registry_is_exactly_kept():
    assert {b["id"] for b in list_backends(include_hidden=True)} == KEPT_TTS

def test_omnivoice_hidden():
    assert "omnivoice" not in {b["id"] for b in list_backends()}

@pytest.mark.parametrize("plat,machine,expected", [("darwin", "arm64", "mlx-audio"),
                         ("linux", "x86_64", "voxcpm2"), ("win32", "AMD64", "voxcpm2")])
def test_default_engine(monkeypatch, plat, machine, expected):
    monkeypatch.setattr(sys, "platform", plat); monkeypatch.setattr(platform, "machine", lambda: machine)
    assert default_tts_backend_id() == expected

def test_mlx_default_model_is_voxcpm2():
    assert <mlx-audio default model id> == "mlx-community/VoxCPM2-8bit"  # use whatever setting
    # mlx-audio's backend reads its default model from (find it in MLXAudioBackend)

def test_saved_removed_engine_falls_back(tmp_prefs):   # Review Focus 1
    tmp_prefs.set("tts_backend", "kittentts")
    assert current_tts_backend_id() == default_tts_backend_id()

def test_catalogue_engines_all_kept():                 # Review Focus 4
    for m in load_model_catalog():
        assert set(m["engines"]) <= KEPT_TTS | KEPT_ASR

def test_no_noncommercial_model_is_required():
    lic = {r["id"]: r for r in licence_records()}
    assert not [m for m in load_model_catalog() if m.get("required")
                and lic[m.get("id", m["repo_id"])]["review_status"] == "noncommercial"]
```

`KEPT_ASR = {"mlx-whisper", "faster-whisper", "faster-whisper-isolated", "whisperx", "parakeet-mlx", "nemo-parakeet"}`. `current_tts_backend_id` is whatever existing function resolves the active engine id; reuse it.

- [ ] **Step 2:** Run them and expect FAIL.
- [ ] **Step 3:** Prune the registry, classes, engine packages and hints. Add `default_tts_backend_id()` and wire it into the `prefs.resolve` default. Make the resolver fall back to it when the saved id isn't in `_REGISTRY`. Set the mlx-audio default model to `mlx-community/VoxCPM2-8bit`. In `models.yaml`:
  - Keep: VoxCPM2, VoxCPM2-8bit, CosyVoice 3 and its GGUF, `audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0`, GPT-SoVITS, the mlx-audio Kokoro, CSM, Qwen3 Base and VoiceDesign, Dia and Chatterbox entries, the kept Whisper and Parakeet entries.
  - Delete: every other entry, and the matching `model_licenses.json` records.
  - `required: true` moves off OmniVoice, onto `openbmb/VoxCPM2`, with `curated_on` for darwin-arm64 set on `mlx-community/VoxCPM2-8bit`. If the catalogue can't express a per-platform required model, mark neither required and rely on the default engine.
- [ ] **Step 4:** Run the full suite, including upstream's catalogue and licence consistency tests. Expected: PASS apart from the baseline failures.
- [ ] **Step 5:** Commit: `feat(fork): game-dev engine set, VoxCPM2 default`.

### Task 8: CI and docs

**Files:**
- Create: `.github/workflows/ci.yml`, with one job on `ubuntu-latest`: `uv sync`, then `HF_HUB_OFFLINE=1 uv run --no-sync pytest tests/ -q -n 4` and `pytest backend/tests/ -q`.
- Delete: docs for removed features (`docs/electron-*`, dubbing, dictation, mobile, release, store, ROCm, Intel Mac, analytics and privacy docs that describe removed telemetry, `docs/readme/` translations, `docs/media/electron/`), and engine docs for removed engines.
- Modify: `docs/` index or README links, so no link points at a deleted file.
- Test: `tests/test_fork_docs_links.py`

- [ ] **Step 1: Write the failing test:** every relative Markdown link in `README.md` and `docs/**/*.md` resolves to an existing file.
- [ ] **Step 2:** Run it and expect FAIL.
- [ ] **Step 3:** Delete and fix docs, and add the workflow.
- [ ] **Step 4:** Run the full suite. Expected: PASS apart from the baseline failures. Then run `wc -l docs/fork/baseline-tests.txt` and record in the commit message how many baseline failures disappeared along with their code.
- [ ] **Step 5:** Commit: `chore(fork): slim CI and docs`.

### Task 9: Smoke test on the Mac (M4 Pro)

Run on the Mac, not the server: it's the only machine with MLX.

- [ ] **Step 1:** `git clone` the fork, `uv sync`, then `uv run uvicorn backend.main:app --host 127.0.0.1 --port 3900`. Expected: the server starts and the log shows the default TTS backend `mlx-audio`.
- [ ] **Step 2:** Run the following. Expected: HTTP 200, and `afinfo /tmp/vf.wav` shows audio of at least 1 s. The first run downloads about 3.3 GB.

  ```
  curl -s -o /tmp/vf.wav -w '%{http_code}\n' http://127.0.0.1:3900/v1/audio/speech \
    -H 'content-type: application/json' \
    -d '{"model":"voxcpm2","input":"Keep your coin, traveller.","voice":"<a voice id from GET /v1/audio/voices or the profiles API>"}'
  ```

  Adjust the body to the schema in `backend/api/routers/openai_compat.py`.
- [ ] **Step 3:** Check `GET /openapi.json`: it lists no removed prefixes. Check that the MCP endpoint `/mcp` answers a tools list.
- [ ] **Step 4:** Note the results (load time, real-time factor, peak memory from Activity Monitor) in `docs/fork/smoke-mac.md`, then commit: `docs(fork): Mac smoke test results`.
