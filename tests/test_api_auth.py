"""Tests for optional API-key middleware."""

from unittest.mock import patch

import pytest


@pytest.fixture
def auth_client(app_client):
    """Return client with API key enforcement enabled."""
    with patch("stepwise.config.settings.api_key", "test-secret-key"):
        yield app_client


class TestAPIKeyMiddleware:
    def test_no_api_key_configured_allows_requests(self, app_client):
        with patch("stepwise.config.settings.api_key", None):
            resp = app_client.get("/health")
        assert resp.status_code == 200

    def test_health_always_public_when_api_key_set(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200

    def test_missing_key_returns_401(self, auth_client):
        resp = auth_client.post("/query/sync", json={"query": "test"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or missing API key"

    def test_wrong_key_returns_401(self, auth_client):
        resp = auth_client.post(
            "/query/sync",
            json={"query": "test"},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_x_api_key_header_allows_request(self, auth_client):
        with patch("stepwise.api.app.query_steps", return_value={"answer": "ok", "steps": []}):
            resp = auth_client.post(
                "/query/sync",
                json={"query": "test"},
                headers={"X-API-Key": "test-secret-key"},
            )
        assert resp.status_code == 200

    def test_bearer_token_allows_request(self, auth_client):
        with patch("stepwise.api.app.query_steps", return_value={"answer": "ok", "steps": []}):
            resp = auth_client.post(
                "/query/sync",
                json={"query": "test"},
                headers={"Authorization": "Bearer test-secret-key"},
            )
        assert resp.status_code == 200

    def test_options_preflight_allowed_without_key(self, auth_client):
        resp = auth_client.options("/query/sync")
        assert resp.status_code != 401
