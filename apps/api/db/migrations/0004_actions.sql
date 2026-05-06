-- Migration: 0004_actions
-- Purpose:   Pending Actions queue (US-007 / US-032).
--            Actions are produced by the orchestrator + adversarial auditor;
--            the user triages them via the dashboard. Sprint 4 chunk 4.8
--            stands up the table + state machine; Sprint 5 chunk 5.x feeds
--            it from real evidence; Sprint 9 chunk 9.14-9.15 ships the
--            "Revert" affordance for completed→revoked transitions.
-- Idempotent: yes — every statement uses IF NOT EXISTS / DO $$ blocks.
-- Refs:      PLAN.md Sprint 4 chunks 4.7, 4.8; ADR-0008 (Neon Postgres);
--            US-007, US-032; system-design.md 4 (ERD).

CREATE TABLE IF NOT EXISTS actions (
    id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           TEXT         NOT NULL,
    scan_run_id       TEXT,
    kind              TEXT         NOT NULL,
    title             TEXT         NOT NULL,
    description       TEXT         NOT NULL DEFAULT '',
    status            TEXT         NOT NULL DEFAULT 'pending_review',
    tsc_id            TEXT,
    source_link       TEXT,
    rejected_reason   TEXT,
    revoked_reason    TEXT,
    revoked_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT actions__status_chk CHECK (
        status IN ('pending_review', 'approved', 'rejected', 'completed', 'revoked')
    )
);

-- Hot-path index for the dashboard list: scope by user, filter by status,
-- order by created_at DESC. user_id leads (consistent with the
-- 0003 connector_scoped_repos pattern, database-reviewer C-2 fix).
CREATE INDEX IF NOT EXISTS ix_actions__user_status_created
    ON actions (user_id, status, created_at DESC);

-- Cross-table query: "actions for this scan_run." user_id leads here too.
CREATE INDEX IF NOT EXISTS ix_actions__user_scan_run
    ON actions (user_id, scan_run_id)
    WHERE scan_run_id IS NOT NULL;

-- Row Level Security — defense-in-depth on top of explicit WHERE filters.
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'actions'
          AND policyname = 'actions__user_isolation'
    ) THEN
        CREATE POLICY actions__user_isolation
            ON actions
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END$$;

COMMENT ON TABLE actions IS
    'Pending Actions queue (US-007). status state machine: pending_review → approved/rejected/completed; completed → revoked (US-032). user_id is the Clerk user id (e.g. user_*).';
