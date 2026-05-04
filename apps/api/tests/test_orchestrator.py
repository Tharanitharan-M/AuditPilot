"""
Tests for the Sprint 2 orchestrator stub.

Acceptance (PLAN.md chunk 2.5):
  Invoke the orchestrator with a mock LLM, expect state to contain the
  compliance-kb-mcp.lookup_control result.

We use Pydantic AI's `FunctionModel` to deterministically choreograph a
two-step conversation:
  turn 1 -> the "LLM" emits a ToolCallPart requesting lookup_control(AC-1)
  turn 2 -> the "LLM" consumes the tool return and emits the final text

No live LLM, no network. Fast and deterministic.
"""

from __future__ import annotations

from typing import cast

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.api.agents.orchestrator import (
    OrchestratorDeps,
    build_orchestrator_agent,
    run_orchestrator,
)
from apps.api.state import AuditPilotState


def _make_lookup_control_then_summarise(control_id: str, summary: str):
    """FunctionModel body that first calls lookup_control, then writes text."""

    call_count = {"n": 0}

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="lookup_control",
                        args={"control_id": control_id},
                        tool_call_id="call_1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content=summary)])

    return fn


@pytest.mark.asyncio
async def test_orchestrator_invokes_lookup_control_and_merges_into_state():
    model = FunctionModel(
        _make_lookup_control_then_summarise(
            "AC-1",
            "AC-1 is the NIST 800-53 Policy and Procedures control.",
        )
    )

    state = AuditPilotState(user_id="user_test", scan_run_id="run_test")
    result = await run_orchestrator(
        state,
        "Look up control AC-1",
        model=model,
    )

    assert result.current_step == "orchestrator_stub_complete"
    # Two messages appended: HumanMessage + AIMessage final text
    assert len(result.messages) == 2
    assert "AC-1" in str(result.messages[-1].content)

    # AC-1 maps to at least one SOC 2 TSC clause (CC5.3 in the
    # curated dataset), so the orchestrator must have populated
    # control_map via the tool's downstream merge.
    assert result.control_map, (
        "orchestrator did not merge lookup_control result into state.control_map"
    )
    all_nist_refs = {
        ref for ca in result.control_map.values() for ref in ca.nist_800_53_refs
    }
    assert "AC-1" in all_nist_refs


@pytest.mark.asyncio
async def test_orchestrator_tolerates_unknown_control_id():
    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Inspect whether we already saw a ToolReturnPart; if so, finish.
        saw_return = any(
            isinstance(p, ToolReturnPart) and p.tool_name == "lookup_control"
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
        )
        if not saw_return:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="lookup_control",
                        args={"control_id": "ZZ-999"},
                        tool_call_id="call_1",
                    )
                ]
            )
        return ModelResponse(
            parts=[TextPart(content="Control ZZ-999 was not found in the catalog.")]
        )

    state = AuditPilotState()
    deps = OrchestratorDeps(user_id="u", scan_run_id="r")
    result = await run_orchestrator(
        state,
        "Look up control ZZ-999",
        model=FunctionModel(fn),
        deps=deps,
    )

    assert result.control_map == {}, (
        "no tsc_ids should have been recorded for a non-existent control"
    )
    assert deps.looked_up_controls == [], (
        "looked_up_controls should remain empty on a miss"
    )


@pytest.mark.asyncio
async def test_build_orchestrator_agent_has_lookup_control_tool():
    agent = build_orchestrator_agent("test")
    tools = agent.toolsets
    names = set()
    for ts in tools:
        tool_def_map = getattr(ts, "tools", None)
        if isinstance(tool_def_map, dict):
            names.update(tool_def_map.keys())
    assert "lookup_control" in names, (
        f"expected lookup_control in registered tools; got {names}"
    )
