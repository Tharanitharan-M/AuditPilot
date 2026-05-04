"""Pydantic v2 schemas for the job queue wire format.

Every message on ``auditpilot:jobs`` and ``auditpilot:jobs:dlq`` is a
:class:`JobMessage`. The discriminator is ``type`` (enum) so dispatchers
can switch on one field; the opaque ``payload`` dict carries type-specific
data validated by the handler, not the queue.

Refs: ADR-0010 "Job types and stream layout", system-design 11.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class JobType(str, Enum):
    """The five job kinds in v1 (ADR-0010 Job types)."""

    QUESTIONNAIRE_FILL = "questionnaire.fill"
    POLICY_FINALIZE = "policy.finalize"
    MOCK_AUDIT_RUN = "mock_audit.run"
    DRIFT_SCAN = "drift.scan"
    EVIDENCE_COMPACT = "evidence.compact"


class JobStatus(str, Enum):
    """Observed status of a job from the caller's point of view."""

    QUEUED = "queued"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


class JobMessage(BaseModel):
    """A single job as serialised on the Redis stream.

    Every field except ``payload`` is a primitive string so XADD accepts
    the message as-is without nested encoding tricks. ``payload`` is JSON
    on the wire and re-hydrated to a dict by ``JobQueue.claim_next``.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: JobType
    user_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    attempt: int = Field(default=1, ge=1)
    payload: dict[str, object] = Field(default_factory=dict)


class JobResult(BaseModel):
    """The outcome returned by ``JobQueue.enqueue``."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    deduplicated: bool = False
