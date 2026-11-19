"""Other websites must not drive the local API (core.browser_guard).

A page the user visits can send form POSTs, no-cors fetches and WebSocket
handshakes to 127.0.0.1:3900, or rebind its own hostname onto it. These tests
pin the refusal paths and, just as importantly, that the first-party UI and
non-browser clients keep working.
"""
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import pytest
from starlette.websockets import WebSocketDisconnect

LOOPBACK = ("127.0.0.1", 1)
EVIL = "https://evil.example"
PUBLIC_IP = "93.184.215.14"


def _client(base_url="http://testserver", client=LOOPBACK):
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, base_url=base_url, client=client)


# A UI on another allowed origin (OMNIVOICE_PUBLIC_API_BASE deployments) loads
# media and downloads with plain GETs: browsers send no Origin there, only
# Sec-Fetch-Site and the page's Referer.
_MEDIA_GET = "/audio/not-an-id.ogg"  # the route 404s before touching disk or DB
_UI = "https://ui.example"


@pytest.mark.parametrize("site", ["same-site", "cross-site"])
def test_media_get_from_an_allowed_ui_origin_passes_by_referer(monkeypatch, site):
    monkeypatch.setenv("OMNIVOICE_ALLOWED_ORIGINS", _UI)
    response = _client().get(
        _MEDIA_GET, headers={"Sec-Fetch-Site": site, "Referer": f"{_UI}/dub?tab=export"}
    )
    assert response.status_code == 404  # reached the route, which has no such audio


@pytest.mark.parametrize(
    "referer",
    [
        None,  # suppressed by the page (Referrer-Policy: no-referrer)
        f"{EVIL}/page",
        "https://ui.example.evil.example/",  # not an exact origin match
        "http://ui.example/",  # scheme differs
        "https://ui.example:8443/",  # port differs
        "https://ui.example@evil.example/",  # userinfo
        "null",
        "not a url",
    ],
)
@pytest.mark.parametrize("site", ["same-site", "cross-site"])
def test_media_get_with_a_missing_or_foreign_referer_is_refused(monkeypatch, site, referer):
    monkeypatch.setenv("OMNIVOICE_ALLOWED_ORIGINS", _UI)
    headers = {"Sec-Fetch-Site": site}
    if referer is not None:
        headers["Referer"] = referer
    response = _client().get(_MEDIA_GET, headers=headers)
    assert response.status_code == 403
    assert "another website" in response.json()["detail"]


def test_referer_never_overrides_a_foreign_origin(monkeypatch):
    monkeypatch.setenv("OMNIVOICE_ALLOWED_ORIGINS", _UI)
    response = _client().get(
        _MEDIA_GET, headers={"Origin": EVIL, "Sec-Fetch-Site": "cross-site", "Referer": f"{_UI}/"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "same-origin", "Referer": f"{EVIL}/"},
        {"Sec-Fetch-Site": "none"},
        {},
    ],
)
def test_same_origin_and_non_browser_media_gets_are_unaffected_by_referer(headers):
    assert _client().get(_MEDIA_GET, headers=headers).status_code == 404


def test_cross_site_post_cannot_enable_lan_sharing(monkeypatch):
    from services import network_share

    called = []

    async def fake_enable(app):
        called.append(app)
        return network_share.ShareState()

    monkeypatch.setattr(network_share, "enable", fake_enable)
    response = _client().post(
        "/system/network/enable",
        headers={"Origin": EVIL, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 403
    assert called == []
    assert _client().post("/system/network/enable").status_code == 200
    assert len(called) == 1


def test_cross_site_reads_do_not_get_cors_access_to_the_pin():
    response = _client().get("/system/network/state", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in response.headers


def test_side_effectful_get_refuses_cross_site_but_navigation_to_the_shell_works():
    client = _client()
    blocked = client.get("/setup/preflight", headers={"Sec-Fetch-Site": "cross-site"})
    assert blocked.status_code == 403
    assert client.get("/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_side_effectful_get_routes_carry_the_cross_site_dependency():
    from main import app

    from core.browser_guard import reject_cross_site_get

    expected = {
        "/history",
        "/archetypes/{archetype_id}/preview",
        "/setup/preflight",
        "/models/access/status",
        "/audio/{audio_id}.ogg",
        "/audio/{audio_id}.opus",
        "/audio/{audio_id}.mp3",
        "/profile-images/search",
        "/api/settings/hf-token/state",
        "/api/settings/storage",
        "/api/settings/perf/offload-after-generation",
        "/api/settings/perf/gguf-resident",
        "/system/tailscale/status",
    }
    guarded = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = list(dependant.dependencies)
        while stack:
            dep = stack.pop()
            if dep.call is reject_cross_site_get:
                guarded.add(route.path)
            stack.extend(dep.dependencies)
    assert expected <= guarded


def test_websocket_from_another_site_is_refused():
    with pytest.raises(WebSocketDisconnect):
        with _client().websocket_connect("/ws/events", headers={"Origin": EVIL}) as ws:
            ws.receive_text()
    with pytest.raises(WebSocketDisconnect):
        with _client().websocket_connect("/ws/tts", headers={"Origin": "null"}) as ws:
            ws.receive_text()


@pytest.mark.parametrize("headers", [{}, {"Origin": "app://voicestudio"}, {"Origin": "http://testserver"}])
def test_websocket_from_the_app_or_a_non_browser_client_connects(headers):
    with _client().websocket_connect("/ws/tts", headers=headers) as ws:
        ws.send_json({})
        assert ws.receive_json()["type"] == "error"


# ── DNS rebinding (Host allowlist) ───────────────────────────────────────


@pytest.fixture
def default_hosts(monkeypatch):
    for name in (
        "OMNIVOICE_ALLOWED_HOSTS",
        "OMNIVOICE_ALLOWED_ORIGINS",
        "OMNIVOICE_MCP_ALLOWED_HOSTS",
        "OMNIVOICE_API_URL",
        "OMNIVOICE_PUBLIC_API_BASE",
        "OMNIVOICE_BIND_HOST",
    ):
        monkeypatch.delenv(name, raising=False)


def test_rebound_hostname_is_refused_even_when_same_origin(default_hosts, monkeypatch):
    from services import network_share

    called = []

    async def fake_enable(app):
        called.append(app)
        return network_share.ShareState()

    monkeypatch.setattr(network_share, "enable", fake_enable)
    client = _client("http://evil.example:3900")
    response = client.post(
        "/system/network/enable", headers={"Origin": "http://evil.example:3900"}
    )
    assert response.status_code == 403
    assert "OMNIVOICE_ALLOWED_HOSTS" in response.json()["detail"]
    assert called == []
    # The public shell still loads so a remote UI can sign in and explain.
    assert client.get("/health").status_code in (200, 503)
    # The PIN-revealing read is refused too, as is a WebSocket.
    assert client.get("/system/network/state").status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/events") as ws:
            ws.receive_text()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:3900",
        "http://127.0.0.1:3900",
        "http://192.168.1.20:3901",  # LAN share by address
        "http://app.localhost:3900",
        "http://gpu-box.tail1234.ts.net",  # tailscale serve
        "http://host.docker.internal:3900",  # n8n / Open WebUI in Docker Desktop
        "http://gateway.docker.internal:3900",
        "http://host.containers.internal:3900",  # Podman
    ],
)
def test_default_host_names_pass(default_hosts, base_url):
    assert _client(base_url).get("/system/network/state").status_code == 200


def test_host_values_parse_strictly(default_hosts):
    from core.browser_guard import host_allowed

    assert host_allowed("[::1]:3900")
    assert host_allowed("[::ffff:127.0.0.1]:3900")
    assert host_allowed("LOCALHOST.:3900")
    assert host_allowed(None)  # no Host header: not a browser
    for value in ("evil.example", "localhost.evil.example", "127.0.0.1@evil.example", "a b"):
        assert not host_allowed(value), value


def test_configured_host_names_pass(default_hosts, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_ALLOWED_HOSTS", "media.lan,.home.example")
    assert _client("http://media.lan:3900").get("/system/network/state").status_code == 200
    assert _client("http://nas.home.example").get("/system/network/state").status_code == 200
    assert _client("http://other.example").get("/system/network/state").status_code == 403


def test_credentialed_remote_clients_are_not_host_checked(default_hosts, monkeypatch):
    from services.admin_sessions import admin_session_store

    admin_session_store.clear()
    monkeypatch.setenv("OMNIVOICE_API_KEY", "s3cret-key")
    client = _client("http://gpu.example.com", client=("10.0.0.5", 1))
    response = client.get(
        "/v1/audio/voices", headers={"Authorization": "Bearer s3cret-key"}
    )
    assert response.status_code == 200
    # Without a credential the API-key gate answers, so the UI can prompt.
    assert client.get("/v1/audio/voices").status_code == 401
    # A rebinding page reaches the backend over loopback; a made-up
    # credential must not lift the host check there.
    rebound = _client("http://evil.example:3900")
    assert rebound.get(
        "/system/network/state", headers={"Authorization": "Bearer guess"}
    ).status_code == 403
    admin_session_store.clear()




def test_loopback_proxy_with_a_valid_key_is_not_host_checked(default_hosts, monkeypatch):
    """Caddy / cloudflared on this machine keep the client's Host header."""
    from services.admin_sessions import admin_session_store

    admin_session_store.clear()
    monkeypatch.setenv("OMNIVOICE_API_KEY", "s3cret-key")
    proxied = _client("https://voice.example.com")  # loopback peer
    assert proxied.get(
        "/system/network/state", headers={"Authorization": "Bearer s3cret-key"}
    ).status_code == 200
    assert proxied.get("/system/network/state?api_key=s3cret-key").status_code == 200
    # Without the key — or with a wrong one — the rebinding defence holds.
    assert proxied.get("/system/network/state").status_code == 403
    assert proxied.get(
        "/system/network/state", headers={"Authorization": "Bearer s3cret-keyX"}
    ).status_code == 403
    admin_session_store.clear()


def test_loopback_proxy_with_an_admin_session_is_not_host_checked_but_a_pin_is(default_hosts, monkeypatch):
    from main import app
    from services.admin_sessions import admin_session_store

    admin_session_store.clear()
    monkeypatch.setenv("OMNIVOICE_API_KEY", "s3cret-key")
    session = admin_session_store.issue("s3cret-key")
    proxied = _client("https://voice.example.com")
    assert proxied.get(
        "/system/network/state", headers={"Authorization": f"Bearer {session.token}"}
    ).status_code == 200
    admin_session_store.clear()

    class _Share:
        pin = "4321"

    monkeypatch.delenv("OMNIVOICE_API_KEY")
    monkeypatch.setattr(app.state, "network_share", _Share(), raising=False)
    # A guessable PIN must not let a rebinding page through with loopback
    # rights; right and wrong PINs are refused alike, so there is no oracle.
    assert proxied.get("/v1/audio/voices", headers={"X-OmniVoice-Pin": "4321"}).status_code == 403
    assert proxied.get("/v1/audio/voices", headers={"X-OmniVoice-Pin": "0000"}).status_code == 403
    assert proxied.get("/system/diagnose", headers={"X-OmniVoice-Pin": "4321"}).status_code == 403


def test_host_refusal_says_where_to_configure_the_desktop_app(default_hosts):
    detail = _client("http://evil.example:3900").get("/system/network/state").json()["detail"]
    assert "OMNIVOICE_ALLOWED_HOSTS" in detail
    assert "~/.config/omnivoice/env" in detail
    assert "%USERPROFILE%\\.config\\omnivoice\\env" in detail


def test_loopback_proxy_websocket_with_a_ticket_is_not_host_checked(default_hosts, monkeypatch):
    from services.admin_sessions import admin_session_store

    admin_session_store.clear()
    monkeypatch.setenv("OMNIVOICE_API_KEY", "s3cret-key")
    session = admin_session_store.issue("s3cret-key")
    ticket = admin_session_store.issue_ws_ticket(session.token, "/ws/tts", "s3cret-key").token
    proxied = _client("https://voice.example.com")
    with proxied.websocket_connect(f"/ws/tts?ws_ticket={ticket}") as ws:
        ws.send_json({})
        assert ws.receive_json()["type"] == "error"
    # Tickets stay single-use.
    with pytest.raises(WebSocketDisconnect):
        with proxied.websocket_connect(f"/ws/tts?ws_ticket={ticket}") as ws:
            ws.receive_text()
    admin_session_store.clear()
