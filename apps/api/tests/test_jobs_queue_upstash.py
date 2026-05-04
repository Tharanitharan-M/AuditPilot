"""Opt-in integration test: JobQueue against the live Upstash REST endpoint.

Runs only when the caller opts in via ``pytest -m integration`` **and**
``UPSTASH_REDIS_REST_URL`` + ``UPSTASH_REDIS_REST_TOKEN`` are set in the
environment. Uses a per-run random stream/group/dlq prefix so concurrent
CI runs or developer laptops don't collide, and tears everything down
with ``DEL`` at the end.

This is the proof-of-life test for ADR-0010's assumption that Upstash
REST supports ``XADD`` / ``XREADGROUP`` / ``XPENDING`` / ``XCLAIM`` /
``XACK``. It is *not* run in the default pytest invocation (``addopts``
in pyproject.toml excludes ``-m integration``).

Usage::

    export UPSTASH_REDIS_REST_URL=https://<host>.upstash.io
    export UPSTASH_REDIS_REST_TOKEN=...
    pytest apps/api/tests/test_jobs_queue_upstash.py -m integration -v
"""

from __future__ import annotations

import os
import uuid

import pytest

from apps.api.jobs.client import UpstashRestRedis
from apps.api.jobs.queue import JobQueue
from apps.api.jobs.schemas import JobMessage, JobType

pytestmark = pytest.mark.integration


@pytest.fixture
async def upstash_client():
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        pytest.skip(
            "UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN not set; "
            "skipping Upstash integration test."
        )
    client = UpstashRestRedis(url, token)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def upstash_queue(upstash_client):
    run_id = uuid.uuid4().hex[:8]
    stream = f"auditpilot:test:jobs:{run_id}"
    group = f"auditpilot-test-workers-{run_id}"
    dlq_stream = f"auditpilot:test:jobs:dlq:{run_id}"
    queue = JobQueue(
        upstash_client,
        stream=stream,
        group=group,
        dlq_stream=dlq_stream,
    )
    await queue.ensure_group()
    try:
        yield queue
    finally:
        await upstash_client.delete(stream, dlq_stream)


async def test_upstash_enqueue_claim_ack_happy_path(upstash_queue: JobQueue) -> None:
    job = JobMessage(
        type=JobType.DRIFT_SCAN,
        user_id="user_integration",
        idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
        payload={"source": "upstash-integration-test"},
    )

    result = await upstash_queue.enqueue(job)
    assert result.deduplicated is False

    claimed = await upstash_queue.claim_next(
        "worker-upstash", count=1, block_ms=2_000
    )
    assert len(claimed) == 1
    mid, reclaimed = claimed[0]
    assert reclaimed.user_id == "user_integration"
    assert reclaimed.payload == {"source": "upstash-integration-test"}

    await upstash_queue.ack(mid)
    empty = await upstash_queue.claim_next(
        "worker-upstash", count=1, block_ms=500
    )
    assert empty == []


async def test_upstash_xpending_and_xclaim_round_trip(upstash_queue: JobQueue) -> None:
    job = JobMessage(
        type=JobType.DRIFT_SCAN,
        user_id="user_integration",
        idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
    )
    await upstash_queue.enqueue(job)

    claimed = await upstash_queue.claim_next(
        "worker-a", count=1, block_ms=2_000
    )
    assert len(claimed) == 1

    stale = await upstash_queue.list_stale(idle_ms=0, count=10)
    assert len(stale) >= 1
    msg_ids = [entry["message_id"] for entry in stale]

    reclaimed = await upstash_queue.reclaim(
        "worker-b", msg_ids, min_idle_time=0
    )
    assert len(reclaimed) == 1

    # Cleanup: ack so nothing lingers in the pending list.
    await upstash_queue.ack(reclaimed[0][0])
