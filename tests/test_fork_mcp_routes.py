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
