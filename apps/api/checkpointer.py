"""
LangGraph checkpointer wiring
=============================
Exposes async context managers that yield a ready-to-use checkpointer for the
orchestrator graph. Production uses `AsyncPostgresSaver`; tests use LangGraph's
`InMemorySaver`. Both satisfy `BaseCheckpointSaver` so callers can swap them
transparently.

Pre-flight verification note (2026-05-04):
  langgraph-checkpoint-postgres 3.0.5 ships as a separate package from
  langgraph 1.1.10. Both imports resolve; `AsyncPostgresSaver.from_conn_string`
  is an async context manager factory. Chunk 2.6 acceptance: run the graph
  twice with the same thread_id; second run resumes from checkpoint.

Refs: PLAN.md chunk 2.6; ADR-0001; ADR-0007; system-design 4, 11.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def postgres_checkpointer(
    conn_string: str,
    *,
    pipeline: bool = False,
    setup: bool = True,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Yield a ready `AsyncPostgresSaver` backed by the given Postgres URL.

    The Drizzle migration at ``apps/api/db/migrations/0001_langgraph_checkpoints.sql``
    provisions the four checkpoint tables. This function still calls
    ``.setup()`` (idempotent) so environments that have not yet run the
    Drizzle migration (fresh Neon branch, local dev) come up cleanly.
    """

    async with AsyncPostgresSaver.from_conn_string(
        conn_string, pipeline=pipeline
    ) as checkpointer:
        if setup:
            await checkpointer.setup()
        yield checkpointer


def memory_checkpointer() -> BaseCheckpointSaver:
    """Return an in-memory checkpointer suitable for unit tests.

    `InMemorySaver` implements `BaseCheckpointSaver`, so a test graph wired
    with it verifies the same resume-from-checkpoint contract that production
    depends on from `AsyncPostgresSaver`, without requiring a live Postgres.
    """

    return InMemorySaver()


__all__ = [
    "memory_checkpointer",
    "postgres_checkpointer",
]
