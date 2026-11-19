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
