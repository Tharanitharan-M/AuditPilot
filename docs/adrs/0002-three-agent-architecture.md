# ADR-0002: Three-Agent Architecture

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS CON-003; PRD 6.1; PLAN.md chunks 2.5, 6.1–6.5, 8.1–8.6

---

## Context and Problem Statement

The original AuditPilot design had eight LLM-powered agents in a peer topology:

- AuditOrchestrator
- EvidenceCollector (with four sub-agents: GitHub, Gmail, Slack, Calendar)
- ControlMapper
- PolicyDrafter
- QuestionnaireAgent
- DriftWatcher
- AdversarialAuditor

Between December 2024 and June 2025, three independent authoritative sources published guidance specifically warning against this peer-agent pattern:

1. Anthropic, "Building Effective Agents" (Schluntz and Zhang, December 2024)
2. Cognition AI, "Don't Build Multi-Agents" (Walden Yan, June 2025)
3. OpenAI orchestration guide (2026)

The question was whether to keep the eight-agent design (more surface area, more named services) or collapse to the minimum viable topology (cleaner architecture, defensible against the published authority guidance).

---

## Decision

**Collapse to three agents. AuditOrchestrator (single writer), AdversarialAuditor (read-only critic, separate process), HumanReviewGate (LangGraph `interrupt()` node).**

The four evidence collectors become four MCP tool calls made concurrently from the orchestrator via `asyncio.gather`. ControlMapper, PolicyDrafter, QuestionnaireAgent, and DriftWatcher become orchestrator steps (LangGraph nodes), not separate LLM-powered agents.

---

## Rationale

### Authority citations

**Anthropic, "Building Effective Agents" (Schluntz and Zhang, December 2024):**

> "Consistently, the most successful implementations weren't using complex frameworks or specialized libraries. Instead, they were building with simple, composable patterns... we recommend finding the simplest solution possible and only increasing complexity when needed."

**Cognition AI, "Don't Build Multi-Agents" (Walden Yan, June 2025):**

> "In 2025, running multiple agents in collaboration only results in fragile systems. The decision-making ends up being too dispersed and context isn't able to be shared thoroughly enough between the agents."

The April 2026 Cognition AI follow-up endorses the single-writer pattern with read-only specialist subagents — exactly the final design.

**OpenAI orchestration guide (2026):**

> "Start with one agent whenever you can. Add specialists only when they materially improve capability isolation, policy isolation, prompt clarity, or trace legibility. Splitting too early creates more prompts, more traces, and more approval surfaces without necessarily making the workflow better."

### What the eight-agent design was actually doing wrong

1. **Redundant LLM calls.** Each agent had its own system prompt and its own reasoning step. ControlMapper calling PolicyDrafter and PolicyDrafter calling QuestionnaireAgent meant three LLM context windows holding largely the same information about the current control state. Every handoff was a lossy compression step.

2. **Dispersed decision-making.** Each agent made local decisions without full context. When the ControlMapper said "CC6.1 is PASSING," it had no visibility into what the PolicyDrafter would write based on that assessment. The orchestrator that held the full picture was not making decisions.

3. **State management complexity.** Eight agents writing to a shared LangGraph state is the multi-writer problem that LangGraph's own documentation warns against. Single writer to state is the canonical correct pattern.

4. **Trace fragmentation.** Eight agents produce eight separate Langfuse traces that must be correlated manually. One orchestrator produces one trace with sub-spans.

### What the three-agent design preserves

Every architectural property that matters in production is preserved:

| Property               | Eight-agent design                   | Three-agent design                                                          |
| ---------------------- | ------------------------------------ | --------------------------------------------------------------------------- |
| Parallel execution     | Four evidence sub-agents in parallel | Four MCP tool calls via `asyncio.gather` in parallel                        |
| Multi-agent claim      | Eight agents                         | Two LLM-powered agents in two separate processes communicating via A2A v1.0 |
| Separation of concerns | Eight dedicated agents               | Five MCP servers each owning a focused tool responsibility                  |
| HITL                   | Ad hoc in each agent                 | First-class `interrupt()` node in the graph                                 |
| A2A protocol           | All agents                           | Orchestrator → AdversarialAuditor cross-process call                        |
| Observability          | Fragmented across 8 traces           | One orchestrator trace with sub-spans                                       |

**The collapse from eight to three removes all the costs while keeping all the portfolio claims.**

### Why AdversarialAuditor stays as a separate agent

AdversarialAuditor is in a genuinely different security domain: it must not have access to the orchestrator's reasoning context when forming objections (context contamination would make the challenge worthless). It runs in a separate Cloud Run service to enforce process-level isolation. The A2A v1.0 protocol boundary between them is load-bearing — it is what makes the "two processes, two contexts, one protocol" architecture claim true and defensible.

---

## Consequences

### Positive

- Single writer to LangGraph state eliminates multi-writer conflicts
- One Langfuse trace per session; sub-spans for every MCP call; no manual correlation
- Four concurrent MCP tool calls via `asyncio.gather` preserves parallelism without sub-agent overhead
- The AdversarialAuditor → AuditOrchestrator A2A boundary is the real cross-agent story, clean and intentional
- Prompt count drops from eight system prompts to two (orchestrator + adversarial); easier to tune, version, and eval

### Negative

- AuditOrchestrator becomes the single most complex file in the codebase; must be well-tested
- Adding a capability that genuinely needs a separate LLM context now requires a new ADR, which may slow future iterations
- The "eight-agent" framing in earlier project notes must be corrected; the accurate description is "two LLM-powered agents in two processes communicating via A2A v1.0"

---

## Alternatives Considered

| Option                                                                     | Why rejected                                                                                                                                                                                                                                      |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Eight-agent peer topology**                                              | Exactly the pattern all three authority sources cited above warn against. More prompts, more traces, more handoff failures, dispersed decision-making. No architectural gain justifies the cost.                                                  |
| **Five-agent intermediate** (orchestrator + 3 domain agents + adversarial) | Still has the multi-writer problem and fragmented traces. The collapse should be complete; halfway measures give half the problems without half the benefits.                                                                                     |
| **OpenAI Swarm-style handoffs**                                            | Swarm uses stateless handoffs where control transfers between agents. Incompatible with the single-writer LangGraph state design. Also, Swarm is an experimental framework, not production-grade.                                                 |
| **Separate microservice per agent**                                        | Microservice-per-agent is the right answer for very large teams. For a two-month solo build, it creates deployment complexity that overwhelms the feature work. AdversarialAuditor is the one justified separate service (for context isolation). |

---
