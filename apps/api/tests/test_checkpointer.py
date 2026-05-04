"""
Tests for chunk 2.6 — PostgresSaver / InMemorySaver checkpointer wiring.

Acceptance (PLAN.md chunk 2.6):
  Invoke the graph twice with the same thread_id; the second call resumes
  from the persisted checkpoint (i.e. the accumulated state is retained).

Two tiers of test:
- Unit (default): runs against `InMemorySaver` — no live Postgres required.
  This verifies the graph's checkpoint semantics (thread_id → resume).
- Integration (opt-in via `-m integration`): runs against the Postgres URL
  supplied by TEST_DATABASE_URL, proving the production path works. CI only
  flips this on once a branch DB is provisioned.

Refs: PLAN.md chunk 2.6; ADR-0001; ADR-0007.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.api.checkpointer import memory_checkpointer, postgres_checkpointer
from apps.api.graph import build_graph


def _canned_reply_model(reply: str) -> FunctionModel:
    """FunctionModel that always returns the same text — no tool calls."""

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=reply)])

    return FunctionModel(fn)


@pytest.mark.asyncio
async def test_graph_resumes_from_checkpoint_with_same_thread_id():
    checkpointer = memory_checkpointer()
    graph = build_graph(
        checkpointer,
        model=_canned_reply_model("acknowledged"),
    )

    config: dict[str, Any] = {"configurable": {"thread_id": "thread-abc"}}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="first turn")]},
        config=config,
    )
    assert len(first["messages"]) == 2
    assert str(first["messages"][-1].content) == "acknowledged"

    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="second turn")]},
        config=config,
    )

    # Resumed state must include the first turn + the second turn + both AI
    # replies — total four. If checkpointing is broken we see only the fresh
    # turn's pair (two messages), which is the regression this test catches.
    assert len(second["messages"]) == 4, (
        "expected [H,A,H,A] after resuming from checkpoint; "
        f"got {len(second['messages'])} messages"
    )
    assert str(second["messages"][0].content) == "first turn"
    assert str(second["messages"][2].content) == "second turn"


@pytest.mark.asyncio
async def test_graph_isolates_threads():
    """Two independent thread_ids must not bleed state into each other."""

    checkpointer = memory_checkpointer()
    graph = build_graph(
        checkpointer,
        model=_canned_reply_model("ok"),
    )

    a_config = {"configurable": {"thread_id": "thread-a"}}
    b_config = {"configurable": {"thread_id": "thread-b"}}

    await graph.ainvoke(
        {"messages": [HumanMessage(content="A says hello")]}, config=a_config
    )
    b = await graph.ainvoke(
        {"messages": [HumanMessage(content="B says hi")]}, config=b_config
    )

    assert len(b["messages"]) == 2, (
        "thread-b must only see its own turn; got "
        f"{[m.content for m in b['messages']]}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_checkpointer_resumes(request):
    """Integration test against a real Postgres (chunk 2.6 acceptance).

    Enable with ``pytest apps/api/tests/test_checkpointer.py -m integration``
    and TEST_DATABASE_URL set to a fresh database (e.g. Neon test branch).
    """

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; skipping Postgres integration test")

    async with postgres_checkpointer(url) as cp:
        graph = build_graph(cp, model=_canned_reply_model("pg-ok"))
        thread_id = f"test-thread-{os.getpid()}"
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        first = await graph.ainvoke(
            {"messages": [HumanMessage(content="pg-turn-1")]},
            config=config,
        )
        assert len(first["messages"]) == 2

        second = await graph.ainvoke(
            {"messages": [HumanMessage(content="pg-turn-2")]},
            config=config,
        )
        assert len(second["messages"]) == 4, (
            "AsyncPostgresSaver did not persist state across invocations"
        )
