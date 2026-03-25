-- Migration: Enable Row-Level Security (RLS) for multi-tenant isolation.
--
-- All org_id-scoped tables get a policy that restricts rows to the current
-- org context set via SET LOCAL app.org_id = '<org_id>'.
--
-- The platform_admin role bypasses RLS to manage all orgs.
-- Idempotent: safe to run multiple times.

-- ============================================================================
-- 1. Helper function: set_org_context(org_id text)
--    Sets the session-local GUC variable used by RLS policies.
-- ============================================================================
CREATE OR REPLACE FUNCTION set_org_context(p_org_id text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM set_config('app.org_id', p_org_id, true);  -- true = local to transaction
END;
$$;

-- ============================================================================
-- 2. Create platform_admin role (if not exists) with BYPASSRLS
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_admin') THEN
        CREATE ROLE platform_admin NOLOGIN BYPASSRLS;
    ELSE
        ALTER ROLE platform_admin BYPASSRLS;
    END IF;
END $$;

-- ============================================================================
-- 3. Enable RLS and create isolation policies on org_id-scoped tables
-- ============================================================================

-- Helper: enable RLS + create org_isolation policy + admin bypass policy.
-- We use a DO block with dynamic SQL so we can skip tables that don't exist yet.

DO $$
DECLARE
    tbl text;
    org_col text;
BEGIN
    -- Tables that have a direct org_id column
    FOR tbl IN
        SELECT unnest(ARRAY[
            'users', 'sessions', 'ban_lists', 'audit_log',
            'feedback', 'bundle_status', 'org_memory',
            'preferences', 'custom_instructions', 'saved_prompts'
        ])
    LOOP
        -- Skip if table does not exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            RAISE NOTICE 'Skipping RLS for non-existent table: %', tbl;
            CONTINUE;
        END IF;

        -- Skip if table has no org_id column
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'org_id'
        ) THEN
            RAISE NOTICE 'Skipping RLS for table without org_id: %', tbl;
            CONTINUE;
        END IF;

        -- Enable RLS (idempotent)
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);

        -- Drop existing policies to make migration re-runnable
        EXECUTE format('DROP POLICY IF EXISTS org_isolation ON %I', tbl);
        EXECUTE format('DROP POLICY IF EXISTS platform_admin_bypass ON %I', tbl);

        -- Org isolation policy: rows visible only when app.org_id matches
        EXECUTE format(
            'CREATE POLICY org_isolation ON %I
                FOR ALL
                USING (org_id = current_setting(''app.org_id'', true))',
            tbl
        );

        -- Platform admin bypass: full access for platform_admin role
        EXECUTE format(
            'CREATE POLICY platform_admin_bypass ON %I
                FOR ALL
                TO platform_admin
                USING (true)
                WITH CHECK (true)',
            tbl
        );

        RAISE NOTICE 'RLS enabled on table: %', tbl;
    END LOOP;
END $$;

-- ============================================================================
-- 4. Messages table: isolate via session's org_id (messages have no direct org_id)
--    Messages join through sessions, so we use a subquery policy.
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'messages'
    ) THEN
        ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

        DROP POLICY IF EXISTS org_isolation ON messages;
        DROP POLICY IF EXISTS platform_admin_bypass ON messages;

        CREATE POLICY org_isolation ON messages
            FOR ALL
            USING (
                session_id IN (
                    SELECT id FROM sessions
                    WHERE org_id = current_setting('app.org_id', true)
                )
            );

        CREATE POLICY platform_admin_bypass ON messages
            FOR ALL
            TO platform_admin
            USING (true)
            WITH CHECK (true);

        RAISE NOTICE 'RLS enabled on table: messages';
    END IF;
END $$;

-- ============================================================================
-- 5. Tables WITHOUT org_id that should NOT have tenant RLS:
--    - bundle_locks (keyed by bundle_id, short-lived)
--    - guardrail_events (system-wide audit, no org scope)
--    - refresh_tokens (keyed by user_id, auth infrastructure)
--
--    These are intentionally excluded from RLS.
-- ============================================================================
