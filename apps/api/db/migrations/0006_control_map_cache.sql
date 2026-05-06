-- Migration: 0006_control_map_cache
-- Purpose:   Memoization table for the evidence → TSC control mapping.
--            Cache key: (user_id, content_hash, control_id, prompt_version,
--                        kb_version).
--
--            When the orchestrator needs to map an Evidence row to a
--            ControlAssessment it first checks this table. On a hit it reuses
--            the stored assessment without re-running BM25 or calling the LLM.
--            On a miss it runs the mapping and INSERTs the result so the next
--            run with the same evidence is free.
--
--            Hit-rate target: ≥ 60% on a re-scan within 24 h (measured in
--            Sprint 10 evals — chunk 10.5).
--
-- Idempotent: yes — IF NOT EXISTS / DO $$ blocks throughout.
-- Refs: PLAN.md Sprint 5 chunk 5.2; system-design.md §12.5; ADR-0013.

CREATE TABLE IF NOT EXISTS control_map_cache (
    id               UUID              PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          TEXT              NOT NULL,
    -- SHA-256 of the normalized evidence payload (same value as evidence.content_hash).
    content_hash     TEXT              NOT NULL,
    -- TSC clause id, e.g. 'CC6.1', or a NIST 800-53 control id, e.g. 'AC-1'.
    control_id       TEXT              NOT NULL,
    -- Prompt version string from YAML at apps/api/agents/prompts/. Defaults to
    -- 'v1' (no LLM call yet in Sprint 4/5; Sprint 10 may introduce one).
    prompt_version   TEXT              NOT NULL DEFAULT 'v1',
    -- compliance-kb-mcp published version that produced the mapping. Bumped
    -- when the NIST 800-53 dataset or SOC 2 TSC mappings change.
    kb_version       TEXT              NOT NULL DEFAULT '0.2.0',
    -- Cached ControlAssessment fields.
    status           TEXT              NOT NULL
        CONSTRAINT control_map_cache__status_chk
            CHECK (status IN ('passing', 'failing', 'partial', 'unknown')),
    confidence       DOUBLE PRECISION  NOT NULL
        CONSTRAINT control_map_cache__confidence_chk
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
    nist_800_53_refs TEXT[]            NOT NULL DEFAULT '{}',
    evidence_ids     TEXT[]            NOT NULL DEFAULT '{}',
    rationale        TEXT,
    computed_at      TIMESTAMPTZ       NOT NULL DEFAULT now()
);

-- Unique cache key — the combination that uniquely identifies one mapping result.
-- ON CONFLICT (user_id, content_hash, control_id, prompt_version, kb_version)
-- DO UPDATE used by the upsert path in evidence_persistence.py.
CREATE UNIQUE INDEX IF NOT EXISTS ux_control_map_cache__key
    ON control_map_cache (user_id, content_hash, control_id, prompt_version, kb_version);

-- Hot-path lookup: "all cached assessments for this user's evidence batch".
-- user_id leads (database-reviewer C-2 pattern from 0003/0004/0005).
CREATE INDEX IF NOT EXISTS ix_control_map_cache__user_hash
    ON control_map_cache (user_id, content_hash);

ALTER TABLE control_map_cache ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'control_map_cache'
          AND policyname = 'control_map_cache__user_isolation'
    ) THEN
        CREATE POLICY control_map_cache__user_isolation
            ON control_map_cache
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END$$;

COMMENT ON TABLE control_map_cache IS
    'Memoisation of evidence → ControlAssessment mappings. Cache key: '
    '(user_id, content_hash, control_id, prompt_version, kb_version). '
    'Eliminates redundant BM25 and LLM calls on re-scans.';
