# AuditPilot Tooling Landscape: What We Use, What We Considered, What We Don't

**Purpose of this document:** This is the comprehensive reference for every tool we evaluated when building AuditPilot. Claude Code uses it as source material when writing ADR-001 (agent runtime decision) and ADR-002 (broader tooling alternatives). Reviewers will ask "did you consider X?" and the answer needs to be specific. This document is that specificity.

**How to read this:** Each category lists the tools we evaluated, what each does, our choice with reasoning, and the deliberate "no" decisions with reasoning. Every "no" is a defensible design-review answer.

**Companion documents:**
- `AUDITPILOT_FOUNDATIONS.md` — domain knowledge and user flow
- `AUDITPILOT_CONTEXT.md` — strategic decisions and the 2026 AI engineering landscape

---

## Category 1: Agent Runtimes

This is the foundational decision. Everything else assembles around the runtime choice.

### Our choice: **LangGraph 1.x** as the runtime, with **Pydantic AI** for typed agent definitions

LangGraph 1.0 went GA in October 2025 with an explicit no-breaking-changes commitment until 2.0. It is the dominant production framework for agent orchestration, with documented deployments at Klarna ($60M+ savings claim from Q3 2025), Uber, LinkedIn, JPMorgan, BlackRock ($11T AUM Aladdin Copilot), Replit, Cisco Outshift, Elastic, AppFolio, and Vanta. It appears in roughly 25-30% of 2026 AI Engineer JDs and is the fastest-growing framework keyword. Native MCP support since Q1 2026 via `langchain-mcp-adapters`. Native A2A v1.0 support via `/a2a/{assistant_id}` endpoint in `langgraph-api>=0.4.21`. Best-in-class HITL pattern via `interrupt()` plus `Command(resume=)` plus `PostgresSaver` checkpointing — the canonical 2026 pattern.

Pydantic AI handles individual agent definitions with type-safe inputs, outputs, and dependency injection. Same team that builds Pydantic v2 (which is the validation backbone of FastAPI, OpenAI SDK, Anthropic SDK, and LangChain itself). v1.0 stable shipped September 4, 2025. Production case studies include MindsDB (10x performance migration from LangChain), Datalayer (chose Pydantic AI after evaluating ten frameworks), Sophos SecOps. Thoughtworks Tech Radar 2026 places it in adoption-ready.

The combination is the cleanest senior-coded architecture available in 2026: LangGraph orchestrates the outer loop with checkpointing and HITL, Pydantic AI defines individual nodes with typed contracts. We get parallel execution via LangGraph's `add_node` plus async tool calls, full type safety throughout, and clean signal of architectural maturity.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **Google ADK 1.31.x** | Google's agent runtime with native A2A and Vertex AI integration | We seriously considered this. ADK has clean primitives like `ParallelAgent` and `SequentialAgent`, plus the strongest A2A v1.0 first-party support. Three reasons we passed: (1) ADK 2.0 is in Beta with explicit breaking changes from 1.x; ADK 1.x had 31 minor releases in 12 months with breaking changes between minors. LangGraph 1.0 has the opposite stability commitment. (2) ADK appears in <1% of 2026 AI engineer JDs versus LangGraph's 25-30%. (3) For an open-source reference architecture, LangGraph's 30+ named external production deployments dwarf ADK's roughly four (Comcast Xfinity Assistant, PayPal, Geotab, Genpact, plus Google's internal dogfood). |
| **LangChain** | Kitchen-sink LLM framework with 700+ integrations | LangChain is the parent ecosystem; LangGraph is the production-grade subset. Using bare LangChain in 2026 reads as legacy. We use LangGraph specifically because it is the production-graph subset of LangChain, not the full kitchen sink. |
| **OpenAI Agents SDK** | OpenAI's production agent framework with explicit handoffs | OpenAI-only. Does not fit our multi-provider routing strategy. Would lock us into OpenAI pricing. The `handoffs` pattern is also closer to the multi-agent anti-pattern that Cognition AI's "Don't Build Multi-Agents" essay warned against. |
| **Microsoft Agent Framework** | Replaces AutoGen, .NET-friendly, enterprise-grade | Microsoft ecosystem. Our backend is Python on Cloud Run. No reason to add complexity. |
| **AutoGen / AG2** | Conversational multi-agent (now AG2 after community fork) | Officially in maintenance mode since September 2025. Microsoft is consolidating into Agent Framework. Multiple 2026 reviews call it "near-zero security mechanisms, suitable for academic research and rapid experimentation, not for enterprise production." |
| **CrewAI** | Role-based agent teams with intuitive API and visual editor | Lowest learning curve in the space. The crew metaphor is the exact peer-agent pattern Cognition warned against. CrewAI itself is fine for some use cases but its mental model conflicts with our chosen single-writer architecture. |
| **Mastra** | TypeScript-native agent framework | TypeScript-only. Our backend is Python (FastAPI on Cloud Run). |
| **Smolagents** | Hugging Face minimalist agent framework | Research-flavored, not production-grade. |
| **Amazon Bedrock AgentCore** | AWS managed agent service | AWS lock-in, our deployment target is Cloud Run not AWS, weaker free tier. |

### Design-review summary

> "I evaluated nine agent runtimes and picked LangGraph plus Pydantic AI. LangGraph 1.0 is the dominant production framework — Klarna, Uber, LinkedIn, BlackRock, JPMorgan all run it. It hit 1.0 GA in October 2025 with an explicit no-breaking-changes commitment until 2.0, and it has native first-class support for MCP, A2A v1.0, and the `interrupt()` HITL pattern that I needed. I use Pydantic AI for individual agent node definitions because it gives me type-safe inputs, outputs, and dependency injection from the same team that builds Pydantic v2, which is already the spinal cord of my backend. I seriously evaluated Google ADK because it has the best A2A first-party support, but ADK 2.0 is a breaking Beta and ADK 1.x had 31 minor releases in 12 months with breakage between them — LangGraph's stability commitment is the opposite. I also rejected LangChain bare as legacy framing, OpenAI Agents SDK as too provider-locked, AutoGen as effectively deprecated, and CrewAI because the crew metaphor conflicts with the single-writer multi-agent architecture I chose."

That summary is 90 seconds of speech. It demonstrates the space was evaluated, deliberate choices were made, specific production deployments can be cited, and the architectural debates of 2025-2026 are understood.

---

## Category 2: LLM Observability

### Our choice: **Langfuse Cloud Hobby**

Langfuse is open-source (MIT), framework-agnostic, and has the most polished LangGraph integration in the OSS observability category. 50k events/month free, OpenTelemetry-native, and runs as a self-hosted fallback if we ever breach free tier. Promptfoo has native `langfuse://` integration for prompt management.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **LangSmith** | LangChain's commercial observability product | The "official" LangGraph pairing, but closed source and only 5k traces/month free (10x lower than Langfuse). For an open-source reference architecture, Langfuse's MIT license is the right fit. We document this trade-off explicitly — LangSmith would be the natural upgrade for paid teams. |
| **Pydantic Logfire** | Pydantic team's observability product | Excellent OpenTelemetry-native tracing from the same team as Pydantic AI. Free tier is generous. Considered seriously. Langfuse won on existing familiarity and broader ecosystem. We may swap to Logfire later — they are interchangeable at the OTel layer. |
| **Arize Phoenix** | OpenTelemetry-native observability, ELv2 license | Genuinely good. Considered. Langfuse won on existing familiarity. |
| **Helicone** | Open-source LLM observability | Solid alternative. Langfuse wins on richer prompt management UI and the dataset feature for continuous eval. |
| **Opik (Comet)** | Open-source observability | Newer entrant. Langfuse has more momentum. |
| **Weights & Biases Weave** | W&B's LLM observability | ML-research orientation, weaker for production agent traces. |
| **Braintrust** | Closed-source eval and tracing platform | Recently raised $80M at $800M valuation, strongest CI-eval-release-gate story. Closed source is the dealbreaker for an OSS reference architecture. We mention it as the natural commercial upgrade. |

---

## Category 3: Eval Frameworks

### Our choice: **Promptfoo + RAGAS**

Promptfoo is the CLI-first prompt testing harness with YAML configs stored in the repo. It has native GitHub Actions integration and stabilized Langfuse integration in 0.100+. We run a 100-case gold set on every PR with LLM-as-judge plus deterministic assertions. We validate the judge against 50 hand-labeled cases and track TPR (true positive rate), TNR (true negative rate), and Cohen's kappa. If TPR/TNR drops below 0.85 or kappa below 0.7, we fix the rubric. This judge-validation discipline is the rare move that separates senior portfolios from bootcamp portfolios.

RAGAS complements Promptfoo specifically for the AuditOrchestrator's retrieval steps over the SOC 2 controls knowledge base. Faithfulness, answer relevancy, context precision, and context recall — four metrics that catch retrieval quality regressions Promptfoo's generic LLM-as-judge would miss. Free, Apache 2.0, integrates into Langfuse, ~50 lines of code to wire up.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **DeepEval** | Pytest-style eval with 50+ metrics | Strong alternative. We stay on Promptfoo because YAML configs in the repo are easier to read at a glance than pytest fixtures, and easier to track in version control alongside the prompts under test. We mention DeepEval in the ADR as the natural choice for teams already standardized on pytest. |
| **Braintrust** | Commercial eval platform with CI gates | Closed source, paid. Mentioned as the natural commercial upgrade. |
| **LangSmith eval** | LangChain's bundled eval | We use LangSmith-compatible patterns but stay on Promptfoo for OSS license and YAML transparency. |
| **TruLens** | Snowflake-acquired, OTel-instrumented | Snowflake-flavored. We have no Snowflake. |
| **Inspect AI** | UK AI Security Institute, capability/safety benchmarks | Different use case (model-level capability evals, not application-level quality). |

---

## Category 4: RAG and Retrieval

### Our choice: **Custom retrieval on pgvector** (no framework)

The AuditOrchestrator does retrieval over the SOC 2 Trust Services Criteria knowledge base. This is a hybrid search problem — vector similarity for semantic matches, BM25 for exact keyword matches, plus graph traversal for parent and child controls. About 200 lines of Python. Building it directly on pgvector means we control every step, can debug every retrieval, and have no framework dependency to upgrade.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **LlamaIndex** | RAG-first framework, advanced retrieval, 300+ data connectors | LlamaIndex would be the right answer if retrieval were AuditPilot's main feature. Retrieval here is one capability among many; the orchestrator does a lot more than RAG. We avoid the framework abstraction we do not need. We mention LlamaIndex in the ADR as the right answer for retrieval-heavy applications. |
| **LangChain RAG** | Generic chains | Same issue as bare LangChain. We use LangGraph specifically; we do not need LangChain's RAG abstractions. |
| **Haystack** | Pipeline-first, deepset, enterprise-grade | Pipeline mental model is heavier than what we need. |
| **DSPy** | Auto-optimize prompts and retrieval | Research-focused. Adds complexity for unclear portfolio benefit. |
| **FlashRAG** | Lightweight RAG | Newer, less production-tested. |

---

## Category 5: Vector Databases

### Our choice: **pgvector (in Neon Postgres)**

The same database that stores controls, evidence, runs, policies, and HITL approvals also stores embeddings. One vendor, one connection pool, one backup story. pgvector is production-grade — Discord, Supabase, and many others run it at scale. For our embedding count (under 100k), it is faster than any dedicated vector DB once you account for network round trips between separate services.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **Pinecone** | Managed vector DB | Paid ($50/month minimum). Rules it out for $0/month constraint. |
| **Qdrant** | Open-source vector DB, excellent benchmarks | Genuinely great. Adding another vendor for our embedding scale is not worth it. We mention Qdrant in the ADR as the right choice if we ever exceed 1M embeddings. |
| **Weaviate** | Open-source, strong hybrid search | Same reasoning as Qdrant. |
| **Milvus** | Distributed vector DB | Overkill for our scale. |
| **Chroma** | Embeddable vector DB | Less production-tested than pgvector at our scale. |

---

## Category 6: Frontend AI Orchestration

### Our choice: **Vercel AI SDK 6 + AI Elements + shadcn/ui**

Vercel AI SDK 6 (released early 2026) has the typed UIMessage SSE protocol, `needsApproval` HITL gates, and tool-call typing that AI SDK 5 lacked. AI Elements gives us pre-built agentic UI components (chat, tool-call cards, generative UI primitives) on top of shadcn/ui's design system. This combination is the de facto standard for Next.js 15 AI applications in 2026.

We additionally use **CopilotKit** for `useFrontendTool` (frontend tools the agent can call directly) and **assistant-ui** for the open-canvas chat pattern on the policies route. Both are established, both are MIT-licensed.

### What we explicitly drop: **A2UI v0.9**

A2UI is Google's declarative server-driven UI protocol launched April 17, 2026. It is a v0.9 spec that no major project outside Google is shipping. It appears in zero AI engineer JDs. The original AuditPilot plan included one A2UI route for a DPIA form because a random LinkedIn JD mentioned it. With that JD pressure removed, A2UI is dead weight — a Beta dependency that adds complexity for no signal. We replace the planned A2UI route with a clean shadcn form. Saves a week of build time, removes Beta dependency risk.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **A2UI v0.9** | Google's declarative agent UI protocol | Beta, zero JD presence, replaceable with shadcn form. |
| **Bare React with manual SSE** | Roll our own | Vercel AI SDK 6 is the right level of abstraction. We do not need to reinvent it. |
| **AG-UI** | Streaming agent events to UI | We use AG-UI patterns inside our Mission Control page for the live agent topology view. Not a runtime, just a streaming convention. |
| **React Flow** | For agent topology visualization | Yes, we use this for `/mission-control` to render the live LangGraph state visually. |

---

## Category 7: Tool Integration (the headline artifact)

### Our choice: **MCP (Model Context Protocol) with five custom servers**

MCP was donated to the Linux Foundation in December 2025. Mike Krieger (Anthropic CPO) called it "the most important thing Anthropic has shipped... the fastest-growing standard in tech history." It appears in 17% of 2026 AI Engineer JDs and is the fastest-growing framework keyword of all. Building five custom MCP servers and publishing them to npm and PyPI is the rare, high-signal portfolio artifact.

Our five servers:
1. **`@auditpilot/compliance-kb-mcp`** — SOC 2 Trust Services Criteria as queryable knowledge base
2. **`@auditpilot/evidence-store-mcp`** — typed read-only access to collected evidence
3. **`@auditpilot/questionnaire-mcp`** — SIG-Lite, CAIQ, ISO 27001 Annex A schema parsers
4. **`@auditpilot/policy-template-mcp`** — Trail of Bits-derived policy templates with placeholder substitution
5. **`@auditpilot/drift-watcher-mcp`** — diff between current and previous evidence snapshots

All five published under Apache 2.0. Each one stands alone — someone forking AuditPilot can use just `compliance-kb-mcp` in their own project.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **Function calling (raw provider)** | Direct OpenAI / Anthropic / Gemini function calls | We wrap these through MCP. MCP is the abstraction over function calling that survives provider changes. |
| **LangChain tools** | `BaseTool` and `@tool` decorator | Tied to LangChain's ecosystem, not a portable standard. MCP is the portable standard. |
| **OpenAI Plugins** | Deprecated | Deprecated. Not a real option. |
| **OpenAPI / function calling JSON schemas only** | Just specs, no runtime | MCP gives us the spec plus a runtime plus an ecosystem. |

---

## Category 8: LLM Provider Routing

### Our choice: **LiteLLM**

LiteLLM is the industry standard for multi-provider routing. We use it to fail over between Gemini 2.5 Flash-Lite (default), Cerebras (speed), Groq (cheap), and OpenAI/Anthropic (quality fallbacks). Hard daily caps prevent runaway costs. One unified streaming interface, one way to swap providers, one config file.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **Portkey** | Commercial alternative | Paid. LiteLLM is the OSS standard. |
| **OpenRouter** | Routing service with bring-your-own-keys | Adds latency layer. We have free Gemini quota. |
| **Helicone Gateway** | Helicone's routing product | Less mature than LiteLLM. |
| **Direct SDK calls only** | Skip the router | Considered. LiteLLM is worth the small dependency for the failover behavior we want. |

---

## Category 9: Frontend Observability

### Our choice: **The full free-tier stack**

For a 2026-credible portfolio project, frontend observability is non-negotiable. Production SaaS teams in 2026 ship observability in sprint one. We replicate the standard combination on $0/month:

- **Vercel Analytics** — page views, top pages, referrers (free with Hobby)
- **Vercel Speed Insights** — Core Web Vitals (LCP, FID, CLS, TTFB) (free with Hobby)
- **Sentry browser SDK** — JS errors, source-mapped stacks (5k events/month free, same Sentry account as backend)
- **PostHog** — funnels, session replay, retention, feature flags (1M events/month free)
- **Better Stack** — uptime monitoring, public status page at `status.auditpilot.dev` (10 monitors free)

The killer combination is **Sentry plus PostHog**: their auto-correlation means when a JS error fires, the session replay link appears in Sentry. When you watch a PostHog replay, the errors that fired during it appear inline. A reviewer or on-call engineer can click any error and watch the user's actual session leading up to it.

### What we deliberately do not use

| Tool | Why not |
|---|---|
| **Datadog** | $31/host/month plus per-span charges. Disqualifying at our scale. Mentioned as the commercial upgrade. |
| **New Relic** | Heavyweight. Mentioned as alternative. |
| **Grafana Cloud** | Yes, we use this — for backend metrics specifically (latency, throughput, error rate via OTel). 10k series, 50 GB logs free. |

---

## Category 10: Backend Infrastructure

### Our choice: **Vercel + Cloud Run + Neon Postgres + Cloudflare R2 + Upstash Redis + Supabase Auth**

| Component | Choice | Why |
|---|---|---|
| Frontend hosting | **Vercel Hobby** | Free, Next.js 15 native, edge-deployed. The default for Next.js. |
| Backend agent runtime | **Cloud Run** | 360k vCPU-seconds/month free, scale-to-zero, container-native. |
| Database | **Neon Postgres** with pgvector | Scale-to-zero with 350ms cold start, branching, no idle-pause penalty. |
| File storage | **Cloudflare R2** | 10GB free + zero egress fees. Better than S3 or Supabase Storage on price. |
| Cache + rate limit | **Upstash Redis** | 500K commands/month free, serverless-friendly, REST API. |
| Auth | **Supabase Auth** | 50k MAU free, OAuth flows for GitHub/Google/Slack. We use Supabase only for auth, not for Postgres or storage. |
| Cron jobs | **Vercel Cron** (default) or **Cloud Run jobs** | Drift watcher runs every 6 hours. Vercel Cron is one config line. |

### Optional Kubernetes path

We ship a **Helm chart** for production-grade Kubernetes deployments on Oracle Cloud Always Free OKE (4 ARM oCPUs, 24GB RAM, no expiry). This is the optional path for enterprise users — and for the K8s claim on the resume. Default deployment is `docker compose up -d` for local and Vercel + Cloud Run for cloud. Both audiences served.

### What we deliberately drop from the original plan

The original plan made K8s mandatory by putting the drift watcher exclusively on Oracle OKE. That added a week of setup time and broke the one-command deploy story. We move to optional K8s — Vercel Cron is the default path, Helm chart is provided for K8s users.

---

## Category 11: Local Development Setup

### Our choice: **Docker Compose (the headline adoption unlock)**

Anyone with Docker can run AuditPilot in 90 seconds:

```bash
git clone https://github.com/Tharanitharan-M/auditpilot
cd auditpilot
cp .env.example .env  # add Gemini API key
docker compose up
# open http://localhost:3000
```

Docker Compose spins up the Next.js frontend, FastAPI backend, Adversarial Auditor service, Postgres with pgvector, Redis, and an optional self-hosted Langfuse instance. This single decision is the biggest unlock for GitHub stars — every successful OSS AI project in 2025-2026 (OpenHands, Dify, Aider, Comp AI, Langflow) had this on day one.

### Production Dockerfiles

Each service (`apps/web`, `apps/api`, `apps/auditor`) gets its own multi-stage Dockerfile. Cloud Run requires this. Self-hosters benefit from this. We ship them on day one.

---

## Category 12: Authentication

### Our choice: **Supabase Auth** (50k MAU free tier, OAuth flows only)

We use Supabase **only for authentication** — not for Postgres (we use Neon), not for Storage (we use Cloudflare R2), not for Edge Functions (we use Cloud Run), not for Realtime (we use SSE from FastAPI). Supabase Auth handles the OAuth flow that lets Maya sign in with Google and grant read-only OAuth scopes for GitHub, Gmail, Slack, and Calendar. That's the entire job.

The 50k MAU free tier is 5x larger than Clerk's, MFA is included for free (Clerk charges $100/mo for MFA as an add-on), and it integrates cleanly with Next.js Server Components via `@supabase/ssr`.

### Alternatives considered

| Tool | What it is | Why we did not pick it |
|---|---|---|
| **Clerk** | Modern auth platform with drop-in `<SignIn />`, `<UserButton />`, `<OrganizationSwitcher />` components; best DX in the category | Genuinely excellent for B2B SaaS with team management. Three reasons we passed: (1) Free tier is **10k MAU vs Supabase's 50k** — 5x smaller. (2) Clerk's killer feature is organization management, which AuditPilot does not use (single-tenant demo). We would be paying the DX premium for features we do not need. (3) Pricing trap: past 10k MAU is $25/mo + $0.02/MAU + $100/mo for MFA add-on. Supabase past 50k MAU is $25/mo + $0.00325/MAU with MFA included. **6x cheaper per user at scale.** Clerk would be the right answer for a paid B2B SaaS with $-revenue per customer; it is the wrong answer for an OSS reference architecture. |
| **Auth0** | Enterprise auth platform with SAML, SSO, comprehensive compliance | Free tier is **7,500 MAU**, smallest of the major options. Pricing escalates to $500+/month at 100k MAU vs Supabase's ~$25/month. Auth0's enterprise features (SAML SSO, SCIM provisioning, advanced threat detection) are real but irrelevant for a portfolio project. Worth it only when enterprise SSO is a sales requirement. |
| **NextAuth.js / Auth.js** | Open-source authentication library, fully self-hosted | Genuinely good and free. Considered. The catch is "free" is misleading — you pay in maintenance time. Every feature Clerk and Supabase ship in their dashboard (org management, MFA, user dashboards, reset flows) you have to build. For a 4-week portfolio project, the maintenance burden is not worth it. NextAuth is the right answer for production internal tools where you need full control. |
| **Firebase Auth** | Google Cloud authentication, 50k MAU free tier | Tied with Supabase on free tier scale. Loses on developer experience for modern Next.js stacks — the Firebase SDK is built for client-side React, and the Server Components / RSC integration is weaker than Supabase's. Also locks the project into Google Cloud ecosystem more than we want. |
| **WorkOS AuthKit** | Enterprise-focused authentication with hosted UI, organization management | 1M MAU free for user management. Generous, but enterprise SSO connections cost $125/connection. WorkOS is optimized for B2B SaaS selling to enterprises that demand SAML SSO. Not relevant for AuditPilot. |
| **AWS Cognito** | AWS-native auth with Lambda integration | Our deployment target is Cloud Run, not AWS. No reason to add AWS to the stack just for auth. |

### Design-review summary

> "I evaluated six auth providers — Supabase Auth, Clerk, Auth0, NextAuth, Firebase Auth, and WorkOS. I chose Supabase Auth because the free tier is 50k MAU versus Clerk's 10k, MFA is included free (Clerk charges $100/mo as an add-on), and I only need OAuth flows for GitHub, Gmail, Slack, and Calendar — not B2B team management. I considered Clerk seriously because the developer experience and Next.js components are best-in-class, but the pricing trap past 10k MAU and the MFA cost made it the wrong choice for an open-source reference architecture. Clerk would be my pick for a paid B2B SaaS with paying customers; it is not the pick for AuditPilot's scale and economics."

### What we explicitly do NOT use Supabase for

This is worth stating clearly because it surfaces the architectural decision:

- **Not Supabase Postgres** — we use Neon (better scale-to-zero behavior, branching, no idle-pause penalty)
- **Not Supabase Storage** — we use Cloudflare R2 (10GB free + zero egress fees)
- **Not Supabase Edge Functions** — we use Cloud Run (more flexible, better Python support)
- **Not Supabase Realtime** — we use SSE from FastAPI (one less vendor to manage)

Supabase earns its keep for one job and one job only: identity. Treating it as a focused auth provider rather than a full-stack platform is the deliberate choice.

---

## Summary table: the complete stack

| Layer | Tool | Free tier | Justification |
|---|---|---|---|
| Agent runtime | LangGraph 1.x | Open source | Dominant production framework, 25-30% of JDs |
| Agent definitions | Pydantic AI | Open source | Type-safe, same team as Pydantic v2 |
| Type validation | Pydantic v2 | Open source | Spinal cord of the stack |
| Tool integration | MCP + 5 custom servers | Open source | Fastest-growing protocol, headline artifact |
| Cross-process protocol | A2A v1.0 | Open source | One endpoint between orchestrator and auditor |
| LLM observability | Langfuse Cloud Hobby | 50k events/mo | OSS, OTel-native, framework-agnostic |
| Eval (general) | Promptfoo | Open source | YAML-readable, GitHub Actions native |
| Eval (RAG) | RAGAS | Open source | RAG-specific metrics |
| RAG | Custom on pgvector | Open source | One vendor, one query layer |
| Vector DB | pgvector in Neon | Free | Co-located with primary DB |
| Backend framework | FastAPI | Open source | Pydantic-native, async, OpenAPI |
| Frontend | Next.js 15 | Free | The standard for 2026 |
| Frontend AI | Vercel AI SDK 6 + AI Elements + shadcn | Free | The standard for 2026 |
| LLM router | LiteLLM | Open source | Multi-provider failover |
| Default LLM | Gemini 2.5 Flash-Lite | Free quota | Free tier, fast, good enough |
| Backend errors | Sentry Python SDK | 5k errors/mo | Industry standard |
| Frontend errors | Sentry browser SDK | Same Sentry account | Auto-correlated with PostHog replay |
| Product analytics | PostHog Cloud Free | 1M events/mo | Funnels + session replay + feature flags |
| Web analytics | Vercel Analytics | Free | Free with Hobby |
| Web vitals | Vercel Speed Insights | Free | Free with Hobby |
| Backend metrics | Grafana Cloud Free | 10k series | OTel exporter from FastAPI |
| Uptime + status | Better Stack Free | 10 monitors | Public status page |
| Frontend hosting | Vercel Hobby | Free | Next.js native |
| Backend hosting | Cloud Run | 360k vCPU-s/mo | Scale-to-zero |
| Database | Neon Postgres + pgvector | 0.5GB | Scale-to-zero, branching |
| File storage | Cloudflare R2 | 10GB | Zero egress fees |
| Cache | Upstash Redis | 500K cmds/mo | Serverless-friendly |
| Auth | Supabase Auth | 50k MAU | OAuth flows only |
| Cron | Vercel Cron | Free | Default drift watcher path |
| K8s (optional) | Oracle Cloud OKE Always Free | Free, no expiry | Helm chart for production users |
| Local dev | Docker Compose | Free | One-command setup |

**Total monthly cost: $0.** Realistic worst case if every free tier is breached simultaneously: ~$120/month.

---

## The deliberate "no" list (defensible design-review answers)

When a reviewer asks "did you consider X," the answer is yes for every X below, and the reasoning is specific:

- **Google ADK** — yes, evaluated; rejected because of ADK 2.0 breaking-change risk and <1% JD presence
- **LangChain bare** — yes, evaluated; rejected as legacy framing, used LangGraph subset instead
- **OpenAI Agents SDK** — yes, evaluated; rejected as too provider-locked
- **CrewAI** — yes, evaluated; rejected because crew metaphor conflicts with single-writer architecture
- **AutoGen** — yes, evaluated; rejected because effectively deprecated since September 2025
- **Pydantic AI as primary runtime** — yes, evaluated; chose LangGraph for orchestration but Pydantic AI for agent definitions, hybrid is the senior answer
- **LangSmith** — yes, evaluated; rejected for OSS license preference (Langfuse is MIT)
- **Datadog** — yes, evaluated; rejected on cost
- **LlamaIndex** — yes, evaluated; rejected because RAG is one capability not the main feature
- **Pinecone / Qdrant / Weaviate** — yes, evaluated; pgvector wins at our scale
- **A2UI v0.9** — yes, evaluated; rejected because Beta and zero JD presence
- **Mandatory K8s** — yes, considered; moved to optional Helm chart, Vercel Cron is default
- **Clerk** — yes, evaluated; rejected because Supabase has 5x larger free tier, includes MFA, and we don't need Clerk's organization management
- **Auth0** — yes, evaluated; rejected because 7.5k MAU free tier is too small and pricing escalates fast
- **NextAuth.js** — yes, evaluated; rejected because the maintenance burden negates the "free" claim for a 4-week project
- **Firebase Auth** — yes, evaluated; rejected because Server Components integration is weaker than Supabase

Each "no" is a 30-second design-review answer. Together they demonstrate the space was actually evaluated rather than picking the first thing that worked.
