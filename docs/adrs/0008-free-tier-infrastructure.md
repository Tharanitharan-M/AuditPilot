# ADR-0008: Free-Tier Infrastructure Stack

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS CON-005, NFR-004; PRD 4.4; PLAN.md Sprint 0F, 2.2

---

## Context and Problem Statement

AuditPilot must operate at $0/month during the portfolio phase (SRS CON-005). The project is published as an open-source reference architecture with no operating budget, and must be reproducible by any reader on the same free tiers. The project must be deployable and publicly accessible by 2026-07-01 (SRS CON-006).

At the same time, the infrastructure must be production-credible — the same services used by real engineering teams, with clear upgrade paths to paid tiers when the project moves from portfolio to production use.

---

## Decision

**Six-service free-tier infrastructure stack:**

| Service             | Role                                              | Free tier limit                                       | Upgrade path                      |
| ------------------- | ------------------------------------------------- | ----------------------------------------------------- | --------------------------------- |
| **Vercel Hobby**    | Next.js 15 frontend hosting                       | Unlimited deployments, 100 GB bandwidth/month         | Vercel Pro ($20/month)            |
| **Cloud Run (GCP)** | FastAPI + LangGraph backend                       | 360,000 vCPU-seconds/month, 180,000 GB-seconds        | Cloud Run always-on min instances |
| **Neon Postgres**   | Primary database (evidence, checkpoints, actions) | 0.5 GB storage, scale-to-zero                         | Neon Launch ($19/month)           |
| **Clerk**           | User authentication + OAuth                       | 10,000 MAU                                            | Clerk Pro ($25/month + usage)     |
| **Cloudflare R2**   | Object storage (policy DOCX, questionnaire XLSX)  | 10 GB storage, 10M operations/month, zero egress fees | R2 paid ($0.015/GB)               |
| **Upstash Redis**   | Rate limiting + session cache                     | 10,000 commands/day                                   | Upstash Pay-as-you-go             |

**Total: $0/month.**

---

## Rationale

### Vercel Hobby for the frontend

Vercel is the first-party hosting platform for Next.js 15. Zero-config deployments: push to `main`, Vercel builds and deploys automatically. Hobby tier includes: unlimited deployments, preview URLs per PR (critical for testing), Vercel Analytics (free), Speed Insights (free), Cron jobs (up to 2/day on Hobby). Edge Network CDN is included. No competitor offers comparable Next.js-native hosting on a free tier.

### Cloud Run for the backend

Cloud Run is the lowest-friction way to deploy a containerized FastAPI application on GCP. 360,000 vCPU-seconds and 180,000 GB-seconds per month is sufficient for a portfolio project with moderate traffic. Key properties: scale-to-zero (no idle cost), pay-per-request, 8 MB request + 32 MB response limit (sufficient for SSE streams). The AdversarialAuditor runs as a separate Cloud Run service (ADR-0002), sharing the same free tier allocation.

The primary limitation of Cloud Run is cold start latency (~1–3 seconds for a Python container). For a portfolio demo this is acceptable; a real production deployment would use minimum instances to eliminate cold starts (Cloud Run billed minimum is 1 instance at ~$10/month, well within a startup's budget).

### Neon Postgres for the primary database

Neon is Postgres 16 with scale-to-zero and branching. The free tier includes 0.5 GB of storage and compute that scales to zero when idle. For AuditPilot, Postgres serves three distinct roles:

1. **Evidence store** — `evidence` table with `pgvector` column for embedding storage (hybrid BM25 + vector search)
2. **LangGraph checkpoints** — `PostgresSaver` writes `AuditPilotState` here at every graph node
3. **Application data** — `users`, `actions`, `drift_events`, `sessions` tables

The 0.5 GB limit covers the static SOC 2 knowledge base (~2 MB), evidence records for a typical readiness scan (~50 MB), and checkpoint data (~10 MB per session). Branching is used in development: each developer gets an isolated database branch with zero additional cost.

**pgvector** is supported natively on Neon (extension `vector` available in Postgres 16). This eliminates the need for a separate vector database (Pinecone, Weaviate, Qdrant) and the associated cost and complexity.

### Clerk for authentication

Clerk handles email/password and GitHub OAuth out of the box with no custom server code. The 10,000 MAU free tier is sufficient for a portfolio project. The JWT tokens issued by Clerk are verifiable in FastAPI using Clerk's JWKS-backed verification flow. No custom session-management framework is required.

Neon remains the only application database and Cloudflare R2 remains the object store. Clerk is used only for identity, which keeps responsibilities clear while avoiding a broader Supabase dependency for a single feature.

### Cloudflare R2 for object storage

Policy documents (DOCX), questionnaire files (XLSX), and gap reports (Markdown) are stored in R2 and served via a pre-signed URL. The critical free-tier property of R2 is **zero egress fees** — S3 charges $0.09/GB for egress, which would add cost on every file download. R2's 10 GB storage and 10M operations/month covers the entire portfolio phase without approaching the limits.

### Upstash Redis for rate limiting and session cache

Upstash Redis is the serverless-friendly Redis option: connection-per-request, no idle cost, compatible with Vercel Edge and Cloud Run. Used for:

- API rate limiting (per-user request caps on `/chat` and `/api/drift/run`)
- Short-lived session data that does not need Postgres durability

The 10,000 commands/day free tier is generous for a portfolio project.

---

## Consequences

### Positive

- $0/month operational cost; no credit card required for any service during portfolio phase
- Each service has a clear, reasonably-priced upgrade path when the project moves to production use
- Vercel + Cloud Run + Neon is a recognizable stack; engineers familiar with production infrastructure recognize each component
- Neon branching means database migrations can be tested on an isolated branch before merging
- Zero egress fees from R2 mean file downloads do not create unexpected costs during a demo or Show HN spike

### Negative

- Cloud Run cold starts (1–3 seconds) add latency to the first request after an idle period; NFR-001 (≤ 30s readiness scan) is measured after the container is warm
- Neon's 0.5 GB storage limit requires evidence compaction if the project accumulates many scan sessions; a `DELETE FROM evidence WHERE created_at < now() - interval '30 days'` job in the drift watcher handles this
- Upstash's 10,000 commands/day limit would be exhausted by aggressive load testing; rate limit the load test itself
- Scale-to-zero on both Cloud Run and Neon means the demo "cold start experience" must be communicated to reviewers (the first request is slow; subsequent requests are fast)

---

## Alternatives Considered

| Option                                             | Why rejected                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AWS (EC2 + RDS + S3)**                           | EC2 free tier expires after 12 months and requires credit card. RDS free tier is 20 GB but t2.micro only. S3 egress fees add up during demo spikes. Vercel + Cloud Run is simpler for our frontend/backend split.                                                                                               |
| **Fly.io**                                         | Excellent for containerized apps; generous free tier. Rejected because Neon is specifically optimized for Postgres + pgvector with branching, which Fly.io's Postgres offering (Fly Postgres) does not match. Fly.io is the right answer for teams that want one platform; we need Neon for database branching. |
| **Railway**                                        | Similar to Fly.io. Good free tier. Rejected for the same reason: Neon branching is a development productivity feature that Railway's managed Postgres does not provide.                                                                                                                                         |
| **Render**                                         | Free tier includes Postgres but with a 90-day data expiration on the free plan, which would destroy evidence data. Neon has no data expiration on the free tier.                                                                                                                                                |
| **Supabase Auth**                                  | Supabase Auth is capable and has a larger free tier, but we do not use Supabase for database or storage. For this architecture, Clerk's pre-built Next.js authentication components remove meaningful frontend implementation work while preserving the vendor-minimal stack around Neon + R2.                  |
| **Pinecone / Weaviate / Qdrant for vector search** | Adding a separate vector database adds a seventh piece of infrastructure and a second managed service for data storage. Neon + pgvector handles both relational and vector storage in one service. The hybrid BM25 + pgvector search is ~200 lines of Python; no framework abstraction is needed.               |

---
