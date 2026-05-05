"""
AuditOrchestrator — Sprint 2 stub
==================================
Single-writer Pydantic AI agent that will, over the course of the build,
coordinate evidence collection, control mapping, policy drafting, and
adversarial challenges. The Sprint 2 stub is intentionally minimal: it
calls one MCP-exposed tool (`compliance-kb-mcp.lookup_control`) and
records the result in `AuditPilotState.control_map`.

Key Sprint 2 properties:
- Model is injectable so tests can supply `TestModel` / `FunctionModel`
  without hitting a live LLM or the network (PLAN 2.5 acceptance).
- Tool is registered via Pydantic AI's native `@agent.tool` decorator.
- Full MCP-over-stdio transport arrives in Sprint 4 chunk 4.3 via
  `MultiServerMCPClient` from `langchain-mcp-adapters`; this stub calls
  the tool function directly so Sprint 2 verification does not require
  running the FastMCP server in a subprocess.

Refs: PLAN.md chunk 2.5; ADR-0001 (LangGraph 1.x runtime);
ADR-0002 (three-agent architecture); ADR-0005 (five MCP servers);
system-design.md 3.2, 6.4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from compliance_kb_mcp.schemas import Control
from compliance_kb_mcp.tools import lookup_control as _kb_lookup_control
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

# Sprint 3 day-0 chunk 3.0b — OWASP LLM06 (Excessive Agency) defence-in-depth.
# Validate ``control_id`` BEFORE handing it to the downstream MCP tool. NIST
# 800-53 Rev 5 control identifiers are {family}-{number} with an optional
# {enhancement} in parentheses, e.g. ``AC-1``, ``AC-2(1)``, ``SC-7(3)``. The
# regex rejects path-traversal (``../../etc/passwd``), SQL injection
# (``'; DROP TABLE…``), prompt-injected free text, and any other shape the
# LLM might be tricked into producing. Reject early and return a typed miss
# without burning a downstream call.
_CONTROL_ID_PATTERN = re.compile(r"^[A-Z]{1,3}-[0-9]{1,3}(?:\([0-9]{1,2}\))?$")


class LookupControlResult(BaseModel):
    """Typed return shape for the orchestrator's ``lookup_control`` tool.

    Pydantic AI generates the JSON Schema the LLM sees from this model's
    annotations. A bare ``dict`` return produces an empty schema with no
    field hints, so the model has to guess. Encoding the contract here
    keeps the prompt-side schema stable as Sprint 4+ extends the field set.
    """

    model_config = ConfigDict(extra="forbid")

    found: bool
    control_id: str = Field(
        description="The control identifier the user asked about (echoed back even on a miss).",
    )
    id: str | None = Field(default=None, description="Canonical NIST 800-53 control id when found.")
    title: str | None = None
    family_id: str | None = None
    family_name: str | None = None
    soc2_tsc_mappings: list[str] = Field(default_factory=list)

tracer = trace.get_tracer(__name__)


@dataclass
class OrchestratorDeps:
    """Run-scoped dependencies surfaced to every tool.

    Pydantic AI injects an instance of this dataclass into each tool call via
    `RunContext[OrchestratorDeps]`. Sprint 2 keeps it small; Sprint 4 will add
    the MCP client handle, GitHub OAuth token, and cost budget.
    """

    user_id: str | None = None
    scan_run_id: str | None = None
    looked_up_controls: list[Control] = field(default_factory=list)


SYSTEM_PROMPT = (
    "You are AuditOrchestrator, the read-only SOC 2 readiness assistant for "
    "AuditPilot. When the user references a NIST 800-53 control identifier "
    "(for example 'AC-1' or 'SC-7'), call the lookup_control tool to fetch "
    "the canonical record, then summarise the control title and purpose in "
    "one sentence. Never invent control identifiers; only report controls "
    "returned by the tool."
)


def build_orchestrator_agent(
    model: Model | str = "test",
) -> Agent[OrchestratorDeps, str]:
    """Construct the orchestrator agent with the given model.

    Separating construction from the module-scope singleton makes tests trivial:
    tests pass `TestModel()` / `FunctionModel(...)`. Production code calls
    `build_orchestrator_agent("gemini-2.5-flash-lite")` (or routes through
    LiteLLM once chunk 2.12 PromptLoader lands).
    """

    agent: Agent[OrchestratorDeps, str] = Agent(
        model,
        deps_type=OrchestratorDeps,
        system_prompt=SYSTEM_PROMPT,
        instrument=True,
    )

    @agent.tool
    async def lookup_control(
        ctx: RunContext[OrchestratorDeps],
        control_id: str,
    ) -> LookupControlResult:
        """Look up a NIST 800-53 control by identifier via compliance-kb-mcp.

        Returns a typed :class:`LookupControlResult`. The orchestrator records
        every successful lookup in ``ctx.deps.looked_up_controls`` so the
        graph node can materialise ``ControlAssessment`` records into state.
        """

        with tracer.start_as_current_span("orchestrator.lookup_control") as span:
            span.set_attribute("control.id", control_id)
            # Sprint 3 day-0 chunk 3.0b — reject malformed/hostile ids before
            # the downstream call. The MCP tool then never sees path traversal,
            # SQL injection, or prompt-injected free text masquerading as a
            # control identifier.
            if not _CONTROL_ID_PATTERN.match(control_id):
                span.set_attribute("control.found", False)
                span.set_attribute("control.invalid_format", True)
                return LookupControlResult(found=False, control_id=control_id)
            control = _kb_lookup_control(control_id)
            if control is None:
                span.set_attribute("control.found", False)
                return LookupControlResult(found=False, control_id=control_id)
            ctx.deps.looked_up_controls.append(control)
            span.set_attribute("control.found", True)
            span.set_attribute("control.title", control.title)
            return LookupControlResult(
                found=True,
                control_id=control_id,
                id=control.id,
                title=control.title,
                family_id=control.family_id,
                family_name=control.family_name,
                soc2_tsc_mappings=list(control.soc2_tsc_mappings),
            )

    return agent


# NOTE: ``run_orchestrator()`` was deleted in Sprint 3 day-0 chunk 3.0d.
# It was a parallel state writer that mutated ``AuditPilotState`` in place
# (``state.messages.append(...)``, ``state.control_map[...] = ...``), bypassing
# the LangGraph graph and silently violating the single-writer invariant from
# ADR-0002. The canonical write path is ``orchestrator_node`` in
# ``apps/api/graph.py``, which returns deltas. Tests invoke
# ``build_graph(memory_checkpointer()).ainvoke({...})`` directly.


__all__ = [
    "LookupControlResult",
    "OrchestratorDeps",
    "SYSTEM_PROMPT",
    "build_orchestrator_agent",
]
