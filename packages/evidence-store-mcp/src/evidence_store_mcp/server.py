"""MCP server factory for evidence-store-mcp.

Creates a `mcp.Server` instance wired to the three evidence store tools.
The Postgres connection pool is created at startup and injected into each
tool call via a closure — the pool reference never leaks into MCP messages.

Transport: stdio (default for subprocess-launched MCP servers).

Refs: PLAN.md Sprint 5 chunk 5.9; MCP spec 2025-11-25.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS, METHOD_NOT_FOUND, TextContent, Tool
from psycopg_pool import AsyncConnectionPool

from evidence_store_mcp import __version__
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

logger = logging.getLogger(__name__)

# Tool descriptors (JSON Schema bodies generated from Pydantic models)
_TOOLS: list[Tool] = [
    Tool(
        name="search_evidence",
        description=(
            "Hybrid semantic + keyword search over collected evidence rows. "
            "Uses Gemini vector embeddings when available, falls back to BM25."
        ),
        inputSchema=SearchEvidenceInput.model_json_schema(),
    ),
    Tool(
        name="get_evidence_by_hash",
        description=(
            "Exact lookup of one evidence row by its SHA-256 content_hash. "
            "Used as a cache key by the control-mapping agent."
        ),
        inputSchema=GetEvidenceByHashInput.model_json_schema(),
    ),
    Tool(
        name="list_evidence_by_source",
        description=(
            "List the most-recent evidence rows for a user, optionally "
            "filtered by source_type. Pure listing — no semantic ranking."
        ),
        inputSchema=ListEvidenceBySourceInput.model_json_schema(),
    ),
    Tool(
        name="list_scan_runs",
        description="Return the most-recent scan runs for a user with evidence counts.",
        inputSchema=ListScanRunsInput.model_json_schema(),
    ),
]


def create_server(
    db_url: str,
    gemini_api_key: str | None = None,
) -> Server:
    """Build and return the MCP Server. Call ``server.run_stdio_async()`` to start."""

    pool: AsyncConnectionPool | None = None
    # MCP 2025-11-25 handshake: version + instructions surface in the
    # initialize response so callers see the implementation identity and a
    # human/model-readable description (mcp-server-validator F1, F2).
    server: Server = Server(
        "evidence-store-mcp",
        version=__version__,
        instructions=(
            "Read-only MCP server exposing AuditPilot evidence rows via "
            "semantic and keyword search. Use search_evidence for hybrid "
            "pgvector + BM25 retrieval, get_evidence_by_hash for cache-key "
            "lookups, and list_scan_runs for run summaries."
        ),
    )

    @server.list_tools()  # type: ignore[misc]
    async def handle_list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()  # type: ignore[misc]
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        nonlocal pool
        if pool is None:
            pool = AsyncConnectionPool(db_url, min_size=1, max_size=5, open=False)
            await pool.open()

        if name == "search_evidence":
            inp = SearchEvidenceInput.model_validate(arguments)
            out = await search_evidence(inp, pool, gemini_api_key=gemini_api_key)
            return [TextContent(type="text", text=out.model_dump_json())]

        if name == "get_evidence_by_hash":
            inp_hash = GetEvidenceByHashInput.model_validate(arguments)
            out_hash = await get_evidence_by_hash(inp_hash, pool)
            return [TextContent(type="text", text=out_hash.model_dump_json())]

        if name == "list_evidence_by_source":
            inp_list = ListEvidenceBySourceInput.model_validate(arguments)
            out_list = await list_evidence_by_source(inp_list, pool)
            return [TextContent(type="text", text=out_list.model_dump_json())]

        if name == "list_scan_runs":
            inp_runs = ListScanRunsInput.model_validate(arguments)
            out_runs = await list_scan_runs(inp_runs, pool)
            return [TextContent(type="text", text=out_runs.model_dump_json())]

        raise McpError(METHOD_NOT_FOUND, f"Unknown tool: {name}")

    return server


__all__ = ["create_server"]
