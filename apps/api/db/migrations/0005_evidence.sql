-- Migration: 0005_evidence
-- Purpose:   Evidence store tables for Sprint 5.
--            1. scan_runs  — lightweight run envelope (US-006/030).
--            2. evidence   — raw evidence rows with pgvector(768) embeddings,
--                            GIN full-text index, HNSW ANN index, RLS, and
--                            a unique-per-(user_id, content_hash) guard so
--                            identical evidence is never duplicated (content-
--                            hash cache, Sprint 5 chunk 5.12).
--
-- Vector dimensions: 768 (Gemini text-embedding-004 default output size).
-- PLAN.md Sprint 5 chunk 5.1 overrides the 1536 placeholder in the original
-- spec after confirming text-embedding-004 outputs 768 dims by default.
--
-- Idempotent: yes — every statement uses IF NOT EXISTS / DO $$ blocks.
-- Refs: PLAN.md Sprint 5 chunks 5.1; ADR-0008 (Neon Postgres + pgvector);
--       ADR-0013; system-design.md §4, §12.5; US-006; US-030.

-- pgvector extension (already enabled on Neon; idempotent here for fresh
-- branches / local Docker where it may not be pre-loaded).
CREATE EXTENSION IF NOT EXISTS vector;

-- ── scan_runs ─────────────────────────────────────────────────────────────────
-- Lightweight envelope for a single readiness scan run. Sprint 4 chunk 4.9
-- tracks cancellation; Sprint 9 chunks 9.10-9.15 add re-run / compare / revert.

CREATE TABLE IF NOT EXISTS scan_runs (
    id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             TEXT         NOT NULL,
    connector_id        TEXT,
    repo_include_list   TEXT[]       NOT NULL DEFAULT '{}',
    status              TEXT         NOT NULL DEFAULT 'running'
        CONSTRAINT scan_runs__status_chk
            CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    cancelled           BOOLEAN      NOT NULL DEFAULT false,
    parent_scan_run_id  UUID         -- Sprint 9 re-run reference
);

-- Dashboard "My scans" list: scope by user, sort by recency.
-- user_id leads (consistent with database-reviewer C-2 rule applied in 0003).
CREATE INDEX IF NOT EXISTS ix_scan_runs__user_status_started
    ON scan_runs (user_id, status, started_at DESC);

ALTER TABLE scan_runs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'scan_runs'
          AND policyname = 'scan_runs__user_isolation'
    ) THEN
        CREATE POLICY scan_runs__user_isolation
            ON scan_runs
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END$$;

COMMENT ON TABLE scan_runs IS
    'Scan run envelope. status machine: running → completed/failed/cancelled. '
    'parent_scan_run_id is set by Sprint 9 re-run flow (US-030).';

-- ── evidence ──────────────────────────────────────────────────────────────────
-- Raw evidence rows collected by the orchestrator. Each row represents one
-- atomic evidence artifact (e.g. branch-protection config for one repo).
-- The content_hash is a SHA-256 of the *normalized* payload (timestamps and
-- ETags stripped per system-design §13.2) — identical artifacts from repeated
-- scans share the same hash so the unique index keeps the table deduplicated
-- and the control-mapping cache gets a stable key.
--
-- Columns:
--   embedding   vector(768) — Gemini text-embedding-004 of the evidence text.
--               NULL until the background embedding job fills it.
--               The HNSW index filters on IS NOT NULL so NULL rows are invisible
--               to the ANN search until they are embedded.
--   valid_until timestamptz — optional freshness window. Sprint 9 drift-watcher
--               marks evidence stale and re-collects past this date.

CREATE TABLE IF NOT EXISTS evidence (
    id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_run_id   TEXT,
    user_id       TEXT         NOT NULL,
    source_type   TEXT         NOT NULL DEFAULT 'github'
        CONSTRAINT evidence__source_type_chk
            CHECK (source_type IN ('github', 'clerk', 'manual', 'mock')),
    source_uri    TEXT,
    raw           JSONB        NOT NULL DEFAULT '{}',
    content_hash  TEXT         NOT NULL,
    embedding     vector(768),
    collected_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    valid_until   TIMESTAMPTZ
);

-- De-duplicate: one row per (user, normalized payload).
-- ON CONFLICT (user_id, content_hash) DO NOTHING in the upsert path keeps
-- re-scans cheap — no re-insert, no embedding re-generation.
CREATE UNIQUE INDEX IF NOT EXISTS ux_evidence__user_content_hash
    ON evidence (user_id, content_hash);

-- HNSW index for approximate nearest-neighbor search on the embedding column.
-- Using cosine similarity (vector_cosine_ops) which Gemini embeddings are
-- calibrated for. The WHERE clause excludes unembedded rows from the index so
-- they cannot appear in ANN results (would return wrong distances).
-- m=16, ef_construction=64 are pgvector defaults — Sprint 10 evals will tune.
CREATE INDEX IF NOT EXISTS ix_evidence__embedding_hnsw
    ON evidence
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- GIN full-text search index over the raw JSONB field so
-- evidence-store-mcp's tsvector BM25 path works without embedding.
-- 'english' configuration strips stop words and applies stemming.
CREATE INDEX IF NOT EXISTS ix_evidence__raw_fts
    ON evidence
    USING gin (to_tsvector('english', raw::text));

-- Cross-table lookup: "all evidence for this scan_run". user_id leads.
CREATE INDEX IF NOT EXISTS ix_evidence__user_scan_run
    ON evidence (user_id, scan_run_id)
    WHERE scan_run_id IS NOT NULL;

-- Source-type filter: "all GitHub evidence for this user".
CREATE INDEX IF NOT EXISTS ix_evidence__user_source_type
    ON evidence (user_id, source_type);

ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'evidence'
          AND policyname = 'evidence__user_isolation'
    ) THEN
        CREATE POLICY evidence__user_isolation
            ON evidence
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END$$;

COMMENT ON TABLE evidence IS
    'Raw evidence rows collected per scan run. content_hash is SHA-256 of the '
    'normalized (timestamp-stripped) payload — identical evidence shares one row. '
    'embedding is vector(768) from Gemini text-embedding-004; NULL until backfilled.';
