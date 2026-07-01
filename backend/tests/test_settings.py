"""Tests for GET/PUT /api/settings and test-connection endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def test_get_settings_returns_keys(client: TestClient):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    for key in ("bgg_api_token", "ntfy_server", "ntfy_topic", "ntfy_token"):
        assert key in data


def test_put_settings_updates_value(client: TestClient):
    r = client.put(
        "/api/settings",
        json={
            "bgg_api_token": "",
            "ntfy_server": "https://ntfy.example.com",
            "ntfy_topic": "alerts",
            "ntfy_token": "",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_put_settings_ignores_placeholder(client: TestClient):
    r = client.put(
        "/api/settings",
        json={
            "bgg_api_token": "****",
            "ntfy_server": "",
            "ntfy_topic": "",
            "ntfy_token": "****",
        },
    )
    assert r.status_code == 200


def test_test_ntfy_sends_notification(client: TestClient):
    """Regression: POST /api/settings/test/ntfy must not raise ImportError."""
    with patch("app.channels.ntfy.NtfyChannel.send") as mock_send:
        r = client.post("/api/settings/test/ntfy")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["kind"] == "test"
    assert "white_check_mark" in call_kwargs["tags"]


def test_test_ntfy_returns_error_on_failure(client: TestClient):
    with patch(
        "app.channels.ntfy.NtfyChannel.send", side_effect=RuntimeError("ntfy down")
    ):
        r = client.post("/api/settings/test/ntfy")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "ntfy down" in r.json()["message"]


def test_test_bgg_returns_ok_on_200(client: TestClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.AsyncClient") as mock_http:
        instance = mock_http.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)
        r = client.post("/api/settings/test/bgg")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_bgg_returns_error_on_401(client: TestClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    with patch("httpx.AsyncClient") as mock_http:
        instance = mock_http.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)
        r = client.post("/api/settings/test/bgg")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_test_bgg_returns_error_on_exception(client: TestClient):
    with patch("httpx.AsyncClient") as mock_http:
        instance = mock_http.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=Exception("timeout"))
        r = client.post("/api/settings/test/bgg")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "timeout" in r.json()["message"]
