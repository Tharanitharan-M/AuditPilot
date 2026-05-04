"""Background job plumbing for AuditPilot.

See ADR-0010 for the full design rationale. The public surface is:

- ``JobMessage`` / ``JobResult`` — Pydantic v2 schemas on the wire.
- ``JobType`` — enum of the five v1 job kinds.
- ``RetryableError`` / ``FatalError`` / ``BudgetExceededError`` — handler
  signals that drive the retry-vs-DLQ decision.
- ``JobQueue`` — thin wrapper over Redis Streams with idempotency,
  exponential-backoff retry, and a dead-letter stream.
- ``make_redis_client`` — factory that returns a redis-py-compatible
  async client for whichever URL scheme ``settings.redis_url`` uses
  (``rediss://`` / ``redis://`` TCP or ``https://`` Upstash REST).
"""

from apps.api.jobs.client import RedisLike, UpstashRestRedis, make_redis_client
from apps.api.jobs.exceptions import (
    BudgetExceededError,
    FatalError,
    RetryableError,
)
from apps.api.jobs.queue import DEFAULT_RETRY_DELAYS_SECONDS, JobQueue
from apps.api.jobs.schemas import JobMessage, JobResult, JobStatus, JobType
from apps.api.jobs.worker import (
    make_dispatcher,
    reclaim_stale_messages,
    run_worker,
)

__all__ = [
    "BudgetExceededError",
    "DEFAULT_RETRY_DELAYS_SECONDS",
    "FatalError",
    "JobMessage",
    "JobQueue",
    "JobResult",
    "JobStatus",
    "JobType",
    "RedisLike",
    "RetryableError",
    "UpstashRestRedis",
    "make_dispatcher",
    "make_redis_client",
    "reclaim_stale_messages",
    "run_worker",
]
