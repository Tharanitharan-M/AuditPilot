"""Worker + reclaim loop tests (chunk 2.11).

These exercise the real asyncio scheduler against ``fakeredis`` so the
exit criterion for Sprint 2 (\"JobQueue accepts and processes a smoke-test
job\") has real-loop coverage, not just the synchronous ``process_once``
unit tests in ``test_jobs_queue``.
"""

from __future__ import annotations

import asyncio

import fakeredis
import pytest

from apps.api.jobs.exceptions import RetryableError
from apps.api.jobs.queue import JobQueue
from apps.api.jobs.schemas import JobMessage, JobType
from apps.api.jobs.worker import (
    _reclaim_once,
    make_dispatcher,
    reclaim_stale_messages,
    run_worker,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def queue():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    q = JobQueue(
        redis,
        stream="auditpilot:worker:test",
        group="worker-test",
        dlq_stream="auditpilot:worker:test:dlq",
    )
    await q.ensure_group()
    yield q


async def test_run_worker_processes_enqueued_job_and_exits_on_cancel(queue: JobQueue) -> None:
    seen: list[JobMessage] = []

    async def drift_handler(message: JobMessage) -> None:
        seen.append(message)

    dispatcher = make_dispatcher({JobType.DRIFT_SCAN: drift_handler})

    stop = asyncio.Event()
    worker = asyncio.create_task(
        run_worker(queue, dispatcher, consumer="t1", poll_block_ms=50, stop_event=stop)
    )

    await queue.enqueue(
        JobMessage(
            type=JobType.DRIFT_SCAN,
            user_id="u1",
            idempotency_key="idem-a",
            payload={"note": "hello"},
        )
    )

    # Give the worker up to 2 seconds to claim + dispatch.
    for _ in range(40):
        if seen:
            break
        await asyncio.sleep(0.05)

    stop.set()
    await asyncio.wait_for(worker, timeout=2.0)

    assert len(seen) == 1
    assert seen[0].payload == {"note": "hello"}


async def test_run_worker_surfaces_unknown_type_as_fatal(queue: JobQueue) -> None:
    handler_calls: list[JobMessage] = []

    async def policy_handler(message: JobMessage) -> None:
        handler_calls.append(message)

    dispatcher = make_dispatcher({JobType.POLICY_FINALIZE: policy_handler})

    # Enqueue a DRIFT_SCAN job but only register a POLICY_FINALIZE handler.
    await queue.enqueue(
        JobMessage(
            type=JobType.DRIFT_SCAN,
            user_id="u1",
            idempotency_key="idem-b",
        )
    )

    stop = asyncio.Event()
    worker = asyncio.create_task(
        run_worker(queue, dispatcher, consumer="t1", poll_block_ms=50, stop_event=stop)
    )
    # Let the worker process one poll cycle.
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(worker, timeout=2.0)

    assert handler_calls == []
    dlq_entries = await queue._redis.xrange(queue.dlq_stream)  # type: ignore[attr-defined]
    assert len(dlq_entries) == 1
    _, fields = dlq_entries[0]
    assert "FatalError" in fields["dlq_reason"]


async def test_reclaim_once_retries_abandoned_message(queue: JobQueue) -> None:
    job = JobMessage(
        type=JobType.DRIFT_SCAN,
        user_id="u1",
        idempotency_key="idem-c",
    )
    await queue.enqueue(job)

    # Original worker claims the job but never acks (simulated crash).
    claimed = await queue.claim_next("crashed-worker", count=1, block_ms=50)
    assert len(claimed) == 1

    handled: list[JobMessage] = []

    async def drift_handler(message: JobMessage) -> None:
        handled.append(message)

    dispatcher = make_dispatcher({JobType.DRIFT_SCAN: drift_handler})

    # Nudge idle time past 1ms so fakeredis's IDLE filter picks the message up.
    await asyncio.sleep(0.01)
    reclaimed_count = await _reclaim_once(
        queue,
        dispatcher,
        consumer_name="recovery-worker",
        idle_threshold_ms=1,
    )

    assert reclaimed_count == 1
    assert len(handled) == 1
    assert handled[0].idempotency_key == "idem-c"

    # The reclaim path also acks on success, so the stream is drained.
    still_claimable = await queue.claim_next("fresh-worker", count=1, block_ms=50)
    assert still_claimable == []


async def test_reclaim_once_retries_on_retryable_handler_error(queue: JobQueue) -> None:
    job = JobMessage(
        type=JobType.DRIFT_SCAN,
        user_id="u1",
        idempotency_key="idem-d",
    )
    await queue.enqueue(job)
    await queue.claim_next("crashed-worker", count=1, block_ms=50)

    async def flaky_handler(message: JobMessage) -> None:
        raise RetryableError("simulated 429")

    dispatcher = make_dispatcher({JobType.DRIFT_SCAN: flaky_handler})
    await asyncio.sleep(0.01)
    await _reclaim_once(
        queue,
        dispatcher,
        consumer_name="recovery-worker",
        idle_threshold_ms=1,
    )

    # Reclaim hit the retry path → a fresh copy should be claimable with attempt=2.
    fresh = await queue.claim_next("fresh-worker", count=1, block_ms=200)
    assert len(fresh) == 1
    _, retried = fresh[0]
    assert retried.attempt == 2


async def test_reclaim_stale_messages_periodic_task_exits_on_cancel(queue: JobQueue) -> None:
    dispatcher = make_dispatcher({})
    stop = asyncio.Event()
    task = asyncio.create_task(
        reclaim_stale_messages(
            queue,
            dispatcher,
            interval_seconds=0.05,
            idle_threshold_ms=1_000,
            stop_event=stop,
        )
    )
    # Let the loop spin twice, then stop.
    await asyncio.sleep(0.12)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)


async def test_run_worker_swallows_non_job_errors_without_dying(queue: JobQueue) -> None:
    """A transient XREADGROUP exception should not kill the worker loop."""

    original_xreadgroup = queue._redis.xreadgroup  # type: ignore[attr-defined]
    call_count = 0

    async def flaky_xreadgroup(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("simulated network blip")
        return await original_xreadgroup(*args, **kwargs)

    queue._redis.xreadgroup = flaky_xreadgroup  # type: ignore[attr-defined]

    seen: list[JobMessage] = []

    async def drift_handler(message: JobMessage) -> None:
        seen.append(message)

    dispatcher = make_dispatcher({JobType.DRIFT_SCAN: drift_handler})
    stop = asyncio.Event()
    worker = asyncio.create_task(
        run_worker(queue, dispatcher, consumer="t1", poll_block_ms=50, stop_event=stop)
    )

    await queue.enqueue(
        JobMessage(
            type=JobType.DRIFT_SCAN,
            user_id="u1",
            idempotency_key="idem-transient",
        )
    )

    for _ in range(80):
        if seen:
            break
        await asyncio.sleep(0.05)

    stop.set()
    await asyncio.wait_for(worker, timeout=5.0)

    assert seen, "worker must recover from the simulated blip and still process the job"
    assert call_count >= 2
