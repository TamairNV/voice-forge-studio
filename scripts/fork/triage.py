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
