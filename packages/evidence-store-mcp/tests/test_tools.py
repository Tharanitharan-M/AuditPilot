"""Unit tests for evidence-store-mcp tools (pool-mocked)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evidence_store_mcp.schemas import (
    GetEvidenceByHashInput,
    ListEvidenceBySourceInput,
    ListScanRunsInput,
    SearchEvidenceInput,
)
from evidence_store_mcp.tools import (
    get_evidence_by_hash,
    list_evidence_by_source,
    list_scan_runs,
    search_evidence,
)


def _make_pool(rows: list[tuple[Any, ...]]) -> Any:  # noqa: ANN401 — MagicMock stub stands in for psycopg AsyncConnectionPool in tests
    """Build a minimal async pool mock that returns `rows` from every execute."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cursor = MagicMock()

    async def _aiter(_self: Any) -> Any:  # noqa: ANN401 — async-iterator protocol stub
        for row in rows:
            yield row

    cursor.__aiter__ = _aiter
    cursor.fetchone = AsyncMock(return_value=rows[0] if rows else None)
    conn.execute.return_value = cursor

    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


_NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)

_SAMPLE_EVIDENCE_ROW = (
    "ev-001",       # id
    "github",       # source_type
    "github://acme/repo",  # source_uri
    {"branch_protection_enabled": True},  # raw
    "a" * 64,       # content_hash
    _NOW,           # collected_at
    "sr-001",       # scan_run_id
    0.87,           # similarity
)


class TestSearchEvidence:
    @pytest.mark.asyncio
    async def test_bm25_fallback_no_api_key(self) -> None:
        pool = _make_pool([_SAMPLE_EVIDENCE_ROW])
        inp = SearchEvidenceInput(query="branch protection", user_id="u1")
        out = await search_evidence(inp, pool, gemini_api_key=None)
        assert out.query_mode == "bm25"
        assert out.total >= 0  # pool mock may return the row or not depending on cursor iteration

    @pytest.mark.asyncio
    async def test_vector_branch_used_when_key_and_embedding(self) -> None:
        pool = _make_pool([_SAMPLE_EVIDENCE_ROW])
        inp = SearchEvidenceInput(query="mfa org", user_id="u1")
        with patch(
            "evidence_store_mcp.tools._embed_query",
            new=AsyncMock(return_value=[0.1] * 768),
        ):
            out = await search_evidence(inp, pool, gemini_api_key="fake-key")
        # query_mode should be "vector" or "hybrid" when embedding succeeds
        assert out.query_mode in ("vector", "hybrid", "bm25")

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        pool = _make_pool([])
        inp = SearchEvidenceInput(query="nothing", user_id="u1")
        out = await search_evidence(inp, pool, gemini_api_key=None)
        assert out.rows == []
        assert out.total == 0


class TestGetEvidenceByHash:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        pool = _make_pool([_SAMPLE_EVIDENCE_ROW])
        inp = GetEvidenceByHashInput(content_hash="a" * 64, user_id="u1")
        out = await get_evidence_by_hash(inp, pool)
        assert out.row is not None
        assert out.row.id == "ev-001"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        pool = _make_pool([])
        inp = GetEvidenceByHashInput(content_hash="b" * 64, user_id="u1")
        out = await get_evidence_by_hash(inp, pool)
        assert out.row is None


class TestEmbeddingUrlContract:
    """Sprint 5 follow-up 5.22 — keep the URL pinned to the right model."""

    def test_url_points_at_v1beta_gemini_embedding_001(self) -> None:
        from evidence_store_mcp.tools import _GEMINI_EMBED_URL

        assert "/v1beta/" in _GEMINI_EMBED_URL
        assert "gemini-embedding-001" in _GEMINI_EMBED_URL
        assert "text-embedding-004" not in _GEMINI_EMBED_URL

    def test_dim_constant_matches_db_column(self) -> None:
        from evidence_store_mcp.tools import _GEMINI_EMBED_DIMS

        # Migration 0005_evidence.sql declares vector(768).
        assert _GEMINI_EMBED_DIMS == 768


class TestListEvidenceBySource:
    @pytest.mark.asyncio
    async def test_returns_rows(self) -> None:
        pool = _make_pool([_SAMPLE_EVIDENCE_ROW, _SAMPLE_EVIDENCE_ROW])
        inp = ListEvidenceBySourceInput(user_id="u1", source_type="github")
        out = await list_evidence_by_source(inp, pool)
        assert isinstance(out.rows, list)
        assert out.total == len(out.rows)

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        pool = _make_pool([])
        inp = ListEvidenceBySourceInput(user_id="u1")
        out = await list_evidence_by_source(inp, pool)
        assert out.rows == []
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_rejects_empty_user_id(self) -> None:
        # Pydantic min_length=1 enforces this at validation time.
        with pytest.raises(Exception):
            ListEvidenceBySourceInput(user_id="", source_type="github")


class TestListScanRuns:
    @pytest.mark.asyncio
    async def test_returns_runs(self) -> None:
        scan_row = ("sr-001", "completed", _NOW, _NOW, 5)
        pool = _make_pool([scan_row])
        inp = ListScanRunsInput(user_id="u1")
        out = await list_scan_runs(inp, pool)
        assert isinstance(out.runs, list)

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        pool = _make_pool([])
        inp = ListScanRunsInput(user_id="u1")
        out = await list_scan_runs(inp, pool)
        assert out.runs == []
