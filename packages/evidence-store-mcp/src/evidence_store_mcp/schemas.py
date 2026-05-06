"""Pydantic v2 input/output schemas for every MCP tool.

All schemas use `extra="forbid"` so callers cannot inject unexpected fields.
Tool descriptions appear in the JSON Schema emitted by the MCP server and are
therefore part of the public interface — keep them stable across minor versions.

Refs: PLAN.md Sprint 5 chunk 5.10; ADR-0008 (Neon Postgres + pgvector).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["github", "clerk", "manual", "mock"]


# ── search_evidence ───────────────────────────────────────────────────────────


class SearchEvidenceInput(BaseModel):
    """Input for the `search_evidence` tool."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language or keyword query to search collected evidence.",
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="Clerk user_id. Only evidence owned by this user is searched.",
    )
    source_type: SourceType | None = Field(
        default=None,
        description="Optional filter: 'github', 'clerk', 'manual', or 'mock'.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of evidence rows to return.",
    )
    similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum cosine similarity (0–1) for vector matches. "
            "Ignored when the row has no embedding."
        ),
    )


class EvidenceRow(BaseModel):
    """A single evidence row returned by search_evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: str
    source_uri: str | None
    raw: dict[str, Any]
    content_hash: str | None
    collected_at: datetime
    scan_run_id: str | None
    similarity: float | None = Field(
        default=None,
        description="Cosine similarity score (null when the row matched via BM25 only).",
    )


class SearchEvidenceOutput(BaseModel):
    """Output for the `search_evidence` tool."""

    model_config = ConfigDict(extra="forbid")

    rows: list[EvidenceRow]
    total: int = Field(description="Number of rows returned (== len(rows)).")
    query_mode: str = Field(
        description="'vector', 'bm25', or 'hybrid' depending on which indexes were used."
    )


# ── get_evidence_by_hash ──────────────────────────────────────────────────────


class GetEvidenceByHashInput(BaseModel):
    """Input for the `get_evidence_by_hash` tool."""

    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hex digest of the normalized evidence payload.",
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="Clerk user_id. RLS will reject rows owned by other users.",
    )


class GetEvidenceByHashOutput(BaseModel):
    """Output for `get_evidence_by_hash`."""

    model_config = ConfigDict(extra="forbid")

    row: EvidenceRow | None = Field(
        default=None,
        description="The matching row, or null if not found.",
    )


# ── list_evidence_by_source ───────────────────────────────────────────────────


class ListEvidenceBySourceInput(BaseModel):
    """Input for the ``list_evidence_by_source`` tool (PLAN.md chunk 5.11).

    Returns the most recent ``Evidence`` rows for the caller, optionally
    filtered to a single ``source_type``. Pure read-only listing — no
    semantic ranking. Used by the dashboard's evidence drawer and by
    AdversarialAuditor when it wants every row of one source kind.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(
        ...,
        min_length=1,
        description="Clerk user_id. RLS scopes the listing to this user.",
    )
    source_type: SourceType | None = Field(
        default=None,
        description=(
            "Optional source filter: 'github', 'clerk', 'manual', or 'mock'. "
            "When omitted, returns rows across every source the user owns."
        ),
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum number of rows to return, ordered by collected_at DESC.",
    )


class ListEvidenceBySourceOutput(BaseModel):
    """Output for ``list_evidence_by_source``."""

    model_config = ConfigDict(extra="forbid")

    rows: list[EvidenceRow]
    total: int = Field(description="Number of rows returned (== len(rows)).")


# ── list_scan_runs ────────────────────────────────────────────────────────────


class ListScanRunsInput(BaseModel):
    """Input for the `list_scan_runs` tool."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class ScanRunSummary(BaseModel):
    """Lightweight summary of one scan run."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = Field(
        default=None,
        description="When the scan run finished (null while running).",
    )
    evidence_count: int


class ListScanRunsOutput(BaseModel):
    """Output for `list_scan_runs`."""

    model_config = ConfigDict(extra="forbid")

    runs: list[ScanRunSummary]


__all__ = [
    "EvidenceRow",
    "GetEvidenceByHashInput",
    "GetEvidenceByHashOutput",
    "ListEvidenceBySourceInput",
    "ListEvidenceBySourceOutput",
    "ListScanRunsInput",
    "ListScanRunsOutput",
    "ScanRunSummary",
    "SearchEvidenceInput",
    "SearchEvidenceOutput",
]
