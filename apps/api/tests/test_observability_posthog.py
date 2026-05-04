"""PostHog wiring contract (chunk 2.13, ADR-0014).

Exercises :mod:`apps.api.observability.posthog` against a stubbed PostHog
client so the unit tests stay hermetic. A live integration test lives in
:mod:`test_observability_posthog_live` and is skipped unless
``POSTHOG_API_KEY`` / ``NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN`` is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.api.observability.posthog import (
    capture_event,
    capture_exception,
    install_middleware,
    make_observability_hook,
)


@dataclass
class _StubPosthog:
    captures: list[dict[str, Any]] = field(default_factory=list)

    def capture(self, *, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        self.captures.append(
            {"distinct_id": distinct_id, "event": event, "properties": properties}
        )

    def flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def test_capture_event_is_noop_when_client_is_none() -> None:
    capture_event(None, "nothing-happens", properties={"x": 1})


def test_capture_event_forwards_to_client() -> None:
    stub = _StubPosthog()
    capture_event(stub, "my_event", properties={"k": "v"})

    assert stub.captures == [
        {"distinct_id": "server", "event": "my_event", "properties": {"k": "v"}}
    ]


def test_capture_exception_attaches_type_and_message() -> None:
    stub = _StubPosthog()
    try:
        raise ValueError("boom")
    except ValueError as exc:
        capture_exception(stub, exc, properties={"endpoint": "/x"})

    assert len(stub.captures) == 1
    props = stub.captures[0]["properties"]
    assert props["exception_type"] == "ValueError"
    assert props["exception_message"] == "boom"
    assert props["endpoint"] == "/x"


def test_capture_exception_is_noop_when_client_is_none() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        capture_exception(None, exc)


def test_make_observability_hook_translates_event_names() -> None:
    stub = _StubPosthog()
    hook = make_observability_hook(stub)
    hook("langfuse_fallback", "orchestrator", {"reason": "timeout"})

    assert stub.captures == [
        {
            "distinct_id": "server",
            "event": "auditpilot.langfuse_fallback",
            "properties": {"subject": "orchestrator", "reason": "timeout"},
        }
    ]


@pytest.mark.asyncio
async def test_middleware_captures_unhandled_exception_and_reraises() -> None:
    stub = _StubPosthog()
    app = FastAPI()
    install_middleware(app, stub)

    @app.get("/raise")
    async def _raise() -> None:
        raise ZeroDivisionError("kaboom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raise")

    assert response.status_code == 500
    assert len(stub.captures) == 1
    captured = stub.captures[0]
    assert captured["event"] == "$exception"
    assert captured["properties"]["exception_type"] == "ZeroDivisionError"
    assert captured["properties"]["request_path"] == "/raise"
    assert captured["properties"]["request_method"] == "GET"


@pytest.mark.asyncio
async def test_middleware_does_not_capture_successful_requests() -> None:
    stub = _StubPosthog()
    app = FastAPI()
    install_middleware(app, stub)

    @app.get("/ok")
    async def _ok() -> dict[str, str]:
        return {"status": "ok"}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ok")

    assert response.status_code == 200
    assert stub.captures == []
