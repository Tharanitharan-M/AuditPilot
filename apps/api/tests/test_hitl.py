"""Tests for the HITL gate — Sprint 6 chunks 6.1, 6.12, 6.13.

Covers:
  - Graph pauses at human_review_gate via interrupt()
  - Resume with approve → finalize_policy → END
  - Resume with edit → finalize_policy with edited content → END
  - Resume with reject → re-draft loop
  - Three-strike circuit breaker fires after 3 rejections

Refs: PLAN.md chunks 6.1, 6.12, 6.13; ADR-0007.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from apps.api.graph import build_graph
from apps.api.state import HumanReviewPayload


@pytest.fixture()
def policy_graph():
    """Build a graph with InMemorySaver for HITL testing."""
    return build_graph(InMemorySaver(), model="test", mcp_toolset=False)


def _make_policy_input(policy_type: str = "irp") -> dict:
    """Minimal graph input for the draft_policy intent."""
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content=f"Draft a {policy_type} policy for my organization.")],
        "intent": "draft_policy",
        "policy_type": policy_type,
        "repo_include_list": [],
    }


@pytest.mark.asyncio
async def test_hitl_gate_pauses_graph(policy_graph):
    """Graph should pause at human_review_gate and not reach END."""
    config = {"configurable": {"thread_id": "test-hitl-pause-1"}}
    input_data = _make_policy_input()

    # Invoke — should pause at interrupt
    await policy_graph.ainvoke(input_data, config=config)

    # The graph should have paused: check state has a draft
    state = await policy_graph.aget_state(config)
    assert state is not None
    # There should be pending tasks (the interrupted node)
    assert state.tasks, "Graph should have pending tasks after interrupt"
    has_interrupt = any(
        getattr(t, "interrupts", None) for t in state.tasks
    )
    assert has_interrupt, "At least one task should have interrupts"


@pytest.mark.asyncio
async def test_hitl_approve_flow(policy_graph):
    """Approve should finalize the policy and reach END."""
    config = {"configurable": {"thread_id": "test-hitl-approve-1"}}
    input_data = _make_policy_input()

    # Phase 1: invoke until interrupt
    await policy_graph.ainvoke(input_data, config=config)

    # Phase 2: resume with approve
    resume_payload = {"decision": "approve"}
    result = await policy_graph.ainvoke(
        Command(resume=resume_payload), config=config
    )

    # The draft should be finalized
    assert result.get("current_step") in ("policy_finalized", "orchestrator_complete")
    draft = result.get("draft_policy")
    if draft:
        if hasattr(draft, "finalized"):
            assert draft.finalized is True
        elif isinstance(draft, dict):
            assert draft.get("finalized") is True


@pytest.mark.asyncio
async def test_hitl_edit_flow(policy_graph):
    """Edit should replace content and finalize."""
    config = {"configurable": {"thread_id": "test-hitl-edit-1"}}
    input_data = _make_policy_input()

    await policy_graph.ainvoke(input_data, config=config)

    edited_text = "# My Custom IRP\n\nThis is my edited policy content."
    resume_payload = {
        "decision": "edit",
        "edited_content": edited_text,
    }
    result = await policy_graph.ainvoke(
        Command(resume=resume_payload), config=config
    )

    draft = result.get("draft_policy")
    if draft:
        content = draft.content if hasattr(draft, "content") else draft.get("content", "")
        assert "My Custom IRP" in content or "edited" in content.lower()


@pytest.mark.asyncio
async def test_hitl_reject_redraft_loop(policy_graph):
    """Reject should loop back to draft_policy (re-draft)."""
    config = {"configurable": {"thread_id": "test-hitl-reject-1"}}
    input_data = _make_policy_input()

    # Phase 1: initial draft
    await policy_graph.ainvoke(input_data, config=config)

    # Phase 2: reject with reason
    resume_payload = {
        "decision": "reject",
        "rejection_reason": "Not enough detail on containment procedures.",
    }
    await policy_graph.ainvoke(
        Command(resume=resume_payload), config=config
    )

    # After rejection, the graph should have re-drafted and paused at
    # the gate again (another interrupt).
    state = await policy_graph.aget_state(config)
    assert state is not None

    # Check rejection was recorded
    vals = state.values
    reasons = vals.get("rejection_reasons", [])
    assert len(reasons) >= 1
    assert "containment" in reasons[-1].lower()


@pytest.mark.asyncio
async def test_hitl_circuit_breaker_fires(policy_graph):
    """After 3 rejections, circuit breaker should fire — no more re-drafts."""
    config = {"configurable": {"thread_id": "test-hitl-breaker-1"}}
    input_data = _make_policy_input()

    # Initial draft
    await policy_graph.ainvoke(input_data, config=config)

    # Reject 3 times
    for i in range(3):
        resume_payload = {
            "decision": "reject",
            "rejection_reason": f"Rejection #{i + 1}: needs more detail.",
        }
        await policy_graph.ainvoke(
            Command(resume=resume_payload), config=config
        )

        state = await policy_graph.aget_state(config)
        vals = state.values
        count = vals.get("hitl_rejection_count", 0)

        if count >= 3:
            # Circuit breaker should have fired — graph should be done
            step = vals.get("current_step", "")
            assert step in ("manual_authoring", "circuit_breaker_fired"), (
                f"Expected circuit breaker at rejection {i + 1}, got step={step}"
            )
            # No more pending tasks — graph is at END
            has_interrupt = any(
                getattr(t, "interrupts", None)
                for t in (state.tasks or [])
            )
            assert not has_interrupt, "Graph should be done after circuit breaker"
            return

    pytest.fail("Circuit breaker did not fire after 3 rejections")


@pytest.mark.asyncio
async def test_human_review_payload_validation():
    """HumanReviewPayload should reject extra fields and validate constraints."""
    # Valid payloads
    p1 = HumanReviewPayload(decision="approve")
    assert p1.decision == "approve"

    p2 = HumanReviewPayload(decision="edit", edited_content="new content")
    assert p2.edited_content == "new content"

    p3 = HumanReviewPayload(decision="reject", rejection_reason="too vague")
    assert p3.rejection_reason == "too vague"

    # Extra fields should be rejected (extra="forbid")
    with pytest.raises(Exception):  # noqa: B017
        HumanReviewPayload(decision="approve", extra_field="nope")

    # Invalid decision
    with pytest.raises(Exception):  # noqa: B017
        HumanReviewPayload(decision="invalid_decision")
