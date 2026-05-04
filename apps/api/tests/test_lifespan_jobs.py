"""End-to-end lifespan test: FastAPI starts → JobQueue + worker run → enqueue → handler fires.

Proves the Sprint 2 exit criterion "JobQueue accepts and processes a
smoke-test job" under the real app lifespan, not just an isolated queue
fixture. Uses fakeredis as the transport and a captured handler map so
the test can assert the handler was called with the right payload.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.jobs.schemas import JobMessage, JobType

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


async def test_lifespan_starts_worker_which_processes_an_enqueued_job() -> None:
    """Mount app with lifespan, enqueue a job, assert the handler fires."""

    from apps.api import main as main_module
    from apps.api.jobs.queue import JobQueue

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    async def _close_noop() -> None:
        pass

    fake_redis.aclose = _close_noop  # type: ignore[method-assign]

    handler_calls: list[JobMessage] = []

    async def capture_drift(message: JobMessage) -> None:
        handler_calls.append(message)

    with (
        patch.object(main_module, "_redis_client_factory", lambda _s: fake_redis),
        patch.object(
            main_module,
            "_job_handlers_factory",
            lambda: {JobType.DRIFT_SCAN: capture_drift},
        ),
    ):
        # ASGITransport does not run lifespan — drive it manually so the
        # worker coroutines actually spawn.
        async with main_module.lifespan(main_module.app):
            transport = ASGITransport(
                app=main_module.app, raise_app_exceptions=False
            )
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get("/health")
                assert resp.status_code == 200

                queue: JobQueue = main_module.get_job_queue()
                assert queue._redis is fake_redis  # type: ignore[attr-defined]

                await queue.enqueue(
                    JobMessage(
                        type=JobType.DRIFT_SCAN,
                        user_id="user_lifespan",
                        idempotency_key="idem-lifespan",
                        payload={"driver": "lifespan-smoke"},
                    )
                )

                for _ in range(60):
                    if handler_calls:
                        break
                    await asyncio.sleep(0.05)

    # Outside the lifespan manager the shutdown path must have cancelled
    # and awaited all background tasks.
    assert main_module._background_tasks == []
    assert len(handler_calls) == 1
    assert handler_calls[0].payload == {"driver": "lifespan-smoke"}
