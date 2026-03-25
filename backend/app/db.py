"""PostgreSQL database layer for user profiles, sessions, and messages.

Uses asyncpg connection pool. Schema is auto-created on startup.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _slugify_org(org_name: str) -> str:
    """Derive org_id from org_name: lowercase, replace spaces with hyphens, strip special chars.

    Examples:
        "Samanvay Foundation" -> "samanvay-foundation"
        "Jan Swasthya Sahyog (JSS)" -> "jan-swasthya-sahyog-jss"
        "  My  Org!  " -> "my-org"
    """
    slug = org_name.lower().strip()
    # Replace any non-alphanumeric (except hyphens) with hyphens
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    # Collapse multiple hyphens and strip leading/trailing hyphens
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE,
    password_hash TEXT,
    org_name      TEXT NOT NULL,
    org_id        TEXT NOT NULL DEFAULT '',
    sector        TEXT NOT NULL DEFAULT '',
    org_context   TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'implementor',
    is_active     BOOLEAN NOT NULL DEFAULT true,
    pending_approval BOOLEAN NOT NULL DEFAULT false,
    force_password_change BOOLEAN NOT NULL DEFAULT false,
    last_login    TIMESTAMPTZ,
    llm_provider_overrides JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(org_id);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id      TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT 'New Chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_org_id ON sessions(org_id);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    rating      TEXT NOT NULL CHECK (rating IN ('up', 'down', 'correction')),
    correction  TEXT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);

CREATE TABLE IF NOT EXISTS bundle_locks (
    bundle_id   TEXT PRIMARY KEY,
    locked_by   TEXT NOT NULL,
    locked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS guardrail_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    session_id  TEXT,
    event_type  TEXT NOT NULL CHECK (event_type IN (
        'pii_detected', 'injection_attempt', 'low_confidence',
        'content_filtered', 'system_prompt_leak', 'script_injection',
        'bundle_safety', 'length_exceeded', 'unsupported_language',
        'gender_bias_fixed', 'ban_list_triggered', 'pii_redacted'
    )),
    details     JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_user_id ON guardrail_events(user_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_session_id ON guardrail_events(session_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_event_type ON guardrail_events(event_type);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_created_at ON guardrail_events(created_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    actor_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT,
    details     JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_id ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS ban_lists (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    word        TEXT NOT NULL,
    reason      TEXT DEFAULT '',
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, word)
);
CREATE INDEX IF NOT EXISTS idx_ban_lists_org_id ON ban_lists(org_id);
"""

# Migrations for existing databases that don't have auth columns yet
MIGRATION_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email') THEN
        ALTER TABLE users ADD COLUMN email TEXT UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash') THEN
        ALTER TABLE users ADD COLUMN password_hash TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='role') THEN
        ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'implementor';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='last_login') THEN
        ALTER TABLE users ADD COLUMN last_login TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='llm_provider_overrides') THEN
        ALTER TABLE users ADD COLUMN llm_provider_overrides JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='is_active') THEN
        ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='force_password_change') THEN
        ALTER TABLE users ADD COLUMN force_password_change BOOLEAN NOT NULL DEFAULT false;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='org_id') THEN
        ALTER TABLE users ADD COLUMN org_id TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='pending_approval') THEN
        ALTER TABLE users ADD COLUMN pending_approval BOOLEAN NOT NULL DEFAULT false;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sessions' AND column_name='org_id') THEN
        ALTER TABLE sessions ADD COLUMN org_id TEXT NOT NULL DEFAULT '';
    END IF;
END $$;

-- Backfill org_id for existing users that have it empty
UPDATE users SET org_id = lower(replace(replace(org_name, ' ', '-'), '''', ''))
    WHERE org_id = '' OR org_id IS NULL;

-- Backfill org_id on sessions from their user's org_id
UPDATE sessions s SET org_id = u.org_id
    FROM users u WHERE s.user_id = u.id AND (s.org_id = '' OR s.org_id IS NULL);

-- Indexes for org_id (idempotent)
CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_sessions_org_id ON sessions(org_id);

-- Migration: bundle_locks table
CREATE TABLE IF NOT EXISTS bundle_locks (
    bundle_id   TEXT PRIMARY KEY,
    locked_by   TEXT NOT NULL,
    locked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

-- Migration: guardrail_events table (Responsible AI audit trail)
CREATE TABLE IF NOT EXISTS guardrail_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    session_id  TEXT,
    event_type  TEXT NOT NULL CHECK (event_type IN (
        'pii_detected', 'injection_attempt', 'low_confidence',
        'content_filtered', 'system_prompt_leak', 'script_injection',
        'bundle_safety', 'length_exceeded', 'unsupported_language',
        'gender_bias_fixed', 'ban_list_triggered', 'pii_redacted'
    )),
    details     JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_user_id ON guardrail_events(user_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_session_id ON guardrail_events(session_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_event_type ON guardrail_events(event_type);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_created_at ON guardrail_events(created_at);

-- Migration: refresh_tokens table (token rotation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

-- Migration: audit_log table (admin action audit trail)
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    actor_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT,
    details     JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_id ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

-- Migration: extend guardrail_events CHECK constraint for new event types
DO $$
BEGIN
    BEGIN
        ALTER TABLE guardrail_events DROP CONSTRAINT IF EXISTS guardrail_events_event_type_check;
        ALTER TABLE guardrail_events ADD CONSTRAINT guardrail_events_event_type_check
            CHECK (event_type IN (
                'pii_detected', 'injection_attempt', 'low_confidence',
                'content_filtered', 'system_prompt_leak', 'script_injection',
                'bundle_safety', 'length_exceeded', 'unsupported_language',
                'gender_bias_fixed', 'ban_list_triggered', 'pii_redacted'
            ));
    EXCEPTION WHEN others THEN
        NULL;
    END;
END $$;

-- Migration: ban_lists table (configurable banned words per org)
CREATE TABLE IF NOT EXISTS ban_lists (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    word        TEXT NOT NULL,
    reason      TEXT DEFAULT '',
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, word)
);
CREATE INDEX IF NOT EXISTS idx_ban_lists_org_id ON ban_lists(org_id);
"""


async def init_db() -> None:
    """Initialize the connection pool and create schema."""
    global _pool
    if not settings.DATABASE_URL:
        logger.warning("DATABASE_URL not set — chat persistence disabled (in-memory only)")
        return
    try:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN,
            max_size=settings.DB_POOL_MAX,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            await conn.execute(MIGRATION_SQL)
        logger.info("PostgreSQL connected and schema ready")
    except Exception as e:
        logger.error("PostgreSQL connection failed: %s — falling back to in-memory", e)
        _pool = None


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def is_connected() -> bool:
    return _pool is not None


# ── Row-Level Security (RLS) ─────────────────────────────────────────────────

async def set_org_context(conn: asyncpg.Connection, org_id: str) -> None:
    """Set the org context for RLS policies within the current transaction.

    Must be called inside a transaction (e.g. after ``BEGIN``).  Uses
    ``SET LOCAL`` so the setting is automatically cleared when the
    transaction ends.

    Args:
        conn: An active asyncpg connection (should be inside a transaction).
        org_id: The organisation identifier to scope queries to.
    """
    await conn.execute("SET LOCAL app.org_id = $1", org_id)


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(
    user_id: str, name: str, org_name: str, sector: str = "", org_context: str = ""
) -> dict:
    """Create or update a user profile. Derives org_id from org_name. Returns the user dict."""
    org_id = _slugify_org(org_name)
    if not _pool:
        return {"id": user_id, "name": name, "org_name": org_name, "org_id": org_id, "sector": sector, "org_context": org_context}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, name, org_name, org_id, sector, org_context)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                org_name = EXCLUDED.org_name,
                org_id = EXCLUDED.org_id,
                sector = EXCLUDED.sector,
                org_context = EXCLUDED.org_context
            RETURNING id, name, org_name, org_id, sector, org_context, created_at
            """,
            user_id, name, org_name, org_id, sector, org_context,
        )
        return dict(row)


async def get_user(user_id: str) -> dict | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None


async def update_user_byok(user_id: str, overrides: dict) -> None:
    """Update a user's BYOK (Bring Your Own Key) LLM provider overrides."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET llm_provider_overrides = $1::jsonb WHERE id = $2",
            json.dumps(overrides), user_id,
        )


# ── Sessions ──────────────────────────────────────────────────────────────────

async def create_session(session_id: str, user_id: str, title: str = "New Chat", org_id: str = "") -> dict:
    if not _pool:
        return {"id": session_id, "user_id": user_id, "org_id": org_id, "title": title, "created_at": datetime.utcnow().isoformat()}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO sessions (id, user_id, org_id, title) VALUES ($1, $2, $3, $4) RETURNING *",
            session_id, user_id, org_id, title,
        )
        return dict(row)


async def update_session_title(session_id: str, title: str) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE sessions SET title = $1 WHERE id = $2", title, session_id)


async def delete_session(session_id: str) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = $1", session_id)


async def get_user_sessions(user_id: str) -> list[dict]:
    """Get all sessions for a user, newest first."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, count(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.user_id = $1
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """,
            user_id,
        )
        return [dict(r) for r in rows]


async def verify_session_ownership(session_id: str, user_id: str) -> bool:
    """Verify that a session belongs to the given user. Returns True if owned or DB unavailable."""
    if not _pool:
        return True
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM sessions WHERE id = $1", session_id
        )
        return row is not None and row["user_id"] == user_id


# ── Messages ──────────────────────────────────────────────────────────────────

async def add_message(
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    if not _pool:
        return {"id": message_id, "session_id": session_id, "role": role, "content": content}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO messages (id, session_id, role, content, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING *
            """,
            message_id, session_id, role, content,
            json.dumps(metadata) if metadata else None,
        )
        return dict(row)


async def get_session_messages(session_id: str, limit: int = 50) -> list[dict]:
    """Get messages for a session, ordered by creation time."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            session_id, limit,
        )
        return [dict(r) for r in rows]


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Get the most recent N messages for LLM context."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            session_id, limit,
        )
        # Reverse to get chronological order
        return [dict(r) for r in reversed(rows)]


# ── Feedback ─────────────────────────────────────────────────────────────────

async def add_feedback(
    feedback_id: str,
    session_id: str,
    message_id: str,
    rating: str,
    correction: str | None = None,
    metadata: dict | None = None,
) -> dict:
    if not _pool:
        return {"id": feedback_id, "rating": rating}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO feedback (id, session_id, message_id, rating, correction, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING *
            """,
            feedback_id, session_id, message_id, rating, correction,
            json.dumps(metadata) if metadata else "{}",
        )
        return dict(row)


async def get_feedback_stats() -> dict:
    """Get aggregate feedback stats for monitoring AI quality."""
    if not _pool:
        return {}
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT rating, COUNT(*) as cnt
            FROM feedback
            GROUP BY rating
        """)
        stats = {r["rating"]: r["cnt"] for r in rows}
        correction_count = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE correction IS NOT NULL"
        )
        stats["corrections_with_text"] = correction_count
        return stats


async def get_corrections(limit: int = 50) -> list[dict]:
    """Get recent corrections for review/training."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT f.id, f.session_id, f.message_id, f.correction, f.metadata,
                   f.created_at, m.content as original_response
            FROM feedback f
            LEFT JOIN messages m ON m.id = f.message_id
            WHERE f.correction IS NOT NULL
            ORDER BY f.created_at DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


# ── Bundle Locks ─────────────────────────────────────────────────────────────

async def acquire_bundle_lock(bundle_id: str, user_id: str, ttl_seconds: int = 300) -> bool:
    """Acquire a lock on a bundle. Returns True if the lock was acquired.

    Inserts a new lock if none exists or the existing lock has expired.
    Uses a single atomic query to prevent race conditions.
    """
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bundle_locks (bundle_id, locked_by, locked_at, expires_at)
            VALUES ($1, $2, now(), now() + make_interval(secs => $3))
            ON CONFLICT (bundle_id) DO UPDATE
                SET locked_by  = EXCLUDED.locked_by,
                    locked_at  = EXCLUDED.locked_at,
                    expires_at = EXCLUDED.expires_at
                WHERE bundle_locks.expires_at < now()
                   OR bundle_locks.locked_by = $2
            RETURNING bundle_id
            """,
            bundle_id, user_id, float(ttl_seconds),
        )
        return row is not None


async def release_bundle_lock(bundle_id: str, user_id: str) -> bool:
    """Release a bundle lock. Only the lock owner can release it.

    Returns True if the lock was released.
    """
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM bundle_locks WHERE bundle_id = $1 AND locked_by = $2",
            bundle_id, user_id,
        )
        return result == "DELETE 1"


async def get_bundle_lock(bundle_id: str) -> dict | None:
    """Get the current lock info for a bundle, or None if unlocked/expired."""
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT bundle_id, locked_by, locked_at, expires_at
            FROM bundle_locks
            WHERE bundle_id = $1 AND expires_at > now()
            """,
            bundle_id,
        )
        return dict(row) if row else None


# ── Guardrail Events (Responsible AI Audit Trail) ────────────────────────────

async def log_guardrail_event(
    event_type: str,
    details: dict | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Log a guardrail event to the audit trail.

    event_type: one of pii_detected, injection_attempt, low_confidence,
                content_filtered, system_prompt_leak, script_injection,
                bundle_safety, length_exceeded, unsupported_language
    """
    if not _pool:
        logger.info("Guardrail event (no DB): %s %s", event_type, details)
        return None
    event_id = str(import_uuid())
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO guardrail_events (id, user_id, session_id, event_type, details)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING *
                """,
                event_id, user_id, session_id, event_type,
                json.dumps(details or {}),
            )
            return dict(row) if row else None
    except Exception as e:
        logger.warning("Failed to log guardrail event: %s", e)
        return None


def import_uuid():
    """Lazy import to avoid circular imports."""
    import uuid as _uuid
    return _uuid.uuid4()


async def get_guardrail_events(
    user_id: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query guardrail events with optional filters."""
    if not _pool:
        return []
    conditions = []
    params = []
    idx = 1
    if user_id:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1
    if session_id:
        conditions.append(f"session_id = ${idx}")
        params.append(session_id)
        idx += 1
    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type)
        idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM guardrail_events
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${idx}
            """,
            *params,
        )
        return [dict(r) for r in rows]


async def get_guardrail_stats() -> dict:
    """Get aggregate guardrail event statistics for monitoring."""
    if not _pool:
        return {}
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT event_type, COUNT(*) as cnt
            FROM guardrail_events
            GROUP BY event_type
            ORDER BY cnt DESC
        """)
        stats = {r["event_type"]: r["cnt"] for r in rows}

        # Get last 24h counts
        recent_rows = await conn.fetch("""
            SELECT event_type, COUNT(*) as cnt
            FROM guardrail_events
            WHERE created_at > now() - interval '24 hours'
            GROUP BY event_type
        """)
        stats["last_24h"] = {r["event_type"]: r["cnt"] for r in recent_rows}

        return stats


# ── Admin User Management ─────────────────────────────────────────────────

async def list_users(
    role: str | None = None,
    org_name: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List users with optional filters. Returns user dicts without password_hash."""
    if not _pool:
        return []
    conditions = []
    params: list[Any] = []
    idx = 1
    if role:
        conditions.append(f"role = ${idx}")
        params.append(role)
        idx += 1
    if org_name:
        conditions.append(f"org_name = ${idx}")
        params.append(org_name)
        idx += 1
    if is_active is not None:
        conditions.append(f"is_active = ${idx}")
        params.append(is_active)
        idx += 1
    if search:
        conditions.append(f"(name ILIKE ${idx} OR email ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, name, email, org_name, org_id, sector, role, is_active, pending_approval, last_login, created_at
            FROM users
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )
        return [dict(r) for r in rows]


async def create_user_admin(
    user_id: str, name: str, email: str, password_hash: str,
    org_name: str, sector: str, role: str, org_context: str,
    force_password_change: bool = False,
    pending_approval: bool = False,
) -> dict:
    """Create a user via admin. Derives org_id from org_name. Returns user dict without password_hash."""
    org_id = _slugify_org(org_name)
    if not _pool:
        return {"id": user_id, "name": name, "email": email, "org_name": org_name, "org_id": org_id, "role": role}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, name, email, password_hash, org_name, org_id, sector, org_context,
                               role, is_active, force_password_change, pending_approval)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, true, $10, $11)
            RETURNING id, name, email, org_name, org_id, sector, org_context, role, is_active,
                      force_password_change, pending_approval, created_at
            """,
            user_id, name, email, password_hash, org_name, org_id, sector, org_context,
            role, force_password_change, pending_approval,
        )
        return dict(row)


async def update_user_role(user_id: str, role: str) -> bool:
    """Update a user's role. Returns True if the user was found and updated."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET role = $1 WHERE id = $2", role, user_id,
        )
        return result == "UPDATE 1"


async def update_user_status(user_id: str, is_active: bool) -> bool:
    """Activate or deactivate a user. Returns True if updated."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET is_active = $1 WHERE id = $2", is_active, user_id,
        )
        return result == "UPDATE 1"


async def count_users_by_role(role: str) -> int:
    """Count users with a given role (only active users)."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE role = $1 AND is_active = true", role,
        )


async def get_platform_stats() -> dict:
    """Get platform-wide stats for the admin dashboard (parallel queries)."""
    if not _pool:
        return {}
    async with _pool.acquire() as conn:
        # Run all independent queries in parallel for ~5x speedup
        (
            total_users,
            active_users,
            role_rows,
            org_rows,
            total_sessions,
            messages_24h,
            messages_7d,
            messages_30d,
        ) = await asyncio.gather(
            conn.fetchval("SELECT COUNT(*) FROM users"),
            conn.fetchval("SELECT COUNT(*) FROM users WHERE is_active = true"),
            conn.fetch("SELECT role, COUNT(*) as cnt FROM users GROUP BY role"),
            conn.fetch("SELECT org_name, COUNT(*) as cnt FROM users GROUP BY org_name ORDER BY cnt DESC"),
            conn.fetchval("SELECT COUNT(*) FROM sessions"),
            conn.fetchval("SELECT COUNT(*) FROM messages WHERE created_at > now() - interval '24 hours'"),
            conn.fetchval("SELECT COUNT(*) FROM messages WHERE created_at > now() - interval '7 days'"),
            conn.fetchval("SELECT COUNT(*) FROM messages WHERE created_at > now() - interval '30 days'"),
        )

        users_by_role = {r["role"]: r["cnt"] for r in role_rows}
        users_by_org = {r["org_name"]: r["cnt"] for r in org_rows}

        return {
            "total_users": total_users or 0,
            "active_users": active_users or 0,
            "users_by_role": users_by_role,
            "users_by_org": users_by_org,
            "total_sessions": total_sessions or 0,
            "messages_24h": messages_24h or 0,
            "messages_7d": messages_7d or 0,
            "messages_30d": messages_30d or 0,
        }


async def has_platform_admin() -> bool:
    """Check if at least one platform_admin user exists."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE role = 'platform_admin' AND is_active = true"
        )
        return (count or 0) > 0


async def get_user_details(user_id: str) -> dict | None:
    """Get full user details including session count and last activity."""
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, email, org_name, org_id, sector, org_context, role, is_active,
                   pending_approval, force_password_change, last_login, created_at
            FROM users WHERE id = $1
            """,
            user_id,
        )
        if not row:
            return None
        user = dict(row)
        user["session_count"] = await conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE user_id = $1", user_id,
        )
        user["last_activity"] = await conn.fetchval(
            """
            SELECT MAX(m.created_at) FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.user_id = $1
            """,
            user_id,
        )
        return user


# ── Org-scoped Queries ───────────────────────────────────────────────────────

async def get_org_users(org_id: str) -> list[dict]:
    """Get all users in an org."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, email, org_name, org_id, sector, role, is_active,
                   pending_approval, last_login, created_at
            FROM users
            WHERE org_id = $1
            ORDER BY created_at DESC
            """,
            org_id,
        )
        return [dict(r) for r in rows]


async def get_org_stats(org_id: str) -> dict:
    """Get stats for a specific org (user count, session count, message count)."""
    if not _pool:
        return {"org_id": org_id, "user_count": 0, "session_count": 0, "message_count": 0}
    async with _pool.acquire() as conn:
        user_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE org_id = $1", org_id,
        ) or 0
        session_count = await conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE org_id = $1", org_id,
        ) or 0
        message_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.org_id = $1
            """,
            org_id,
        ) or 0
        return {
            "org_id": org_id,
            "user_count": user_count,
            "session_count": session_count,
            "message_count": message_count,
        }


async def get_all_orgs() -> list[dict]:
    """Get list of all orgs with user counts."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT org_id, org_name, COUNT(*) as user_count, MIN(created_at) as created_at
            FROM users
            WHERE org_id != ''
            GROUP BY org_id, org_name
            ORDER BY user_count DESC
            """
        )
        return [dict(r) for r in rows]


async def count_all_users() -> int:
    """Count total users in the database. Used for first-user bootstrap check."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users") or 0


async def update_user_approval(user_id: str, pending_approval: bool) -> bool:
    """Update a user's pending_approval status. Returns True if updated."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET pending_approval = $1 WHERE id = $2",
            pending_approval, user_id,
        )
        return result == "UPDATE 1"


async def update_force_password_change(user_id: str, force: bool) -> bool:
    """Update a user's force_password_change flag. Returns True if updated."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET force_password_change = $1 WHERE id = $2",
            force, user_id,
        )
        return result == "UPDATE 1"


# ── Refresh Token Management (Token Rotation) ────────────────────────────

async def store_refresh_token(token_hash: str, user_id: str, expires_at: datetime) -> None:
    """Store a hashed refresh token in the database."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO refresh_tokens (token_hash, user_id, expires_at) VALUES ($1, $2, $3)",
            token_hash, user_id, expires_at,
        )


async def verify_refresh_token(token_hash: str) -> dict | None:
    """Verify a refresh token exists and is not expired. Returns token record or None."""
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT token_hash, user_id, expires_at, created_at FROM refresh_tokens WHERE token_hash = $1 AND expires_at > now()",
            token_hash,
        )
        return dict(row) if row else None


async def revoke_refresh_token(token_hash: str) -> None:
    """Revoke (delete) a single refresh token."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM refresh_tokens WHERE token_hash = $1", token_hash)


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (used on logout or password change)."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)


async def cleanup_expired_tokens() -> int:
    """Delete all expired refresh tokens. Returns the number removed."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM refresh_tokens WHERE expires_at < now()")
        return int(result.split()[-1])


# ── Admin Audit Log ──────────────────────────────────────────────────────

async def log_admin_action(
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict | None = None,
) -> dict | None:
    """Log an admin action to the audit trail.

    action: e.g. 'user_created', 'role_changed', 'status_changed', 'user_deleted'
    target_type: e.g. 'user', 'session', 'bundle'
    """
    if not _pool:
        logger.info("Admin audit (no DB): %s %s %s %s", actor_id, action, target_type, details)
        return None
    event_id = str(import_uuid())
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_log (id, actor_id, action, target_type, target_id, details)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                event_id, actor_id, action, target_type, target_id,
                json.dumps(details or {}),
            )
            return dict(row) if row else None
    except Exception as e:
        logger.warning("Failed to log admin action: %s", e)
        return None


async def get_audit_log(
    actor_id: str | None = None,
    action: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query audit log with optional filters."""
    if not _pool:
        return []
    conditions = []
    params: list[Any] = []
    idx = 1
    if actor_id:
        conditions.append(f"actor_id = ${idx}")
        params.append(actor_id)
        idx += 1
    if action:
        conditions.append(f"action = ${idx}")
        params.append(action)
        idx += 1
    if target_id:
        conditions.append(f"target_id = ${idx}")
        params.append(target_id)
        idx += 1
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM audit_log
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${idx}
            """,
            *params,
        )
        return [dict(r) for r in rows]


async def update_user_password(user_id: str, password_hash: str) -> bool:
    """Update a user's password hash. Returns True if updated."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET password_hash = $1, force_password_change = false WHERE id = $2",
            password_hash, user_id,
        )
        return result == "UPDATE 1"


async def cleanup_expired_locks() -> int:
    """Delete all expired bundle locks. Returns the number of locks removed."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM bundle_locks WHERE expires_at < now()"
        )
        # result is like "DELETE 5"
        return int(result.split()[-1])


# ── Ban Lists (per-org configurable banned words) ───────────────────────────

async def add_ban_word(org_id: str, word: str, reason: str = "", created_by: str = "") -> dict | None:
    """Add a word to an org's ban list. Returns the created row."""
    if not _pool:
        return None
    ban_id = str(import_uuid())
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ban_lists (id, org_id, word, reason, created_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (org_id, word) DO UPDATE SET reason = EXCLUDED.reason
            RETURNING *
            """,
            ban_id, org_id, word.lower().strip(), reason, created_by,
        )
        return dict(row) if row else None


async def remove_ban_word(org_id: str, word: str) -> bool:
    """Remove a word from an org's ban list. Returns True if removed."""
    if not _pool:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM ban_lists WHERE org_id = $1 AND word = $2",
            org_id, word.lower().strip(),
        )
        return result == "DELETE 1"


async def get_org_ban_list(org_id: str) -> list[dict]:
    """Get all banned words for an org."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, org_id, word, reason, created_by, created_at FROM ban_lists WHERE org_id = $1 ORDER BY word",
            org_id,
        )
        return [dict(r) for r in rows]


async def load_all_ban_lists() -> list[dict]:
    """Load all ban list entries from all orgs. Used for in-memory cache warm-up."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT org_id, word, reason FROM ban_lists ORDER BY org_id, word"
        )
        return [dict(r) for r in rows]
