"""FastMCP server for policy-template-mcp (Sprint 6 chunk 6.3).

Exposes three tools over stdio MCP transport:
  - get_template(policy_type) -> PolicyTemplate | None
  - list_templates() -> list[PolicyTemplateSummary]
  - render_template(template_id, context) -> RenderResult

Refs: PLAN.md chunk 6.3; ADR-0005.
"""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from policy_template_mcp.schemas import (
    PolicyTemplate,
    PolicyTemplateSummary,
    PolicyType,
    RenderResult,
)
from policy_template_mcp.tools import (
    get_template as _get_template,
)
from policy_template_mcp.tools import (
    list_templates as _list_templates,
)
from policy_template_mcp.tools import (
    render_template_full as _render_template_full,
)

mcp = FastMCP(
    "policy-template-mcp",
    description="Policy template rendering server for AuditPilot. "
    "Provides IRP, Access Control, Change Management, and Vendor Management templates "
    "with Jinja2 citation slots for SOC 2 TSC grounding.",
)


@mcp.tool()
async def get_template(policy_type: PolicyType) -> PolicyTemplate | None:
    """Look up a policy template by type.

    Returns the full template including Markdown content with citation
    slots, or None if the policy type is not recognized.
    """
    return await asyncio.to_thread(_get_template, policy_type)


@mcp.tool()
async def list_templates() -> list[PolicyTemplateSummary]:
    """List all available policy templates with summaries."""
    return await asyncio.to_thread(_list_templates)


@mcp.tool()
async def render_template(template_id: str, context: dict[str, str] | None = None) -> RenderResult:
    """Render a policy template with control assessment context.

    Context keys map to Jinja2 slots. For example, passing
    ``{"CC7_1": "CC7.1 (passing) — NIST: IR-4"}`` fills the
    ``{{ controls.CC7_1 }}`` slot in the template.

    Unfilled slots keep their default placeholder text.
    """
    return await asyncio.to_thread(_render_template_full, template_id, context)


def main() -> None:
    """CLI entrypoint — run the MCP server over stdio."""
    mcp.run(transport="stdio")


__all__ = ["main", "mcp"]
