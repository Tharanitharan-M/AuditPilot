"""
LangGraph state schema — AuditPilotState
========================================
Single Pydantic v2 model that travels across every LangGraph node in the
orchestrator graph. Every node reads this state; the orchestrator (and only
the orchestrator) writes to it. AdversarialAuditor returns findings via the
A2A boundary; the orchestrator merges them into `adversarial_findings`
(single-writer invariant from ADR-0002).

The `messages` field uses the LangGraph `add_messages` reducer so every node
append is merged instead of replacing. Other fields use last-writer-wins.

Refs: PLAN.md chunk 2.4; ADR-0001 (LangGraph 1.x runtime);
ADR-0002 (three-agent architecture + single-writer rule);
system-design.md 4 (ERD), 6 (components).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    """A single evidence artifact collected from a user source system.

    Sprint 5 shape: fields align with the `evidence` DB table (migration
    0005_evidence.sql). The `embedding` field is intentionally omitted from
    the in-graph model — it is a 768-float vector too large for LangGraph
    state and is only stored in Postgres by `evidence_persistence.py`.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: str
    source_type: Literal["github", "clerk", "manual", "mock"] = Field(
        default="mock",
        description="Origin system of the evidence artifact.",
    )
    source_uri: str | None = Field(
        default=None,
        description="Canonical URI, e.g. 'github://owner/repo' or 'github://org/acme'.",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Normalized (timestamp-stripped) payload from the source API.",
    )
    content_hash: str | None = Field(
        default=None,
        description="SHA-256 of the normalized raw payload. Used as cache key.",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Wall-clock time the evidence was collected.",
    )
    # Sprint 5 — bookkeeping used by the persistence layer and drift-watcher.
    scan_run_id: str | None = Field(
        default=None,
        description="ID of the scan run that produced this evidence row.",
    )
    user_id: str | None = Field(
        default=None,
        description="Clerk user_id that owns this row. Set by the persistence layer.",
    )
    valid_until: datetime | None = Field(
        default=None,
        description="Optional freshness window. Sprint 9 drift-watcher re-collects past this.",
    )


class ControlAssessment(BaseModel):
    """One row of the SOC 2 TSC posture grid, grounded in NIST 800-53 controls.

    Sprint 2 skeleton; full shape and caching logic in Sprint 4 chunk 4.5.

    Refs: ADR-0013 (NIST 800-53 catalog, SOC 2 TSC mappings).
    """

    model_config = ConfigDict(extra="forbid")

    tsc_id: str
    status: Literal["passing", "failing", "partial", "unknown"] = "unknown"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    nist_800_53_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None


class Finding(BaseModel):
    """A single adversarial finding returned by AdversarialAuditor.

    Sprint 2 skeleton; full shape in Sprint 8 when AdversarialAuditor lands.

    Refs: ADR-0002 (three-agent architecture), US-019/US-020.
    """

    model_config = ConfigDict(extra="forbid")

    severity: Literal["low", "medium", "high", "critical"]
    tsc_id: str | None = None
    objection: str
    recommended_next_step: str | None = None


class HumanReviewPayload(BaseModel):
    """Typed resume payload for the HITL gate (ADR-0007).

    Sent from ``POST /chat/resume`` and delivered to the graph node via
    ``Command(resume=payload)``. The ``interrupt()`` call inside
    ``human_review_gate`` returns this as its result.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "edit", "reject"] = Field(
        description="User decision on the draft output.",
    )
    edited_content: str | None = Field(
        default=None,
        description="Populated when decision='edit'. Replaces the draft.",
        max_length=100_000,
    )
    rejection_reason: str | None = Field(
        default=None,
        description="Populated when decision='reject'. Injected into re-draft prompt.",
        max_length=2000,
    )


class PolicyDraft(BaseModel):
    """A single policy draft stored in graph state (Sprint 6 chunk 6.9)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique draft id (UUID hex).")
    policy_type: str = Field(
        description="One of 'irp', 'access_control', "
        "'change_management', 'vendor_management'.",
    )
    title: str = Field(default="")
    content: str = Field(default="", description="Markdown body with [CC*] citations.")
    version: int = Field(default=1)
    finalized: bool = Field(default=False)


POLICY_TYPES: frozenset[str] = frozenset({
    "irp",
    "access_control",
    "change_management",
    "vendor_management",
})

HITL_MAX_REJECTIONS: int = 3


class AuditPilotState(BaseModel):
    """Canonical orchestrator state.

    The Pydantic v2 shape serves three roles:
    1. In-memory value that LangGraph nodes read and write
    2. Checkpointed payload persisted by `AsyncPostgresSaver` (chunk 2.6) — so
       `model_dump()` must round-trip via `model_validate()`
    3. Source of truth for the SSE mapper (chunk 2.7) — the orchestrator
       surfaces typed parts derived from this state

    The model is NOT frozen because LangGraph nodes mutate it in place via
    `add_messages` on the `messages` reducer field. Non-reducer fields use
    last-writer-wins semantics per LangGraph's default merge behaviour.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        # extra="forbid" would reject reducer-produced scratch keys — keep the
        # default "allow" for the state model itself while every *component*
        # model (Evidence, ControlAssessment, Finding) uses extra="forbid".
        extra="ignore",
    )

    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    control_map: dict[str, ControlAssessment] = Field(default_factory=dict)
    adversarial_findings: list[Finding] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    current_step: str = Field(default="init")

    # Optional bookkeeping surfaced in traces and the SSE `finish` payload.
    user_id: str | None = None
    scan_run_id: str | None = None
    thread_id: str | None = None
    intent: str | None = None

    # Sprint 3.5 chunk 3.5.5: the user-chosen repo scope, seeded from
    # connector_scoped_repos at /chat call time. Empty list means the
    # user has not yet picked any repos; the orchestrator refuses to
    # start a readiness scan in that state (ADR-0015 default-deny).
    # Each entry is GitHub's `provider_repo_id` (numeric, string-encoded
    # for parity with the DB column).
    repo_include_list: list[str] = Field(default_factory=list)

    # Sprint 6 — policy drafting + HITL gate (ADR-0007)
    draft_policy: PolicyDraft | None = Field(
        default=None,
        description="The current policy draft awaiting HITL review.",
    )
    policy_type: str | None = Field(
        default=None,
        description="Policy type requested by the user (e.g. 'irp').",
    )
    hitl_rejection_count: int = Field(
        default=0,
        description="Consecutive rejections on current draft. "
        "Circuit breaker fires at 3.",
    )

    # Sprint 5 chunk 5.19 — ``repo_full_names`` was removed from state.
    # The mapping is now captured exclusively in the GitHub evidence
    # collector's closure (see ``make_github_evidence_collector``) so it
    # never enters the LangGraph checkpoint store. Repo names are not
    # secrets, but they are user-controlled external strings and there
    # is no graph node that reads them — keeping them out of state
    # shrinks every checkpoint row and removes a write surface.


# Intents that require a non-empty connector scope before any tool calls.
# Free chat ("free_chat" or None) never requires a scope.
SCOPE_REQUIRED_INTENTS: frozenset[str] = frozenset({"run_readiness_scan"})

# Intents that trigger the policy drafting pipeline (Sprint 6).
POLICY_DRAFT_INTENTS: frozenset[str] = frozenset({"draft_policy"})


class ScanRunValidationError(Exception):
    """Raised when an intent that requires a connector scope is invoked
    with an empty ``repo_include_list``. The /chat SSE bridge catches
    this and emits ``start`` → text → ``finish`` without any tool call
    (Sprint 3.5 chunk 3.5.5)."""


__all__ = [
    "AuditPilotState",
    "ControlAssessment",
    "Evidence",
    "Finding",
    "HITL_MAX_REJECTIONS",
    "HumanReviewPayload",
    "POLICY_DRAFT_INTENTS",
    "POLICY_TYPES",
    "PolicyDraft",
    "ScanRunValidationError",
    "SCOPE_REQUIRED_INTENTS",
]
