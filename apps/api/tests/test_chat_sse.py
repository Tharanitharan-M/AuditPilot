"""
Tests for chunk 2.7 — /chat AI SDK 6 UIMessage SSE bridge.

Acceptance (PLAN.md chunk 2.7):
  curl -N -H "Accept: text/event-stream" POST /chat ... streams the AI SDK 6
  wire format with header ``x-vercel-ai-ui-message-stream: v1``.

We reproduce the curl invocation with httpx + ASGITransport and assert:
- header `x-vercel-ai-ui-message-stream: v1` is present
- content-type is text/event-stream
- frames arrive in spec order: start -> start-step -> (tool-input-available
  -> tool-output-available)? -> text-* -> finish-step -> finish -> [DONE]
- every JSON frame is valid and matches one of the AI SDK 6 chunk types
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

_TEST_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgres://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CLERK_SECRET_KEY": "sk_test_fake",
    "CLERK_PUBLISHABLE_KEY": "pk_test_fake",
    "GEMINI_API_KEY": "fake-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-fake",
    "LANGFUSE_SECRET_KEY": "sk-lf-fake",
}


@pytest.fixture(autouse=True)
def _env():
    from apps.api.main import get_settings

    with patch.dict(os.environ, _TEST_ENV, clear=False):
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def lookup_then_reply_model():
    """FunctionModel that emits a ToolCallPart then a final TextPart.

    Two-turn choreography:
      turn 1: call lookup_control(AC-1)
      turn 2: read the ToolReturnPart, emit the summary text
    """

    call_count = {"n": 0}

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="lookup_control",
                        args={"control_id": "AC-1"},
                        tool_call_id="call_1",
                    )
                ]
            )
        return ModelResponse(
            parts=[TextPart(content="AC-1 is Policy and Procedures.")]
        )

    return FunctionModel(fn)


@pytest.fixture
async def client(lookup_then_reply_model):
    """Async HTTP client with the /chat route wired to a FunctionModel.

    We monkeypatch ``_chat_model_factory`` so the endpoint uses our stub
    model, avoiding any LLM network dependency. Sprint 4 chunk 4.3 also
    flips ``_chat_mcp_toolset`` to ``False`` so the test path does not
    fork the ``compliance-kb-mcp`` subprocess on every request — the
    Sprint-2 FunctionModel emits ToolCallParts directly, so the toolset
    is irrelevant to the SSE wire-format assertions in this file.
    """

    from apps.api import main as main_module

    original_model = main_module._chat_model_factory
    original_mcp = main_module._chat_mcp_toolset
    main_module._chat_model_factory = lambda: lookup_then_reply_model
    main_module._chat_mcp_toolset = lambda: False
    try:
        transport = ASGITransport(app=main_module.app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        main_module._chat_model_factory = original_model
        main_module._chat_mcp_toolset = original_mcp


async def _consume_sse_stream(client: AsyncClient, body: dict) -> tuple[dict, list[str]]:
    """Hit /chat, return (headers_dict, list_of_sse_data_lines)."""
    async with client.stream("POST", "/chat", json=body) as resp:
        assert resp.status_code == 200, (
            f"POST /chat returned {resp.status_code}"
        )
        headers = {k.lower(): v for k, v in resp.headers.items()}
        lines: list[str] = []
        async for raw in resp.aiter_lines():
            if raw.startswith("data: "):
                lines.append(raw[len("data: ") :])
    return headers, lines


def _parse_chunks(data_lines: list[str]) -> list[dict | str]:
    """Decode each SSE data line; return dict for JSON frames, str for [DONE]."""
    out: list[dict | str] = []
    for line in data_lines:
        if line.strip() == "[DONE]":
            out.append("[DONE]")
        else:
            out.append(json.loads(line))
    return out


@pytest.mark.asyncio
async def test_chat_sse_wire_format_header_is_v1(client: AsyncClient):
    headers, _ = await _consume_sse_stream(
        client,
        body={
            "messages": [{"role": "user", "content": "look up AC-1"}],
            "thread_id": "thread-wire",
        },
    )

    assert headers.get("content-type", "").startswith("text/event-stream"), (
        f"expected text/event-stream; got {headers.get('content-type')}"
    )
    assert headers.get("x-vercel-ai-ui-message-stream") == "v1", (
        "AI SDK 6 useChat REQUIRES the handshake header `x-vercel-ai-ui-message-stream: v1` "
        f"-- got {headers.get('x-vercel-ai-ui-message-stream')!r}"
    )


@pytest.mark.asyncio
async def test_chat_sse_emits_start_step_tool_text_finish_done_in_order(
    client: AsyncClient,
):
    _, data_lines = await _consume_sse_stream(
        client,
        body={
            "messages": [{"role": "user", "content": "look up AC-1"}],
            "thread_id": "thread-order",
        },
    )
    chunks = _parse_chunks(data_lines)

    # Mandatory terminator
    assert chunks[-1] == "[DONE]", (
        f"AI SDK 6 streams must end with data: [DONE]; got {chunks[-1]!r}"
    )

    types = [c.get("type") if isinstance(c, dict) else c for c in chunks]

    # `start` must come first, before any content
    assert types[0] == "start", f"first chunk must be 'start'; got {types[0]!r}"
    # `start-step` immediately after `start`
    assert types[1] == "start-step", (
        f"second chunk must be 'start-step'; got {types[1]!r}"
    )
    # `finish` must precede `[DONE]`
    assert types[-3] == "finish-step"
    assert types[-2] == "finish"

    # Tool-call pair: tool-input-available must come *before* tool-output-available
    tool_in_idx = types.index("tool-input-available") if "tool-input-available" in types else -1
    tool_out_idx = (
        types.index("tool-output-available") if "tool-output-available" in types else -1
    )
    assert tool_in_idx != -1, "lookup_control should produce tool-input-available"
    assert tool_out_idx != -1, "lookup_control should produce tool-output-available"
    assert tool_in_idx < tool_out_idx, (
        "tool-input-available must precede tool-output-available"
    )

    # Text block: text-start -> text-delta -> text-end, in order
    assert "text-start" in types
    assert "text-delta" in types
    assert "text-end" in types
    start_idx = types.index("text-start")
    delta_idx = types.index("text-delta")
    end_idx = types.index("text-end")
    assert start_idx < delta_idx < end_idx


@pytest.mark.asyncio
async def test_chat_sse_start_chunk_includes_message_id(client: AsyncClient):
    _, data_lines = await _consume_sse_stream(
        client,
        body={
            "messages": [{"role": "user", "content": "look up AC-1"}],
            "thread_id": "thread-mid",
        },
    )
    chunks = _parse_chunks(data_lines)
    start = next(
        c for c in chunks if isinstance(c, dict) and c.get("type") == "start"
    )
    assert "messageId" in start, f"AI SDK 6 start must carry messageId; got {start}"
    assert start["messageId"].startswith("msg_"), (
        f"messageId should use msg_ prefix; got {start['messageId']!r}"
    )


@pytest.mark.asyncio
async def test_chat_sse_text_delta_carries_final_text(client: AsyncClient):
    _, data_lines = await _consume_sse_stream(
        client,
        body={
            "messages": [{"role": "user", "content": "look up AC-1"}],
            "thread_id": "thread-text",
        },
    )
    chunks = _parse_chunks(data_lines)

    deltas = [c for c in chunks if isinstance(c, dict) and c.get("type") == "text-delta"]
    assert len(deltas) == 1, f"expected exactly one text-delta (coarse stream); got {len(deltas)}"
    assert "AC-1" in deltas[0]["delta"], (
        f"text-delta should contain the orchestrator's final summary; got {deltas[0]!r}"
    )


@pytest.mark.asyncio
async def test_chat_sse_tool_call_payload_shape(client: AsyncClient):
    _, data_lines = await _consume_sse_stream(
        client,
        body={
            "messages": [{"role": "user", "content": "look up AC-1"}],
            "thread_id": "thread-tool",
        },
    )
    chunks = _parse_chunks(data_lines)
    tool_in = next(
        c
        for c in chunks
        if isinstance(c, dict) and c.get("type") == "tool-input-available"
    )
    tool_out = next(
        c
        for c in chunks
        if isinstance(c, dict) and c.get("type") == "tool-output-available"
    )

    assert tool_in["toolName"] == "lookup_control"
    assert tool_in["input"] == {"control_id": "AC-1"}
    assert tool_out["toolCallId"] == tool_in["toolCallId"]
    assert isinstance(tool_out["output"], (str, dict))
