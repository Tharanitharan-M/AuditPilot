-- Migration: 0001_langgraph_checkpoints
-- Purpose:   Create the four tables + three indexes that LangGraph's
--            `AsyncPostgresSaver` uses to persist graph state across
--            container restarts (HITL resume, scan re-run, adversarial
--            challenge cold-start tolerance).
-- Idempotent: yes — every statement uses IF NOT EXISTS / IF NOT EXISTS on
--            indexes, matching the DDL LangGraph 1.1.x emits at runtime.
-- Refs:      PLAN.md chunk 2.6, ADR-0001 (LangGraph runtime), ADR-0007 (HITL
--            via LangGraph interrupt), system-design 4.

-- ── Schema-version ledger LangGraph writes into ────────────────────────────────
CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

-- ── Full checkpoint rows (one per graph step per thread_id) ────────────────────
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- ── Per-channel payload blobs (one row per messages append, etc.) ──────────────
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

-- ── In-flight writes (pending edits to the current checkpoint step) ────────────
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- ── Thread-id indexes (RLS column pattern, per sql-drizzle rule) ───────────────
-- NOTE: LangGraph creates these with CREATE INDEX CONCURRENTLY, which cannot
-- run inside a transaction. Drizzle's migration runner wraps each file in a
-- transaction by default; we omit CONCURRENTLY here since the tables are
-- fresh (no concurrent writes to conflict with) and runtime AsyncPostgresSaver
-- .setup() will skip these via IF NOT EXISTS.
CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx
    ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx
    ON checkpoint_blobs(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx
    ON checkpoint_writes(thread_id);
