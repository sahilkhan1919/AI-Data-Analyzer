"""
test_application.py – Tests for application-level behavior.

Covers: imports, Flask init, health endpoint, invalid routes.
"""

import pytest


class TestAppImports:
    def test_app_imports_successfully(self):
        """Backend module can be imported without errors."""
        import app  # noqa: F401
        assert True

    def test_config_imports_successfully(self):
        """config module can be imported without errors."""
        import config  # noqa: F401
        assert True

    def test_datasets_dict_exists(self):
        """DATASETS dict is present in the app module."""
        from app import DATASETS
        assert isinstance(DATASETS, dict)


class TestFlaskInitialization:
    def test_app_is_testing(self, app):
        assert app.config["TESTING"] is True

    def test_max_content_length_configured(self, app):
        assert app.config["MAX_CONTENT_LENGTH"] is not None
        assert app.config["MAX_CONTENT_LENGTH"] > 0


class TestHealthEndpoint:
    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_returns_json(self, client):
        resp = client.get("/")
        data = resp.get_json()
        assert data is not None
        assert "message" in data

    def test_root_message_content(self, client):
        resp = client.get("/")
        data = resp.get_json()
        assert "running" in data["message"].lower()


class TestInvalidRoutes:
    def test_unknown_route_returns_404(self, client):
        resp = client.get("/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_invalid_post_route_returns_404(self, client):
        resp = client.post("/does-not-exist", json={})
        assert resp.status_code == 404

    def test_wrong_method_on_upload_returns_405(self, client):
        resp = client.get("/upload")
        assert resp.status_code == 405
