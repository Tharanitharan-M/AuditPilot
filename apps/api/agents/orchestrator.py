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

from dataclasses import dataclass, field

from compliance_kb_mcp.schemas import Control
from compliance_kb_mcp.tools import lookup_control as _kb_lookup_control
from langchain_core.messages import AIMessage, HumanMessage
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from apps.api.state import AuditPilotState, ControlAssessment


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


async def run_orchestrator(
    state: AuditPilotState,
    user_input: str,
    *,
    model: Model | str = "test",
    deps: OrchestratorDeps | None = None,
) -> AuditPilotState:
    """Invoke the orchestrator with `user_input` and merge the result into `state`.

    This is the single graph-node entrypoint for Sprint 2. Downstream sprints
    will split this into dedicated LangGraph nodes (`evidence_collection`,
    `control_mapping`, `adversarial_challenge`, `hitl_gate`).
    """

    deps = deps or OrchestratorDeps(
        user_id=state.user_id,
        scan_run_id=state.scan_run_id,
    )
    agent = build_orchestrator_agent(model)

    with tracer.start_as_current_span("orchestrator.run") as span:
        span.set_attribute("orchestrator.user_id", deps.user_id or "anonymous")
        span.set_attribute("orchestrator.scan_run_id", deps.scan_run_id or "none")
        result = await agent.run(user_input, deps=deps)

    state.messages.append(HumanMessage(content=user_input))
    state.messages.append(AIMessage(content=result.output))

    for control in deps.looked_up_controls:
        for tsc_id in control.soc2_tsc_mappings:
            existing = state.control_map.get(tsc_id)
            nist_refs = list(existing.nist_800_53_refs) if existing else []
            if control.id not in nist_refs:
                nist_refs.append(control.id)
            state.control_map[tsc_id] = ControlAssessment(
                tsc_id=tsc_id,
                status=existing.status if existing else "unknown",
                confidence=existing.confidence if existing else 0.0,
                nist_800_53_refs=nist_refs,
                evidence_ids=list(existing.evidence_ids) if existing else [],
                rationale=existing.rationale if existing else None,
            )

    state.current_step = "orchestrator_stub_complete"
    return state


__all__ = [
    "LookupControlResult",
    "OrchestratorDeps",
    "SYSTEM_PROMPT",
    "build_orchestrator_agent",
    "run_orchestrator",
]
