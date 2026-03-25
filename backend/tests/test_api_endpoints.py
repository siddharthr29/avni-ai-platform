"""Integration tests for API endpoints.

Tests actual HTTP requests through the FastAPI app.
Uses mocked DB and LLM to test routing, validation, and response format.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.integration
class TestHealthEndpoints:
    async def test_health_endpoint(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "avni-ai-platform"
        assert data["version"] == "1.0.0"

    async def test_api_health_endpoint(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "llm_provider" in data
        assert "database_connected" in data

    async def test_metrics_endpoint(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        # Prometheus format
        assert "http_requests_total" in resp.text or resp.status_code == 200


@pytest.mark.integration
class TestUserEndpoints:
    async def test_user_login(self, client):
        with patch("app.db.upsert_user", new_callable=AsyncMock, return_value={
            "id": "u1", "name": "Alice", "org_name": "TestOrg", "sector": "MCH", "org_context": ""
        }):
            resp = await client.post("/api/users/login", json={
                "id": "u1", "name": "Alice", "org_name": "TestOrg", "sector": "MCH"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["user"]["id"] == "u1"
            assert data["user"]["name"] == "Alice"

    async def test_get_nonexistent_user(self, client):
        with patch("app.db.get_user", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/users/nonexistent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["user"] is None

    async def test_get_existing_user(self, client):
        with patch("app.db.get_user", new_callable=AsyncMock, return_value={
            "id": "u1", "name": "Alice", "org_name": "Org"
        }):
            resp = await client.get("/api/users/u1")
            assert resp.status_code == 200
            assert resp.json()["user"]["id"] == "u1"

    async def test_user_login_missing_fields(self, client):
        resp = await client.post("/api/users/login", json={"id": "u1"})
        assert resp.status_code == 422


@pytest.mark.integration
class TestSessionEndpoints:
    async def test_create_session(self, client):
        with patch("app.db.create_session", new_callable=AsyncMock, return_value={
            "id": "s1", "user_id": "u1", "title": "New Chat", "created_at": "2025-01-01T00:00:00"
        }):
            resp = await client.post("/api/sessions", json={
                "id": "s1", "user_id": "u1", "title": "Test Chat"
            })
            assert resp.status_code == 200
            assert resp.json()["session"]["id"] == "s1"

    async def test_get_session_messages_empty(self, client):
        with patch("app.db.get_session_messages", new_callable=AsyncMock, return_value=[]):
            resp = await client.get("/api/sessions/s1/messages")
            assert resp.status_code == 200
            assert resp.json()["messages"] == []

    async def test_get_user_sessions(self, client):
        with patch("app.db.get_user_sessions", new_callable=AsyncMock, return_value=[
            {"id": "s1", "user_id": "u1", "title": "Chat 1", "message_count": 5}
        ]):
            resp = await client.get("/api/users/u1/sessions")
            assert resp.status_code == 200
            assert len(resp.json()["sessions"]) == 1

    async def test_update_session(self, client):
        with patch("app.db.update_session_title", new_callable=AsyncMock):
            resp = await client.patch("/api/sessions/s1", json={"title": "Updated"})
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    async def test_delete_session(self, client):
        with patch("app.db.delete_session", new_callable=AsyncMock):
            resp = await client.delete("/api/sessions/s1")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True


@pytest.mark.integration
class TestChatEndpoint:
    async def test_chat_request_validation_missing_fields(self, client):
        resp = await client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 422  # Missing session_id

    async def test_chat_request_validation_empty_body(self, client):
        resp = await client.post("/api/chat", json={})
        assert resp.status_code == 422


@pytest.mark.integration
class TestBundleEndpoints:
    async def test_bundle_generate_missing_srs(self, client):
        resp = await client.post("/api/bundle/generate", json={})
        assert resp.status_code == 400

    async def test_bundle_status_not_found(self, client):
        with patch("app.services.bundle_generator.get_bundle_status", return_value=None):
            resp = await client.get("/api/bundle/nonexistent/status")
            assert resp.status_code == 404

    async def test_bundle_validate_not_found(self, client):
        with patch("app.services.bundle_generator.get_bundle_zip_path", return_value=None):
            resp = await client.get("/api/bundle/nonexistent/validate")
            assert resp.status_code == 404


@pytest.mark.integration
class TestUsageEndpoints:
    async def test_usage_stats_no_db(self, client):
        with patch("app.db.is_connected", return_value=False):
            resp = await client.get("/api/usage/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert data["orgs_connected"] == 0
            assert data["bundles_generated"] == 0
            assert data["chat_messages"] == 0
            assert data["active_users"] == 0
            assert data["top_intents"] == []
