"""
MCP client wiring for the AuditOrchestrator
============================================
Sprint 4 chunk 4.3: replace the direct Python import of
``compliance_kb_mcp.tools`` (Sprint 2 stub) with a real MCP transport,
so the orchestrator agent talks to the published MCP server the same
way third-party consumers will.

Why ``MCPServerStdio`` and not ``MultiServerMCPClient``?
-------------------------------------------------------
The Sprint-1 PLAN entry references ``MultiServerMCPClient`` from
``langchain-mcp-adapters``. That predates Pydantic AI 1.x's native
MCP support. ``langchain-mcp-adapters`` returns LangChain ``BaseTool``
objects, which would force us to write a LangChain↔Pydantic-AI tool
adapter inside the orchestrator. ``pydantic_ai.mcp.MCPServerStdio``
attaches directly as a Pydantic AI ``toolset`` — the agent dispatches
calls over the stdio transport with no glue code. Same wire format
(MCP 2025-11-25), one fewer abstraction layer.

The orchestrator graph in ``apps.api.graph`` is unchanged: it still
returns ``AIMessage(tool_calls=...)`` and ``ToolMessage`` so the SSE
bridge can render Tool cards on the frontend (chunk 4.2). The only
thing that moves is *where* the tool implementation runs — out of the
FastAPI process, into a stdio subprocess.

Tests
-----
``apps/api/tests/test_orchestrator_mcp.py`` spawns ``compliance-kb-mcp``
over real stdio and asserts the orchestrator's ``lookup_control`` call
round-trips through the MCP server. The Sprint-2 ``FunctionModel``
tests still pass because they bypass the toolset and emit
``ToolCallPart`` directly.

Refs
----
- PLAN.md Sprint 4 chunk 4.3
- ADR-0005 (five MCP servers)
- ADR-0001 (LangGraph 1.x runtime + Pydantic AI agents)
- system-design.md §6.4
- MCP spec 2025-11-25 (stdio transport)
"""

from __future__ import annotations

import logging
import shutil
import sys
from typing import Any

from pydantic_ai.mcp import MCPServerStdio

logger = logging.getLogger(__name__)


# Module-level singletons. Tests may monkeypatch these to redirect at a
# stub server. Production code calls ``compliance_kb_mcp_server()`` to
# build the connection on demand and lets Pydantic AI manage the
# subprocess lifecycle through its async context manager.
_compliance_kb_mcp_factory: type[MCPServerStdio] = MCPServerStdio


def _resolve_python_executable() -> str:
    """Return the Python interpreter that should run the MCP server.

    We prefer ``sys.executable`` so the MCP subprocess shares the
    parent's virtualenv and dependency resolution. ``shutil.which``
    fallback is for the unlikely case ``sys.executable`` is empty
    (e.g. embedded interpreters).
    """

    if sys.executable:
        return sys.executable
    resolved = shutil.which("python3") or shutil.which("python")
    if resolved is None:
        raise RuntimeError(
            "Could not resolve a Python interpreter to spawn the MCP server"
        )
    return resolved


def compliance_kb_mcp_server(
    *,
    timeout: float = 10.0,
    read_timeout: float = 30.0,
    process_tool_call=None,
) -> MCPServerStdio:
    """Build the ``compliance-kb-mcp`` stdio connection.

    Returns a Pydantic AI :class:`MCPServerStdio` configured to spawn
    ``python -m compliance_kb_mcp`` (the ``__main__`` entry on the
    published package). The agent attaches this as a toolset; Pydantic
    AI handles the subprocess lifecycle when used as an
    ``async with`` context manager.

    Parameters
    ----------
    timeout : float
        Maximum seconds to wait for the MCP server to respond to
        ``initialize``. 10 s is generous for stdio + Python import
        time on a cold cache.
    read_timeout : float
        Per-tool-call response timeout. 30 s is well above the
        in-memory ``compliance-kb-mcp`` lookups (sub-millisecond) but
        leaves headroom for future tools that might do real work.

    Notes
    -----
    The compliance-kb-mcp server is in-process Python with a
    pre-loaded NIST 800-53 dataset (1.17 MB embedded in the wheel,
    `__main__.py` opens stdio inline). No network, no DB, no auth —
    safe to spawn on every chat handler invocation.
    """

    # ``dict[str, Any]`` because ``MCPServerStdio.__init__`` accepts a
    # heterogeneous keyword surface (str command, list args, float
    # timeouts, optional callable). Listed explicitly here per
    # python-reviewer F5 / architecture-reviewer F1.
    kwargs: dict[str, Any] = {
        "command": _resolve_python_executable(),
        "args": ["-m", "compliance_kb_mcp"],
        "timeout": timeout,
        "read_timeout": read_timeout,
        # ``id`` makes the toolset addressable by name in Langfuse traces
        # and in Pydantic AI's ``toolsets`` introspection.
        "id": "compliance_kb_mcp",
    }
    if process_tool_call is not None:
        kwargs["process_tool_call"] = process_tool_call
    return _compliance_kb_mcp_factory(**kwargs)


def evidence_store_mcp_server(
    *,
    db_url: str,
    gemini_api_key: str | None = None,
    timeout: float = 15.0,
    read_timeout: float = 30.0,
) -> MCPServerStdio:
    """Build the ``evidence-store-mcp`` stdio connection.

    Spawns ``python -m evidence_store_mcp`` (the package entry point in
    ``packages/evidence-store-mcp``). Environment variables ``DATABASE_URL``
    and optionally ``GEMINI_API_KEY`` are injected into the subprocess
    environment; they never appear in LangGraph state.

    The token is passed via the subprocess env rather than as a tool argument
    so that it does not appear in Langfuse traces or LangGraph checkpoints.
    """
    import os

    env: dict[str, str] = {**os.environ, "DATABASE_URL": db_url}
    if gemini_api_key:
        env["GEMINI_API_KEY"] = gemini_api_key

    kwargs: dict[str, Any] = {
        "command": _resolve_python_executable(),
        "args": ["-m", "evidence_store_mcp"],
        "timeout": timeout,
        "read_timeout": read_timeout,
        "id": "evidence_store_mcp",
        "env": env,
    }
    return MCPServerStdio(**kwargs)


__all__ = [
    "compliance_kb_mcp_server",
    "evidence_store_mcp_server",
]
