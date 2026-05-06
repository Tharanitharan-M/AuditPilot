"""
AuditOrchestrator — Sprint 4
============================
Single-writer Pydantic AI agent that coordinates evidence collection,
control mapping, policy drafting, and adversarial challenges. As of
Sprint 4 chunk 4.3 the orchestrator talks to ``compliance-kb-mcp`` over
a real stdio MCP transport (see ``apps.api.agents.mcp_clients``)
instead of the Sprint-2 in-process import.

Key properties:
- Model is injectable so tests can supply ``TestModel`` /
  ``FunctionModel`` without hitting a live LLM or the network
  (PLAN 2.5 acceptance, retained through Sprint 4).
- Sprint 4 chunk 4.3: when ``mcp_toolset=True`` the agent's toolset
  is the live MCP server; when ``mcp_toolset=False`` the orchestrator
  falls back to the typed in-process wrapper (used by Sprint-2
  FunctionModel tests and by the Sprint-3 day-0 hostile-id regex
  regression suite, both of which are deterministic and fast).
- Tool is registered via Pydantic AI's native ``@agent.tool`` decorator
  so the LLM sees a typed JSON Schema either way.

Refs: PLAN.md chunks 2.5, 4.3; ADR-0001 (LangGraph 1.x runtime);
ADR-0002 (three-agent architecture); ADR-0005 (five MCP servers);
system-design.md 3.2, 6.4.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from compliance_kb_mcp.schemas import Control
from compliance_kb_mcp.tools import lookup_control as _kb_lookup_control
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from apps.api.agents.mcp_clients import compliance_kb_mcp_server

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
    "AuditPilot. The ONLY tools available to you are: lookup_control, "
    "lookup_by_soc2_tsc, search_controls, list_controls. All four read the "
    "static NIST 800-53 catalog. You have NO tool that reads the user's "
    "GitHub repositories, no tool that lists files, no tool that checks "
    "branch protection, 2FA, code scanning, secret scanning, or Dependabot "
    "status. The evidence collectors that pull repo state are not yet "
    "wired in this build (they ship in a later sprint).\n"
    "\n"
    "You operate in three modes:\n"
    "\n"
    "1. FREE CHAT ABOUT CONTROLS. When the user asks a question that "
    "references a NIST 800-53 control identifier (for example 'AC-1' or "
    "'SC-7'), call lookup_control. For broader questions about controls "
    "or families, call search_controls, lookup_by_soc2_tsc, or list_controls.\n"
    "\n"
    "2. READINESS-SCAN SUMMARY. When the user asks you to summarise a "
    "readiness scan, the system has already mapped evidence to SOC 2 Trust "
    "Services Criteria clauses. The result is surfaced to you as a "
    "'SCAN CONTEXT' block in the user message. Read that block and produce "
    "a 4-6 sentence summary that names the top TSC clauses with their "
    "statuses and the count of supporting NIST 800-53 controls. Be explicit "
    "that the underlying evidence in this build is placeholder data, not a "
    "live read of the user's repositories. Do NOT call tools to re-fetch "
    "what is already in SCAN CONTEXT.\n"
    "\n"
    "3. REPO-STATE QUESTIONS. If the user asks anything that requires "
    "reading their repositories — examples: 'can you get info from the "
    "repo I shared', 'is branch protection enabled', 'what files are in "
    "my repo', 'do I have 2FA', 'what are my Dependabot alerts', 'list my "
    "PRs', 'check my secret scanning' — refuse honestly with one short "
    "paragraph: explain that you do not have a tool to read GitHub "
    "repositories in this build, that the evidence pulled into the "
    "readiness summary is placeholder data, and that the real GitHub "
    "evidence collectors land in a later sprint. Do NOT rephrase the "
    "SCAN CONTEXT block as a substitute answer. Do NOT call any tool. Do "
    "NOT speculate about the user's repos.\n"
    "\n"
    "In every mode: never invent control identifiers, never claim "
    "AuditPilot can issue official compliance reports, and never offer to "
    "take a write action. AuditPilot is read-only by design — your output "
    "is always draft readiness suggestions for the user to apply."
)


async def _mcp_process_tool_call(
    ctx: RunContext[OrchestratorDeps],
    call_tool: Callable[..., Awaitable[Any]],
    name: str,
    tool_args: dict[str, Any],
) -> Any:
    """Pydantic AI ``process_tool_call`` hook for the MCP toolset.

    Sprint 3 day-0 chunk 3.0b's hostile-control-id defence-in-depth
    runs HERE when the orchestrator dispatches over the live MCP
    transport. Before forwarding the call to the subprocess we
    revalidate ``control_id`` against the orchestrator's tighter
    pattern (the MCP server's own ``Field(pattern=...)`` rejects path
    traversal and SQL injection but does not allow NIST OSCAL
    enhancement parens like ``AC-2(1)``). On reject we return a typed
    miss without burning a subprocess round-trip.

    Successful returns also feed ``ctx.deps.looked_up_controls`` so the
    graph node can fold soc2_tsc_mappings into ``control_map`` (this
    used to live in the local ``@agent.tool`` wrapper).
    """

    if name == "lookup_control":
        control_id = str(tool_args.get("control_id", ""))
        with tracer.start_as_current_span(
            "orchestrator.lookup_control_via_mcp"
        ) as span:
            span.set_attribute("control.id", control_id)
            if not _CONTROL_ID_PATTERN.match(control_id):
                span.set_attribute("control.found", False)
                span.set_attribute("control.invalid_format", True)
                return LookupControlResult(
                    found=False, control_id=control_id
                ).model_dump()
            result = await call_tool(name, tool_args)
            # The MCP server returns ``Control | None`` serialised as a
            # dict (or ``None`` literal). Fold into deps so the graph
            # node can mint ControlAssessment rows downstream.
            payload = result if isinstance(result, dict) else None
            if payload:
                try:
                    ctx.deps.looked_up_controls.append(Control.model_validate(payload))
                except Exception:  # noqa: BLE001
                    # Schema drift between client and server: log via
                    # the trace attribute so the operator sees it but
                    # don't crash the run.
                    span.set_attribute("control.deps_merge_failed", True)
            span.set_attribute("control.found", payload is not None)
            return result

    # Any other tool the MCP server exposes flows through unchanged.
    return await call_tool(name, tool_args)


def build_orchestrator_agent(
    model: Model | str = "test",
    *,
    mcp_toolset: bool = False,
) -> Agent[OrchestratorDeps, str]:
    """Construct the orchestrator agent with the given model.

    Separating construction from the module-scope singleton makes tests trivial:
    tests pass ``TestModel()`` / ``FunctionModel(...)``. Production code calls
    ``build_orchestrator_agent(model, mcp_toolset=True)`` so the agent talks
    to ``compliance-kb-mcp`` over the real stdio MCP transport (chunk 4.3).

    Parameters
    ----------
    model : Model | str
        Pydantic AI model — accepts a string identifier or an instance.
        Production passes the result of
        ``apps.api.agents.models.build_model(...)``.
    mcp_toolset : bool
        When True, the agent registers ``compliance-kb-mcp`` as a
        ``MCPServerStdio`` toolset and the local ``@agent.tool`` wrapper
        is skipped (avoids a tool-name conflict). When False (default),
        the agent uses only the in-process ``@agent.tool`` wrapper,
        keeping unit tests fast and deterministic. The graph node in
        ``apps.api.graph`` flips this on through its own kwarg.
    """

    toolsets = (
        [_build_mcp_server_with_callback()]
        if mcp_toolset
        else []
    )

    agent: Agent[OrchestratorDeps, str] = Agent(
        model,
        deps_type=OrchestratorDeps,
        system_prompt=SYSTEM_PROMPT,
        instrument=True,
        toolsets=toolsets,
    )

    if not mcp_toolset:
        @agent.tool
        async def lookup_control(
            ctx: RunContext[OrchestratorDeps],
            control_id: str,
        ) -> LookupControlResult:
            """Look up a NIST 800-53 control by identifier (in-process Sprint-2 stub).

            Used in ``mcp_toolset=False`` test paths only. The production
            orchestrator dispatches over the MCP transport and applies the
            chunk 3.0b regex check via ``_mcp_process_tool_call``.
            """

            with tracer.start_as_current_span("orchestrator.lookup_control") as span:
                span.set_attribute("control.id", control_id)
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


def _build_mcp_server_with_callback():
    """Construct the MCP server with the regex-validation hook attached.

    ``MCPServerStdio`` accepts ``process_tool_call`` as a constructor
    kwarg, so we pass our hook in directly rather than mutating the
    instance after construction.
    """

    return compliance_kb_mcp_server(process_tool_call=_mcp_process_tool_call)


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
