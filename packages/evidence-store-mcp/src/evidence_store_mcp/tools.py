"""MCP tool implementations for the evidence-store-mcp server.

Three tools:
  search_evidence      — hybrid vector + BM25 retrieval
  get_evidence_by_hash — exact lookup by content hash (cache key)
  list_scan_runs       — most-recent scan runs for a user

All tools are pure async functions that accept a psycopg AsyncConnectionPool
injected at server startup. They never perform write operations (ADR-0001
read-only-by-design invariant).

Refs: PLAN.md Sprint 5 chunks 5.10–5.11; ADR-0008 (Neon Postgres + pgvector).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from opentelemetry import trace

from evidence_store_mcp.schemas import (
    EvidenceRow,
    GetEvidenceByHashInput,
    GetEvidenceByHashOutput,
    ListEvidenceBySourceInput,
    ListEvidenceBySourceOutput,
    ListScanRunsInput,
    ListScanRunsOutput,
    ScanRunSummary,
    SearchEvidenceInput,
    SearchEvidenceOutput,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# gemini-embedding-001 is the current stable Gemini embedding model
# (text-embedding-004 was retired). Default output is 3072 dim; we request
# 768 dim explicitly via outputDimensionality so query vectors are comparable
# to the rows persisted by apps.api.services.evidence_persistence.
_GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)
_GEMINI_EMBED_DIMS = 768


# ── Embedding helper ──────────────────────────────────────────────────────────


async def _embed_query(text: str, gemini_api_key: str) -> list[float] | None:
    """Generate a query embedding via Gemini text-embedding-004. Returns None on error."""
    try:
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": _GEMINI_EMBED_DIMS,
        }
        # Use x-goog-api-key header — keeps the key out of URLs, logs, and proxy access logs.
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": gemini_api_key,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(_GEMINI_EMBED_URL, json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning("embed_query.failed status=%d", r.status_code)
            return None
        return [float(v) for v in r.json()["embedding"]["values"]]
    except Exception as exc:  # noqa: BLE001
        # Log only the type — never the URL or headers (key leak risk).
        logger.warning("embed_query.exception type=%s", type(exc).__name__)
        return None


# ── RLS helper ────────────────────────────────────────────────────────────────


def _require_user_id(user_id: str | None) -> str:
    """Raise ValueError if user_id is falsy — prevents silent RLS bypass."""
    if not user_id:
        raise ValueError("user_id is required for RLS context")
    return user_id


async def _set_rls(conn: Any, user_id: str) -> None:
    await conn.execute(
        "SELECT set_config('app.current_user_id', %s, true)",
        (user_id,),
    )


# ── search_evidence ───────────────────────────────────────────────────────────


async def search_evidence(
    inp: SearchEvidenceInput,
    pool: Any,
    *,
    gemini_api_key: str | None = None,
) -> SearchEvidenceOutput:
    """Hybrid search: vector cosine similarity + websearch_to_tsquery full-text fallback.

    Strategy:
    1. If gemini_api_key is available, embed the query and run a vector search
       filtered by ``similarity_threshold``.
    2. If the vector search returns fewer than ``limit`` rows, supplement with a
       full-text search using ``websearch_to_tsquery`` (safe for user-supplied input).
    3. Deduplicate by id, label ``query_mode``.
    """
    uid = _require_user_id(inp.user_id)

    with tracer.start_as_current_span("evidence_store_mcp.search_evidence") as span:
        span.set_attribute("user_id", uid)
        span.set_attribute("limit", inp.limit)

        rows: list[EvidenceRow] = []
        query_mode = "bm25"

        async with pool.connection() as conn:
            await _set_rls(conn, uid)

            # ── Vector branch ──────────────────────────────────────────────
            if gemini_api_key:
                embedding = await _embed_query(inp.query, gemini_api_key)
                if embedding:
                    # Explicit float() cast guards against malformed Gemini responses.
                    vec_literal = f"[{','.join(str(float(v)) for v in embedding)}]"
                    result = await conn.execute(
                        """
                        SELECT id, source_type, source_uri, raw, content_hash,
                               collected_at, scan_run_id,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM   evidence
                        WHERE  user_id = %s
                          AND  embedding IS NOT NULL
                          AND  1 - (embedding <=> %s::vector) >= %s
                          AND  (%s::text IS NULL OR source_type = %s)
                        ORDER  BY embedding <=> %s::vector
                        LIMIT  %s
                        """,
                        [
                            vec_literal, uid, vec_literal, inp.similarity_threshold,
                            inp.source_type, inp.source_type,
                            vec_literal, inp.limit,
                        ],
                    )
                    async for row in result:
                        rows.append(_row_to_model(row, has_similarity=True))
                    if rows:
                        query_mode = "vector"

            # ── BM25 branch (supplement or fallback) ──────────────────────
            if len(rows) < inp.limit:
                remaining = inp.limit - len(rows)
                seen_ids = {r.id for r in rows}

                # websearch_to_tsquery handles arbitrary user input safely
                # (never raises, treats operators as plain text).
                bm25_result = await conn.execute(
                    """
                    SELECT id, source_type, source_uri, raw, content_hash,
                           collected_at, scan_run_id,
                           NULL::double precision AS similarity
                    FROM   evidence
                    WHERE  user_id = %s
                      AND  (%s::text IS NULL OR source_type = %s)
                      AND  to_tsvector('english', raw::text)
                           @@ websearch_to_tsquery('english', %s)
                    LIMIT  %s
                    """,
                    [uid, inp.source_type, inp.source_type, inp.query, remaining],
                )
                async for row in bm25_result:
                    if row[0] not in seen_ids:
                        rows.append(_row_to_model(row, has_similarity=False))
                if query_mode == "vector" and len(rows) > len(seen_ids):
                    query_mode = "hybrid"

        span.set_attribute("result_count", len(rows))
        span.set_attribute("query_mode", query_mode)
        return SearchEvidenceOutput(rows=rows, total=len(rows), query_mode=query_mode)


# ── get_evidence_by_hash ──────────────────────────────────────────────────────


async def get_evidence_by_hash(
    inp: GetEvidenceByHashInput,
    pool: Any,
) -> GetEvidenceByHashOutput:
    """Exact lookup by SHA-256 content_hash. Used as cache key by map_controls."""
    uid = _require_user_id(inp.user_id)

    with tracer.start_as_current_span("evidence_store_mcp.get_by_hash") as span:
        span.set_attribute("user_id", uid)
        span.set_attribute("content_hash", inp.content_hash)

        async with pool.connection() as conn:
            await _set_rls(conn, uid)
            result = await conn.execute(
                """
                SELECT id, source_type, source_uri, raw, content_hash,
                       collected_at, scan_run_id,
                       NULL::double precision AS similarity
                FROM   evidence
                WHERE  user_id = %s AND content_hash = %s
                LIMIT  1
                """,
                (uid, inp.content_hash),
            )
            row = await result.fetchone()
            span.set_attribute("found", row is not None)
            if row is None:
                return GetEvidenceByHashOutput(row=None)
            return GetEvidenceByHashOutput(row=_row_to_model(row, has_similarity=False))


# ── list_evidence_by_source ──────────────────────────────────────────────────


async def list_evidence_by_source(
    inp: ListEvidenceBySourceInput,
    pool: Any,
) -> ListEvidenceBySourceOutput:
    """Return the most-recent evidence rows, optionally filtered by source.

    PLAN.md Sprint 5 chunk 5.11. Pure listing — no semantic ranking, no
    embeddings, no full-text — RLS scopes the rows to the caller's user_id.
    """

    uid = _require_user_id(inp.user_id)

    with tracer.start_as_current_span("evidence_store_mcp.list_by_source") as span:
        span.set_attribute("user_id", uid)
        span.set_attribute("limit", inp.limit)
        if inp.source_type:
            span.set_attribute("source_type", inp.source_type)

        async with pool.connection() as conn:
            await _set_rls(conn, uid)
            result = await conn.execute(
                """
                SELECT id, source_type, source_uri, raw, content_hash,
                       collected_at, scan_run_id,
                       NULL::double precision AS similarity
                FROM   evidence
                WHERE  user_id = %s
                  AND  (%s::text IS NULL OR source_type = %s)
                ORDER  BY collected_at DESC
                LIMIT  %s
                """,
                (uid, inp.source_type, inp.source_type, inp.limit),
            )
            rows: list[EvidenceRow] = []
            async for row in result:
                rows.append(_row_to_model(row, has_similarity=False))
            span.set_attribute("result_count", len(rows))
            return ListEvidenceBySourceOutput(rows=rows, total=len(rows))


# ── list_scan_runs ────────────────────────────────────────────────────────────


async def list_scan_runs(
    inp: ListScanRunsInput,
    pool: Any,
) -> ListScanRunsOutput:
    """Return the most-recent scan runs for a user with evidence counts."""
    uid = _require_user_id(inp.user_id)

    with tracer.start_as_current_span("evidence_store_mcp.list_scan_runs") as span:
        span.set_attribute("user_id", uid)
        span.set_attribute("limit", inp.limit)

        async with pool.connection() as conn:
            await _set_rls(conn, uid)
            # Column name aligns with migration 0005_evidence.sql
            # (completed_at, not finished_at). The JOIN casts sr.id (UUID) to
            # text so it matches evidence.scan_run_id (TEXT) — implicit casts
            # between UUID and TEXT are not allowed.
            result = await conn.execute(
                """
                SELECT sr.id, sr.status, sr.started_at, sr.completed_at,
                       COUNT(e.id)::int AS evidence_count
                FROM   scan_runs sr
                LEFT   JOIN evidence e ON e.scan_run_id = sr.id::text
                WHERE  sr.user_id = %s
                GROUP  BY sr.id, sr.status, sr.started_at, sr.completed_at
                ORDER  BY sr.started_at DESC
                LIMIT  %s
                """,
                (uid, inp.limit),
            )
            runs: list[ScanRunSummary] = []
            async for row in result:
                runs.append(
                    ScanRunSummary(
                        id=str(row[0]),
                        status=row[1],
                        started_at=row[2],
                        completed_at=row[3],
                        evidence_count=row[4],
                    )
                )
            span.set_attribute("run_count", len(runs))
            return ListScanRunsOutput(runs=runs)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_model(row: Any, *, has_similarity: bool) -> EvidenceRow:
    return EvidenceRow(
        id=str(row[0]),
        source_type=row[1],
        source_uri=row[2],
        raw=row[3] if isinstance(row[3], dict) else {},
        content_hash=row[4],
        collected_at=row[5],
        scan_run_id=row[6],
        similarity=float(row[7]) if has_similarity and row[7] is not None else None,
    )


__all__ = [
    "get_evidence_by_hash",
    "list_evidence_by_source",
    "list_scan_runs",
    "search_evidence",
]
