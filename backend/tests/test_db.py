"""Tests for database operations (with mocked asyncpg pool).

Tests user CRUD, session management, message storage, and feedback.
Verifies both connected (mocked pool) and disconnected (fallback) paths.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import db


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_row(data: dict):
    """Create a mock asyncpg Record that supports dict() conversion."""
    mock = MagicMock()
    mock.__getitem__ = lambda self, key: data[key]
    mock.keys = lambda: data.keys()
    mock.values = lambda: data.values()
    mock.items = lambda: data.items()
    # Make dict(mock) return the data dict
    mock.__iter__ = lambda self: iter(data)
    # For asyncpg Record compatibility
    class FakeRecord(dict):
        pass
    return FakeRecord(data)


def _mock_pool():
    """Create a mock asyncpg pool with connection context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = ctx
    return pool, conn


# ── Disconnected (no pool) Fallbacks ────────────────────────────────────────

class TestDBNotConnected:
    """Tests for fallback behavior when DB pool is None."""

    @pytest.fixture(autouse=True)
    def _set_pool_none(self):
        original = db._pool
        db._pool = None
        yield
        db._pool = original

    def test_is_connected_false(self):
        assert db.is_connected() is False

    async def test_upsert_user_fallback(self):
        result = await db.upsert_user("u1", "Alice", "TestOrg")
        assert result["id"] == "u1"
        assert result["name"] == "Alice"

    async def test_get_user_returns_none(self):
        result = await db.get_user("nonexistent")
        assert result is None

    async def test_create_session_fallback(self):
        result = await db.create_session("s1", "u1", "Chat 1")
        assert result["id"] == "s1"
        assert result["user_id"] == "u1"
        assert "created_at" in result

    async def test_get_user_sessions_empty(self):
        result = await db.get_user_sessions("u1")
        assert result == []

    async def test_add_message_fallback(self):
        result = await db.add_message("m1", "s1", "user", "Hello")
        assert result["id"] == "m1"
        assert result["content"] == "Hello"

    async def test_get_session_messages_empty(self):
        result = await db.get_session_messages("s1")
        assert result == []

    async def test_get_recent_messages_empty(self):
        result = await db.get_recent_messages("s1")
        assert result == []

    async def test_add_feedback_fallback(self):
        result = await db.add_feedback("f1", "s1", "m1", "up")
        assert result["id"] == "f1"
        assert result["rating"] == "up"

    async def test_get_feedback_stats_empty(self):
        result = await db.get_feedback_stats()
        assert result == {}

    async def test_get_corrections_empty(self):
        result = await db.get_corrections()
        assert result == []

    async def test_update_session_title_noop(self):
        # Should not raise
        await db.update_session_title("s1", "New Title")

    async def test_delete_session_noop(self):
        # Should not raise
        await db.delete_session("s1")


# ── Connected (mocked pool) ─────────────────────────────────────────────────

class TestDBConnected:
    """Tests for DB operations with a mocked asyncpg pool."""

    @pytest.fixture(autouse=True)
    def _set_mock_pool(self):
        self.pool, self.conn = _mock_pool()
        original = db._pool
        db._pool = self.pool
        yield
        db._pool = original

    def test_is_connected_true(self):
        assert db.is_connected() is True

    async def test_upsert_user_new(self):
        row_data = {
            "id": "u1", "name": "Alice", "org_name": "TestOrg",
            "sector": "MCH", "org_context": "", "created_at": datetime.utcnow()
        }
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.upsert_user("u1", "Alice", "TestOrg", "MCH")
        assert result["id"] == "u1"
        assert result["name"] == "Alice"
        self.conn.fetchrow.assert_called_once()

    async def test_upsert_user_update(self):
        row_data = {
            "id": "u1", "name": "Alice Updated", "org_name": "NewOrg",
            "sector": "WASH", "org_context": "updated", "created_at": datetime.utcnow()
        }
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.upsert_user("u1", "Alice Updated", "NewOrg", "WASH", "updated")
        assert result["name"] == "Alice Updated"
        assert result["org_name"] == "NewOrg"

    async def test_get_nonexistent_user(self):
        self.conn.fetchrow = AsyncMock(return_value=None)
        result = await db.get_user("nonexistent")
        assert result is None

    async def test_get_existing_user(self):
        row_data = {"id": "u1", "name": "Alice", "org_name": "Org", "sector": "", "org_context": "", "created_at": datetime.utcnow()}
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.get_user("u1")
        assert result["id"] == "u1"

    async def test_create_session(self):
        row_data = {"id": "s1", "user_id": "u1", "title": "New Chat", "created_at": datetime.utcnow()}
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.create_session("s1", "u1")
        assert result["id"] == "s1"

    async def test_get_user_sessions(self):
        rows = [
            _mock_row({"id": "s1", "user_id": "u1", "title": "Chat 1", "created_at": datetime.utcnow(), "message_count": 5}),
            _mock_row({"id": "s2", "user_id": "u1", "title": "Chat 2", "created_at": datetime.utcnow(), "message_count": 3}),
        ]
        self.conn.fetch = AsyncMock(return_value=rows)
        result = await db.get_user_sessions("u1")
        assert len(result) == 2

    async def test_add_and_get_messages(self):
        row_data = {"id": "m1", "session_id": "s1", "role": "user", "content": "Hello", "metadata": None, "created_at": datetime.utcnow()}
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.add_message("m1", "s1", "user", "Hello")
        assert result["content"] == "Hello"

    async def test_get_session_messages(self):
        rows = [
            _mock_row({"id": "m1", "session_id": "s1", "role": "user", "content": "Hi", "metadata": None, "created_at": datetime.utcnow()}),
            _mock_row({"id": "m2", "session_id": "s1", "role": "assistant", "content": "Hello!", "metadata": None, "created_at": datetime.utcnow()}),
        ]
        self.conn.fetch = AsyncMock(return_value=rows)
        result = await db.get_session_messages("s1")
        assert len(result) == 2

    async def test_recent_messages_limit(self):
        rows = [
            _mock_row({"role": "user", "content": "First"}),
            _mock_row({"role": "assistant", "content": "Second"}),
        ]
        self.conn.fetch = AsyncMock(return_value=rows)
        result = await db.get_recent_messages("s1", limit=5)
        # Results are reversed (chronological order)
        assert len(result) == 2

    async def test_add_feedback(self):
        row_data = {"id": "f1", "session_id": "s1", "message_id": "m1", "rating": "up", "correction": None, "metadata": {}, "created_at": datetime.utcnow()}
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.add_feedback("f1", "s1", "m1", "up")
        assert result["rating"] == "up"

    async def test_feedback_stats(self):
        rows = [
            _mock_row({"rating": "up", "cnt": 10}),
            _mock_row({"rating": "down", "cnt": 2}),
        ]
        self.conn.fetch = AsyncMock(return_value=rows)
        self.conn.fetchval = AsyncMock(return_value=1)
        result = await db.get_feedback_stats()
        assert result["up"] == 10
        assert result["down"] == 2
        assert result["corrections_with_text"] == 1

    async def test_update_session_title(self):
        self.conn.execute = AsyncMock()
        await db.update_session_title("s1", "Updated Title")
        self.conn.execute.assert_called_once()

    async def test_delete_session(self):
        self.conn.execute = AsyncMock()
        await db.delete_session("s1")
        self.conn.execute.assert_called_once()

    async def test_add_message_with_metadata(self):
        meta = {"intent": "bundle", "action": "create"}
        row_data = {"id": "m1", "session_id": "s1", "role": "user", "content": "Create bundle", "metadata": meta, "created_at": datetime.utcnow()}
        self.conn.fetchrow = AsyncMock(return_value=_mock_row(row_data))
        result = await db.add_message("m1", "s1", "user", "Create bundle", metadata=meta)
        assert result["metadata"] == meta
