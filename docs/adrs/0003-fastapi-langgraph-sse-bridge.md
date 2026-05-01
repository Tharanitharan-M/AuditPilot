# ADR-0003: FastAPI ↔ LangGraph ↔ Vercel AI SDK 6 SSE Bridge

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS FR-057, FR-058, NFR-003; PLAN.md chunks 2.7, 4.1–4.2

---

## Context and Problem Statement

AuditOrchestrator runs in Python (LangGraph on FastAPI, Cloud Run). The frontend is Next.js 15 consuming Vercel AI SDK 6. The AI SDK 6 client (`useChat`) expects a specific SSE wire format — `UIMessage` parts streamed with the header `x-vercel-ai-ui-message-stream: v1` — and renders tool calls, text deltas, and finish events natively when that format is respected.

LangGraph exposes events via the async `astream_events()` method. These events do not match the AI SDK 6 wire format. A bridge layer is required.

The problem: design the bridge with the least possible abstraction, highest type safety, and full observability, while keeping latency under 3 000 ms to first token (NFR-003).

---

## Decision

**FastAPI `StreamingResponse` endpoint at `/chat` reads LangGraph `astream_events()`, maps events to Vercel AI SDK 6 `UIMessage` SSE format, and emits them with the `x-vercel-ai-ui-message-stream: v1` header.**

No intermediary service. No WebSocket. No polling. One endpoint, one stream, one header.

The mapping table from LangGraph event to AI SDK 6 part type:

| LangGraph event type | AI SDK 6 UIMessage part | Notes |
|---|---|---|
| `on_chat_model_stream` | `type: "text-delta"` | Streamed token by token |
| `on_tool_start` | `type: "tool-call"` | Contains `toolCallId`, `toolName`, `args` |
| `on_tool_end` | `type: "tool-result"` | Contains `toolCallId`, `result` |
| `on_chain_end` (final) | `type: "finish"` | Contains `finishReason: "stop"` |
| `on_chain_end` (interrupt) | `type: "finish"` | Contains `finishReason: "stop"`, signals HITL pause |

The frontend `useChat` hook's `onToolCall` handler renders each `tool-call` / `tool-result` pair as an expandable Tool card (FR-059 in PRD §6.1).

---

## Rationale

### Why SSE over WebSocket

| Criterion | SSE | WebSocket |
|---|---|---|
| Server → client streaming | Yes (native) | Yes |
| Client → server messaging | No (separate POST) | Yes (bidirectional) |
| Reconnection | Browser-native auto-reconnect | Manual |
| Proxy / CDN compatibility | Excellent (HTTP/1.1 + HTTP/2) | Requires upgrade handling |
| Vercel AI SDK 6 support | First-class native | Experimental / manual |
| Firewall compatibility | No issues (HTTP) | Some enterprise firewalls block WS |

AuditPilot's interaction pattern is request → stream response → done. The client never needs to push mid-stream. SSE is the correct choice. WebSocket adds bidirectional complexity that the use case does not need.

### Why FastAPI `StreamingResponse` over LangGraph Platform (LangGraph Cloud)

LangGraph Platform is the hosted version of the LangGraph server — it handles SSE streaming, state persistence, A2A routing, and deployment automatically. The reason not to use it:

1. **Cost.** LangGraph Platform is a paid commercial service. AuditPilot must operate at $0/month (SRS CON-005). The free tier does not exist for production use.
2. **Vendor lock-in.** A portfolio project that relies on a proprietary hosting layer cannot be self-hosted by forks. The open-source value proposition requires a fully self-hostable backend.
3. **Pedagogical value.** Building the bridge manually demonstrates the AI SDK 6 wire format, LangGraph's event API, and FastAPI streaming — three concepts central to any senior AI engineering work. Using LangGraph Platform hides all of them, which weakens the project's value as a reference architecture.

### Why Vercel AI SDK 6 UIMessage format (not a custom format)

The AI SDK 6 `UIMessage` SSE format is versioned (the `v1` header) and consumed natively by `useChat` on the frontend. Every AI Elements component (streaming text, tool call cards, progress indicators) renders correctly when the wire format matches. Rolling a custom format means re-implementing every rendering behavior that AI SDK 6 already provides.

The `x-vercel-ai-ui-message-stream: v1` header is the handshake. Without it, `useChat` treats the stream as a legacy data stream and loses typed tool-call rendering.

### HITL signaling over SSE

When the orchestrator hits a `interrupt()` node, LangGraph emits `on_chain_end` with the interrupt payload. The bridge maps this to a `finish` part with a custom `interruptReason` field. The frontend receives the finish event, renders the HITL state (Pending Actions queue), and stops streaming. When the user approves, the frontend POSTs to `/chat/resume` with the `thread_id` and `resume_payload`, which calls `Command(resume=...)` on the LangGraph graph. A new SSE stream opens from the resumed checkpoint.

---

## Consequences

### Positive
- Zero intermediary services; one FastAPI endpoint is the entire bridge
- Typed end-to-end: `AuditPilotState` (Pydantic v2) → LangGraph events → `UIMessage` parts (AI SDK 6) → `useChat` (Zod-validated on the frontend)
- Full observability: every LangGraph event is also emitted to Langfuse before being forwarded to the client
- Self-hostable: any fork that runs Cloud Run + Vercel gets the full streaming experience
- HITL over SSE is elegant: the same stream that delivers tokens also delivers the interrupt signal

### Negative
- The mapping table must stay in sync with AI SDK 6 UIMessage spec changes; Vercel has shipped breaking changes to the wire format between major versions
- `astream_events()` API in LangGraph is v2 (the recommended version); upgrading LangGraph must not break the event schema
- CORS configuration on the FastAPI endpoint must be explicitly set to allow the Vercel frontend origin; misconfiguration silently breaks streaming in some browsers

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **WebSocket bidirectional stream** | Bidirectional messaging is not needed. SSE is simpler, proxy-compatible, and first-class in AI SDK 6. |
| **Long-polling** | Latency is unacceptable for real-time token streaming. P50 first-token NFR-003 (≤ 3 000 ms) cannot be met. |
| **LangGraph Platform (hosted)** | Paid commercial service; violates $0/month constraint (SRS CON-005). Removes self-hostability and learning signal. |
| **gRPC server streaming** | Cross-language complexity. Requires gRPC client in Next.js (not native). No AI SDK 6 integration. |
| **Intermediary Node.js proxy** | Adds a third service and a second hop. Increases latency, complexity, and failure surface with no benefit. |
| **GraphQL subscriptions** | Heavyweight for a streaming chat interaction. No AI SDK 6 integration. |

---

