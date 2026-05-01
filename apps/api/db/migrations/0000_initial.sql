-- Migration: 0000_initial
-- Purpose:   Baseline migration — enables pgvector and establishes the
--            migration runner pattern. Application tables ship in Sprint 2+.
-- Idempotent: yes (all statements use IF NOT EXISTS).
-- Refs:      PLAN.md chunk 0F.5, ADR-0008 (Neon Postgres), system-design §4

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;         -- pgvector: embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- trigram similarity for BM25 hybrid search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";    -- uuid_generate_v4() helper

-- ── Schema ownership note ──────────────────────────────────────────────────────
-- Row Level Security (RLS) policies on all multi-tenant tables will reference
-- auth.uid() from Supabase Auth. The Supabase Auth schema ships with the
-- Supabase project and does not need to be created here.
--
-- Pattern used throughout:
--   CREATE POLICY <name> ON <table>
--     USING ((SELECT auth.uid()) = user_id);
-- Wrapping auth.uid() in SELECT enables query-plan caching (postgres-patterns skill).

-- ── Placeholder: tables added in Sprint 2+ ────────────────────────────────────
-- Sprint 2: users, scan_runs, actions, checkpoints (LangGraph PostgresSaver)
-- Sprint 5: evidence, control_map
-- Sprint 6: policy_revisions
-- Sprint 7: questionnaire_runs
-- Sprint 9: drift_events, monitored_controls
-- Sprint 11: demo_resets
