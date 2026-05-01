# AuditPilot — Software Requirements Specification

**Status:** Draft | **Version:** 0.1 | **Date:** 2026-05-01
**Companion docs:** `docs/prd.md`, `docs/adrs/`

> AuditPilot is a readiness reference architecture. This document specifies the requirements of the software system only. Nothing in this document constitutes legal or accounting advice, and nothing in this system constitutes a licensed attestation, certification, or signed opinion from a CPA firm.

---

## Section 1: Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the functional requirements, non-functional requirements, and constraints for AuditPilot v1.0. It is the authoritative reference for:
- Sprint planning (each FR maps to at least one PLAN.md chunk)
- Acceptance testing (every FR has a verifiable condition)
- ADR context (ADRs cite FRs they satisfy)
- Open-source contributor onboarding (FRs explain *what* before the code explains *how*)

### 1.2 Scope

AuditPilot v1.0 covers:
- GitHub read-only connector + automated evidence collection
- SOC 2 Trust Services Criteria (TSC) control mapping (64 controls, CC1–CC9)
- Draft policy generation with human review gate
- SIG-Lite questionnaire auto-fill
- Adversarial mock readiness challenge (AdversarialAuditor via A2A v1.0)
- Drift detection and Pending Actions queue
- Full observability stack (Langfuse + Sentry + PostHog + Grafana + Better Stack)

Out of scope for v1.0: write API calls to any source tool, ISO 27001 / HIPAA / PCI-DSS mappings, Gmail / Slack / Calendar connectors (Should-tier), Oracle OKE Helm chart. See PRD §5 (Non-Goals).

### 1.3 Definitions

| Term | Definition |
|---|---|
| TSC | Trust Services Criteria — the SOC 2 control framework published by AICPA |
| MCP | Model Context Protocol (spec 2025-11-25) — the tool integration protocol |
| HITL | Human-in-the-loop — a required human approval step before AI output is delivered |
| Pending Action | A card in the dashboard queue containing a suggested fix the human applies in the source tool |
| Draft policy | An AI-generated document a human reviews and adopts; never published autonomously |
| Gap report | Output combining control posture + adversarial objections; human downloads and acts on it |
| Readiness snapshot | A point-in-time record of control statuses used for drift comparison |

---

## Section 2: Functional Requirements

Requirements are grouped by functional area. Priority: **M** = Must (v1), **S** = Should (v1 if velocity allows).

### 2.1 Authentication and Authorization

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-001 | M | System shall support user registration via email + password through Supabase Auth | POST /auth/sign-up creates user; user appears in Supabase Auth dashboard |
| FR-002 | M | System shall support user login via email + password | POST /auth/sign-in returns a session; dashboard route becomes accessible |
| FR-003 | M | System shall support GitHub OAuth connector with read-only scopes (`repo` read, `read:org`) | OAuth dialog requests only read scopes; no write scope granted |
| FR-004 | M | System shall persist authenticated sessions via HTTP-only cookies with a 7-day TTL | Authenticated state survives browser tab close; cookie is HttpOnly + Secure + SameSite=Lax |
| FR-005 | M | System shall redirect unauthenticated requests to `/login` via Next.js middleware | `curl /dashboard` without session returns 302 to `/login` |
| FR-006 | M | System shall invalidate sessions on logout and redirect to `/login` | Click Logout; subsequent request to `/dashboard` returns 302 to `/login` |

### 2.2 Integrations (Read-only Connectors)

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-007 | M | System shall connect to the GitHub API using the user's read-only OAuth token | GitHub API call returns 200; scopes header confirms no write permissions |
| FR-008 | M | System shall list all repositories in the connected GitHub organization | `github.list_repos(org)` returns at least the count visible in the GitHub org dashboard |
| FR-009 | M | System shall read branch protection rules for each non-archived repository | Branch protection record stored with fields: `require_pull_request_reviews`, `require_status_checks`, `enforce_admins` |
| FR-010 | M | System shall read MFA enforcement status at the organization level | `github.get_org_mfa()` returns `required: true/false` |
| FR-011 | M | System shall read GitHub Advanced Security (code scanning) enabled status per repository | Code scanning field stored per repo |
| FR-012 | M | System shall read secret scanning enabled and alerts count per repository | Secret scanning field + alert count stored per repo |
| FR-013 | M | System shall read Dependabot alert count and auto-remediation configuration per repository | Dependabot fields stored per repo |
| FR-014 | M | System shall not persist the raw OAuth access token to disk or database beyond the current session | Token stored in memory / server-side session only; no token column in any database table |

### 2.3 Evidence Collection and Control Mapping

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-015 | M | AuditOrchestrator shall map each collected evidence item to SOC 2 TSC controls via `compliance-kb-mcp` | Each evidence item linked to one or more `control_id` values in the control map |
| FR-016 | M | Each control assessment shall produce a structured result: `{control_id, status, confidence, evidence_refs, gap_description}` | `state.control_map` round-trips via `model_dump()` / `model_validate()` without data loss |
| FR-017 | M | Control status shall be one of four values: `PASSING` / `FAILING` / `NOT_ASSESSED` / `NOT_APPLICABLE` | Any other value raises a Pydantic `ValidationError` |
| FR-018 | M | Evidence records shall persist to Postgres with fields: `source_type`, `source_uri`, `raw_content`, `embedding` (pgvector), `content_hash`, `valid_until` | `SELECT count(*) FROM evidence` increases after a scan run |
| FR-019 | M | System shall cache control-mapping LLM decisions keyed on `(content_hash, control_id)` | Second scan of identical evidence does not emit a new LLM call; verified via Langfuse trace showing zero new spans for cached controls |
| FR-020 | M | Evidence collection shall execute concurrently across multiple controls using Python `asyncio.gather` | Langfuse trace shows overlapping spans for at least two MCP tool calls |
| FR-021 | M | Every AuditOrchestrator invocation shall emit a complete OpenTelemetry trace to Langfuse | Each `/chat` request produces a trace visible in Langfuse within 30 seconds |
| FR-022 | M | The control map shall cover all 64 SOC 2 Trust Services Criteria (CC1.1 through CC9.9) | `len(state.control_map) == 64` after a complete scan |

### 2.4 Policy Drafting

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-023 | M | AuditOrchestrator shall draft an Incident Response Plan grounded in the current control posture | Draft references at least 3 TSC control IDs as footnotes |
| FR-024 | M | AuditOrchestrator shall draft an Access Control Policy grounded in the current control posture | Draft references at least 3 TSC control IDs as footnotes |
| FR-025 | M | AuditOrchestrator shall draft a Change Management Policy grounded in the current control posture | Draft references at least 3 TSC control IDs as footnotes |
| FR-026 | M | All draft policies shall include TSC control ID citations in the body text as inline footnotes | Regex `\[CC\d+\.\d+\]` matches at least once per policy draft |
| FR-027 | M | Draft policies shall be available as downloadable files (Markdown + DOCX); system shall not publish them to any external destination | File download endpoint returns content-type `text/markdown` or `application/vnd.openxmlformats-officedocument.wordprocessingml.document`; no outbound HTTP call to external systems |
| FR-028 | M | All policy drafts shall require HumanReviewGate approval before appearing in the download queue | Policy file unavailable at download endpoint until `state.review_status == "approved"` |

### 2.5 Questionnaire Auto-Fill

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-029 | M | User shall be able to upload a SIG-Lite XLSX (128 questions) via the questionnaire workspace | File input accepts `.xlsx`; upload returns HTTP 200 |
| FR-030 | M | `questionnaire-mcp` shall parse the uploaded XLSX into structured objects: `{section, domain, question_text, answer_field}` | Known SIG-Lite fixture parses to exactly 128 objects; test: `test_siglite_parser.py` |
| FR-031 | M | Parsed questions shall be clustered by control domain before evidence retrieval | Cluster count is between 10 and 20 for a standard SIG-Lite input |
| FR-032 | M | Per cluster, AuditOrchestrator shall retrieve relevant evidence from `evidence-store-mcp` | Langfuse trace shows `evidence-store-mcp.search_evidence` called once per cluster |
| FR-033 | M | System shall draft an answer for each question with an evidence citation | Each answer object has a non-empty `citation` field referencing a stored evidence URI |
| FR-034 | M | Answers with `confidence < 0.70` shall be flagged for human review | Flagged answers highlighted in the workspace UI; downloadable XLSX includes a "flagged" column |
| FR-035 | M | Filled questionnaire shall be downloadable as XLSX; system shall not submit it to any external system | Download endpoint streams the XLSX; no HTTP call to external questionnaire submission URL |

### 2.6 Drift Detection

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-036 | M | Drift detector shall run every 6 hours via Vercel Cron | Cron schedule `0 */6 * * *` wired in `vercel.json`; manual trigger via `POST /api/drift/run` also works |
| FR-037 | M | Drift detector shall diff the current evidence snapshot against the previous readiness snapshot for each monitored control | Diff function returns `{added, removed, changed}` sets; unit test covers each branch |
| FR-038 | M | Each drift event shall produce a Pending Action card with: what changed, suggested fix description, and link to the relevant setting in the source tool | Pending Action card has non-empty `what_changed`, `suggested_fix`, and `source_link` fields |
| FR-039 | M | Users shall mark a Pending Action as done (human confirmation that the fix was applied); system shall log timestamp and `user_id` | `PATCH /api/actions/{id}/done` sets `completed_at` and `completed_by` in the database |
| FR-040 | M | System shall never apply a suggested fix automatically to any source tool | Code review: no GitHub, Gmail, Slack, or Calendar write API call anywhere in `apps/api/` |

### 2.7 Adversarial Mock Readiness Challenge

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-041 | M | User shall explicitly trigger the mock readiness challenge from the dashboard; it shall never run automatically | No cron or background task triggers the AdversarialAuditor; trigger requires a user POST action |
| FR-042 | M | AuditOrchestrator shall send the current control map to AdversarialAuditor via the A2A v1.0 protocol | `curl auditor:8001/.well-known/agent.json` returns a valid A2A AgentCard; task accepted returns HTTP 202 |
| FR-043 | M | AdversarialAuditor shall return a list of written objections: `{control_id, objection_text, severity}` | `len(findings) >= 1` for any control map with at least one FAILING control |
| FR-044 | M | Adversarial objections shall merge into a gap report downloadable as Markdown | `GET /api/gap-report` returns a valid Markdown document after the challenge completes |
| FR-045 | M | AdversarialAuditor shall operate within a 30-turn maximum and a $0.50 token-budget hard cap per session | Budget exceeded → agent raises `BudgetExceededError`; test: inject a cap of $0.001 and verify termination |

### 2.8 Human-in-the-Loop Gate

| ID | Priority | Requirement | Acceptance condition |
|---|---|---|---|
| FR-046 | M | HumanReviewGate shall pause the LangGraph workflow at every draft-output boundary using `interrupt()` | Orchestrator state is `INTERRUPTED` in Langfuse trace before any draft is delivered |
| FR-047 | M | Pending Actions queue on the dashboard shall list all items awaiting human review with status, type, and creation timestamp | Queue renders all items with `status == "pending_review"` from the database |
| FR-048 | M | Each pending item shall support three explicit actions: Approve, Edit (inline), Reject (with reason) | All three buttons render; each sends a distinct PATCH to `/api/actions/{id}` |
| FR-049 | M | Approved items shall resume the workflow via `Command(resume="approve")` | After Approve click, orchestrator continues from the interrupted node; Langfuse trace shows resumed execution |
| FR-050 | M | Rejected items shall feed the rejection reason back to the orchestrator as context for re-drafting | `state.rejection_reasons[-1]` is non-empty after a Reject action; orchestrator re-drafts with this context injected |

---

## Section 3: Non-Functional Requirements

Every NFR has a measurement method. Unmeasurable requirements are not requirements.

| ID | Category | Requirement | Measurement method | Target |
|---|---|---|---|---|
| NFR-001 | Performance | P50 wall-clock latency for a complete GitHub readiness scan (connect → control map produced) | Measure via Langfuse trace `total_duration_ms` across 10 consecutive runs on local Docker Compose | ≤ 30 000 ms |
| NFR-002 | Performance | P50 latency for a single SIG-Lite question answer (evidence retrieval + LLM draft) | Measure via Langfuse span `question_answer_ms` across 20 questions | ≤ 5 000 ms |
| NFR-003 | Performance | First-token latency from POST `/chat` to first SSE byte | Measure via `curl --trace-time` on the `/chat` endpoint | ≤ 3 000 ms |
| NFR-004 | Cost | Monthly operational cost during portfolio phase | Billing dashboard across all providers | $0 / month |
| NFR-005 | Cost | Per-session LLM token cost for a complete readiness scan | Langfuse `total_cost` field per trace | ≤ $0.10 / session |
| NFR-006 | Cost | AdversarialAuditor hard token budget per session | Code-enforced via LiteLLM callback that raises `BudgetExceededError` when cumulative cost reaches cap | $0.50 / session |
| NFR-007 | Security | No write OAuth scopes granted to any connector | Code review: grep for `write`, `push`, `admin` in OAuth scope declarations returns zero matches | 0 write scopes |
| NFR-008 | Security | OWASP Top 10 coverage | security-reviewer sub-agent run before v1.0 tag; all Critical + High findings resolved | 0 unresolved Critical / High |
| NFR-009 | Security | All user-supplied inputs validated via Pydantic v2 before processing | Code review: every FastAPI endpoint parameter has a Pydantic model; no bare `request.json()` usage | 100% |
| NFR-010 | Security | No raw OAuth token persisted to database or disk | database-reviewer sub-agent confirms no `token` column in any migration | 0 token columns |
| NFR-011 | Observability | Every AuditOrchestrator invocation produces a Langfuse trace | Langfuse dashboard trace count matches `/chat` endpoint call count | 100% |
| NFR-012 | Observability | All unhandled Python exceptions captured in Sentry | Sentry event count matches production error count in Grafana error-rate panel | ≥ 95% capture rate |
| NFR-013 | Observability | AICPA UPAct compliance: zero forbidden terms in external-facing copy | compliance-language-guard sub-agent run on every PR; CI gate blocks merge on any violation | 0 violations |
| NFR-014 | Reliability | Public demo URL uptime | Better Stack monitor on `/health`; status page at `status.auditpilot.dev` | ≥ 99% over 30-day window |
| NFR-015 | Maintainability | Promptfoo eval regression gate | CI runs 100-case gold set on every PR touching prompts / agents / MCP servers; blocks merge on > 2% regression | 0 regressions > 2% |

---

## Section 4: Constraints

Constraints are fixed conditions that cannot be changed by design decisions. They are documented here so that ADRs that solve problems within these constraints can reference them by ID.

| ID | Constraint | Reason | Impact |
|---|---|---|---|
| CON-001 | **AICPA UPAct language prohibition.** Four terms — `audit`, `attest`, `certify`, and `SOC 2 report` — may not appear in prose without a safe prefix (`draft`, `readiness`, `reference architecture`, `mock`, `simulated`, `internal`, `sample`, `pre-`, `adversarial`, or `fake`) within 80 characters. | AICPA Uniform Practice Act imposes civil liability for unlicensed practice of accountancy. AuditPilot is not a CPA firm. | Every doc, README, blog post, and UI string passes compliance-language-guard before shipping. |
| CON-002 | **Read-only-by-design.** No write, push, admin, or delete OAuth scope may be requested or used from any connector (GitHub, Gmail, Slack, Calendar). | Legal liability, blast-radius reduction, user trust. Detailed in ADR-0004. | Every connector implementation reviewed by security-reviewer sub-agent before merge. |
| CON-003 | **Three LLM-powered agents maximum (without an ADR).** AuditOrchestrator, AdversarialAuditor, HumanReviewGate. Spawning a fourth LLM-powered agent requires a new ADR with rationale. | Cognition AI "Don't Build Multi-Agents" (June 2025) and Anthropic "Building Effective Agents" (December 2024) both warn against over-agentification. | Any PR adding a new agent triggers architecture-reviewer sub-agent which blocks unless an ADR exists. |
| CON-004 | **Apache 2.0 license only.** All first-party code and all MCP server packages must be Apache 2.0. Dependencies must not be AGPLv3 or SSPL. | Commercial users and enterprise forkers cannot use AGPLv3 code without open-sourcing their product. | License is verified on every dependency add via `license-checker` in CI. |
| CON-005 | **$0 operational cost during portfolio phase.** All infrastructure must fit within free tiers of the chosen providers (Vercel Hobby, Cloud Run free tier, Neon free, Supabase Auth free, Cloudflare R2 free, Upstash free). | Open-source reference architecture published with no operating budget; the project must be reproducible by any reader on the same free tiers. | Detailed free-tier limits documented in ADR-0008. Any paid-only solution requires explicit approval. |
| CON-006 | **Code-complete by 2026-06-30.** AuditPilot must ship a live demo URL by 2026-07-01. That leaves roughly 43 calendar days from 2026-05-01. 11 sprints. | A live demo by July 2026 gives the project a public surface for the first wave of fork-and-feedback while the architecture is still fresh. | Any sprint that slips more than 3 days triggers a replan using the cut order in PLAN.md §Buffer. |
| CON-007 | **LangGraph 1.x, Pydantic AI 1.x, Pydantic v2, MCP spec 2025-11-25, A2A v1.0, Vercel AI SDK 6.** These version pins are fixed. Upgrading any of them requires an ADR. | Stability commitment: LangGraph 1.0 has an explicit no-breaking-changes promise until 2.0. Other pins chosen for their GA stability windows. Detailed in CLAUDE.md stack pins table. | `pyproject.toml` and `package.json` pin exact major versions; Dependabot is configured to alert but not auto-merge major bumps. |
| CON-008 | **Five MCP servers maximum (without an ADR).** `compliance-kb-mcp`, `evidence-store-mcp`, `questionnaire-mcp`, `policy-template-mcp`, `drift-watcher-mcp`. Adding a sixth requires a new ADR. | MCP server count is the headline portfolio claim. More than five creates maintenance burden without proportional portfolio value. | architecture-reviewer sub-agent checks server count on any PR touching `packages/`. |

---

_Last updated: 2026-05-01. Section 2 FRs map 1:1 to PLAN.md Sprint 1–9 chunks. Section 4 constraints are referenced by ADR-0001 through ADR-0009._
