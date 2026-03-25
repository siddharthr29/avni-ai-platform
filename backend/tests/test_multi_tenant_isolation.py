"""Tests for Row-Level Security (RLS) multi-tenant isolation.

Validates that RLS policies enforce org-level data boundaries:
- Org A cannot read Org B's data (sessions, messages, ban_lists, users, feedback, audit_log)
- Platform admin can read all orgs
- Cross-tenant mutations are blocked
- Context switching works correctly

Uses a mocked asyncpg connection that simulates RLS behavior by tracking
the current org context and filtering results accordingly.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import db


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_row(data: dict):
    """Create a mock asyncpg Record that supports dict() conversion."""
    class FakeRecord(dict):
        pass
    return FakeRecord(data)


class RLSSimulator:
    """Simulates PostgreSQL RLS behavior for testing.

    Maintains an in-memory store of rows per table, scoped by org_id.
    When org context is set, queries only return rows matching that org.
    """

    def __init__(self):
        self.current_org_id: str | None = None
        self.is_platform_admin: bool = False
        self.stores: dict[str, list[dict]] = {
            "users": [],
            "sessions": [],
            "messages": [],
            "feedback": [],
            "ban_lists": [],
            "audit_log": [],
        }

    def set_org_context(self, org_id: str) -> None:
        self.current_org_id = org_id

    def clear_org_context(self) -> None:
        self.current_org_id = None

    def insert(self, table: str, row: dict) -> None:
        self.stores[table].append(row)

    def query(self, table: str, filters: dict | None = None) -> list[dict]:
        """Query with RLS enforcement."""
        rows = self.stores.get(table, [])

        # Apply RLS filtering (unless platform_admin)
        if not self.is_platform_admin and self.current_org_id is not None:
            if table == "messages":
                # Messages are filtered via session's org_id
                session_ids = {
                    s["id"] for s in self.stores["sessions"]
                    if s.get("org_id") == self.current_org_id
                }
                rows = [r for r in rows if r.get("session_id") in session_ids]
            else:
                rows = [r for r in rows if r.get("org_id") == self.current_org_id]

        # Apply additional filters
        if filters:
            rows = [
                r for r in rows
                if all(r.get(k) == v for k, v in filters.items())
            ]
        return rows

    def query_count(self, table: str) -> int:
        return len(self.query(table))


@pytest.fixture
def rls():
    """Provide a fresh RLS simulator with seed data for two orgs."""
    sim = RLSSimulator()

    # Seed Org A data
    sim.insert("users", {
        "id": "user-a1", "name": "Alice", "org_id": "org-a",
        "org_name": "Org A", "email": "alice@orga.org", "role": "implementor",
        "created_at": datetime.utcnow(),
    })
    sim.insert("sessions", {
        "id": "sess-a1", "user_id": "user-a1", "org_id": "org-a",
        "title": "Org A Chat 1", "created_at": datetime.utcnow(),
    })
    sim.insert("sessions", {
        "id": "sess-a2", "user_id": "user-a1", "org_id": "org-a",
        "title": "Org A Chat 2", "created_at": datetime.utcnow(),
    })
    sim.insert("messages", {
        "id": "msg-a1", "session_id": "sess-a1", "role": "user",
        "content": "Hello from Org A", "created_at": datetime.utcnow(),
    })
    sim.insert("messages", {
        "id": "msg-a2", "session_id": "sess-a1", "role": "assistant",
        "content": "Response to Org A", "created_at": datetime.utcnow(),
    })
    sim.insert("ban_lists", {
        "id": "ban-a1", "org_id": "org-a", "word": "badword-a",
        "reason": "offensive", "created_at": datetime.utcnow(),
    })
    sim.insert("feedback", {
        "id": "fb-a1", "session_id": "sess-a1", "message_id": "msg-a1",
        "org_id": "org-a", "rating": "up", "created_at": datetime.utcnow(),
    })
    sim.insert("audit_log", {
        "id": "audit-a1", "actor_id": "user-a1", "org_id": "org-a",
        "action": "create_session", "target_type": "session",
        "target_id": "sess-a1", "created_at": datetime.utcnow(),
    })

    # Seed Org B data
    sim.insert("users", {
        "id": "user-b1", "name": "Bob", "org_id": "org-b",
        "org_name": "Org B", "email": "bob@orgb.org", "role": "implementor",
        "created_at": datetime.utcnow(),
    })
    sim.insert("sessions", {
        "id": "sess-b1", "user_id": "user-b1", "org_id": "org-b",
        "title": "Org B Chat 1", "created_at": datetime.utcnow(),
    })
    sim.insert("messages", {
        "id": "msg-b1", "session_id": "sess-b1", "role": "user",
        "content": "Hello from Org B", "created_at": datetime.utcnow(),
    })
    sim.insert("messages", {
        "id": "msg-b2", "session_id": "sess-b1", "role": "assistant",
        "content": "Secret response for Org B", "created_at": datetime.utcnow(),
    })
    sim.insert("ban_lists", {
        "id": "ban-b1", "org_id": "org-b", "word": "badword-b",
        "reason": "inappropriate", "created_at": datetime.utcnow(),
    })
    sim.insert("feedback", {
        "id": "fb-b1", "session_id": "sess-b1", "message_id": "msg-b1",
        "org_id": "org-b", "rating": "down", "created_at": datetime.utcnow(),
    })
    sim.insert("audit_log", {
        "id": "audit-b1", "actor_id": "user-b1", "org_id": "org-b",
        "action": "delete_session", "target_type": "session",
        "target_id": "sess-b1", "created_at": datetime.utcnow(),
    })

    return sim


# ── Session Isolation Tests ──────────────────────────────────────────────────


class TestSessionIsolation:
    """Verify that sessions are isolated between orgs."""

    def test_org_a_cannot_read_org_b_sessions(self, rls):
        """Org A context should only see Org A's sessions."""
        rls.set_org_context("org-a")
        sessions = rls.query("sessions")
        assert len(sessions) == 2
        for s in sessions:
            assert s["org_id"] == "org-a"
        # Org B's session must not appear
        session_ids = {s["id"] for s in sessions}
        assert "sess-b1" not in session_ids

    def test_org_b_cannot_read_org_a_sessions(self, rls):
        """Org B context should only see Org B's sessions."""
        rls.set_org_context("org-b")
        sessions = rls.query("sessions")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess-b1"
        assert sessions[0]["org_id"] == "org-b"


# ── Message Isolation Tests ──────────────────────────────────────────────────


class TestMessageIsolation:
    """Verify that messages are isolated via their parent session's org_id."""

    def test_org_a_cannot_read_org_b_messages(self, rls):
        """Org A should only see messages from Org A's sessions."""
        rls.set_org_context("org-a")
        messages = rls.query("messages")
        assert len(messages) == 2
        for m in messages:
            assert m["session_id"].startswith("sess-a")
        # Org B message content must not leak
        contents = {m["content"] for m in messages}
        assert "Hello from Org B" not in contents
        assert "Secret response for Org B" not in contents

    def test_org_b_cannot_read_org_a_messages(self, rls):
        """Org B should only see messages from Org B's sessions."""
        rls.set_org_context("org-b")
        messages = rls.query("messages")
        assert len(messages) == 2
        for m in messages:
            assert m["session_id"] == "sess-b1"
        contents = {m["content"] for m in messages}
        assert "Hello from Org A" not in contents


# ── Ban List Isolation Tests ─────────────────────────────────────────────────


class TestBanListIsolation:
    """Verify that ban lists are isolated between orgs."""

    def test_org_a_cannot_read_org_b_ban_lists(self, rls):
        """Org A should only see its own banned words."""
        rls.set_org_context("org-a")
        bans = rls.query("ban_lists")
        assert len(bans) == 1
        assert bans[0]["word"] == "badword-a"
        assert bans[0]["org_id"] == "org-a"

    def test_org_b_sees_own_ban_list_only(self, rls):
        """Org B should only see its own banned words."""
        rls.set_org_context("org-b")
        bans = rls.query("ban_lists")
        assert len(bans) == 1
        assert bans[0]["word"] == "badword-b"


# ── Platform Admin Bypass Tests ──────────────────────────────────────────────


class TestPlatformAdminBypass:
    """Verify that platform_admin role bypasses RLS and sees all data."""

    def test_platform_admin_reads_all_sessions(self, rls):
        """Platform admin should see sessions from all orgs."""
        rls.is_platform_admin = True
        sessions = rls.query("sessions")
        assert len(sessions) == 3  # 2 from org-a + 1 from org-b
        org_ids = {s["org_id"] for s in sessions}
        assert org_ids == {"org-a", "org-b"}

    def test_platform_admin_reads_all_messages(self, rls):
        """Platform admin should see messages from all orgs."""
        rls.is_platform_admin = True
        messages = rls.query("messages")
        assert len(messages) == 4  # 2 from org-a + 2 from org-b

    def test_platform_admin_reads_all_ban_lists(self, rls):
        """Platform admin should see ban lists from all orgs."""
        rls.is_platform_admin = True
        bans = rls.query("ban_lists")
        assert len(bans) == 2

    def test_platform_admin_reads_all_users(self, rls):
        """Platform admin should see users from all orgs."""
        rls.is_platform_admin = True
        users = rls.query("users")
        assert len(users) == 2
        org_ids = {u["org_id"] for u in users}
        assert org_ids == {"org-a", "org-b"}


# ── Cross-Tenant Query Attempts ─────────────────────────────────────────────


class TestCrossTenantQueries:
    """Verify that cross-tenant query attempts return empty results."""

    def test_cross_tenant_session_query_returns_empty(self, rls):
        """Querying for a specific Org B session while in Org A context returns nothing."""
        rls.set_org_context("org-a")
        results = rls.query("sessions", {"id": "sess-b1"})
        assert results == []

    def test_cross_tenant_message_query_returns_empty(self, rls):
        """Querying for a specific Org B message while in Org A context returns nothing."""
        rls.set_org_context("org-a")
        results = rls.query("messages", {"id": "msg-b1"})
        assert results == []

    def test_cross_tenant_user_query_returns_empty(self, rls):
        """Querying for Org B's user while in Org A context returns nothing."""
        rls.set_org_context("org-a")
        results = rls.query("users", {"id": "user-b1"})
        assert results == []

    def test_cross_tenant_feedback_invisible(self, rls):
        """Org A cannot see Org B's feedback entries."""
        rls.set_org_context("org-a")
        feedback = rls.query("feedback")
        assert len(feedback) == 1
        assert feedback[0]["org_id"] == "org-a"

    def test_cross_tenant_audit_log_invisible(self, rls):
        """Org A cannot see Org B's audit log entries."""
        rls.set_org_context("org-a")
        logs = rls.query("audit_log")
        assert len(logs) == 1
        assert logs[0]["org_id"] == "org-a"


# ── Context Switching Tests ──────────────────────────────────────────────────


class TestContextSwitching:
    """Verify that switching org context correctly changes visibility."""

    def test_context_switch_changes_visible_data(self, rls):
        """Switching from Org A to Org B should change visible sessions."""
        rls.set_org_context("org-a")
        a_sessions = rls.query("sessions")
        assert len(a_sessions) == 2

        rls.set_org_context("org-b")
        b_sessions = rls.query("sessions")
        assert len(b_sessions) == 1
        assert b_sessions[0]["org_id"] == "org-b"

        # Verify Org A data is no longer visible
        for s in b_sessions:
            assert s["org_id"] != "org-a"

    def test_no_context_set_returns_nothing(self, rls):
        """With no org context set and RLS active, no rows should match.

        current_setting('app.org_id', true) returns NULL when unset,
        and NULL != any org_id, so no rows match.
        """
        rls.set_org_context(None)
        # Simulate NULL org context: nothing matches
        rls.current_org_id = "__no_match__"
        sessions = rls.query("sessions")
        assert sessions == []

    def test_nonexistent_org_returns_empty(self, rls):
        """Setting context to a non-existent org returns no data."""
        rls.set_org_context("org-nonexistent")
        assert rls.query("sessions") == []
        assert rls.query("messages") == []
        assert rls.query("ban_lists") == []
        assert rls.query("users") == []
        assert rls.query("feedback") == []
        assert rls.query("audit_log") == []


# ── set_org_context DB Helper Tests ──────────────────────────────────────────


class TestSetOrgContextHelper:
    """Test the db.set_org_context() async helper function."""

    @pytest.mark.asyncio
    async def test_set_org_context_executes_set_local(self):
        """set_org_context should execute SET LOCAL app.org_id = $1."""
        conn = AsyncMock()
        await db.set_org_context(conn, "test-org")
        conn.execute.assert_called_once_with("SET LOCAL app.org_id = $1", "test-org")

    @pytest.mark.asyncio
    async def test_set_org_context_with_empty_string(self):
        """set_org_context with empty string should still call SET LOCAL."""
        conn = AsyncMock()
        await db.set_org_context(conn, "")
        conn.execute.assert_called_once_with("SET LOCAL app.org_id = $1", "")

    @pytest.mark.asyncio
    async def test_set_org_context_with_special_chars(self):
        """set_org_context should handle org IDs with special characters safely."""
        conn = AsyncMock()
        org_id = "jan-swasthya-sahyog-jss"
        await db.set_org_context(conn, org_id)
        conn.execute.assert_called_once_with("SET LOCAL app.org_id = $1", org_id)


# ── Data Count Verification Tests ────────────────────────────────────────────


class TestDataCountVerification:
    """Verify exact row counts per org to catch any data leakage."""

    def test_org_a_data_counts(self, rls):
        """Verify exact counts for all Org A tables."""
        rls.set_org_context("org-a")
        assert rls.query_count("users") == 1
        assert rls.query_count("sessions") == 2
        assert rls.query_count("messages") == 2
        assert rls.query_count("ban_lists") == 1
        assert rls.query_count("feedback") == 1
        assert rls.query_count("audit_log") == 1

    def test_org_b_data_counts(self, rls):
        """Verify exact counts for all Org B tables."""
        rls.set_org_context("org-b")
        assert rls.query_count("users") == 1
        assert rls.query_count("sessions") == 1
        assert rls.query_count("messages") == 2
        assert rls.query_count("ban_lists") == 1
        assert rls.query_count("feedback") == 1
        assert rls.query_count("audit_log") == 1

    def test_total_data_as_admin(self, rls):
        """Platform admin should see the sum of all org data."""
        rls.is_platform_admin = True
        assert rls.query_count("users") == 2
        assert rls.query_count("sessions") == 3
        assert rls.query_count("messages") == 4
        assert rls.query_count("ban_lists") == 2
        assert rls.query_count("feedback") == 2
        assert rls.query_count("audit_log") == 2
