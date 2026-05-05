"""Unit tests for :class:`apps.api.jobs.client.UpstashRestRedis`.

Sprint 3 day-1 chunk 3.0f — verify that Upstash REST 4xx responses whose
JSON body carries a recoverable error (notably ``BUSYGROUP`` on the second
``XGROUP CREATE`` against an existing consumer group) surface as
``RuntimeError("Upstash error: ...")`` rather than ``httpx.HTTPStatusError``.

This is the contract ``UpstashRestRedis.xgroup_create`` and ``JobQueue``
depend on: a recoverable error is a ``RuntimeError`` whose ``str`` contains
the upstream error code (``BUSYGROUP``, ``NOSCRIPT``, etc.). Without this
shape, the BUSYGROUP swallow at ``client.py:117-120`` never fires and every
uvicorn restart trips ``background_tasks.start_failed``.

Uses respx (already in dev deps) to mock the Upstash REST endpoint.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from apps.api.jobs.client import UpstashRestRedis

UPSTASH_URL = "https://test-host.upstash.io"
UPSTASH_TOKEN = "test-token"


@pytest.fixture
async def upstash_client():
    client = UpstashRestRedis(UPSTASH_URL, UPSTASH_TOKEN)
    try:
        yield client
    finally:
        await client.aclose()


@respx.mock
async def test_exec_translates_400_with_error_body_into_runtime_error(
    upstash_client: UpstashRestRedis,
) -> None:
    """Upstash returns HTTP 400 + body ``{"error": "..."}`` for benign
    "already exists" cases. The adapter must surface those as RuntimeError
    so the BUSYGROUP swallow in ``xgroup_create`` can recognise them."""

    respx.post(UPSTASH_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": "BUSYGROUP Consumer Group name already exists"},
        )
    )

    with pytest.raises(RuntimeError) as excinfo:
        await upstash_client._exec("XGROUP", "CREATE", "stream", "group", "0")

    assert "BUSYGROUP" in str(excinfo.value), (
        f"expected BUSYGROUP marker preserved in RuntimeError; got {excinfo.value!r}"
    )
    # Crucially NOT an httpx.HTTPStatusError — that would mask the BUSYGROUP
    # marker behind the HTTP-status-shape and break xgroup_create's swallow.
    assert not isinstance(excinfo.value, httpx.HTTPStatusError)


@respx.mock
async def test_xgroup_create_swallows_busygroup_on_400(
    upstash_client: UpstashRestRedis,
) -> None:
    """End-to-end contract for ``xgroup_create``: a BUSYGROUP 400 must
    return ``"OK"`` (the redis-py-shape "noop" return), not raise.

    This is the case that fires on every uvicorn restart after the first —
    consumer group already exists from the previous run."""

    respx.post(UPSTASH_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": "BUSYGROUP Consumer Group name 'auditpilot-workers' already exists"},
        )
    )

    result = await upstash_client.xgroup_create(
        "auditpilot:jobs", "auditpilot-workers", id="0", mkstream=True
    )

    assert result == "OK", (
        f"BUSYGROUP must be swallowed and return 'OK'; got {result!r}"
    )


@respx.mock
async def test_exec_still_raises_for_non_recoverable_400_without_error_body(
    upstash_client: UpstashRestRedis,
) -> None:
    """Defensive: a 4xx with no JSON body (e.g., a transport-level error
    page) must still raise — we should not silently swallow it."""

    respx.post(UPSTASH_URL).mock(
        return_value=httpx.Response(400, content=b"<html>upstream error</html>"),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await upstash_client._exec("PING")


@respx.mock
async def test_exec_returns_result_field_on_success(
    upstash_client: UpstashRestRedis,
) -> None:
    """Smoke test: the happy path is unchanged — 200 + ``{"result": ...}``
    returns the result value verbatim."""

    respx.post(UPSTASH_URL).mock(
        return_value=httpx.Response(200, json={"result": "PONG"}),
    )

    assert await upstash_client._exec("PING") == "PONG"


@respx.mock
async def test_exec_translates_other_named_redis_errors_into_runtime_error(
    upstash_client: UpstashRestRedis,
) -> None:
    """The same envelope contract holds for any Redis error name Upstash
    might return — NOSCRIPT, WRONGTYPE, CROSSSLOT, etc. We do not need to
    enumerate them; the test pins the *shape* (RuntimeError with the
    upstream message embedded)."""

    respx.post(UPSTASH_URL).mock(
        return_value=httpx.Response(
            400, json={"error": "WRONGTYPE Operation against a key holding the wrong kind of value"}
        ),
    )

    with pytest.raises(RuntimeError) as excinfo:
        await upstash_client._exec("LPUSH", "stream-key", "value")

    assert "WRONGTYPE" in str(excinfo.value)
