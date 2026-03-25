"""V2 schema migrations for Avni AI Platform.

Adds new columns to existing tables (users, sessions, messages) and creates
new tables: user_preferences, saved_prompts, org_memory, audit_log,
token_usage, bundle_versions, schema_migrations.

All operations are idempotent -- safe to run multiple times.
Uses asyncpg throughout; accepts a pool parameter or falls back to app.db._pool.
"""

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# ── Migration Definitions ────────────────────────────────────────────────────

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "Add role, org_id, last_login, is_active to users; org_id to sessions and messages",
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'implementor';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT '';

        ALTER TABLE messages ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT '';
        """,
    ),
    (
        2,
        "Create user_preferences table",
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id             TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            theme               TEXT DEFAULT 'light',
            language            TEXT DEFAULT 'en',
            default_view        TEXT DEFAULT 'chat',
            sidebar_collapsed   BOOLEAN DEFAULT false,
            show_tour           BOOLEAN DEFAULT true,
            auto_confirm        BOOLEAN DEFAULT false,
            custom_instructions TEXT DEFAULT '',
            notification_prefs  JSONB DEFAULT '{"email": false, "in_app": true}'::jsonb,
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        );
        """,
    ),
    (
        3,
        "Create saved_prompts table",
        """
        CREATE TABLE IF NOT EXISTS saved_prompts (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            category    TEXT DEFAULT 'general',
            is_pinned   BOOLEAN DEFAULT false,
            use_count   INT DEFAULT 0,
            created_at  TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_saved_prompts_user ON saved_prompts(user_id);
        """,
    ),
    (
        4,
        "Create org_memory table",
        """
        CREATE TABLE IF NOT EXISTS org_memory (
            org_id              TEXT PRIMARY KEY,
            org_name            TEXT NOT NULL,
            subject_types       JSONB DEFAULT '[]'::jsonb,
            programs            JSONB DEFAULT '[]'::jsonb,
            encounter_types     JSONB DEFAULT '[]'::jsonb,
            known_concepts      JSONB DEFAULT '[]'::jsonb,
            terminology         JSONB DEFAULT '{}'::jsonb,
            previous_bundles    JSONB DEFAULT '[]'::jsonb,
            avni_server_url     TEXT DEFAULT '',
            last_synced         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        );
        """,
    ),
    (
        5,
        "Create audit_log table",
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id              BIGSERIAL PRIMARY KEY,
            user_id         TEXT,
            org_id          TEXT,
            action          TEXT NOT NULL,
            resource_type   TEXT NOT NULL DEFAULT '',
            resource_id     TEXT,
            details         JSONB DEFAULT '{}'::jsonb,
            ip_address      TEXT,
            created_at      TIMESTAMPTZ DEFAULT now()
        );
        -- Add user_id column if table was created by legacy MIGRATION_SQL with actor_id
        DO $$ BEGIN
            ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS user_id TEXT;
            ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS org_id TEXT;
            ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS resource_type TEXT DEFAULT '';
            ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS resource_id TEXT;
            ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS ip_address TEXT;
        EXCEPTION WHEN others THEN NULL;
        END $$;
        CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
        """,
    ),
    (
        6,
        "Create token_usage table",
        """
        CREATE TABLE IF NOT EXISTS token_usage (
            id                  BIGSERIAL PRIMARY KEY,
            org_id              TEXT NOT NULL,
            user_id             TEXT,
            provider            TEXT NOT NULL,
            model               TEXT NOT NULL,
            prompt_tokens       INT DEFAULT 0,
            completion_tokens   INT DEFAULT 0,
            total_tokens        INT DEFAULT 0,
            cost_usd            NUMERIC(10, 6) DEFAULT 0,
            created_at          TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_token_usage_org ON token_usage(org_id);
        CREATE INDEX IF NOT EXISTS idx_token_usage_created ON token_usage(created_at);
        CREATE INDEX IF NOT EXISTS idx_token_usage_org_month
            ON token_usage(org_id, date_trunc('month', created_at AT TIME ZONE 'UTC'));
        """,
    ),
    (
        7,
        "Create bundle_versions table",
        """
        CREATE TABLE IF NOT EXISTS bundle_versions (
            id                  TEXT PRIMARY KEY,
            org_id              TEXT NOT NULL,
            user_id             TEXT NOT NULL,
            bundle_name         TEXT NOT NULL,
            version             INT DEFAULT 1,
            status              TEXT DEFAULT 'generated',
            srs_snapshot        JSONB,
            validation_result   JSONB,
            file_path           TEXT,
            file_size_bytes     BIGINT,
            uploaded_at         TIMESTAMPTZ,
            upload_result       JSONB,
            created_at          TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bundle_versions_org ON bundle_versions(org_id);
        CREATE INDEX IF NOT EXISTS idx_bundle_versions_user ON bundle_versions(user_id);
        """,
    ),
    (
        8,
        "Add email and password_hash to users for JWT auth",
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
        """,
    ),
    (
        9,
        "Create tool_calling_settings table for MCP tool configuration",
        """
        CREATE TABLE IF NOT EXISTS tool_calling_settings (
            id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            org_id          TEXT NOT NULL DEFAULT '',
            tool_name       TEXT NOT NULL,
            enabled         BOOLEAN DEFAULT true,
            model_override  TEXT,
            config          JSONB DEFAULT '{}',
            created_at      TIMESTAMPTZ DEFAULT now(),
            updated_at      TIMESTAMPTZ DEFAULT now(),
            UNIQUE(org_id, tool_name)
        );
        CREATE INDEX IF NOT EXISTS idx_tcs_org ON tool_calling_settings(org_id);
        """,
    ),
]


# ── Bootstrap: ensure schema_migrations table exists ─────────────────────────

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT now()
);
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_pool(pool: asyncpg.Pool | None = None) -> asyncpg.Pool:
    """Return the provided pool or fall back to the global pool from app.db."""
    if pool is not None:
        return pool
    from app.db import _pool as global_pool
    if global_pool is None:
        raise RuntimeError("No database pool available. Call init_db() first.")
    return global_pool


# ── Migration Runner ─────────────────────────────────────────────────────────

async def run_migrations(pool: asyncpg.Pool | None = None) -> list[str]:
    """Run all pending migrations idempotently.

    Returns a list of descriptions for migrations that were applied in this run.
    """
    p = _get_pool(pool)
    applied: list[str] = []

    async with p.acquire() as conn:
        # Ensure the tracking table exists
        await conn.execute(SCHEMA_MIGRATIONS_DDL)

        # Find which versions have already been applied
        rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        applied_versions: set[int] = {r["version"] for r in rows}

        for version, description, sql in MIGRATIONS:
            if version in applied_versions:
                logger.debug("Migration v%d already applied, skipping: %s", version, description)
                continue

            logger.info("Applying migration v%d: %s", version, description)
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES ($1, $2)",
                        version, description,
                    )
                applied.append(description)
                logger.info("Migration v%d applied successfully", version)
            except Exception:
                logger.exception("Migration v%d failed", version)
                raise

    if applied:
        logger.info("Applied %d migration(s)", len(applied))
    else:
        logger.info("All migrations already applied — schema is up to date")

    return applied


async def get_current_version(pool: asyncpg.Pool | None = None) -> int:
    """Return the highest applied migration version, or 0 if none."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        await conn.execute(SCHEMA_MIGRATIONS_DDL)
        val = await conn.fetchval("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        return int(val)


# ══════════════════════════════════════════════════════════════════════════════
# CRUD Functions for New Tables
# ══════════════════════════════════════════════════════════════════════════════


# ── User Preferences ─────────────────────────────────────────────────────────

async def upsert_preferences(
    user_id: str,
    pool: asyncpg.Pool | None = None,
    *,
    theme: str | None = None,
    language: str | None = None,
    default_view: str | None = None,
    sidebar_collapsed: bool | None = None,
    show_tour: bool | None = None,
    auto_confirm: bool | None = None,
    custom_instructions: str | None = None,
    notification_prefs: dict | None = None,
) -> dict[str, Any]:
    """Create or update user preferences. Only provided fields are updated."""
    p = _get_pool(pool)

    # Build the SET clause dynamically for non-None fields
    fields: dict[str, Any] = {}
    if theme is not None:
        fields["theme"] = theme
    if language is not None:
        fields["language"] = language
    if default_view is not None:
        fields["default_view"] = default_view
    if sidebar_collapsed is not None:
        fields["sidebar_collapsed"] = sidebar_collapsed
    if show_tour is not None:
        fields["show_tour"] = show_tour
    if auto_confirm is not None:
        fields["auto_confirm"] = auto_confirm
    if custom_instructions is not None:
        fields["custom_instructions"] = custom_instructions
    if notification_prefs is not None:
        fields["notification_prefs"] = json.dumps(notification_prefs)

    async with p.acquire() as conn:
        if not fields:
            # Just ensure the row exists with defaults
            row = await conn.fetchrow(
                """
                INSERT INTO user_preferences (user_id)
                VALUES ($1)
                ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
                RETURNING *
                """,
                user_id,
            )
        else:
            # Build parameterized upsert
            columns = ["user_id"] + list(fields.keys())
            values = [user_id] + list(fields.values())
            placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
            col_list = ", ".join(columns)

            update_parts = [f"{k} = EXCLUDED.{k}" for k in fields]
            update_parts.append("updated_at = now()")
            update_clause = ", ".join(update_parts)

            # Handle notification_prefs cast
            cast_placeholders = []
            for i, col in enumerate(columns):
                if col == "notification_prefs":
                    cast_placeholders.append(f"${i+1}::jsonb")
                else:
                    cast_placeholders.append(f"${i+1}")
            placeholders = ", ".join(cast_placeholders)

            sql = f"""
                INSERT INTO user_preferences ({col_list})
                VALUES ({placeholders})
                ON CONFLICT (user_id) DO UPDATE SET {update_clause}
                RETURNING *
            """
            row = await conn.fetchrow(sql, *values)

        return dict(row) if row else {}


async def get_preferences(user_id: str, pool: asyncpg.Pool | None = None) -> dict[str, Any] | None:
    """Get user preferences. Returns None if no preferences are saved."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM user_preferences WHERE user_id = $1", user_id)
        return dict(row) if row else None


# ── Saved Prompts ────────────────────────────────────────────────────────────

async def save_prompt(
    user_id: str,
    title: str,
    content: str,
    category: str = "general",
    pool: asyncpg.Pool | None = None,
) -> dict[str, Any]:
    """Save a new prompt template."""
    p = _get_pool(pool)
    prompt_id = str(uuid.uuid4())
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO saved_prompts (id, user_id, title, content, category)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            prompt_id, user_id, title, content, category,
        )
        return dict(row)


async def get_saved_prompts(
    user_id: str,
    category: str | None = None,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get all saved prompts for a user, optionally filtered by category."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        if category:
            rows = await conn.fetch(
                """
                SELECT * FROM saved_prompts
                WHERE user_id = $1 AND category = $2
                ORDER BY is_pinned DESC, use_count DESC, created_at DESC
                """,
                user_id, category,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM saved_prompts
                WHERE user_id = $1
                ORDER BY is_pinned DESC, use_count DESC, created_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]


async def delete_saved_prompt(prompt_id: str, pool: asyncpg.Pool | None = None) -> bool:
    """Delete a saved prompt. Returns True if a row was actually deleted."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        result = await conn.execute("DELETE FROM saved_prompts WHERE id = $1", prompt_id)
        return result == "DELETE 1"


async def increment_prompt_use(prompt_id: str, pool: asyncpg.Pool | None = None) -> None:
    """Bump the use_count for a saved prompt."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        await conn.execute(
            "UPDATE saved_prompts SET use_count = use_count + 1 WHERE id = $1",
            prompt_id,
        )


# ── Org Memory ───────────────────────────────────────────────────────────────

async def upsert_org_memory(
    org_id: str,
    org_name: str,
    pool: asyncpg.Pool | None = None,
    *,
    subject_types: list | None = None,
    programs: list | None = None,
    encounter_types: list | None = None,
    known_concepts: list | None = None,
    terminology: dict | None = None,
    previous_bundles: list | None = None,
    avni_server_url: str | None = None,
    last_synced: datetime | None = None,
) -> dict[str, Any]:
    """Create or update an org's auto-learned memory."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO org_memory (
                org_id, org_name, subject_types, programs, encounter_types,
                known_concepts, terminology, previous_bundles, avni_server_url, last_synced
            )
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb,
                    $7::jsonb, $8::jsonb, $9, $10)
            ON CONFLICT (org_id) DO UPDATE SET
                org_name = EXCLUDED.org_name,
                subject_types = COALESCE(EXCLUDED.subject_types, org_memory.subject_types),
                programs = COALESCE(EXCLUDED.programs, org_memory.programs),
                encounter_types = COALESCE(EXCLUDED.encounter_types, org_memory.encounter_types),
                known_concepts = COALESCE(EXCLUDED.known_concepts, org_memory.known_concepts),
                terminology = COALESCE(EXCLUDED.terminology, org_memory.terminology),
                previous_bundles = COALESCE(EXCLUDED.previous_bundles, org_memory.previous_bundles),
                avni_server_url = COALESCE(EXCLUDED.avni_server_url, org_memory.avni_server_url),
                last_synced = COALESCE(EXCLUDED.last_synced, org_memory.last_synced),
                updated_at = now()
            RETURNING *
            """,
            org_id,
            org_name,
            json.dumps(subject_types) if subject_types is not None else None,
            json.dumps(programs) if programs is not None else None,
            json.dumps(encounter_types) if encounter_types is not None else None,
            json.dumps(known_concepts) if known_concepts is not None else None,
            json.dumps(terminology) if terminology is not None else None,
            json.dumps(previous_bundles) if previous_bundles is not None else None,
            avni_server_url,
            last_synced,
        )
        return dict(row) if row else {}


async def get_org_memory(org_id: str, pool: asyncpg.Pool | None = None) -> dict[str, Any] | None:
    """Get org memory. Returns None if the org has no stored memory."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM org_memory WHERE org_id = $1", org_id)
        return dict(row) if row else None


# ── Audit Log ────────────────────────────────────────────────────────────────

async def add_audit_log(
    user_id: str | None,
    org_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    pool: asyncpg.Pool | None = None,
) -> int:
    """Insert an audit log entry. Returns the new row id."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO audit_log (user_id, org_id, action, resource_type, resource_id, details, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id
            """,
            user_id, org_id, action, resource_type, resource_id,
            json.dumps(details) if details else "{}",
            ip_address,
        )
        return int(row_id)


async def get_audit_log(
    org_id: str,
    limit: int = 50,
    offset: int = 0,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get audit log entries for an org, newest first."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM audit_log
            WHERE org_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            org_id, limit, offset,
        )
        return [dict(r) for r in rows]


async def get_audit_log_by_user(
    user_id: str,
    limit: int = 50,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get audit log entries for a specific user, newest first."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM audit_log
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [dict(r) for r in rows]


# ── Token Usage ──────────────────────────────────────────────────────────────

async def track_token_usage(
    org_id: str,
    user_id: str | None,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    pool: asyncpg.Pool | None = None,
) -> int:
    """Record LLM token usage. Returns the new row id."""
    p = _get_pool(pool)
    total_tokens = prompt_tokens + completion_tokens
    async with p.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO token_usage
                (org_id, user_id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost_usd)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            org_id, user_id, provider, model,
            prompt_tokens, completion_tokens, total_tokens,
            Decimal(str(cost_usd)),
        )
        return int(row_id)


async def get_monthly_token_usage(
    org_id: str,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get token usage aggregated by month for an org."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                date_trunc('month', created_at) AS month,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(cost_usd) AS total_cost_usd,
                COUNT(*) AS request_count
            FROM token_usage
            WHERE org_id = $1
            GROUP BY month
            ORDER BY month DESC
            """,
            org_id,
        )
        return [dict(r) for r in rows]


async def get_token_usage_by_provider(
    org_id: str,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get token usage broken down by provider and model for an org."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                provider,
                model,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(cost_usd) AS total_cost_usd,
                COUNT(*) AS request_count
            FROM token_usage
            WHERE org_id = $1
            GROUP BY provider, model
            ORDER BY total_tokens DESC
            """,
            org_id,
        )
        return [dict(r) for r in rows]


# ── Bundle Versions ──────────────────────────────────────────────────────────

async def save_bundle_version(
    bundle_id: str,
    org_id: str,
    user_id: str,
    bundle_name: str,
    version: int = 1,
    status: str = "generated",
    srs_snapshot: dict | None = None,
    validation_result: dict | None = None,
    file_path: str | None = None,
    file_size_bytes: int | None = None,
    pool: asyncpg.Pool | None = None,
) -> dict[str, Any]:
    """Save a new bundle version record."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bundle_versions
                (id, org_id, user_id, bundle_name, version, status,
                 srs_snapshot, validation_result, file_path, file_size_bytes)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                validation_result = COALESCE(EXCLUDED.validation_result, bundle_versions.validation_result),
                file_path = COALESCE(EXCLUDED.file_path, bundle_versions.file_path),
                file_size_bytes = COALESCE(EXCLUDED.file_size_bytes, bundle_versions.file_size_bytes)
            RETURNING *
            """,
            bundle_id, org_id, user_id, bundle_name, version, status,
            json.dumps(srs_snapshot) if srs_snapshot else None,
            json.dumps(validation_result) if validation_result else None,
            file_path, file_size_bytes,
        )
        return dict(row)


async def update_bundle_upload(
    bundle_id: str,
    uploaded_at: datetime,
    upload_result: dict,
    status: str = "uploaded",
    pool: asyncpg.Pool | None = None,
) -> None:
    """Update a bundle version after upload to Avni."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        await conn.execute(
            """
            UPDATE bundle_versions
            SET uploaded_at = $1, upload_result = $2::jsonb, status = $3
            WHERE id = $4
            """,
            uploaded_at,
            json.dumps(upload_result),
            status,
            bundle_id,
        )


async def get_bundle_versions(
    org_id: str,
    limit: int = 50,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Get all bundle versions for an org, newest first."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM bundle_versions
            WHERE org_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            org_id, limit,
        )
        return [dict(r) for r in rows]


async def get_bundle_version(
    bundle_id: str,
    pool: asyncpg.Pool | None = None,
) -> dict[str, Any] | None:
    """Get a single bundle version by id."""
    p = _get_pool(pool)
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bundle_versions WHERE id = $1", bundle_id)
        return dict(row) if row else None
