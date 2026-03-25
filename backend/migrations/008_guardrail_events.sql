-- Migration 008: Responsible AI guardrail events audit trail
-- Date: 2026-03-11
-- Description: Adds guardrail_events table for tracking PII detection,
--              prompt injection attempts, low confidence responses,
--              system prompt leaks, and other guardrail triggers.

CREATE TABLE IF NOT EXISTS guardrail_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    session_id  TEXT,
    event_type  TEXT NOT NULL CHECK (event_type IN (
        'pii_detected',
        'injection_attempt',
        'low_confidence',
        'content_filtered',
        'system_prompt_leak',
        'script_injection',
        'bundle_safety',
        'length_exceeded',
        'unsupported_language'
    )),
    details     JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_guardrail_events_user_id ON guardrail_events(user_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_session_id ON guardrail_events(session_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_event_type ON guardrail_events(event_type);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_created_at ON guardrail_events(created_at);

-- Useful aggregate view for monitoring
CREATE OR REPLACE VIEW guardrail_summary AS
SELECT
    event_type,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours') AS last_24h,
    COUNT(*) FILTER (WHERE created_at > now() - interval '7 days') AS last_7d,
    MAX(created_at) AS last_occurrence
FROM guardrail_events
GROUP BY event_type
ORDER BY total_count DESC;
