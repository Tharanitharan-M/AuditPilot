# ADR-0009: Observability Stack

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS NFR-011, NFR-012; PRD §4.3; PLAN.md Sprint 9; ADR-0008

---

## Context and Problem Statement

Production engineering teams in 2026 ship observability in sprint one, not sprint twelve. The standard paid combination is Datadog (metrics + logs + APM) + Sentry (errors) + PagerDuty (alerting), at roughly $200–500/month for a small team. AuditPilot must replicate the same coverage at $0/month.

Additionally, AuditPilot is an LLM-powered system. General-purpose observability tools (Datadog, Grafana) do not observe the interior of LLM calls: token counts, prompt versions, model latency per call, retrieval quality, eval scores. A separate LLM observability layer is required.

The question: what combination of tools provides complete observability across LLM calls, backend errors, product analytics, infrastructure metrics, web vitals, and uptime — at $0/month?

---

## Decision

**Seven-layer observability stack, all free-tier:**

| Layer | Tool | Free tier | What it covers |
|---|---|---|---|
| **LLM observability** | Langfuse Cloud Hobby | 50,000 traces/month | Agent traces, prompt versions, datasets, eval scoring, token costs |
| **Backend errors** | Sentry Python SDK | 5,000 errors/month | FastAPI tracebacks, source-mapped stacks, performance monitoring |
| **Frontend errors** | Sentry Browser SDK | 5,000 errors/month (shared) | JavaScript exceptions, source-mapped stacks, auto-correlated with session replay |
| **Product analytics + session replay** | PostHog Cloud Free | 1,000,000 events/month; 5,000 replays/month | User funnels, retention, replay correlated with Sentry errors |
| **Infrastructure metrics** | Grafana Cloud Free | 10,000 series, 50 GB logs/month | Cloud Run latency, throughput, error rate from OTel |
| **Web analytics + vitals** | Vercel Analytics + Speed Insights | Free with Hobby | Page views, referrers, LCP/FID/CLS/TTFB per page |
| **Uptime + status page** | Better Stack Free | 10 monitors, public status page | `/health` monitor; `status.auditpilot.dev`; downtime alerts |

**Total: $0/month.**

---

## Rationale

### Why Langfuse (not LangSmith, not Arize Phoenix, not Pydantic Logfire)

**Langfuse** is open-source (MIT license), framework-agnostic, and has the most polished LangGraph integration in the OSS observability category. Key properties:
- **50,000 traces/month free** — 10x more generous than LangSmith's 5,000/month
- **Pydantic AI integration** — automatic span creation for every Pydantic AI agent invocation
- **Promptfoo integration** — eval results link back to Langfuse traces via `langfuse://` provider
- **Prompt management** — version-controlled prompts with A/B testing and deployment tracking
- **Dataset feature** — eval cases can be stored in Langfuse and replayed against new model versions
- **Self-hostable fallback** — if free tier is breached, Langfuse can be self-hosted on the existing Neon Postgres instance

The maintainer's prior familiarity with Langfuse means the learning curve is zero and the integration time is one afternoon.

**LangSmith** (rejected): 5,000 traces/month free tier is 10x less generous. Closed source — incompatible with the open-source reference architecture positioning. The natural LangGraph pairing, but Langfuse's MIT license and 10x higher free tier win.

**Pydantic Logfire** (rejected): Excellent OTel-native tracing from the Pydantic team. Considered seriously. Langfuse won on existing familiarity and the richer eval + prompt management UI. The two are interchangeable at the OTel transport layer; a fork that prefers Logfire can swap the exporter in one file.

**Arize Phoenix** (rejected): Genuinely good. ELv2 license (not fully open source). Langfuse wins on license and familiarity.

### The Sentry + PostHog killer combination

The most important observability decision is the Sentry + PostHog pairing. These two tools auto-correlate:
- When a JavaScript error fires in the browser, Sentry captures the stack trace and embeds a PostHog session replay link in the error detail
- When you watch a PostHog session replay, all Sentry errors that fired during that session appear inline as timeline events
- A reviewer or on-call engineer can click any Sentry error and watch the exact user session — every click, every scroll, every network request — that led to the error

This is a senior engineering pattern. The combination is more powerful than either tool alone. It costs $0/month.

Frontend instrumentation initializes four things in `instrumentation-client.ts`:
1. Sentry browser SDK (errors + performance)
2. PostHog client (product analytics + session replay)
3. `<Analytics />` component (Vercel Analytics — page views, referrers)
4. `<SpeedInsights />` component (Vercel Speed Insights — LCP, FID, CLS, TTFB per page)

### Why Grafana Cloud for infrastructure metrics

Grafana Cloud Free accepts OpenTelemetry metrics from the FastAPI backend via OTLP exporter. Metrics collected:
- `http.server.duration` — Cloud Run latency histogram by endpoint
- `http.server.request.count` — throughput per endpoint
- `http.server.error.rate` — 5xx rate per endpoint
- Custom metric: `orchestrator.scan.duration_ms` — readiness scan wall-clock time (NFR-001 gate)
- Custom metric: `orchestrator.cost_usd` — per-session LLM cost (NFR-005 gate)

The 10,000 series limit is well above what a portfolio project needs (expect ~50–100 active series).

### Why Better Stack for uptime

Better Stack Free provides:
- 10 uptime monitors with 3-minute check intervals
- A public status page at a custom domain (`status.auditpilot.dev`)
- Email + Slack downtime alerts
- 90-day incident history

The public status page is a trust signal for any open-source project. Any visitor to the AuditPilot repo who sees a "status.auditpilot.dev" link with green uptime history reads it as production-grade discipline.

---

## Consequences

### Positive
- Complete observability across all five layers (LLM, errors, product, infrastructure, uptime) at $0/month
- Sentry + PostHog auto-correlation is a production-grade engineering pattern, not just a marketing point
- Langfuse traces link to Promptfoo eval results; any reviewer can inspect the full reasoning chain for any eval case
- Public status page at `status.auditpilot.dev` is a trust signal
- Every layer has a clear upgrade path to paid when the project needs it

### Negative
- Seven tools to configure, monitor, and keep in sync when endpoints or schemas change
- Langfuse's 50,000 trace/month limit would be breached by a successful Show HN spike; self-hosted fallback must be ready
- PostHog session replay captures user behavior by design — privacy policy must disclose this clearly to users of the live demo
- Sentry's 5,000 error/month limit is shared between Python backend and JavaScript frontend; a noisy error source can exhaust the budget

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Datadog** | ~$15/host/month for infrastructure + $0.01/1,000 log events + separate APM pricing. Violates $0/month constraint (SRS CON-005). The right answer for a funded team; wrong for a portfolio phase. |
| **New Relic** | Free tier exists but is complex to configure for Cloud Run + Next.js split. Grafana Cloud + Sentry covers the same ground with less configuration. |
| **LangSmith** | 5,000 traces/month, closed source. Both properties make it inferior to Langfuse for this project. |
| **Honeycomb** | Excellent distributed tracing; strong opinions on structured events. 20M events/month free. Considered. Grafana Cloud won on familiarity with the Grafana dashboard ecosystem, which is the most common paid observability stack in enterprise teams — a familiar setup is a stronger portfolio signal. |
| **Single tool for all layers** | No single free-tier tool covers LLM observability + errors + product analytics + infrastructure + uptime. The seven-tool stack is the minimum set to achieve full coverage. |

---

