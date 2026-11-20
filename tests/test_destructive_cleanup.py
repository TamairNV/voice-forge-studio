"""Destructive endpoints must not report success when file cleanup fails."""
from contextlib import contextmanager
import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def app_modules():
    """Resolve application modules at test time to avoid stale import state."""
    return SimpleNamespace(
        system=importlib.import_module("api.routers.system"),
    )


@pytest.mark.asyncio
async def test_tauri_log_clear_reports_truncate_failure(monkeypatch, tmp_path, app_modules):
    system = app_modules.system
    log = tmp_path / "webview.log"
    log.write_text("data", encoding="utf-8")
    monkeypatch.setattr(system, "_tauri_log_candidates", lambda: [str(log)])
    # Clear now goes through the plugin-log half only, so patching the
    # composite alone no longer reaches it. Patching both keeps this honest
    # against the pre-split code too; without it the real resolver is
    # consulted and the result depends on whether the machine running the
    # test happens to have a shell log on disk.
    monkeypatch.setattr(
        system, "_tauri_plugin_log_candidates", lambda: [str(log)], raising=False
    )
    monkeypatch.setattr(
        system,
        "_truncate_file",
        lambda _path: (_ for _ in ()).throw(PermissionError("locked")),
    )

    with pytest.raises(HTTPException) as caught:
        await system.clear_tauri_logs()

    assert caught.value.status_code == 500
    assert str(log) not in caught.value.detail
