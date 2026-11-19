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
