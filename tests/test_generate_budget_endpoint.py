"""GET /generate/budget reports the active budgets."""
from __future__ import annotations


def test_operator_overrides_are_reported(monkeypatch):
    from services import model_manager

    monkeypatch.setattr(model_manager, "GPU_QUEUE_TIMEOUT_S", 7200.0)
    monkeypatch.setattr(model_manager, "CPU_JOB_TIMEOUT_S", 4000.0)
    monkeypatch.setenv("OMNIVOICE_MODEL_LOAD_TIMEOUT", "9000")
    budget = model_manager.generate_budget_s()
    assert budget["queueWait"] == 7200.0
    assert budget["executionBase"] >= 4000.0
    assert budget["modelLoad"] == 9000.0


def test_route_is_registered():
    from api.routers import generation

    paths = {(route.path, tuple(sorted(route.methods))) for route in generation.router.routes}
    assert ("/generate/budget", ("GET",)) in paths
