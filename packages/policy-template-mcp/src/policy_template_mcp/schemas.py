"""Pydantic v2 schemas for policy templates (Sprint 6 chunk 6.4).

Every schema uses ``extra="forbid"`` so ``model_json_schema()`` produces
``additionalProperties: false`` — required by the mcp-server-validator.

Refs: PLAN.md chunk 6.4; ADR-0005; system-design 3.3.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PolicyType = Literal[
    "irp",
    "access_control",
    "change_management",
    "vendor_management",
]

POLICY_TYPE_TITLES: dict[str, str] = {
    "irp": "Incident Response Plan",
    "access_control": "Access Control Policy",
    "change_management": "Change Management Policy",
    "vendor_management": "Vendor Management Policy",
}


class PolicyTemplate(BaseModel):
    """A policy template with Jinja2 citation slots."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique template identifier, e.g. 'irp'.")
    policy_type: PolicyType = Field(description="Policy type key.")
    title: str = Field(description="Human-readable title.")
    description: str = Field(default="", description="One-line summary.")
    content: str = Field(description="Markdown body with {{ controls.CC7_1 }} citation slots.")
    version: str = Field(default="1.0", description="Template version string.")
    soc2_tsc_refs: list[str] = Field(
        default_factory=list,
        description="SOC 2 TSC clause IDs this policy addresses.",
    )


class PolicyTemplateSummary(BaseModel):
    """Lightweight summary for list_templates()."""

    model_config = ConfigDict(extra="forbid")

    id: str
    policy_type: PolicyType
    title: str
    description: str = ""
    version: str = "1.0"
    soc2_tsc_refs: list[str] = Field(default_factory=list)


class RenderResult(BaseModel):
    """Result of render_template()."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    rendered_content: str = Field(description="Markdown with citation slots filled.")
    unfilled_slots: list[str] = Field(
        default_factory=list,
        description="Slot names that had no matching context value.",
    )


__all__ = [
    "POLICY_TYPE_TITLES",
    "PolicyTemplate",
    "PolicyTemplateSummary",
    "PolicyType",
    "RenderResult",
]
