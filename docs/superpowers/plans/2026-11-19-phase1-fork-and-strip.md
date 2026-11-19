# Phase 1: Fork and Strip - Detailed Agent Plan (v3)

> **For agentic workers:** Use superpowers:subagent-driven-development (one fresh agent per task and one fresh reviewer per task) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Read sections 0 to 4 of this file, then only your own task. Do not start the next task.

**Goal:** Turn the VoiceStudio checkout into an API-only "Voice Forge Studio" backend with the game-dev engine set, VoxCPM2 as the default engine, and a test suite that is no worse than upstream.

**Spec:** `docs/superpowers/plans/2026-11-19-roadmap.md`.
**Base:** upstream `debpalash/VoiceStudio` at `8f6c11343`, branch `game-dev`, remote `upstream`.
**Tech stack:** Python 3.11+, FastAPI, SQLite, uv, pytest (+ xdist), mlx-audio (Mac), torch (Linux/CUDA).

Every file path, line number, route and test file in this plan was taken from upstream `8f6c11343` on 2026-11-19. Line numbers drift after earlier edits to the same file: when a number looks wrong, search for the quoted text instead and carry on. Never guess.

## 0. How to read a task

Each task has the same parts:

- **Why:** one line, so you know what "done" means.
- **Delete:** exact paths. Delete all of them, nothing else.
- **Edit:** exact file, the text to find, and what to do with it.
- **Routes that must disappear:** the exact lines that must vanish from `tests/fixtures/api_routes.txt`. No other line may change.
- **Tests to delete:** test files whose whole subject is gone. Delete them without reading them.
- **Tests to check:** test files that import something you removed but also test things that stay. Open each one, delete only the test functions (and now-unused imports or fixtures) that fail because of your removal, and keep the rest.
- **Keep:** things that look removable but must stay. Do not touch them.
- **Expected result:** what the commands should print when you are done.

## 1. Rules for agents

1. Do only your task. If a step needs a change not named in your task, stop and report.
2. Stage exact paths only. Never `git add -A` or `git add .`. For a deleted directory use `git add -u <dir>`.
3. Never edit `docs/fork/baseline-tests.txt`, `docs/fork/orphans-baseline.txt` or the roadmap after Task 2. Append to `docs/fork/leftovers.md` (see rule 11) instead.
4. Never weaken a test to make it pass: no skip, xfail, `pytest.importorskip`, loosened asserts or try/except around asserts, unless your task says so.
5. A failure listed in `docs/fork/baseline-tests.txt` is not yours. Any other failure is yours.
6. Stop and report (do not improvise) when:
   - a route disappears that your task does not list, or any route is added;
   - an import error points into a file your task does not list under Delete or Edit;
   - you would delete a test file that is in neither of your test lists;
   - the full suite has a new failure you cannot trace to your own change within 3 attempts.
7. Never delete anything under `backend/migrations/`. Old migrations stay so existing databases upgrade.
8. Run tests offline. Every pytest and import command in this plan starts with `HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test`. This plan writes that as `$T`; run `export T="HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test"` once per shell and use `env $T ...`.
9. Comments and docs: British English, ASCII only (no em dashes, arrows, curly quotes, emoji). Code identifiers keep their existing spelling.
10. Commit messages: exactly the message your task gives. No AI co-author trailers.
11. If you leave something in place on purpose because removing it is out of scope (for example a module still imported by kept code), append one line to `docs/fork/leftovers.md`: `- <path or name>: <why it stays> (Task N)`. Phase 7 uses this list.
12. Finish with a report of at most 15 lines: what changed, modules touched, test summary versus baseline, anything added to leftovers.

## 2. Standard commands

Shorthand used in every task. Run them from the repo root.

- **IMPORT** (does the app still import and register every router): `env $T uv run --no-sync python scripts/dump_api_routes.py --print > /tmp/routes.txt && echo IMPORT-OK` Expected: `IMPORT-OK`. On failure the traceback names the file to fix.
- **ORPHANS** (modules nothing imports any more): `uv run --no-sync python scripts/fork/triage.py orphans` Expected after your task: only modules your task lists under Delete, or nothing.
- **COLLECT** (test files that no longer import): `env $T uv run --no-sync python scripts/fork/triage.py collect` Expected after your task: no output.
- **SNAPSHOT** (regenerate the route list and review the diff): `env $T uv run --no-sync python scripts/dump_api_routes.py && git diff --stat tests/fixtures/api_routes.txt && git diff tests/fixtures/api_routes.txt | grep '^[-+][A-Z]'` Expected: only `-` lines, and exactly the routes your task lists.
- **SUITE** (full tests): `env $T uv run --no-sync pytest tests/ -q -n 6 -p no:randomly --tb=line -rf 2>&1 | tail -60` then `env $T uv run --no-sync pytest backend/tests/ -q --tb=line -rf 2>&1 | tail -30`. Expected: every FAILED line also appears in `docs/fork/baseline-tests.txt`.
- **BASEDIFF** (new failures only): `env $T uv run --no-sync pytest tests/ backend/tests/ -q -n 6 -p no:randomly --tb=no -rf 2>/dev/null | grep '^FAILED' | sort > /tmp/now.txt; comm -13 <(grep '^FAILED' docs/fork/baseline-tests.txt | sort) /tmp/now.txt` Expected: no output.

## 3. Removal recipe (Tasks 8 to 19)

- [ ] R1 Delete every path under Delete.
- [ ] R2 Make every change under Edit.
- [ ] R3 Run IMPORT. Fix only files listed in your task. Repeat until `IMPORT-OK`.
- [ ] R4 Run ORPHANS. For each module printed: if your task lists it under Delete, delete it. If not, check `git grep -n "<last part of the module name>" -- backend` and, if every hit is inside code you already deleted, delete it and add it to your report; otherwise leave it and add it to `docs/fork/leftovers.md`. Repeat R3 and R4 until ORPHANS prints nothing new.
- [ ] R5 Delete every file under Tests to delete. Then run COLLECT. Every file it prints must be under Tests to check; handle those as section 0 says. Repeat until COLLECT prints nothing.
- [ ] R6 Run SNAPSHOT. Compare with Routes that must disappear. Any difference: stop (rule 6).
- [ ] R7 Open `tests/test_api_route_inventory.py`. In the `_CRITICAL` list (around line 48), delete any entry your task lists under Routes that must disappear. Never delete an entry that Task 3 added (they are marked `# fork: MCP`).
- [ ] R8 Run BASEDIFF. Fix any new failure caused by your change. Repeat until no output.
- [ ] R9 `git add` the exact paths, then commit with the task's message.

## 4. Global constraints (every task)

- Keep the Python package name `omnivoice`, the `OMNIVOICE_*` env prefix and `omnivoice_data/`.
- Licence stays AGPL-3.0. Keep `LICENSE` and `LICENSE-NOTICE.md`.
- Bind `127.0.0.1` by default. Never write `0.0.0.0` in docs or defaults.
- TTS registry after Phase 1, exactly: `omnivoice` (hidden, non-default), `mlx-audio`, `voxcpm2`, `cosyvoice`, `cosyvoice-gguf`, `indextts2`, `dots-tts`, `audiocpp-dots`, `moss-tts-v15`, `qwen3-tts`, `gpt-sovits`, `pockettts`.
- ASR registry after Phase 1, exactly: `mlx-whisper`, `faster-whisper`, `faster-whisper-isolated`, `whisperx`, `parakeet-mlx`, `nemo-parakeet`.
- Default TTS: `mlx-audio` with model key `voxcpm2` on `darwin-arm64`, `voxcpm2` elsewhere. `OMNIVOICE_TTS_BACKEND` still overrides.
- Downloads from Hugging Face, PyPI, `download.pytorch.org` and GitHub engine sources stay.
- Routes MCP needs, which must exist after every task: `POST /generate`, `GET /profiles`, `POST /profiles`, `GET /personalities`, `POST /transcribe`, `GET /health`, `GET /history`, `POST /design/describe`, `POST /v1/audio/speech`.

### Decisions already made (do not revisit; Tamair can override)

- D1. ASR drops `openai-compat-asr` (remote service), `whisper-cpp`, `pytorch-whisper`, `moonshine`, `funasr`, `sherpa-onnx-asr`.
- D2. `backend/api/routers/capture.py` (`POST /transcribe`) stays: the MCP transcribe tool uses it.
- D3. `cli/` and `skills/` are deleted; the API and MCP replace them.
- D4. The generic job routes (`/jobs`, `/tasks`) live in `dub_export.py` today. Task 13 moves them to a new `api/routers/jobs.py` before dubbing is removed, because Phase 3's queue needs them.
- D5. Diarisation (pyannote, Sortformer) stays in Phase 1. `/transcribe` speaker hints and `services/model_manager.py` depend on it. Phase 7 removes it.
- D6. Translation service modules (`services/translation_engines.py`, `translation_apis.py`) stay because `core/prefs.py`, `api/routers/system.py` and the performance modules import them. Only the translation routes go (Task 14).
- D7. `engines/omnivoice_gguf/` and `engines/omnivoice_subprocess/` packages stay. Other kept code imports helpers from them (GPU probes; OmniVoice on Apple Silicon runs through `OmniVoiceMPSSubprocessBackend`). Only their registry keys and their own routes go.
- D8. `services/loudness.py` and `services/longform_render.py` stay. They hold an ffmpeg two-pass loudnorm implementation that Phase 4 reuses for -23 LUFS export.
- D9. A model catalogue entry is removed only if `scripts/check_model_licenses.py` still passes without it. Entries that kept code hard-codes stay and go into leftovers (Task 25).

### Review focus

- A saved `tts_backend` naming a removed engine (`"kittentts"`) falls back to the platform default. Test in Task 22.
- Every route the MCP tools call still exists after every task. Test in Task 3; `_CRITICAL` guards it.
- The backend imports on Linux without `mlx*` and on the Mac without CUDA. Test in Task 6; CI in Task 27 runs it on Linux; Task 30 covers the Mac.
- `GET /setup/recommendations` lists no model whose engine was removed. Test in Task 26.
- `models.yaml` and `model_licenses.json` stay in step. Upstream `tests/test_model_licenses.py` stays green after Task 25.

### Task map

| # | Task | Kind | Depends on |
|---|---|---|---|
| 1 | Baseline | setup | - |
| 2 | Triage helper and leftovers file | tooling | 1 |
| 3 | Pin MCP routes | test | 2 |
| 4 | Fork identity and notice | small change | 3 |
| 5 | README, CLAUDE.md, AGENTS.md | docs | 4 |
| 6 | Remove desktop and mobile apps | removal | 5 |
| 7 | Remove store, packaging, release tooling | removal | 6 |
| 8 | Remove analytics and diagnostics upload | removal | 7 |
| 9 | Remove cloud account and sync | removal | 8 |
| 10 | Remove community, gallery, marketplace, project bundles | removal | 9 |
| 11 | Remove telephony and calls | removal | 10 |
| 12 | No phone-home hosts | test + fixes | 11 |
| 13 | Move job routes to jobs.py | refactor | 12 |
| 14 | Remove batch, glossary, SoniTranslate, translation routes | removal | 13 |
| 15 | Remove dubbing | removal | 14 |
| 16 | Remove yt-dlp from media tools | removal | 15 |
| 17 | Remove dictation and live capture | removal | 16 |
| 18 | Remove audiobook, stories, long-form | removal | 17 |
| 19 | Remove sound effects | removal | 18 |
| 20 | Drop unused dependencies | cleanup | 19 |
| 21 | Prune TTS registry | engine | 20 |
| 22 | Hide OmniVoice, platform default, safe fallback | engine | 21 |
| 23 | mlx-audio defaults to VoxCPM2 | engine | 22 |
| 24 | Prune ASR registry | engine | 23 |
| 25 | Model catalogue and licence records | catalogue | 24 |
| 26 | Recommendations list only kept models | test | 25 |
| 27 | CI workflow | CI | 26 |
| 28 | Docs clean-up and link check | docs | 27 |
| 29 | Close leftovers and phone-home pending list | cleanup | 28 |
| 30 | Mac smoke test | Tamair, on the Mac | 29 |

Tasks must run in this order. Do not parallelise removal tasks: they all edit `backend/main.py`.

---

## Task 1: Baseline

**Why:** later tasks compare against this, so pre-existing failures are not blamed on them.

**Create:** `docs/fork/baseline-tests.txt`, `docs/fork/routes-baseline.txt`.

- [ ] 1.1 `git fetch upstream && git checkout -b game-dev 8f6c11343` (if the branch exists: `git checkout game-dev` and verify it is based on `8f6c11343`).
- [ ] 1.2 `uv sync`. On Linux without a GPU this installs CPU torch; that is fine. Expected: exits 0. If it fails, stop and report the last 30 lines.
- [ ] 1.3 `export T="HF_HUB_OFFLINE=1 OMNIVOICE_MODEL=test"`, then `env $T uv run --no-sync pytest tests/ backend/tests/ -q -n 6 -p no:randomly --tb=no -rf > /tmp/base.txt 2>&1; tail -3 /tmp/base.txt`. Expected: a summary line like `N passed, M failed, ...`. It may take a long time.
- [ ] 1.4 `mkdir -p docs/fork && { grep '^FAILED' /tmp/base.txt | sort; echo; tail -1 /tmp/base.txt; } > docs/fork/baseline-tests.txt`
- [ ] 1.5 `cp tests/fixtures/api_routes.txt docs/fork/routes-baseline.txt`
- [ ] 1.6 `git add docs/fork/baseline-tests.txt docs/fork/routes-baseline.txt && git commit -m "chore(fork): record upstream test and route baseline"`

**Expected result:** two new files committed. `git status` is clean.

---

## Task 2: Triage helper and leftovers file

**Why:** removal tasks use ORPHANS and COLLECT instead of hand-searching 900 test files.

**Create:** `scripts/fork/triage.py`, `tests/test_fork_triage.py`, `docs/fork/orphans-baseline.txt`, `docs/fork/leftovers.md`.

- [ ] 2.1 Create `tests/test_fork_triage.py` with exactly:

```python
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "fork_triage", Path(__file__).resolve().parents[1] / "scripts" / "fork" / "triage.py")
triage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(triage)


def _write(root, rel, text=""):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_find_orphans_follows_imports_and_lazy_strings(tmp_path):
    _write(tmp_path, "main.py", "from services import a\n")
    _write(tmp_path, "services/__init__.py")
    _write(tmp_path, "services/a.py", "import services.b\nREG = {'x': ('engines.d', 'D')}\n")
    _write(tmp_path, "services/b.py")
    _write(tmp_path, "services/c.py")
    _write(tmp_path, "engines/__init__.py")
    _write(tmp_path, "engines/d/__init__.py")
    assert triage.find_orphans(tmp_path, ("services", "engines")) == ["services.c"]


def test_collect_errors_reads_pytest_output():
    out = (
        "_____________ ERROR collecting tests/test_dub_x.py _____________\n"
        "ImportError while importing test module '/r/tests/test_dub_x.py'.\n"
        "E   ModuleNotFoundError: No module named 'services.dub_pipeline'\n"
    )
    assert triage.collect_errors(out) == [("tests/test_dub_x.py", "services.dub_pipeline")]
```

- [ ] 2.2 `uv run --no-sync pytest tests/test_fork_triage.py -q`. Expected: FAIL (file not found).
- [ ] 2.3 Create `scripts/fork/triage.py` with exactly this content:

```python
#!/usr/bin/env python3
"""Triage helper for the Phase 1 strip tasks.

Commands:
  orphans  Print backend modules that nothing in backend/ imports any more,
           minus those listed in docs/fork/orphans-baseline.txt.
           "orphans --all" ignores the baseline (used once, in Task 2).
  collect  Run pytest --collect-only and print test files that fail to import,
           with the missing module, one "file<TAB>module" line each.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
SCANNED = ("services", "core", "engines", "utils", "api")
ROOTS = {"main", "mcp_server", "docker_entrypoint"}
_STR = re.compile(r"""["']((?:services|core|engines|api|utils|plugins|schemas|speech_client|mcp_shim)(?:\.\w+)+)["']""")
_ERR_FILE = re.compile(r"^(?:_+ )?ERROR (?:collecting )?(\S+\.py)")
_MISSING = re.compile(r"(?:ModuleNotFoundError: No module named|ImportError: cannot import name \S+ from) '([\w.]+)'")


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _modules(root: Path) -> dict[str, Path]:
    out = {}
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("tests/", "migrations/")) or "/tests/" in rel:
            continue
        out[_module_name(root, path)] = path
    return out


def _resolve(name: str, mods: set[str]) -> str | None:
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in mods:
            return candidate
    return None


def _imports(name: str, path: Path, mods: set[str]) -> set[str]:
    source = path.read_text(errors="ignore")
    found: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(r for a in node.names if (r := _resolve(a.name, mods)))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                pkg = package.split(".") if package else []
                pkg = pkg[: len(pkg) - (node.level - 1)]
                base = ".".join(pkg + ([base] if base else []))
            if r := _resolve(base, mods):
                found.add(r)
            for alias in node.names:
                if r := _resolve(f"{base}.{alias.name}" if base else alias.name, mods):
                    found.add(r)
    found.update(r for s in _STR.findall(source) if (r := _resolve(s, mods)))
    found.discard(name)
    return found


def find_orphans(root: Path = BACKEND, package_dirs: tuple[str, ...] = SCANNED) -> list[str]:
    """Modules under package_dirs that no other backend module imports."""
    files = _modules(root)
    mods = set(files)
    used: set[str] = set()
    for name, path in files.items():
        for target in _imports(name, path, mods):
            used.add(target)
            parts = target.split(".")  # a used submodule keeps its packages alive
            used.update(".".join(parts[:i]) for i in range(1, len(parts)))
    return sorted(
        m for m in mods
        if m.split(".")[0] in package_dirs and m not in used and m not in ROOTS
        and m.count(".") >= 1 and not m.startswith("api.routers.")
    )


def collect_errors(pytest_output: str) -> list[tuple[str, str]]:
    """(test_file, missing_module) pairs from `pytest --collect-only -q` output."""
    results: list[tuple[str, str]] = []
    current = None
    for line in pytest_output.splitlines():
        if m := _ERR_FILE.match(line.strip()):
            current = m.group(1)
        elif current and (m := _MISSING.search(line)):
            results.append((current, m.group(1)))
            current = None
    return results


def main(argv: list[str]) -> int:
    if argv[1:2] == ["orphans"]:
        found = find_orphans()
        baseline = REPO / "docs" / "fork" / "orphans-baseline.txt"
        if "--all" not in argv and baseline.exists():
            known = set(baseline.read_text().split())
            found = [m for m in found if m not in known]
        print("\n".join(found))
        return 0
    if argv[1:2] == ["collect"]:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests", "backend/tests"],
            cwd=REPO, capture_output=True, text=True,
        )
        for test_file, module in collect_errors(proc.stdout + proc.stderr):
            print(f"{test_file}\t{module}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] 2.4 `uv run --no-sync pytest tests/test_fork_triage.py -q`. Expected: 2 passed.
- [ ] 2.5 `uv run --no-sync python scripts/fork/triage.py orphans --all > docs/fork/orphans-baseline.txt; wc -l docs/fork/orphans-baseline.txt`. Expected: about 25 lines (entry-point scripts such as `engines.dots_tts.main` that run as subprocesses, so nothing imports them).
- [ ] 2.6 `uv run --no-sync python scripts/fork/triage.py orphans`. Expected: no output.
- [ ] 2.7 Create `docs/fork/leftovers.md`:

```markdown
# Fork leftovers

Things Phase 1 left in place on purpose. Phase 7 works through this list.
One line each: `- <path or name>: <why it stays> (Task N)`.

- backend/engines/omnivoice_gguf/: GPU probe helpers used by gpu_sandbox, health_device, settings_store (Task 21)
- backend/engines/omnivoice_subprocess/: OmniVoice on Apple Silicon runs through it (Task 21)
- diarisation (pyannote, Sortformer): /transcribe speaker hints and model_manager use it (Task 17)
- services/translation_engines.py, services/translation_apis.py: imported by core/prefs.py, system router, performance modules (Task 14)
```

- [ ] 2.8 `git add scripts/fork/triage.py tests/test_fork_triage.py docs/fork/orphans-baseline.txt docs/fork/leftovers.md && git commit -m "chore(fork): add triage helper for strip tasks"`

---

## Task 3: Pin the routes MCP depends on

**Why:** later deletions must never break the MCP tools.

**Create:** `tests/test_fork_mcp_routes.py`. **Edit:** `tests/test_api_route_inventory.py`.

- [ ] 3.1 Create `tests/test_fork_mcp_routes.py`:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "fixtures" / "api_routes.txt"
MCP = ROOT / "backend" / "mcp_server.py"
CALLS = re.compile(r'_(?:api_get|submit_json|api_post\w*|post\w*)\(\s*"(/[^"]*)"')
EXPECTED = {"/design/describe", "/generate", "/health", "/history",
            "/personalities", "/profiles", "/transcribe"}


def _route_paths():
    return {line.split(" ", 1)[1] for line in SNAPSHOT.read_text().splitlines()
            if line and not line.startswith("#")}


def test_mcp_calls_found():
    assert set(CALLS.findall(MCP.read_text())) == EXPECTED


def test_every_mcp_path_is_a_live_route():
    assert sorted(EXPECTED - _route_paths()) == []
```

- [ ] 3.2 In `tests/test_api_route_inventory.py`, find `_CRITICAL = [` (around line 48). Add these lines just after it, each ending with `# fork: MCP`. Skip any that is already in the list:

```python
    "POST /generate",  # fork: MCP
    "GET /profiles",  # fork: MCP
    "POST /profiles",  # fork: MCP
    "GET /personalities",  # fork: MCP
    "POST /transcribe",  # fork: MCP
    "GET /health",  # fork: MCP
    "GET /history",  # fork: MCP
    "POST /design/describe",  # fork: MCP
    "POST /v1/audio/speech",  # fork: MCP
```

- [ ] 3.3 `env $T uv run --no-sync pytest tests/test_fork_mcp_routes.py tests/test_api_route_inventory.py -q`. Expected: all pass. If `test_mcp_calls_found` fails, the set differs from upstream: stop and report.
- [ ] 3.4 `git add tests/test_fork_mcp_routes.py tests/test_api_route_inventory.py && git commit -m "test(fork): pin routes used by MCP tools"`

---

## Task 4: Fork identity and AGPL notice

**Why:** AGPL section 5(a) requires a prominent modification notice; the product name changes.

**Edit:** `config/app.json`. **Create:** `FORK-NOTICE.md`, `tests/test_fork_identity.py`.

- [ ] 4.1 Create `tests/test_fork_identity.py`:

```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_name():
    assert json.loads((ROOT / "config" / "app.json").read_text())["productName"] == "Voice Forge Studio"


def test_fork_notice_present():
    text = (ROOT / "FORK-NOTICE.md").read_text()
    for needle in ("debpalash/VoiceStudio", "8f6c11343", "AGPL-3.0", "2026-11-19", "Tamair"):
        assert needle in text
```

- [ ] 4.2 Run it. Expected: 2 failed.
- [ ] 4.3 In `config/app.json` change `"productName": "VoiceStudio"` to `"productName": "Voice Forge Studio"`. Change nothing else in that file.
- [ ] 4.4 Create `FORK-NOTICE.md`:

```markdown
# Modification notice

Voice Forge Studio is a modified version of VoiceStudio
(https://github.com/debpalash/VoiceStudio), forked at commit 8f6c11343.

Modified from 2026-11-19 by Tamair. This notice is given under section 5(a) of the
GNU Affero General Public License version 3 (AGPL-3.0). The licence is unchanged;
see LICENSE and LICENSE-NOTICE.md.

## What changed

- Removed: the Electron desktop app, mobile apps, app-store and packaging tooling.
- Removed: cloud account and sync, analytics and diagnostics upload, community gallery,
  marketplace, telephony.
- Removed: dubbing, translation and video, dictation and live capture, audiobook and long-form.
- Reduced the speech engines and model catalogue to a game-development set, with VoxCPM2 as the
  default engine.

Generated audio is not covered by the AGPL. Each model's own licence decides whether its output
can be shipped.
```

- [ ] 4.5 Run `tests/test_fork_identity.py` and `tests/test_app_config.py`. Expected: pass. If an upstream test asserts the string `"VoiceStudio"` as the product name, change only that expected string to `"Voice Forge Studio"` and mention it in your report.
- [ ] 4.6 `git add config/app.json FORK-NOTICE.md tests/test_fork_identity.py` (plus any test you changed) and commit: `chore(fork): Voice Forge Studio identity and AGPL notice`.

---

## Task 5: README, CLAUDE.md and AGENTS.md

**Why:** upstream agent rules (Electron only, release channels) no longer apply.

**Replace:** `README.md`, `CLAUDE.md`, `AGENTS.md`. **Create:** `tests/test_fork_agent_docs.py`.

- [ ] 5.1 Create `tests/test_fork_agent_docs.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_claude_md():
    text = (ROOT / "CLAUDE.md").read_text()
    assert "127.0.0.1" in text and "@AGENTS.md" in text and "0.0.0.0" not in text


def test_agents_md():
    assert "2026-11-19-roadmap.md" in (ROOT / "AGENTS.md").read_text()


def test_readme():
    text = (ROOT / "README.md").read_text()
    assert "uvicorn" in text and "FORK-NOTICE.md" in text and "0.0.0.0" not in text


def test_docs_are_ascii():
    for name in ("README.md", "CLAUDE.md", "AGENTS.md", "FORK-NOTICE.md"):
        (ROOT / name).read_text().encode("ascii")
```

- [ ] 5.2 Run it. Expected: some fail.
- [ ] 5.3 Replace `README.md` with:

```markdown
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
```

- [ ] 5.4 Replace `CLAUDE.md` with:

```markdown
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
```

- [ ] 5.5 Replace `AGENTS.md` with:

```markdown
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
```

- [ ] 5.6 Run the test file. Expected: 4 passed.
- [ ] 5.7 `git add README.md CLAUDE.md AGENTS.md tests/test_fork_agent_docs.py && git commit -m "docs(fork): replace upstream agent and readme files"`

---

## Task 6: Remove desktop and mobile apps

**Why:** the fork is API-only. The backend already copes with a missing web UI (`core/spa_inject.frontend_available()` returns False when there is no build).

**Delete:** `electron/`, `mobile/`, `native/`, `frontend/`, and these tests: `tests/frontend/` (whole directory), `tests/smoke/test_macos_hotkey_pump.py`, `tests/test_android_play_workflow.py`, `tests/test_android_repository.py`, `tests/test_android_sdk_install_retry.py`, `tests/test_docker_electron_webui.py`, `tests/test_electron_model_management.py`, `tests/test_electron_only_ui.py`, `tests/test_electron_rehearsal_runtime.py`, `tests/test_electron_release_assets.py`, `tests/test_electron_test_timeouts.py`, `tests/test_electron_transition.py`, `tests/test_gguf_desktop_bundle.py`, `tests/test_google_play_listing.py`, `tests/test_ios_accessibility_query_limits.py`, `tests/test_ios_archive_signing.py`, `tests/test_ios_background_runtime.py`, `tests/test_ios_ci_test_harness.py`, `tests/test_ios_native_host_runtime.py`, `tests/test_ios_phone_job_diagnostic_owners.py`, `tests/test_ios_privacy_manifests.py`, `tests/test_ios_tab_navigation.py`, `tests/test_ios_testflight.py`, `tests/test_ios_uitest_taps.py`, `tests/test_locale_parity.py`, `tests/test_macos_icon_grid.py`, `tests/test_mobile_artifact_retry.py`, `tests/test_mobile_contract.py`, `tests/test_mobile_contributors.py`, `tests/test_mobile_mp3_source.py`, `tests/test_mobile_support_pages.py`, `tests/test_native_notice_checkout.py`, `tests/test_no_hardcoded_cjk.py`, `tests/test_no_shouted_labels.py`, `tests/test_packaged_lan_frontend.py`.

**Create:** `tests/test_fork_startup.py`.

**Tests to check** (they read files under the deleted directories; remove only the failing cases): `tests/test_app_config.py`, `tests/test_cors_exposed_headers.py`, `tests/test_identity_gate.py`, `tests/test_identity_paths_survive_the_rename.py`, `tests/test_issue_fixes.py`, `tests/test_no_windows_hostile_paths.py`, `tests/test_oss_has_no_licence_client.py`, `tests/test_path_authorization.py`, `tests/test_port_in_use_exit.py`, `tests/test_voicestudio_branding.py`.

**Routes that must disappear:** none.

- [ ] 6.1 Create `tests/test_fork_startup.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOVED_APP_DIRS = ["electron", "mobile", "native", "frontend"]


def test_app_dirs_gone():
    assert [d for d in REMOVED_APP_DIRS if (ROOT / d).exists()] == []


def test_backend_imports_in_a_fresh_interpreter():
    # Must work on Linux without mlx and on the Mac without CUDA.
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "OMNIVOICE_MODEL": "test"}
    result = subprocess.run([sys.executable, "-c", "import main"], cwd=ROOT / "backend",
                            env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
```

- [ ] 6.2 `env $T uv run --no-sync pytest tests/test_fork_startup.py -q`. Expected: 1 failed, 1 passed.
- [ ] 6.3 `git rm -r -q electron mobile native frontend tests/frontend` then `git rm -q` each test file listed under Delete.
- [ ] 6.4 Run `tests/test_fork_startup.py` again. Expected: 2 passed.
- [ ] 6.5 Run BASEDIFF. Handle every new failure that is in Tests to check. A new failure in any other file: stop (rule 6).
- [ ] 6.6 Commit (the `git rm` calls already staged the deletions): `git add tests/test_fork_startup.py` plus any checked test you edited, then `git commit -m "chore(fork): remove desktop and mobile apps"`.

---

## Task 7: Remove store, packaging and release tooling

**Why:** nothing is published to app stores; CI is replaced in Task 27.

**Delete (directories):** `store/`, `fastlane/`, `snap/`, `packaging/`, `notebooks/`, `omnivoice-gallery/`, `patches/`, `cli/`, `skills/`, `.agents/`, `.github/workflows/`, `.github/actions/`, `.github/scripts/`, `tests/cli/`.

**Delete (files):** `skills-lock.json`, `flake.nix`, `flake.lock`, `dagger.json`, `greptile.json`, `funding.json`, `SPONSORS.md`, `.coderabbit.yaml`, `bun.lock`, `.github/FUNDING.yml`, `.github/CODEOWNERS`, `.github/CLA-1.0.md`, `.github/CCLA-1.0.md`, `.github/AGENT_PR_GUIDE.md`.

**Delete (scripts, all under `scripts/`):** `android_version_code.py`, `build_demos.sh`, `build_dub_demo.sh`, `build_windows_user_manifest.py`, `capture-readme-electron.mjs`, `check_commit_identities.py`, `blocked_identity_hashes.txt`, `check_electron_release_assets.py`, `cla_audit.py`, `clean-all.mjs`, `clear-dev-ports.mjs`, `cli_install_smoke.py`, `cli_package_smoke.py`, `create_google_play_assets.py`, `create_microsoft_store_handoff.mjs`, `create_snap_store_assets.mjs`, `create_store_artifact_manifest.mjs`, `create_store_artifact_manifest.test.mjs`, `dev-backend.mjs`, `dub_demo_scripts.json`, `electron-smoke-test.mjs`, `export-mobile-contributors.ts`, `export-mobile-design.ts`, `export-mobile-tokens.ts`, `export_cli_contract.py`, `export_mobile_models.py`, `freeze_cli.py`, `generate_supermetry_config.py`, `macos-dev-unquarantine.sh`, `prepare-apple-notarization.sh`, `prepare-dev.mjs`, `prepare_android_repository.py`, `prepare_electron_release.py`, `prepare_mobile_contributors.py`, `prune-runtime-node-modules.mjs`, `readme-media/`, `release.py`, `release_signing_notes.py`, `render_brand_icons.py`, `render_dub_demo_audio.py`, `render_gallery.py`, `resolve_supertonic3_sha.py`, `setup-api.mjs`, `smoke_dub_url_captions.py`, `stage_mas_media.py`, `stage_mas_python.py`, `update_contributors.py`, `validate_store_foundation.mjs`, `validate_store_foundation.test.mjs`, `verify-macos-signing.sh`, `verify_microsoft_store_authenticode.ps1`, `verify_snap_artifact.mjs`, `virustotal.py`, `wait-app-port.mjs`.

**Keep (scripts):** `dump_api_routes.py`, `dump_route_auth.py`, `check_model_licenses.py`, `generate_model_license_data.py`, `migrate_model_licenses.py`, `check-docs-drift.py`, `crash_class_report.py`, `export_openapi.py`, `install.sh`, `install.ps1`, `uninstall.sh`, `uninstall.ps1`, `run.sh`, `setup.py`, `seed-test-fixture.py`, `uv-sync-retry.sh`, every `smoke_*` not listed above, `bench/`, `perf/`, `lib/`, `fork/` and everything else not in the delete list.

**Delete (tests):** `tests/test_agent_skill_discovery.py`, `tests/test_aur_package.py`, `tests/test_beta_release_bash_selection.py`, `tests/test_beta_release_channel.py`, `tests/test_bot_configs.py`, `tests/test_build_commit.py`, `tests/test_bun_toolchain_pins.py`, `tests/test_cancel_stale_runs.py`, `tests/test_changelog_style.py`, `tests/test_ci_apt_retry.py`, `tests/test_ci_change_detection.py`, `tests/test_ci_pass_cache.py`, `tests/test_ci_pytest_parallel.py`, `tests/test_ci_queue_hygiene.py`, `tests/test_ci_release_smoke.py`, `tests/test_ci_required_gate.py`, `tests/test_ci_runtime_scope.py`, `tests/test_ci_windows_ffmpeg_retry.py`, `tests/test_cla_check.py`, `tests/test_cla_workflow.py`, `tests/test_cli_packaging.py`, `tests/test_colab_asr_setup.py`, `tests/test_colab_proxy_trust_2705.py`, `tests/test_commit_identities.py`, `tests/test_docker_registry_owner.py`, `tests/test_docker_workflow.py`, `tests/test_gitleaks_allowlist.py`, `tests/test_mac_app_store_workflow.py`, `tests/test_macos_notarization_api.py`, `tests/test_mas_python_runtime.py`, `tests/test_microsoft_store_workflow.py`, `tests/test_n8n_workflow.py`, `tests/test_nix_runtime_scope.py`, `tests/test_published_image_path_is_pinned.py`, `tests/test_release_contributors.py`, `tests/test_release_rehearsal.py`, `tests/test_release_script.py`, `tests/test_release_signing_notes.py`, `tests/test_reusable_workflow_permissions.py`, `tests/test_snapcraft_yaml.py`, `tests/test_source_archive.py`, `tests/test_sponsors_lockstep.py`, `tests/test_supermetry_app_build_config.py`, `tests/test_unified_release_workflow.py`, `tests/test_virustotal.py`.

**Tests to check:** `tests/test_app_version.py` (must still pass: `package.json` keeps its version), `tests/test_setup_rocm_variant.py`, `tests/test_docs_drift.py`, `tests/test_docs_links.py`, `tests/scripts/test_crash_class_report.py`, `tests/test_actions_pinned.py` (it scans workflows; with none left it should pass; if it fails because the directory is missing, create `.github/workflows/.gitkeep`).

**Edit:**

- `package.json`: replace the whole file with the four keys below, keeping the current version string (upstream: `0.5.9-beta.6`):

```json
{
  "name": "voice-forge-studio",
  "version": "0.5.9-beta.6",
  "license": "AGPL-3.0-only",
  "private": true
}
```

- `tests/test_fork_startup.py`: change `REMOVED_APP_DIRS` to `["electron", "mobile", "native", "frontend", "store", "fastlane", "snap", "packaging", "cli", "skills"]`.

**Routes that must disappear:** none.

- [ ] 7.1 Make the `tests/test_fork_startup.py` edit. Run it. Expected: `test_app_dirs_gone` fails.
- [ ] 7.2 `git rm -r -q` every path under Delete.
- [ ] 7.3 Replace `package.json`.
- [ ] 7.4 `grep -n "cli" pyproject.toml`. If a `[tool.uv.workspace]` members list names `cli`, remove that entry and run `uv lock`. Otherwise change nothing.
- [ ] 7.5 Run IMPORT, then `tests/test_fork_startup.py` and `tests/test_app_version.py`. Expected: pass.
- [ ] 7.6 Run BASEDIFF; handle Tests to check only.
- [ ] 7.7 `git add package.json tests/test_fork_startup.py` (plus `pyproject.toml uv.lock` if changed, plus checked tests) and commit: `chore(fork): remove store, packaging and release tooling`.

---

## Task 8: Remove analytics and diagnostics upload

**Why:** no data leaves the machine. Local diagnostics (error journal, reports on disk) stay; only the upload transports go.

**Delete:** `backend/core/analytics.py`, `backend/core/analytics_transport.py`, `backend/core/diagnostic_app_transport.py`, `config/analytics.json`, `config/diagnostics.json`.

**Edit:**

- `backend/main.py`:
  - Delete the function `def _start_analytics_lifecycle(app: FastAPI, crash_record) -> None:` (around line 1282) and its whole body, up to the blank lines before the next `def`.
  - Delete the function `async def _wait_for_analytics_thread(app: FastAPI) -> None:` (around line 1306) and its body.
  - Delete the block that starts with the comment `# Opt-in lifecycle analytics (core/analytics.py)` (around line 1421) through `logger.exception("Analytics startup lifecycle failed (non-fatal).")`.
  - Delete the line `await _wait_for_analytics_thread(app)` (around line 1496).
- `backend/api/routers/generation.py`: delete from the comment `# Opt-in analytics (core/analytics.py): no-op unless the user turned it on.` (around line 1801) through the line `logger.warning("analytics: speech_generated capture failed", exc_info=True)`. The next line must be `return audio_tensor, {`.
- `backend/api/routers/capture.py`: delete the `try:` block that contains `from core.analytics import capture as _capture_analytics` (around lines 438 to 453), through `logger.warning("analytics: transcription_completed capture failed", exc_info=True)`. The next line must be `if speakers:`.
- `backend/api/routers/settings.py`: delete from the comment line that contains `Opt-in product analytics (hardened; default OFF)` (around line 1667) up to, but not including, `class _DiagnosticsBody(BaseModel):`. This removes `_AnalyticsBody`, `get_analytics`, `_UiEventBody`, `post_analytics_event`, `set_analytics`.
- `backend/core/error_journal.py`: delete the comment starting `# Opt-in analytics (core/analytics.py): a no-op unless the user opted` (around line 265) and the `try: / from core import analytics / analytics.record_error_event(...) / except Exception: pass` block after it. The next line must be `return entry`.
- `backend/core/diagnostic_reports.py`:
  - Replace the whole body of `def _diagnostic_destination():` (around line 137) with: `    """Diagnostic upload is disabled in this fork."""` and `    return {}`.
  - In the block `if not self.transport:` (around line 876), delete the whole `if not self.transport:` statement and its body (the lines that import `SupermetryTransport` and `AppDiagnosticTransport` and build a transport).
  - A few lines below, replace the two lines `from core.diagnostic_app_transport import AppDiagnosticTransport` and `app_transport = isinstance(transport, AppDiagnosticTransport)` with the single line `app_transport = False`.
  - Run `grep -n "analytics\|diagnostic_app_transport\|SupermetryTransport" backend/core/diagnostic_reports.py`. Any remaining import of a deleted module must go; plain mentions in comments may stay.

**Routes that must disappear:** `GET /api/settings/analytics`, `PUT /api/settings/analytics`, `POST /api/settings/analytics/event`.

**Tests to delete:** `tests/test_analytics_lifecycle.py`, `tests/test_analytics_optin.py`, `tests/test_diagnostic_app_transport.py`, `tests/test_no_committed_analytics_token.py`, `tests/test_startup_analytics_background.py`.

**Tests to check:** `tests/test_diagnostic_reports.py` (cases about upload destinations or transports fail; delete those cases only), `tests/test_error_journal*.py`.

- [ ] 8.1 Follow R1 to R8.
- [ ] 8.2 `git grep -n "core.analytics\|core import analytics\|analytics_transport\|diagnostic_app_transport" -- backend`. Expected: no output.
- [ ] 8.3 R9 with message `chore(fork): remove analytics and diagnostics upload`.

---

## Task 9: Remove cloud account and cloud sync

**Delete:** `backend/services/cloud_account.py` (and any `backend/services/cloud_account*`), `backend/services/cloud_sync/` (whole package), `backend/api/routers/cloud_sync.py`.

**Keep:** `backend/migrations/versions/0014_cloud_sync.py` and `0015_voice_sync_prep.py` (rule 7), and the `cloud_sync` tables in `_BASE_SCHEMA` in `backend/core/db.py` (removing them would need a migration). Add one line to `docs/fork/leftovers.md` for the tables.

**Edit (`backend/main.py` only):**

- Delete the comment `# Importing it removes Electron's account-bridge capability from os.environ, so`, the next comment line, and `importlib.import_module("services.cloud_account")` (around lines 159 to 161). The variable it stripped only existed under Electron.
- Delete `from api.routers import cloud_sync as _cloud_sync_router  # noqa: E402` (around line 832) and `_cloud_sync_router` from the `_router_modules.extend([...])` list.
- Delete the block from `# VoiceStudio Cloud settings sync: idles` (around line 1260) through `app.state.cloud_sync_task = asyncio.create_task(_start_cloud_sync())`.
- Delete the shutdown block that starts `if getattr(app.state, "cloud_sync_task", None) is not None:` (around line 1510) and its whole body (it imports `services.cloud_sync.service`).
- Check `importlib` is still used in `main.py` (`grep -n "importlib" backend/main.py`). If not, remove its import.

**Routes that must disappear (14):** `GET /api/cloud-sync/devices`, `GET /api/cloud-sync/local`, `GET /api/cloud-sync/local/keys`, `GET /api/cloud-sync/status`, `POST /api/cloud-sync/confirm-deletes`, `POST /api/cloud-sync/devices/{device_id}/revoke`, `POST /api/cloud-sync/off`, `POST /api/cloud-sync/on`, `POST /api/cloud-sync/run`, `POST /api/cloud-sync/start`, `POST /api/cloud-sync/stop`, `POST /api/cloud-sync/use-choices-of/{device_id}`, `PUT /api/cloud-sync/choices`, `PUT /api/cloud-sync/local`.

**Tests to delete:** `tests/backend/api/routers/test_cloud_sync.py`, `tests/backend/services/test_cloud_account.py`, and every `tests/backend/services/test_cloud_sync_*.py` (allowlist, client, engine, events, merge, record_ids, service, store, voices, vsb1).

**Tests to check:** none expected; COLLECT will show any.

- [ ] 9.1 R1 to R9. Commit message: `chore(fork): remove cloud account and sync`.

---

## Task 10: Remove community, gallery, marketplace and project bundles

**Why:** remote voice galleries are out of scope. Project bundles are dub-project archives: they import helpers from both marketplace and `dub_generate`, so they go now.

**Delete:** `backend/api/routers/community.py`, `backend/api/routers/gallery.py`, `backend/api/routers/marketplace.py`, `backend/api/routers/project_bundles.py`. Then R4 will offer `services.gallery` only if `api.routers.archetypes` no longer imports it: it still does, so `services/gallery.py` stays (archetypes use it).

**Edit:**

- `backend/main.py`: remove `gallery,`, `community,`, `marketplace,` from the `from api.routers import (...)` block and from `_router_modules.extend([...])`.
- `backend/api/routers/projects.py` (around lines 97 to 98): delete `from api.routers.project_bundles import router as project_bundles_router` and `router.include_router(project_bundles_router)`. That is the only place project bundles are registered.
- `backend/main.py` around line 1088: delete `from api.routers.gallery import _init_gallery_db` and `_init_gallery_db()`. Add a leftovers line: gallery tables stay in the database.

**Routes that must disappear (29):**
- community: `GET /community/items`, `GET /community/items/{item_id}/preview`, `GET /community/manifest`, `GET /community/sources`, `GET /community/submit-url`, `POST /community/items/{item_id}/use`
- gallery: `DELETE /gallery/voices/{voice_id}`, `GET /gallery/categories`, `GET /gallery/voices`, `GET /gallery/voices/{voice_id}`, `GET /gallery/voices/{voice_id}/preview`, `PATCH /gallery/voices/{voice_id}`, `POST /gallery/download`, `POST /gallery/search/youtube`, `POST /gallery/upload`, `POST /gallery/voices/batch-delete`, `POST /gallery/voices/{voice_id}/save-as-profile`, `POST /gallery/voices/{voice_id}/to-profile`
- marketplace: `DELETE /marketplace/{filename}`, `GET /marketplace/browse`, `POST /marketplace/export/{profile_id}`, `POST /marketplace/import`, `POST /marketplace/install/{filename}`, `POST /marketplace/publish/{profile_id}`
- project bundles: `GET /project-bundles`, `GET /project-bundles/{identifier}`, `GET /project-bundles/{identifier}/document`, `POST /project-bundles/export`, `POST /project-bundles/import`.

**_CRITICAL entries to remove:** `GET /gallery/voices`.

**Tests to delete:** `backend/tests/test_community.py`, `backend/tests/test_gallery_profiles.py`, `tests/test_gallery_pin.py`, `tests/test_gallery_previews.py`, `tests/test_mobile_gallery_copy.py`, `tests/test_project_bundle.py`, `tests/test_project_bundle_chapters.py`, `tests/test_project_bundle_ffmpeg_whitelist.py`, `tests/test_project_bundle_routes.py`, `tests/test_project_bundle_translation_targets.py`.

**Tests to check:** `backend/tests/test_stored_path_containment.py`, `tests/test_browser_guard.py`, `tests/test_filesystem_boundaries.py`, `tests/test_model_download_containment.py`, `tests/test_no_audio_track.py`, `tests/test_persona_kind.py`, `tests/test_url_import_native_downloads.py`, `tests/test_url_import_safety.py`.

- [ ] 10.1 R1 to R9. R4 may list `services.project_bundle` (the service behind the router): delete it if `git grep -n "project_bundle" -- backend` shows only deleted code. Commit message: `chore(fork): remove community, gallery, marketplace and project bundles`.

---

## Task 11: Remove telephony and calls

**Delete:** `backend/api/routers/telephony_twilio.py`, `backend/api/routers/calls.py`, `backend/services/telephony/` (whole package).

**Edit (`backend/main.py`):**

- Delete `from api.routers import telephony_twilio as _telephony_twilio_router  # noqa: E402` and `from api.routers import calls as _calls_router  # noqa: E402` (around lines 830 to 831), and both names from `_router_modules.extend([...])`.
- Delete the block from `# Phone calls (opt-in): the separate loopback telephony listener resumes` (around line 1273) through `logger.exception("Telephony gateway startup failed (continuing without it)")`.
- Delete the shutdown block `try: / from services.telephony import gateway as telephony_gateway / await telephony_gateway.stop() / except Exception: / logger.exception("Telephony gateway shutdown failed")` (around lines 1497 to 1501).
- `grep -n "webhook_router\|telephony" backend/main.py`: remove any remaining registration of the Twilio webhook router.

**Routes that must disappear (16, plus any Twilio webhook route):** `GET /api/integrations/twilio/state`, `POST /api/integrations/twilio/test`, `PUT /api/integrations/twilio/config`, `DELETE /calls/{call_id}`, `GET /calls`, `GET /calls/options`, `GET /calls/readiness`, `GET /calls/settings`, `GET /calls/{call_id}`, `GET /calls/{call_id}/events`, `GET /calls/{call_id}/recording`, `POST /calls`, `POST /calls/{call_id}/hangup`, `POST /calls/{call_id}/say`, `POST /calls/{call_id}/takeover`, `PUT /calls/settings`. If the snapshot diff also removes a `/telephony/...` or `/twilio/...` webhook route, that is expected.

**Tests to delete:** `tests/test_call_agent.py`, `tests/test_call_finalization.py`, `tests/test_telephony_twilio.py`, and `tests/test_mobile_call_control.py` if it still exists.

- [ ] 11.1 R1 to R9. Commit message: `chore(fork): remove telephony and calls`.

---

## Task 12: No phone-home hosts

**Why:** pins that removed services cannot creep back.

**Create:** `tests/test_fork_no_phone_home.py`.

- [ ] 12.1 Create the test:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED_HOSTS = ["voicestudio.sh", "supermetry.com", "posthog", "twilio.com", "jsdelivr.net"]
# Files that still mention a banned host because a later task removes them.
# Each entry names that task. Task 29 empties this set.
PENDING: dict[str, str] = {}


def test_no_phone_home_hosts_in_backend():
    hits = sorted(
        (path.relative_to(ROOT).as_posix(), host)
        for path in (ROOT / "backend").rglob("*.py")
        for host in BANNED_HOSTS
        if host in path.read_text(errors="ignore")
        and path.relative_to(ROOT).as_posix() not in PENDING
    )
    assert hits == []
```

- [ ] 12.2 Run it. Expected: PASS. On upstream every hit was in files Tasks 8 to 11 deleted (`core/analytics.py`, `services/cloud_sync/`, `services/telephony/twilio.py`, `api/routers/community.py`). If it fails, the assertion lists the hits; go to 12.3.
- [ ] 12.3 Only if 12.2 failed: for each hit, open the file and find the line:
  - If the file is in a feature a later task deletes (dubbing, batch, dictation, audiobook, sfx; see the task map), add it to `PENDING` as `"backend/...py": "Task NN"`.
  - If the host is in a URL constant used only for update checks, telemetry or account links, delete the constant and the code that calls it (update checks: make the function return "no update available" with the same return type).
  - If the host is only in a comment, edit the comment to remove the host name.
  - If unsure, stop and report the file and line.
- [ ] 12.4 Run the test (expect pass) and BASEDIFF.
- [ ] 12.5 `git add tests/test_fork_no_phone_home.py` plus changed files, commit: `chore(fork): remove remaining phone-home calls`.

---

## Task 13: Move the generic job routes into jobs.py

**Why:** `GET /jobs`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/events`, `GET /tasks/stream/{task_id}` and `POST /tasks/cancel/{task_id}` are used by every background job, but they live in `api/routers/dub_export.py`, which Task 15 deletes. Phase 3's queue needs them. This task moves them without changing behaviour. No route may appear or disappear.

**Create:** `backend/api/routers/jobs.py`, `tests/test_fork_jobs_router.py`.
**Edit:** `backend/api/routers/dub_export.py`, `backend/main.py`, `tests/test_job_event_watermark.py`.

- [ ] 13.1 Create `tests/test_fork_jobs_router.py`:

```python
JOB_ROUTES = {
    ("GET", "/jobs"), ("GET", "/jobs/{job_id}"), ("GET", "/jobs/{job_id}/events"),
    ("GET", "/tasks/stream/{task_id}"), ("POST", "/tasks/cancel/{task_id}"),
}


def _routes(router):
    return {(m, r.path) for r in router.routes for m in getattr(r, "methods", set()) - {"HEAD"}}


def test_jobs_router_owns_job_routes():
    from api.routers import jobs
    assert _routes(jobs.router) == JOB_ROUTES


def test_dub_export_no_longer_has_them():
    from api.routers import dub_export
    assert not (_routes(dub_export.router) & JOB_ROUTES)
```

- [ ] 13.2 Run it. Expected: FAIL (`No module named 'api.routers.jobs'` or similar).
- [ ] 13.3 In `backend/api/routers/dub_export.py`, find these and cut them (remove from `dub_export`, keep the text for the next step):
  - the constant `TASK_STREAM_KEEPALIVE_S = 15.0` (around line 118), only if nothing else in `dub_export` uses it after the cut (`grep -n TASK_STREAM_KEEPALIVE_S`);
  - from `@router.get("/tasks/stream/{task_id}")` (around line 285) through the end of `async def cancel_task(...)` (the line `return {"cancelled": True, "task_id": task_id}`, around line 408). This span includes `stream_task`, `list_jobs`, `get_job`, `class PersistedJobEvents`, `list_job_events` and `cancel_task`. If the span also contains a function that is not one of those six, leave that function in `dub_export`.
- [ ] 13.4 Create `backend/api/routers/jobs.py`:

```python
"""Generic background job and task routes.

Moved unchanged from api/routers/dub_export.py so they survive the removal of dubbing.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.tasks import task_manager

router = APIRouter()

TASK_STREAM_KEEPALIVE_S = 15.0

# <paste the six cut items here, unchanged>
```

Then run `uv run --no-sync python -m pyflakes backend/api/routers/jobs.py` (install with `uv pip install pyflakes` if missing). Add an import for every "undefined name" it reports, copying the import line from the top of `dub_export.py`. Remove every "imported but unused" import.

- [ ] 13.5 If `dub_export.py` still uses `TASK_STREAM_KEEPALIVE_S`, change it to `from api.routers.jobs import TASK_STREAM_KEEPALIVE_S`. Run pyflakes on `dub_export.py` and remove imports that are now unused there.
- [ ] 13.6 In `backend/main.py`, add `jobs,` to the `from api.routers import (...)` block (just after `exports,`) and `jobs` to `_router_modules.extend([...])` (just after `exports`).
- [ ] 13.7 In `tests/test_job_event_watermark.py`, change `from api.routers.dub_export import router` to `from api.routers.jobs import router`. Run `grep -rln "dub_export" tests backend/tests`; in `tests/test_tasks_stream_keepalive.py` and any other file that patches or imports the moved names from `dub_export`, point it at `api.routers.jobs` instead.
- [ ] 13.8 Run the new test, `tests/test_job_event_watermark.py`, `tests/test_tasks_stream_keepalive.py`. Expected: pass.
- [ ] 13.9 Run SNAPSHOT. Expected: no diff at all (same routes, new owner).
- [ ] 13.10 BASEDIFF, then commit the five files (plus any updated test): `refactor(fork): move generic job routes out of dubbing`.

---

## Task 14: Remove batch, glossary, SoniTranslate and translation routes

**Why:** batch was a dubbing queue; translation is out of scope. Batch goes before dubbing because `batch.py` imports from `dub_core.py`.

**Delete:** `backend/api/routers/batch.py`, `backend/api/routers/glossary.py`, `backend/api/routers/sonitranslate.py`. R4 will then list `services.sonitranslate`: delete it.

**Edit:**

- `backend/main.py`: remove `glossary,`, `batch,`, `sonitranslate,` from the import block and from `_router_modules.extend([...])`.
- `backend/api/routers/settings.py` (around line 147): delete `from api.routers.batch import list_batch_jobs` and change `if job_store.list_jobs(status="active", limit=1) or list_batch_jobs(status="active", limit=1):` to `if job_store.list_jobs(status="active", limit=1):`.
- `backend/services/model_manager.py`: in `_generation_jobs_active()` (around line 4575) delete the five lines from `batch = sys.modules.get("api.routers.batch")` through the inner `return True` of that `try/except`, so the function ends with `return False`. Check `sys` is still used in the file before removing any import (it will be).
- `backend/api/routers/engines.py`: delete from `@router.get("/engines/translation")` (around line 274) through the end of `uninstall_translation_engine` (the line `return {"status": "uninstalled", "engine": engine_id, "package": pkg, "log_tail": out[-800:]}`, around line 444). This removes `TranslationSelection`, `ArgosPackRequest`, `_argos_pack_request` and the six translation routes. The next non-blank line must be the comment about the audio.cpp runtime install. Then check line 33 (`from services import tts_backend, asr_backend, llm_backend, translation_engines`): if `translation_engines` is no longer used in the file, remove it from that import.

**Keep:** `services/translation_engines.py`, `services/translation_apis.py` (decision D6).

**Routes that must disappear (24):**
- batch: `DELETE /batch/jobs/{job_id}`, `GET /batch/download/{job_id}/{lang}`, `GET /batch/jobs`, `GET /batch/jobs/{job_id}`, `POST /batch/enqueue`, `POST /batch/jobs/{job_id}/cancel`, `POST /batch/jobs/{job_id}/retry`
- glossary: `DELETE /glossary/{project_id}`, `DELETE /glossary/{project_id}/{term_id}`, `GET /glossary/{project_id}`, `POST /glossary/{project_id}`, `POST /glossary/{project_id}/auto-extract`, `PUT /glossary/{project_id}/{term_id}`
- SoniTranslate: `GET /engines/sonitranslate/status`, `POST /engines/sonitranslate/dub`, `POST /engines/sonitranslate/install`, `POST /engines/sonitranslate/start`, `POST /engines/sonitranslate/stop`
- translation: `GET /engines/translation`, `DELETE /engines/translation/{engine_id}`, `POST /engines/translation/argos/packs/install`, `POST /engines/translation/argos/packs/status`, `POST /engines/translation/select`, `POST /engines/translation/{engine_id}/install`.

**_CRITICAL entries to remove:** `POST /batch/enqueue`.

**Tests to delete:** `backend/tests/test_batch.py`, `tests/test_batch_job_lifecycle_race.py`, `tests/test_batch_prepared_budget.py`, `tests/test_diagnostic_batch_asr_job_owner.py`, `tests/test_dub_batch_engine_selection.py`, `tests/test_dub_batch_width_and_budget.py`, `tests/test_glossary_scrub.py`, `tests/test_sonitranslate_venv.py`, `tests/test_argos_pack_source.py`, `tests/test_translation_install_command.py`.

**Tests to check:** `tests/test_asr_duration_deadlines.py`, `tests/test_diagnostic_reports.py`, `tests/test_llm_skills.py`, `tests/test_perf_operation_budgets.py`, `tests/test_relock_cache_identity.py`, `tests/test_synthetic_audio_watermark_1169.py`, `tests/test_text_normalization_routes.py`, `tests/test_whisper_cpp_language.py`, `tests/test_windows_rocm_argos_isolation.py`, `tests/test_engine_language_options.py`.

- [ ] 14.1 R1 to R9. Commit message: `chore(fork): remove batch, glossary and translation routes`.

---

## Task 15: Remove dubbing

**Delete:** `backend/api/routers/dub_core.py`, `dub_generate.py`, `dub_export.py`, `dub_translate.py` (all in `backend/api/routers/`). R4 should then list, possibly over two rounds, and you delete: `services/dub_pipeline.py`, `services/dub_background.py`, `services/dub_batching.py`, `services/dub_language.py`, `services/dub_mix.py`, `services/dub_resume.py`, `services/dub_qc.py`, `services/duration_planner.py`, `services/fit_planner.py`, `services/fitted_subtitles.py`, `services/karaoke_ass.py`, `services/onset_align.py`, `services/prosody_mirror.py`, `services/rvc.py`, `services/speaker_clone.py`, `services/translation_quality.py`, `services/video_retime.py`, `core/file_cleanup.py`, `services/project_bundle.py`, `services/longform_parser.py` only if R4 lists them. Anything R4 lists that is not in this paragraph: apply R4's rule.

**Keep:** `services/srt_parser.py` (used by `openai_compat.py`), `services/video_encoder.py` (settings router), `services/video_voice_swap.py` (voice_convert router), `services/segmentation.py`, `services/transcript_diarization.py` and the diarisation modules (decision D5), `services/translator.py` if anything kept imports it, `services/longform_render.py` and `services/loudness.py` (decision D8).

**Edit:**

- `backend/main.py`: remove `dub_core,`, `dub_generate,`, `dub_export,`, `dub_translate,` from the import block and from `_router_modules.extend([...])`. Leave the comment around line 429.
- `backend/api/routers/tools.py`: delete from the comment line containing `Video context analysis` (around line 180) through the end of `async def analyse_video_context(job_id: str):`. The next definition must be `def _decode_workflow_audio(data: bytes):`. If `services/video_context.py` is then listed by R4, delete it.
- `backend/services/model_lifecycle.py`:
  - Delete the block starting with the comment `# 7. Offline translation can remain resident` (around line 269) through `degraded_sources.append("translation")` (around line 286).
  - Delete the block `if model_id == "translation:nllb":` (around line 362) through its `return {"unloaded": model_id, "success": True}`.
  - Around line 412, remove `"translation:nllb"` from the list of model kinds.

**Routes that must disappear:** every snapshot line whose path starts with `/dub/` (42 lines in upstream: 15 from `dub_core`, 25 from `dub_export`, 2 from `dub_generate`, 2 from `dub_translate`, counted by path prefix), plus `GET /preview/{filename}`, `POST /preview/upload`, `POST /tools/video-context/{job_id}`. Not `/jobs` or `/tasks` (Task 13 moved them). Check with `diff <(grep -v '^#' docs/fork/routes-baseline.txt) tests/fixtures/api_routes.txt`.

**_CRITICAL entries to remove:** `POST /dub/upload`, `POST /dub/ingest-url`, `POST /dub/generate/{job_id}`, `POST /dub/translate`, and any other entry starting with `/dub`.

**Tests to delete:** every `tests/test_dub_*.py` and `backend/tests/test_dub_*.py` file, plus `tests/backend/api/routers/test_dub_cleanup_segments_route.py`, `tests/backend/api/routers/test_dub_prosody_mirror_route.py`, `tests/backend/services/test_prosody_mirror.py`, `tests/backend/test_dub_pipeline_wav.py`, `tests/probe/test_probe_dubbing.py`, `tests/test_deleting_a_dub_keeps_dirs_others_use.py`, `tests/test_duration_planner.py`, `tests/test_fit_planner.py`, `tests/test_fitted_subtitles.py`, `tests/test_karaoke_ass.py`, `tests/test_onset_align.py`, `tests/test_redub_incremental.py`, `tests/test_speaker_clone_purity.py`, `tests/test_video_retime_odd_dimensions.py`, `tests/test_smart_fit_export.py`, `tests/test_smart_fit_generate.py`, `tests/test_fit_overlapping_cues.py`, `tests/test_stretch_video_track_strategy.py`, `tests/test_clone_refs_live_in_their_own_job_dir.py`, `tests/test_segment_refs.py`, `tests/test_yt_bot_check_2034.py`, `tests/test_yt_drm_escalation.py`, `tests/test_translate_degraded_not_failed.py`, `tests/test_translator.py` (only if `services/translator.py` was deleted).

**Tests to check:** `backend/tests/test_validation_error_handler.py`, `tests/test_api.py`, `tests/test_arabic_varieties_3816.py`, `tests/test_asr_model_missing.py`, `tests/test_busy_engine_wait.py`, `tests/test_caption_markup_not_speech.py`, `tests/test_ffmpeg_subtitle_filter_path.py`, `tests/test_funasr_global_speaker_chunking.py`, `tests/test_hf_revisions.py`, `tests/test_pitch_stretch_async.py`, `tests/test_portuguese_variants_3143.py`, `tests/test_speaker_hint.py`, `tests/test_subtitle_timestamp_rounding.py`, `tests/test_summersec_backend.py`, `tests/test_text_upload_encoding.py`, `tests/test_torchaudio_io_gate.py`, `tests/test_transcribe_media_tool_failure.py`, `tests/test_tts_placement_self_heal.py`, `tests/test_uyghur_target_2810.py`, `tests/test_video_encoder.py`, `tests/test_webvtt_character_references.py`, `tests/test_webvtt_export_escaping.py`, `tests/test_engine_language_options.py`.

- [ ] 15.1 R1 to R9. This is the biggest task: run R4 and R5 in rounds until both print nothing. Commit message: `chore(fork): remove dubbing`.

---

## Task 16: Remove yt-dlp from media tools

**Why:** no video downloads. ffmpeg and ffprobe management stays.

**Edit:**

- `backend/api/routers/media_tools.py`: delete the comment about literal ytdlp routes (around line 45), `media_tools_ytdlp_update` and `media_tools_ytdlp_restore` with their decorators (lines 48 to 59).
- `backend/services/media_tools.py`: delete `_ytdlp_status`, `_read_ytdlp_version`, `_ytdlp_overlay_dir`, `activate_ytdlp_overlay`, `_fetch_pypi_ytdlp`, `update_ytdlp`, `restore_ytdlp`, the line `tools["ytdlp"] = _ytdlp_status()` (around line 473), and the `"ytdlp_update": {...}` state entry (around line 114). Then `grep -n "ytdlp\|yt_dlp\|yt-dlp" backend/services/media_tools.py`: delete any remaining code that only served yt-dlp. If a remaining hit is shared with ffmpeg handling, stop and report.
- `backend/main.py` (around lines 667 to 669): delete the `try:` block that imports and calls `activate_ytdlp_overlay`.
- `pyproject.toml`: remove the line `"yt-dlp>=2026.7.4",` (around line 100), then `uv lock`.
- If `POST /media-tools/{tool}/restore` or `use-system` or `custom-path` validates tool against a list containing `"ytdlp"`, remove `"ytdlp"` from that list.

**Keep:** mentions of yt-dlp in `core/failure.py` and `core/url_safety.py` (error text only); add a leftovers line.

**Routes that must disappear:** `POST /media-tools/ytdlp/restore`, `POST /media-tools/ytdlp/update`.

**Tests to check:** COLLECT and BASEDIFF will name them (expect tests with `ytdlp` or `media_tools` in their name). Delete only yt-dlp cases.

- [ ] 16.1 R2 to R9 (there is no R1). Also stage `pyproject.toml uv.lock`. Commit message: `chore(fork): remove yt-dlp from media tools`.

---

## Task 17: Remove dictation and live capture

**Delete:** `backend/api/routers/dictation.py`, `backend/api/routers/capture_ws.py`, `backend/api/routers/speech_platform.py`, `backend/speech_client/` (whole package). R4 will then list `services.aec`: delete `backend/services/aec.py`.

**Keep:** `backend/api/routers/capture.py` (`POST /transcribe`, decision D2), `services/sherpa_dictation.py` and `services/dictation_cleanup.py` (`capture.py` and the ASR and performance modules still import them; add leftovers lines). The dictation warm-up code in `main.py` (around lines 468 to 500 and 1160 to 1200) is the capture ASR warm-up: keep it.

**Edit:**

- `backend/main.py`: remove `capture_ws,`, `speech_platform,`, `dictation,` from the import block and from `_router_modules.extend([...])`. Keep `capture`.
- `backend/api/routers/capture.py` (around line 170), the nested function `_hint_kwargs` reads:

```python
        def _hint_kwargs(backend) -> dict:
            if not apply_hint:
                return {}
            from api.routers.dictation import dictation_transcribe_kwargs
            return dictation_transcribe_kwargs(backend)
```

Replace its body so it is:

```python
        def _hint_kwargs(backend) -> dict:
            # Dictation hints came from the removed dictation router.
            return {}
```

Leave `apply_hint` and the `dictation` form field in place (the API shape stays the same).

**Routes that must disappear (7):** `GET /dictation/models`, `GET /dictation/prefs`, `GET /dictation/readiness`, `POST /dictation/prefs`, `GET /.well-known/voicestudio-speech`, `GET /v1/audio/capabilities`, `WS /ws/transcribe`.

**Must stay:** `POST /transcribe`. Task 3's tests enforce it.

**Tests to delete:** `backend/tests/test_capture_ws.py`, `backend/tests/test_dictation_model_demotion.py`, `backend/tests/test_dictation_silent_model.py`, `tests/backend/api/routers/test_capture_ws_aec.py`, `tests/backend/services/test_aec.py`, `tests/probe/test_probe_dictation.py`, `tests/test_capture_ws.py`, `tests/test_dictation_prompt.py`, `tests/test_dictation_recovery_tail_bound.py`, `tests/test_dictation_router.py`, `tests/test_sherpa_ws_streaming.py`, `tests/test_speech_client.py`, `tests/test_speech_client_boundaries.py`, `tests/test_speech_platform.py`.

**Tests to check:** `tests/test_capture_null_segment_end.py`, `tests/test_model_acceptance_asr.py`, `tests/test_ws_authorization.py`, `tests/test_dictation_cleanup.py` and `tests/test_sherpa_dictation.py` (their modules stay, so these should still pass; delete only cases that import the removed routers).

- [ ] 17.1 R1 to R9. Then run `env $T uv run --no-sync pytest tests/test_fork_mcp_routes.py -q` once more. Expected: pass. Commit message: `chore(fork): remove dictation and live capture`.

---

## Task 18: Remove audiobook, stories and long-form jobs

**Delete:** `backend/api/routers/audiobook.py`, `backend/api/routers/stories.py`, `backend/api/routers/longform_jobs.py`. R4 will list some of: `services/audiobook.py`, `services/longform_import.py`, `services/longform_progress.py`, `services/longform_resume.py`, `services/text_upload.py`, `services/longform_parser.py`, `services/ssml_lite.py`: delete those. R4 may also list `services/loudness.py`: do not delete it (decision D8); add it to `docs/fork/orphans-baseline.txt` with a comment-free line so ORPHANS stops listing it, and mention it in your report.

**Keep:** `services/longform_render.py` (`main.py` imports `record_startup_voices_root` from it, and its loudnorm builders feed Phase 4), `services/loudness.py`, `services/chunked_tts.py` (generation uses it).

**Edit:** `backend/main.py`: remove `stories,`, `audiobook,`, `longform_jobs,` from the import block and from `_router_modules.extend([...])`.

**Routes that must disappear (11):** `GET /audiobook/jobs`, `POST /audiobook`, `POST /audiobook/cover`, `POST /audiobook/import`, `POST /audiobook/plan`, `POST /audiobook/preview`, `POST /audiobook/resume/{job_id}`, `POST /longform/render`, `DELETE /longform/jobs/{job_id}`, `GET /longform/jobs`, `POST /stories/encode`.

**_CRITICAL entries to remove:** `POST /audiobook`, `POST /stories/encode`.

**Tests to delete:** every `tests/test_audiobook*.py`, `backend/tests/test_audiobook_resume_api.py`, `backend/tests/test_longform_import_*.py`, and in `tests/`: `test_longform_cache_portable_2279.py`, `test_longform_e2e.py`, `test_longform_import.py`, `test_longform_jobs.py`, `test_longform_language_cache.py`, `test_longform_limits.py`, `test_longform_parser.py`, `test_longform_progress_3417.py`, `test_longform_resume.py`, `test_longform_segment_cache.py`, `test_longform_synth_params.py`, `test_ssml_lite.py`, `test_stories_encode.py`.

**Tests to keep:** `tests/test_longform_render.py`, `tests/test_loudness.py` (their modules stay).

**Tests to check:** `tests/test_cache_metadata_regression.py`, `tests/test_epub_member_uris.py`, `tests/test_ffmetadata_line_breaks.py`, `tests/test_inline_override_chapters_3561.py`, `tests/test_job_store_chapters_3562.py`, `tests/test_library_filter_regression.py`, `tests/test_pause_fill.py`, `tests/test_profile_language_propagation.py`, `tests/test_render_trace.py`, `tests/test_resume_handoff_regression.py`, `tests/test_stream_keepalive.py`, `tests/test_text_normalization.py`.

- [ ] 18.1 R1 to R9. Commit message: `chore(fork): remove audiobook, stories and long-form`.

---

## Task 19: Remove sound effects (returns in Phase 7)

**Delete:** `backend/api/routers/sfx.py`, `backend/engines/moss_sfx/` (whole package).

**Edit:**

- `backend/main.py`: remove the line `sfx,  # Tools > Sound effects (#3577): opt-in MOSS-SoundEffect sidecar` from the import block and `sfx` from `_router_modules.extend([...])`.
- `backend/services/sidecar_install.py`: delete `_sfx_installed` and `_sfx_host` (around lines 419 to 427) and the whole `"moss-soundeffect": SidecarSpec(...)` entry (around line 652, up to the closing `),` of that entry).
- `backend/api/routers/generation.py`: search for `"sfx"`. The history feature field may mention it; leave plain strings, delete only code that imports from `engines.moss_sfx`.

**Keep:** the `OpenMOSS-Team/MOSS-SoundEffect-v2.0` entry in `models.yaml` (Task 25 decides).

**Routes that must disappear:** `GET /api/sfx/status`, `POST /api/sfx/generate`.

**Tests to delete:** `tests/test_sfx.py`. **Tests to check:** `tests/test_sidecar_install.py`.

- [ ] 19.1 R1 to R9. Commit message: `chore(fork): remove sound effects for now`.

---

## Task 20: Drop unused Python dependencies

**Why:** smaller installs, fewer licences to track.

**Edit:** `pyproject.toml`, `uv.lock`.

- [ ] 20.1 Make a candidate list. For each package below, run the import check shown and note the ones with no output:

| Package in pyproject | Import name to grep |
|---|---|
| `gradio_client` | `gradio_client` |
| `twilio` (if present) | `twilio` |
| `posthog` (if present) | `posthog` |
| `ebooklib` (if present) | `ebooklib` |
| `argostranslate` (if present) | `argostranslate` |
| `demucs` (if present) | `demucs` |
| `kittentts` (if present) | `kittentts` |
| `moonshine*` (if present) | `moonshine` |
| `funasr` (if present) | `funasr` |

Command: `git grep -nE "^\s*(import|from) <import name>\b" -- backend omnivoice`.

- [ ] 20.2 For each package with no hits, delete its line from `pyproject.toml` (main dependencies or an optional group). Never remove: `torch`, `torchaudio`, `transformers`, `mlx*`, `fastapi`, `uvicorn`, `numpy`, `soundfile`, `huggingface_hub`, `faster-whisper`, `whisperx`, `pyannote*` (decision D5), `sherpa-onnx` (decision D5 keeps its module).
- [ ] 20.3 `uv lock && uv sync`. Expected: both exit 0.
- [ ] 20.4 IMPORT, BASEDIFF. `tests/backend/test_pyproject.py` may pin dependency names; update its expected list only for packages you removed.
- [ ] 20.5 Commit `pyproject.toml uv.lock` (plus that test if changed): `chore(fork): drop unused dependencies`. List the removed packages in the commit body.

---

## Task 21: Prune the TTS engine registry

**Why:** the registry must equal the game-dev set exactly.

**Delete (packages):** `backend/engines/confucius4/`, `backend/engines/ming_tts/`, `backend/engines/moss_tts_nano_subprocess/`, `backend/engines/supertonic3/`.

**Keep (packages, decision D7):** `backend/engines/omnivoice_gguf/`, `backend/engines/omnivoice_subprocess/`.
**Keep (class):** `AudioCPPBackend` in `backend/engines/audiocpp/__init__.py`. `AudioCPPDotsBackend` subclasses it, so only the `"audiocpp"` registry key goes. Add a leftovers line for the Breeze code.

**Create:** `tests/test_fork_engines.py`.

**Edit `backend/services/tts_backend.py`:**

1. `_LAZY_REGISTRY` (around line 4111): delete the entries (and the comment lines directly above each) for `"omnivoice-gguf"`, `"supertonic3"`, `"omnivoice-subprocess"`, `"confucius4-tts"`, `"ming-tts"`, `"audiocpp"`. Keep `"audiocpp-dots"`.
2. `_REGISTRY` (around line 4225): delete `"kittentts"`, `"moss-tts-nano"`, `"sherpa-onnx"`.
3. `_INSTALL_HINTS` (around line 4252), `_SETUP_SNIPPETS` (around line 4284), `_ENGINE_DOCS` (around line 4304): delete the entry for each removed id: `kittentts`, `moss-tts-nano`, `sherpa-onnx`, `supertonic3`, `confucius4-tts`, `ming-tts`, `omnivoice-gguf`, `omnivoice-subprocess`, `audiocpp`.
4. `_OWN_VENV_SIDECARS` (around line 4618): delete the `"moss-tts-nano"` entry.
5. `list_backends()` (around line 4464): delete the two lines `if not include_hidden and caps.family == "mps" and bid == "omnivoice-subprocess": / continue`.
6. Delete these top-level definitions. Get exact line ranges first with:

```bash
python3 - <<'PY'
import ast
src = open("backend/services/tts_backend.py").read()
for n in ast.parse(src).body:
    if getattr(n, "name", "") in {"MossTTSNanoBackend", "KittenTTSBackend", "SherpaOnnxBackend",
                                  "_sherpa_model_file", "_sherpa_vits_extras"}:
        print(n.name, n.lineno, n.end_lineno)
PY
```

Upstream answer: `MossTTSNanoBackend` 2433-2547, `KittenTTSBackend` 2553-2749, `_sherpa_model_file` 3931-3949, `_sherpa_vits_extras` 3952-3967, `SherpaOnnxBackend` 3970-4098. Delete bottom-up (highest line numbers first) so earlier numbers stay valid. Also delete any comment banner directly above each deleted class (lines starting with `# --` or `# ==`).
7. Run `git grep -nE '"(kittentts|moss-tts-nano|sherpa-onnx|supertonic3|confucius4-tts|ming-tts|omnivoice-gguf|omnivoice-subprocess|audiocpp)"' -- backend/services/tts_backend.py` and remove remaining dictionary entries keyed by those ids. Leave `"sherpa-onnx"` strings that belong to ASR code.

**Edit other files:**

8. `backend/services/sidecar_install.py`: delete `_confucius4_invalidate`, `_confucius4_installed`, `_ming_invalidate`, `_ming_installed` (around lines 225 to 251) and the `SidecarSpec` entries `"confucius4-tts"`, `"ming-tts"`, `"supertonic3"`, `"moss-tts-nano"` (around lines 556, 619, 687, 752; each entry ends at its closing `),`).
9. `backend/api/routers/engines.py`: delete from `class GGUFQuantRequest(BaseModel):` (around line 481, plus any section comment directly above it) up to, but not including, the comment line containing `One-click sidecar-engine install` (around line 553). Keep the `omnivoice_gguf.compute` import near line 918 (decision D7).
10. `backend/api/routers/settings.py`: delete from the comment line containing `OmniVoice GGUF resident server` (around line 248) up to, but not including, the comment line containing `Pause fill` (around line 292).

**Leave alone:** string mentions of removed ids in `services/performance_*.py`, `services/engine_disk_usage.py`, `core/engine_licenses.py`, `services/model_acceptance.py`, `core/health_device.py`, `api/routers/engines.py` lines 49 and 73. They are dictionary data and do not import anything. Add one leftovers line listing these files.

**Routes that must disappear (7):** `GET /engines/omnivoice-gguf/gpu-offer`, `GET /engines/omnivoice-gguf/quants`, `POST /engines/omnivoice-gguf/gpu-offer`, `POST /engines/omnivoice-gguf/quants/download`, `POST /engines/omnivoice-gguf/quants/select`, `GET /api/settings/perf/gguf-resident`, `PUT /api/settings/perf/gguf-resident`.

**Tests to delete:** `tests/test_confucius4_scaffold.py`, `tests/test_confucius4_sidecar.py`, `tests/test_kitten_input_shape_1173.py`, `tests/test_ming_tts.py`, `tests/test_moss_tts_nano_subprocess.py`, `tests/test_moss_tts_nano_transformers5_3851.py`, `tests/test_supertonic3.py`, `tests/test_supertonic3_language_names.py`, plus any test file whose name contains `gguf_quant`, `gpu_offer` or `gguf_resident`.

**Tests to check:** `tests/backend/services/test_tts_backend_language_enforcement_2104.py`, `tests/backend/services/test_tts_backend_registry.py`, `backend/tests/test_omnivoice_subprocess.py`, `tests/test_openai_speech_unsupported_knobs_3654.py`, `tests/test_preset_voices_2938.py`, `tests/test_rocm_custom_mirrors.py`, `tests/test_sidecar_install.py`.

- [ ] 21.1 Create `tests/test_fork_engines.py`:

```python
KEPT_TTS = {"omnivoice", "mlx-audio", "voxcpm2", "cosyvoice", "cosyvoice-gguf", "indextts2",
            "dots-tts", "audiocpp-dots", "moss-tts-v15", "qwen3-tts", "gpt-sovits", "pockettts"}
KEPT_ASR = {"mlx-whisper", "faster-whisper", "faster-whisper-isolated", "whisperx",
            "parakeet-mlx", "nemo-parakeet"}


def test_tts_registry_is_exactly_kept():
    from services import tts_backend
    assert set(tts_backend._REGISTRY) == KEPT_TTS


def test_every_kept_tts_engine_resolves():
    from services import tts_backend
    for engine_id in KEPT_TTS:
        assert tts_backend._REGISTRY[engine_id] is not None
```

- [ ] 21.2 Run it. Expected: `test_tts_registry_is_exactly_kept` fails.
- [ ] 21.3 Make every edit above, then R3 to R9. Run `tests/test_fork_engines.py`: 2 passed. Commit message: `feat(fork): prune TTS engines to the game-dev set`.

---

## Task 22: Hide OmniVoice, platform default engine, safe fallback

**Edit:** `backend/services/tts_backend.py`. **Edit:** `tests/test_fork_engines.py`.

**Interfaces** (produced here; Phases 2 and 3 import them by these exact names):

- `HIDDEN_TTS: frozenset[str] = frozenset({"omnivoice"})`, module level, next to `_REGISTRY`.
- `def default_tts_backend_id() -> str`: returns `"mlx-audio"` when `sys.platform == "darwin" and platform.machine() == "arm64"`, otherwise `"voxcpm2"`.
- `def active_backend_id() -> str`: same signature as now.

- [ ] 22.1 Append to `tests/test_fork_engines.py`:

```python
import platform
import sys

import pytest


def test_omnivoice_hidden_from_default_listing():
    from services import tts_backend
    assert "omnivoice" not in {b["id"] for b in tts_backend.list_backends()}
    assert "omnivoice" in {b["id"] for b in tts_backend.list_backends(include_hidden=True)}


@pytest.mark.parametrize("plat,machine,expected", [
    ("darwin", "arm64", "mlx-audio"),
    ("darwin", "x86_64", "voxcpm2"),
    ("linux", "x86_64", "voxcpm2"),
    ("win32", "AMD64", "voxcpm2"),
])
def test_default_engine_by_platform(monkeypatch, plat, machine, expected):
    from services import tts_backend
    monkeypatch.setattr(sys, "platform", plat)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert tts_backend.default_tts_backend_id() == expected


def _with_saved_engine(monkeypatch, value):
    from core import prefs
    real_get = prefs.get
    monkeypatch.setattr(prefs, "get",
                        lambda key, default=None: value if key == "tts_backend" else real_get(key, default))
    monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)


def test_saved_removed_engine_falls_back_to_default(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "kittentts")
    assert tts_backend.active_backend_id() == tts_backend.default_tts_backend_id()


def test_nothing_saved_uses_default(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, None)
    assert tts_backend.active_backend_id() == tts_backend.default_tts_backend_id()


def test_saved_valid_engine_is_kept(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "cosyvoice")
    assert tts_backend.active_backend_id() == "cosyvoice"


def test_env_override_wins(monkeypatch):
    from services import tts_backend
    _with_saved_engine(monkeypatch, "cosyvoice")
    monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "voxcpm2")
    assert tts_backend.active_backend_id() == "voxcpm2"
```

- [ ] 22.2 Run it. Expected: the new tests fail.
- [ ] 22.3 Implement in `tts_backend.py`:
  - `HIDDEN_TTS` right after the `_REGISTRY = _LazyRegistry({...})` statement.
  - `default_tts_backend_id()` just above `def active_backend_id()`. Import `platform` and `sys` at the top of the file if they are not already imported (`grep -n "^import platform\|^import sys"`). Read `sys.platform` and `platform.machine()` inside the function each time (not at import), or the monkeypatched test cannot see them.
  - Replace the body of `active_backend_id()` with:

```python
    # Env var > persisted UI choice > platform default. An id that is no longer
    # registered (an engine removed by the fork) falls back to the default.
    from core import prefs
    default = default_tts_backend_id()
    chosen = prefs.resolve("tts_backend", env="OMNIVOICE_TTS_BACKEND", default=default)
    if chosen not in _REGISTRY:
        logger.warning("Saved TTS engine %r is not available in this build; using %r", chosen, default)
        return default
    return chosen
```

  - In `list_backends()`, inside the `for bid, cls in _REGISTRY.items():` loop, add as the first statement: `if not include_hidden and bid in HIDDEN_TTS: / continue`.

- [ ] 22.4 Run `tests/test_fork_engines.py`. Expected: all pass.
- [ ] 22.5 `git grep -n 'default="omnivoice"\|or "omnivoice"' -- backend`. For each hit that picks a default TTS engine (not a model path or a log message), replace the literal with a call to `default_tts_backend_id()` (import it from `services.tts_backend` inside the function). List each change in your report. If unsure whether a hit is a TTS default, leave it and report it.
- [ ] 22.6 BASEDIFF. Upstream tests that assert the default is `"omnivoice"` are expected to fail: change only their expected value to `default_tts_backend_id()` or the platform-correct id.
- [ ] 22.7 Commit `backend/services/tts_backend.py tests/test_fork_engines.py` (plus files from 22.5 and 22.6): `feat(fork): platform default engine, hidden OmniVoice, safe fallback`.

---

## Task 23: mlx-audio defaults to VoxCPM2

**Edit:** `MLXAudioBackend` in `backend/services/tts_backend.py`; `tests/test_fork_engines.py`.

- [ ] 23.1 Append:

```python
def test_mlx_audio_defaults_to_voxcpm2():
    from services.tts_backend import MLXAudioBackend, _MLX_AUDIO_MODEL_LABELS
    assert MLXAudioBackend.DEFAULT_MODEL_KEY == "voxcpm2"
    assert MLXAudioBackend.CURATED_MODELS["voxcpm2"] == "mlx-community/VoxCPM2-8bit"
    for key in ("melotts", "outetts"):
        assert key not in MLXAudioBackend.CURATED_MODELS
        assert key not in MLXAudioBackend.CURATED_MODEL_LANGUAGES
        assert key not in _MLX_AUDIO_MODEL_LABELS
```

- [ ] 23.2 Run: FAIL. Then edit:
  - `DEFAULT_MODEL_KEY = "kokoro"` (around line 3090) becomes `DEFAULT_MODEL_KEY = "voxcpm2"`.
  - In `CURATED_MODELS` (around line 3079) delete the `"melotts"` and `"outetts"` lines.
  - In `CURATED_MODEL_LANGUAGES` delete the `"melotts"` entry and the multi-line `"outetts"` entry. Delete their two source-comment lines in the comment block above it.
  - In `_MLX_AUDIO_MODEL_LABELS` (around line 4348) delete the `melotts` and `outetts` entries.
  - In the class docstring, change `Default is Kokoro (82M, multilingual, small).` to `Default is VoxCPM2 8-bit (game-dev fork).` and remove MeloTTS and OuteTTS from the engine list in the docstring and in `display_name`.
  - `git grep -n "melotts\|outetts\|MeloTTS\|OuteTTS" -- backend`: remove remaining code entries; leave catalogue entries for Task 25.
- [ ] 23.3 Run: pass. BASEDIFF: tests asserting Kokoro is the default change their expected value to `"voxcpm2"`; tests about MeloTTS or OuteTTS lose those cases.
- [ ] 23.4 Commit: `feat(fork): VoxCPM2 is the mlx-audio default`.

---

## Task 24: Prune the ASR registry

**Edit:** `backend/services/asr_backend.py`; `tests/test_fork_engines.py`.

- [ ] 24.1 Append:

```python
def test_asr_registry_is_exactly_kept():
    from services import asr_backend
    assert set(asr_backend._REGISTRY) == KEPT_ASR
```

- [ ] 24.2 Run: FAIL. Then edit:
  - `_REGISTRY = _LazyASRRegistry({...})` (around line 2985): delete `"pytorch-whisper"`, `"moonshine"`, `"funasr"`, `"sherpa-onnx-asr"`, `"openai-compat-asr"`.
  - `_LAZY` in `_LazyASRRegistry` (around line 2948): delete `"whisper-cpp"`.
  - `_INSTALL_HINTS` (just below): delete the same six ids.
  - Do not delete the backend classes. Kept code (`capture.py`, `sherpa_dictation`, performance modules) still references some of them. Add one leftovers line naming the six classes.
- [ ] 24.3 Add the same "saved id not registered falls back" behaviour as Task 22 if the ASR resolver lacks it: find the function that reads the saved ASR choice (`grep -n 'prefs.resolve("asr_backend"\|resolve("asr' backend/services/asr_backend.py`). If a saved id that is not in `_REGISTRY` would raise, make it fall back to the existing default and add a test like `test_saved_removed_engine_falls_back_to_default` using key `"asr_backend"` and value `"moonshine"`. If it already falls back, add only the test.
- [ ] 24.4 BASEDIFF. Tests named after the removed backends (`test_moonshine*`, `test_funasr*`, `test_pytorch_whisper*`, `test_whisper_cpp*`, `test_openai_compat_asr*`, `test_asr_openai_compat_877.py`) fail: delete only their cases that need the registry entry; if a whole file is about one removed backend, delete the file.
- [ ] 24.5 Commit: `feat(fork): prune ASR engines`.

---

## Task 25: Model catalogue and licence records

**Edit:** `backend/config/models.yaml`, `backend/config/model_licenses.json`, `tests/test_fork_engines.py`.

**KEEP set** (top-level `repo_id`s that must remain): `k2-fsa/OmniVoice`, `audio-cpp/audio.cpp-gguf` (the `:dots-tts-soar-q8_0` package entry), `openbmb/VoxCPM2`, `mlx-community/VoxCPM2-8bit`, `FunAudioLLM/Fun-CosyVoice3-0.5B-2512`, `Lourdle/Fun-CosyVoice3-0.5B-2512-GGUF`, `lj1995/GPT-SoVITS`, `mlx-community/Kokoro-82M-bf16`, `mlx-community/csm-1b-8bit`, `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`, `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit`, `mlx-community/Dia-1.6B`, `mlx-community/Chatterbox-TTS-4bit`, `mlx-community/whisper-large-v3-turbo`, `mlx-community/whisper-tiny-mlx`, `deepdml/faster-whisper-large-v3-turbo-ct2`, `Systran/faster-whisper-base`, `nvidia/parakeet-tdt-0.6b-v3`, `mlx-community/parakeet-tdt-0.6b-v3`, `pyannote/speaker-diarization-3.1` (decision D5).

**REMOVE candidates** (in this order): `mlx-community/Llama-OuteTTS-1.0-1B-4bit`, `mlx-community/MeloTTS-English-v3-MLX`, `KittenML/kitten-tts-mini-0.8`, `OpenMOSS-Team/MOSS-TTS-Nano-100M`, `inclusionAI/Ming-3.0-tts-0.5b`, `OpenMOSS-Team/MOSS-SoundEffect-v2.0`, `UsefulSensors/moonshine-base`, `UsefulSensors/moonshine-tiny`, the five `csukuangfj/sherpa-onnx-*` entries, `facebook/nllb-200-distilled-600M`, `openai/whisper-large-v3`, `mlx-community/whisper-large-v3-mlx`, `mlx-community/whisper-large-v3-turbo-asr-fp16`, `Systran/faster-whisper-large-v3`, `Systran/faster-distil-whisper-large-v3`, `Systran/faster-whisper-medium`, `Systran/faster-whisper-small`, `nvidia/parakeet-tdt-0.6b-v2`, the Breeze package entry of `audio-cpp/audio.cpp-gguf`.

- [ ] 25.1 For each REMOVE candidate, in order:
  1. Delete its entry from `models.yaml` (the `- repo_id:` line through the line before the next `- repo_id:` at the same indent; for multi-package repos, the entry whose id matches).
  2. Delete the record with the matching id from the `"models"` list in `model_licenses.json`.
  3. Run `uv run --no-sync python scripts/check_model_licenses.py`. Expected: exit 0.
  4. If it fails naming a source file that hard-codes this model, undo steps 1 and 2 for this candidate (`git checkout -p` the hunks), add a leftovers line `- <repo_id>: hard-coded in <file> (Task 25)`, and continue with the next candidate.
- [ ] 25.2 Move `required: true` from the `k2-fsa/OmniVoice` entry to the `openbmb/VoxCPM2` entry. Add `curated_on: [darwin-arm64]` to `mlx-community/VoxCPM2-8bit` (merge with an existing `curated_on` list if present). Run the checker again.
- [ ] 25.3 In `model_licenses.json`, for each kept record whose `"engines"` list names a removed engine id (for example `"omnivoice-subprocess"` on OmniVoice), remove that id from the list. Run the checker.
- [ ] 25.4 Append to `tests/test_fork_engines.py`:

```python
from pathlib import Path

import yaml

_MODELS_YAML = Path(__file__).resolve().parents[1] / "backend" / "config" / "models.yaml"


def _catalogue():
    data = yaml.safe_load(_MODELS_YAML.read_text())
    return data["models"] if isinstance(data, dict) else data


def test_catalogue_engines_all_kept():
    for entry in _catalogue():
        assert set(entry.get("engines") or []) <= KEPT_TTS | KEPT_ASR | {"pyannote", "sortformer"}, entry["repo_id"]


def test_voxcpm2_is_the_required_model():
    required = [e["repo_id"] for e in _catalogue() if e.get("required")]
    assert required == ["openbmb/VoxCPM2"]
```

Run it. If `test_catalogue_engines_all_kept` fails only because of an entry kept in 25.1 step 4, add that entry's engine id to the allowed set with a comment `# leftover: see docs/fork/leftovers.md`. Check how the yaml is structured first (`head -60 backend/config/models.yaml`) and adjust `_catalogue()` if the list key is not `models`.

- [ ] 25.5 Run `tests/test_model_licenses.py`, `tests/backend/test_models_yaml_engines.py`, `tests/test_hf_revisions.py`, then BASEDIFF.
- [ ] 25.6 Commit: `feat(fork): slim model catalogue and licence records`. Body: which candidates were kept and why.

---

## Task 26: Recommendations list only kept models

**Create:** `tests/test_fork_recommendations.py`. Edit `backend/api/routers/setup/models.py` only if the test fails.

- [ ] 26.1 Create the test (helpers copied from upstream `tests/test_setup_recommendations.py`):

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from test_fork_engines import KEPT_ASR, KEPT_TTS

ALLOWED = KEPT_TTS | KEPT_ASR | {"pyannote", "sortformer"}


@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)


def _recommend(client, tags):
    from api.routers.setup import models as setup_models
    with patch.object(setup_models, "_current_platform_tags", return_value=tags):
        response = client.get("/setup/recommendations")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("tags", [
    ["darwin", "darwin-arm64"],
    ["linux", "linux-x86_64", "cuda"],
    ["linux", "linux-x86_64", "cpu"],
])
def test_recommendations_only_use_kept_engines(client, tags):
    for model in _recommend(client, tags)["models"]:
        assert set(model.get("engines") or []) <= ALLOWED, model["repo_id"]


def test_mac_recommends_voxcpm2_8bit(client):
    ids = {m["repo_id"] for m in _recommend(client, ["darwin", "darwin-arm64"])["models"]}
    assert "mlx-community/VoxCPM2-8bit" in ids
```

If `from test_fork_engines import ...` fails because `tests/` is not on `sys.path`, copy the two sets into this file instead.

- [ ] 26.2 Run it. If a model in the response has no `engines` key, look up the response shape with `print(_recommend(client, [...]))` once and match on whatever field names the engine, then remove the print.
- [ ] 26.3 If a test fails because the endpoint returns a removed model, the fix belongs in `models.yaml` (`curated_on`), not in code. Remove that model's `curated_on` tag for that platform.
- [ ] 26.4 BASEDIFF (upstream `tests/test_setup_recommendations.py` may expect removed models; update only those expectations). Commit: `test(fork): recommendations only list kept engines`.

---

## Task 27: CI workflow

**Create:** `.github/workflows/ci.yml`. Remove `.github/workflows/.gitkeep` if Task 7 created it.

- [ ] 27.1 Look up the action SHAs that upstream used, so `tests/test_actions_pinned.py` passes: `git show 8f6c11343:.github/workflows/ | head` then `git grep -h "uses: actions/checkout@\|uses: astral-sh/setup-uv@" 8f6c11343 -- .github/workflows | sort -u | head -4`. Use the same `actions/checkout@<sha> # vX` and `astral-sh/setup-uv@<sha> # vX` lines.
- [ ] 27.2 Write:

```yaml
name: ci
on:
  push:
    branches: [game-dev]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    env:
      HF_HUB_OFFLINE: "1"
      OMNIVOICE_MODEL: test
    steps:
      - uses: actions/checkout@<SHA from 27.1>  # vX
      - uses: astral-sh/setup-uv@<SHA from 27.1>  # vX
      - run: uv sync
      - run: uv run --no-sync pytest tests/ -q -n 4 -p no:randomly
      - run: uv run --no-sync pytest backend/tests/ -q
```

- [ ] 27.3 `env $T uv run --no-sync pytest tests/test_actions_pinned.py -q`. Expected: pass.
- [ ] 27.4 Commit: `ci(fork): single Linux test job`. (Baseline failures will also fail in CI; that is expected until Task 29.)

---

## Task 28: Docs clean-up and link check

**Delete:** `docs/electron-*.md`, `docs/dubbing/`, `docs/DESKTOP_RELEASE.md`, `docs/RELEASING.md`, `docs/STORE-PUBLISHING.md`, `docs/calls.md`, `docs/readme/`, `docs/media/electron/`, every file in `docs/superpowers/plans/` whose name does not start with `2026-11-19-`, and these engine pages if present in `docs/engines/`: `kittentts*`, `moss-tts-nano*`, `supertonic3*`, `confucius4-tts*`, `ming-tts*`, `sherpa-onnx*`, `audiocpp.md` (Breeze; keep any dots page), `omnivoice-gguf*`, `moss-soundeffect*`, `sfx*`.

**Create:** `tests/test_fork_docs_links.py`.

- [ ] 28.1 Create the test:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _markdown_files():
    yield ROOT / "README.md"
    yield from (ROOT / "docs").rglob("*.md")


def test_relative_links_resolve():
    broken = []
    for md in _markdown_files():
        for target in LINK.findall(md.read_text(errors="ignore")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (md.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert broken == []
```

- [ ] 28.2 Run it before deleting anything and save the output to `/tmp/links-before.txt` (upstream may already have broken links).
- [ ] 28.3 Delete the docs above. Run the test again. For each broken link: if it points at a deleted file, remove the link (keep the link text as plain text) or the whole bullet if the bullet is only that link. If it was already broken in 28.2 and points at something unrelated, fix the path if the target exists elsewhere (`git ls-files | grep <file name>`), otherwise remove the link.
- [ ] 28.4 `tests/test_docs_links.py` and `tests/test_docs_drift.py` (upstream) may list files you deleted: remove those expectations only.
- [ ] 28.5 BASEDIFF. Commit: `docs(fork): remove docs for removed features`.

---

## Task 29: Close out Phase 1

**Edit:** `tests/test_fork_no_phone_home.py`, `docs/fork/leftovers.md`, `docs/fork/baseline-tests.txt` (this task only).

- [ ] 29.1 `PENDING` in `tests/test_fork_no_phone_home.py` must be empty. If it is not, each entry's file should now be gone; remove the entry and run the test.
- [ ] 29.2 Run SUITE. For each remaining failure:
  - If its test file is about a feature this phase removed, delete the file or the case.
  - Otherwise leave it and list it in the report.
- [ ] 29.3 Rewrite `docs/fork/baseline-tests.txt` with the current FAILED lines plus a first line `# Phase 1 end state. Upstream baseline: see git history of this file.`.
- [ ] 29.4 Read `docs/fork/leftovers.md` top to bottom and sort it by path. Do not remove entries.
- [ ] 29.5 Commit: `chore(fork): close Phase 1`. In the body, say how many upstream baseline failures disappeared with their code and how many remain.

---

## Task 30: Mac smoke test (Tamair, on the M4 Pro)

Not for an agent: it needs MLX hardware and a 3.3 GB download.

- [ ] 30.1 `git clone` the fork, `uv sync`, then `uv run uvicorn backend.main:app --host 127.0.0.1 --port 3900`. Expected: the server starts and the log names `mlx-audio` as the TTS engine.
- [ ] 30.2 `curl -s http://127.0.0.1:3900/v1/audio/voices | head -c 600` to pick a voice id.
- [ ] 30.3 Render (check the request schema in `backend/api/routers/openai_compat.py` around line 847 if this returns 422):

```bash
curl -s -o /tmp/vf.wav -w '%{http_code}\n' http://127.0.0.1:3900/v1/audio/speech \
  -H 'content-type: application/json' \
  -d '{"model":"voxcpm2","input":"Keep your coin, traveller.","voice":"<voice id>"}'
afinfo /tmp/vf.wav
```

Expected: 200, and `afinfo` shows at least 1 s of audio.

- [ ] 30.4 `curl -s http://127.0.0.1:3900/openapi.json | python3 -c "import json,sys; p=json.load(sys.stdin)['paths']; print([x for x in p if x.startswith(('/dub','/batch','/audiobook','/dictation','/calls','/gallery','/marketplace'))])"`. Expected: `[]`.
- [ ] 30.5 Point an MCP client at `http://127.0.0.1:3900/mcp`. Expected: 9 tools listed.
- [ ] 30.6 Write load time, real-time factor and peak memory (Activity Monitor) into `docs/fork/smoke-mac.md` and commit: `docs(fork): Mac smoke test results`.

---

## Modules touched in Phase 1

`backend/main.py`; `backend/api/routers/` (removed routers, plus edits to `settings`, `generation`, `capture`, `engines`, `tools`, `media_tools`, `projects`, new `jobs.py`); `backend/services/` (`tts_backend`, `asr_backend`, `model_manager`, `model_lifecycle`, `sidecar_install`, `media_tools`, removed feature services); `backend/engines/`; `backend/core/` (analytics removed; `diagnostic_reports`, `error_journal` edited); `backend/config/`; `config/`; `pyproject.toml`, `uv.lock`, `package.json`; `tests/`, `backend/tests/`; `scripts/`; `docs/`; `.github/`; root files.
