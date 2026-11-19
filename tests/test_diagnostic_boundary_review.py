"""Operation ownership and expected outcomes at local diagnostic boundaries."""
from collections import OrderedDict
import json

from test_diagnostic_reports import reporter  # noqa: F401


def test_journal_keeps_local_entry_when_diagnostic_exception_inspection_raises(reporter, monkeypatch, tmp_path):
    from starlette.exceptions import HTTPException
    from core import error_journal

    class BrokenStatusError(HTTPException):
        @property
        def status_code(self):
            raise RuntimeError("unreadable exception metadata")

        @status_code.setter
        def status_code(self, value):
            pass

        def __str__(self):
            return "synthetic journal failure"

    monkeypatch.setattr(error_journal, "JOURNAL_PATH", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(error_journal, "_entries", OrderedDict())
    reporter.consent(True)
    entry = error_journal.record(BrokenStatusError(500), route="/api/generate")
    assert entry["type"] == "BrokenStatusError"
    assert entry in error_journal.recent()
    saved = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved == [entry]
