# ADR-0001: LangGraph 1.x as the Agent Orchestration Runtime

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS CON-003, CON-007; PLAN.md chunks 2.4, 2.5

---

## Context and Problem Statement

AuditPilot requires an agent orchestration runtime that can:
- Manage a stateful, multi-step workflow across evidence collection, control mapping, policy drafting, and a mock readiness challenge
- Support human-in-the-loop interruption at specific graph nodes
- Persist workflow state across restarts (for long-running scans and HITL pauses)
- Call MCP servers as tools from orchestrator nodes
- Communicate with a remote AdversarialAuditor process via A2A v1.0
- Emit OpenTelemetry traces to Langfuse for observability

Nine frameworks were evaluated between March and April 2026.

---

## Decision

**Use LangGraph 1.x as the orchestration runtime. Use Pydantic AI 1.x for individual agent node definitions.**

LangGraph handles the outer loop: graph topology, state machine, checkpointing, HITL via `interrupt()` + `Command(resume=)`, and parallel node execution. Pydantic AI handles individual nodes: typed inputs, typed outputs, dependency injection, and structured LLM output parsing.

---

## Rationale

### Production proof points (asymmetric advantage)

LangGraph has 30+ independently attested named production deployments as of April 2026:

- **Klarna** — agent platform powering customer support; claimed $60M+ annualised savings (Q3 2025 earnings call)
- **Uber** — internal developer tooling
- **LinkedIn** — job recommendation and content moderation pipelines
- **JPMorgan Chase** — internal research automation
- **BlackRock** — Aladdin Copilot, $11T AUM under management
- **Replit** — code generation agent
- **Cisco Outshift** — security automation
- **Elastic** — observability copilot
- **AppFolio** — property management AI
- **Vanta** — compliance automation (notable: the commercial incumbent in AuditPilot's problem space uses LangGraph)

Google ADK, the primary alternative evaluated, has roughly four named external production deployments (Comcast Xfinity Assistant, PayPal, Geotab, Genpact) plus Google internal dogfood. The asymmetry is approximately 10:1 in independently-attested breadth.

### Industry adoption

LangGraph appears in approximately 25–30% of 2026 AI Engineer and AI Software Engineer job descriptions based on a manual sample of 80+ postings from LinkedIn, Greenhouse, and Lever in Q1 2026. ADK appears in under 1% of the same sample, concentrated in Google-ecosystem roles. For an open-source reference architecture meant to be widely forkable, LangGraph has the broadest industry alignment in the agent-orchestration space.

### Stability commitment

LangGraph 1.0 reached GA in October 2025 with an explicit no-breaking-changes commitment until 2.0. ADK 1.x had 31 minor releases in 12 months with breaking changes between minors. ADK 2.0 is in Beta with explicit breaking changes from 1.x; Google's own migration docs warn "Do NOT use with ADK 1.x databases or sessions — they are incompatible." Building a 6-week portfolio on ADK means betting on framework stability that does not exist.

### Native protocol support

LangGraph provides:
- **MCP support** via `langchain-mcp-adapters` (GA Q1 2026): `MultiServerMCPClient` wraps MCP server tools directly as LangGraph-compatible tool callables
- **A2A v1.0 support** via `langgraph-api >= 0.4.21`: exposes a `/a2a/{assistant_id}` endpoint on the LangGraph server that speaks the A2A protocol natively
- **HITL** via `interrupt()` + `Command(resume=)` + `PostgresSaver` — the canonical pattern referenced in LangGraph's official docs and in multiple 2026 engineering blog posts

### Pydantic AI for node definitions

Pydantic AI 1.0 reached GA on September 4, 2025. It is built by the same team as Pydantic v2 (which is the validation backbone of FastAPI, the OpenAI SDK, the Anthropic SDK, and LangChain itself). AuditPilot uses Pydantic v2 as a "spinal cord" throughout — FastAPI models, MCP tool schemas, LangGraph state, structured LLM outputs. Using Pydantic AI for agent definitions keeps the entire backend type-safe under a single validation model.

Production case studies for Pydantic AI: MindsDB (10x performance improvement over LangChain), Datalayer (chosen after evaluating 10 frameworks), Sophos SecOps. Thoughtworks Technology Radar 2026 places it in the Adopt ring.

---

## Consequences

### Positive
- LangGraph has 25–30% industry penetration in the agent-orchestration space
- 30+ named production deployments provide a strong evidence base for design decisions
- `interrupt()` + `Command(resume=)` + `PostgresSaver` is best-in-class HITL in 2026 — the canonical 2026 implementation pattern
- Native MCP and A2A support removes the need for custom glue code
- Pydantic AI gives typed contracts for every agent node, matching the end-to-end Pydantic v2 discipline

### Negative
- LangGraph is Python-only; the frontend is Next.js 15 (TypeScript), requiring the FastAPI SSE bridge documented in ADR-0003
- LangGraph adds abstraction above raw Python asyncio; debugging graph execution requires Langfuse traces rather than `print()` statements
- Upgrading to LangGraph 2.0 (when it arrives) will require a migration; the no-breaking-changes commitment applies until that version

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Google ADK 1.31.x** | ADK 2.0 is a breaking Beta; ADK 1.x had 31 minor releases with breakage between them. ~4 named external deployments vs. LangGraph's ~30. Appears in <1% of 2026 AI Engineer JDs. ADK was kept as the A2A protocol inspiration — we use A2A v1.0 as the cross-process protocol between AuditOrchestrator and AdversarialAuditor, giving us the protocol claim without the framework lock-in. |
| **LangChain (bare)** | LangChain is the parent ecosystem; LangGraph is the production-grade orchestration subset. Using bare LangChain in 2026 reads as legacy. LangGraph is the correct answer. |
| **OpenAI Agents SDK** | Provider-locked to OpenAI. Incompatible with our LiteLLM multi-provider routing. The `handoffs` pattern conflicts with the single-writer state design documented in ADR-0002. |
| **AutoGen / AG2** | Officially in maintenance mode since September 2025 following the Microsoft Agent Framework announcement. Multiple 2026 reviews describe it as "suitable for academic research, not enterprise production." |
| **CrewAI** | The "crew" mental model is the peer-agent pattern that Cognition AI's "Don't Build Multi-Agents" (June 2025) explicitly warns against. Clean API, wrong architecture for our single-writer design. |
| **Microsoft Agent Framework** | Microsoft ecosystem. Our backend is Python on Cloud Run. No reason to add cross-language complexity. |
| **Mastra** | TypeScript-only. Our backend is Python (FastAPI on Cloud Run). |
| **Smolagents** | Hugging Face minimalist framework. Research-flavored; not production-grade for a compliance use case. |
| **Amazon Bedrock AgentCore** | AWS lock-in. Our deployment target is Cloud Run + Vercel. Weaker free tier than our chosen stack. |

---

