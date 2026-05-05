-- Migration: 0002_checkpoints_indexes
-- Purpose:   Add the composite indexes LangGraph 1.x ``AsyncPostgresSaver``
--            actually queries against. The 0001 migration only created
--            single-column ``thread_id`` indexes, which forces a partition
--            scan on any multi-namespace thread (resume, HITL gate, scan
--            re-run). Filed as Sprint 3 day-0 chunk 3.0e after the
--            database-reviewer flagged it during the Sprint 2 critical pass.
-- Idempotent: yes — every statement uses CREATE INDEX IF NOT EXISTS.
-- Refs:      PLAN.md chunk 3.0e (Sprint 3 day-0 follow-ups), ADR-0001
--            (LangGraph runtime), system-design 4.

-- ── Why a composite index ──────────────────────────────────────────────────────
-- LangGraph's ``aget_tuple`` and ``aput`` paths filter on
--   (thread_id, checkpoint_ns)
-- and order by
--   checkpoint_id DESC
-- to return the most-recent checkpoint per namespace. With only a single-column
-- ``thread_id`` index, Postgres has to fetch every row for the thread (across
-- every namespace) and sort in memory — expensive once a single user
-- accumulates HITL+drift+scan-rerun namespaces. The composite index turns the
-- access pattern into an index-only scan over the leading prefix.

-- ── Note on CONCURRENTLY ──────────────────────────────────────────────────────
-- We omit CONCURRENTLY because Drizzle's migration runner wraps each file in a
-- transaction and CREATE INDEX CONCURRENTLY cannot run inside one. The 0001
-- migration creates these tables fresh, so 0002 only conflicts with concurrent
-- writes if 0002 is applied against an already-populated database (e.g.,
-- after rolling back 0001). That window is narrow; if it ever needs to be
-- closed, split the CREATE INDEX statements out of the Drizzle bundle and run
-- them via psql with CONCURRENTLY.

-- ── checkpoints: latest checkpoint per (thread, namespace) ─────────────────────
CREATE INDEX IF NOT EXISTS checkpoints_thread_ns_id_idx
    ON checkpoints (thread_id, checkpoint_ns, checkpoint_id DESC);

-- ── checkpoint_writes: in-flight writes per (thread, namespace, checkpoint) ────
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_ns_id_idx
    ON checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id);

-- ── checkpoint_blobs: per-channel blob lookup per (thread, namespace) ──────────
-- channel + version are part of the PK, so a (thread_id, checkpoint_ns) prefix
-- is enough to short-circuit the partition before the PK lookup completes.
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_ns_idx
    ON checkpoint_blobs (thread_id, checkpoint_ns);
