-- Sprint 6 chunk 6.11: policy_drafts + policy_revisions tables
-- Refs: PLAN.md chunk 6.11; ADR-0007; US-011, US-012.

-- policy_drafts — stores the current state of each policy draft
CREATE TABLE IF NOT EXISTS policy_drafts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    policy_type TEXT NOT NULL CHECK (policy_type IN ('irp', 'access_control', 'change_management', 'vendor_management')),
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    version     INTEGER NOT NULL DEFAULT 1,
    finalized   BOOLEAN NOT NULL DEFAULT FALSE,
    thread_id   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_drafts_user_id
    ON policy_drafts (user_id);

CREATE INDEX IF NOT EXISTS idx_policy_drafts_user_type
    ON policy_drafts (user_id, policy_type);

-- RLS policy: users can only see their own policy drafts.
ALTER TABLE policy_drafts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'policy_drafts' AND policyname = 'policy_drafts__user_isolation'
    ) THEN
        CREATE POLICY policy_drafts__user_isolation ON policy_drafts
            USING (user_id = current_setting('app.current_user_id', true));
    END IF;
END $$;


-- policy_revisions — immutable log of every version for the internal change history
CREATE TABLE IF NOT EXISTS policy_revisions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id   UUID NOT NULL REFERENCES policy_drafts(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    version     INTEGER NOT NULL DEFAULT 1,
    source      TEXT NOT NULL DEFAULT 'agent_draft' CHECK (source IN ('agent_draft', 'user_edit', 'hitl_edit', 'finalize')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_revisions_policy_id
    ON policy_revisions (policy_id);

CREATE INDEX IF NOT EXISTS idx_policy_revisions_user_id
    ON policy_revisions (user_id);

-- RLS policy: users can only see revisions for their own policies.
ALTER TABLE policy_revisions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'policy_revisions' AND policyname = 'policy_revisions__user_isolation'
    ) THEN
        CREATE POLICY policy_revisions__user_isolation ON policy_revisions
            USING (user_id = current_setting('app.current_user_id', true));
    END IF;
END $$;
