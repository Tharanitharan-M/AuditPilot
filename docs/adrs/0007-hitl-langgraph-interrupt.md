# ADR-0007: HITL via LangGraph `interrupt()` + `Command(resume=)` + PostgresSaver

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS FR-046–FR-050; PRD NG-4; PLAN.md chunk 6.1; ADR-0004

---

## Context and Problem Statement

AuditPilot's read-only-by-design principle (ADR-0004) requires that every AI-generated output — policy draft, gap report, questionnaire answers — be reviewed and explicitly approved by a human before it is delivered. This human-in-the-loop (HITL) step is not optional: it is the architectural mechanism that distinguishes "the AI suggested this" from "the human decided this."

The HITL implementation must:
- Pause the orchestrator workflow at a specific graph node
- Persist the paused state durably so the user can review over minutes or hours without losing progress
- Resume the workflow from the exact paused checkpoint when the user approves, edits, or rejects
- Pass the human's decision (approve / edit / reject) back to the orchestrator as typed context
- Be transparent to the user: the Pending Actions queue must show all items awaiting review

---

## Decision

**Implement HITL using LangGraph's `interrupt()` primitive, `Command(resume=)` for workflow resumption, and `PostgresSaver` as the durable state checkpointer.**

`HumanReviewGate` is a named LangGraph node that calls `interrupt()`. The graph halts. `PostgresSaver` checkpoints the full `AuditPilotState` to Postgres. When the user acts in the dashboard (Approve / Edit with new text / Reject with reason), the frontend POSTs to `/chat/resume` with the `thread_id` and a typed resume payload. FastAPI calls `Command(resume=payload)` on the LangGraph graph, which resumes from the saved checkpoint.

---

## Rationale

### Why `interrupt()` (not an async queue, not webhooks, not a separate approval service)

LangGraph `interrupt()` is the canonical HITL mechanism as of LangGraph 1.0. It is:
- **In-graph:** the HITL gate is a named node in the graph topology, visible in every Langfuse trace, not an out-of-band side channel
- **Stateful:** the full `AuditPilotState` is serialized to `PostgresSaver` at the interrupt point; the graph can resume days later from the exact checkpoint
- **Typed:** `Command(resume=payload)` carries a Pydantic-typed payload (approve / edit / reject + optional edited text + optional rejection reason); the orchestrator receives a typed object, not a raw string
- **Idempotent:** if the frontend sends the resume signal twice (network retry), `PostgresSaver` ensures the graph does not execute the resumed node twice

Alternatives that were rejected are documented below. The key insight is that `interrupt()` makes HITL a first-class graph citizen rather than an afterthought bolted on via webhook or queue.

### Why `PostgresSaver` (not `MemorySaver`, not Redis)

`MemorySaver` stores state in Python process memory. If the FastAPI process restarts between interrupt and resume — likely on Cloud Run, which scales to zero — the state is lost and the user's review session is destroyed.

`PostgresSaver` persists state to Neon Postgres (the same database used for evidence storage). The state survives process restarts, Cloud Run cold starts, and deployments. A user who starts a readiness scan at 9am, gets the HITL gate at 9:05am, goes to lunch, and comes back at 1pm to review will find their session exactly where they left it.

Redis (`RedisSaver`) is a plausible alternative but adds a sixth piece of infrastructure (Upstash Redis is already used for rate limiting). Using `PostgresSaver` consolidates state persistence on the existing Neon Postgres instance, reducing operational surface.

### Resume payload typing

The resume payload is a Pydantic v2 model:

```python
class HumanReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "edit", "reject"]
    edited_content: str | None = None   # populated when decision == "edit"
    rejection_reason: str | None = None  # populated when decision == "reject"
```

When `decision == "approve"`, the orchestrator continues with the draft as-is.
When `decision == "edit"`, the orchestrator replaces the draft with `edited_content` and continues.
When `decision == "reject"`, the orchestrator adds `rejection_reason` to the state's `rejection_reasons` list and re-drafts the policy with the reason injected into the prompt context.

All three paths are tested in `tests/test_hitl.py`.

### HITL in the Langfuse trace

Every `interrupt()` call produces an `on_chain_end` event in LangGraph's event stream. The SSE bridge (ADR-0003) maps this to a `finish` part with `finishReason: "interrupt"`. In Langfuse, the trace shows:
- Span: `AuditOrchestrator` → child span: `HumanReviewGate` → status: `INTERRUPTED`
- The interrupted span is left open until the resume signal arrives
- After resume, the span closes with `decision: "approve"` (or `"edit"` or `"reject"`) in the metadata

This means every HITL event is fully observable: when did the interrupt happen, how long the human took to review, what decision was made, and what the orchestrator did next.

---

## Consequences

### Positive
- Durable HITL: state survives Cloud Run restarts and cold starts
- Typed resume payloads: approve / edit / reject are first-class typed values, not free-text commands
- First-class observability: HITL events appear in Langfuse traces with full metadata
- In-graph gate: `HumanReviewGate` is visible in the graph topology and every trace
- Re-draft loop is built in: rejection flows back to the orchestrator with the reason as context

### Negative
- `PostgresSaver` adds latency on state writes (estimated 20–50ms per checkpoint); acceptable given the human-paced nature of review
- Long interrupt durations (hours/days) require that `PostgresSaver` rows are not garbage-collected; must set a TTL policy on the `checkpoints` table
- The resume endpoint `/chat/resume` must be authenticated (same session as the original `/chat` request) to prevent unauthorized workflow resumption
- Testing HITL flows requires a running Postgres instance; unit tests use a mock checkpointer

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Async queue (SQS, Upstash Queue)** | The queue holds the resume signal but not the graph state. The graph must be re-hydrated from a separate store on every resume. `PostgresSaver` handles both: state storage and resume coordination in one primitive. |
| **Webhook-based HITL** | The external system receives a webhook when HITL is needed and POSTs back to resume. No built-in state persistence; the graph state must be managed separately. More moving parts than `interrupt()` + `PostgresSaver`. |
| **Separate approval microservice** | Overkill for a two-agent system. The approval service would need its own state management, its own database table, and its own API surface — all of which `PostgresSaver` + the Pending Actions queue already provide. |
| **`MemorySaver`** | In-process only. State lost on Cloud Run restart. Unacceptable for a user-facing HITL flow where review may take minutes to hours. |
| **Redis (`RedisSaver`)** | Plausible but adds a sixth piece of stateful infrastructure. `PostgresSaver` consolidates on the existing Neon Postgres instance. |
| **No HITL (fully autonomous delivery)** | Violates ADR-0004 (read-only-by-design) and the AICPA UPAct principle that assurance actions require human professional judgment. Not an option. |

---

