# ADR-0005: Five Published MCP Servers

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS CON-008; PRD §6.1; PLAN.md Sprints 1, 5, 7; CLAUDE.md stack pins

---

## Context and Problem Statement

AuditOrchestrator needs access to five distinct tool domains:
1. SOC 2 control knowledge (the AICPA Trust Services Criteria taxonomy and control descriptions)
2. Evidence storage and retrieval (collected GitHub, Gmail, Slack, Calendar evidence with pgvector embeddings)
3. Security questionnaire parsing and clustering (SIG-Lite XLSX ingestion)
4. Policy template generation (structured policy document templates with control citations)
5. Drift detection (diff current evidence snapshot vs. previous)

Options for providing these tools: direct Python function calls, a single monolithic MCP server, five separate MCP servers published to npm + PyPI, or third-party MCP servers.

---

## Decision

**Author and publish five standalone MCP servers:**
- `compliance-kb-mcp` — SOC 2 TSC knowledge base (64 controls, lookup + semantic search)
- `evidence-store-mcp` — evidence storage and retrieval with pgvector hybrid search
- `questionnaire-mcp` — SIG-Lite XLSX parser, question clustering, and answer scaffolding
- `policy-template-mcp` — policy template generation grounded in control posture
- `drift-watcher-mcp` — evidence snapshot diffing and drift event production

Each server is a standalone Python package (PyPI) and Node.js package (npm), published independently, usable outside of AuditPilot.

---

## Rationale

### MCP is the fastest-growing tool integration protocol in 2026

The Model Context Protocol (spec 2025-11-25) went from announcement (November 2024) to appearing in approximately 17% of AI Engineer job descriptions by Q1 2026. It is supported natively by Claude, the Anthropic API, LangChain (via `langchain-mcp-adapters`), LangGraph, Pydantic AI, OpenAI Agents SDK, and the major IDE tooling (Cursor, Claude Code, Zed). Authoring published MCP servers is one of the clearest senior AI engineer signals available in 2026 — it demonstrates protocol-level thinking, published artifact discipline, and the ability to build tools that other engineers consume.

### Five published packages as concrete artifacts

The artifact claim "five open-source MCP servers published to npm and PyPI" is concrete, verifiable, and rare. Anyone evaluating the project can `pip install compliance-kb-mcp` or `npm install compliance-kb-mcp` and run the server. This is the difference between a written claim and a runnable artifact. Each package:
- Has its own README, CHANGELOG, and semver versioning
- Has Pydantic v2 typed schemas generating JSON Schema via `model_json_schema()`
- Is validated by the `mcp-server-validator` sub-agent before every publish
- Runs over stdio (local use) and can be configured for HTTP/SSE transport (remote use)

### Separation of concerns as individual packages

Each server has a focused, single responsibility. `compliance-kb-mcp` does not know about evidence. `evidence-store-mcp` does not know about questionnaires. This means:
- A fork that only needs compliance knowledge can install `compliance-kb-mcp` alone
- A different compliance tool (HIPAA, ISO 27001, PCI-DSS) can extend `compliance-kb-mcp` without touching the other servers
- Each server can be tested independently with a mock MCP client
- Breaking changes in one server do not affect the others

### Publish timing: Sprint 4, not Sprint 1

`compliance-kb-mcp` is built in Sprint 1 but published to npm + PyPI in Sprint 4, after AuditOrchestrator has actually consumed the server end-to-end. This avoids version churn from discovering API mistakes after the first publish. The Sprint 1 artifact (`npm pack --dry-run` + `uv build`) is staged locally; Sprint 4 chunk 4.7 is the actual publish command.

---

## Consequences

### Positive
- Five independently downloadable, runnable packages; the portfolio claim is verifiable
- Each server is usable outside AuditPilot; community members can build on them
- Pydantic v2 schemas generate correct JSON Schema automatically; no manual schema maintenance
- `mcp-server-validator` sub-agent enforces spec compliance, publish readiness, and Pydantic v2 typing on every change
- MCP appears in ~17% of 2026 AI Engineer JDs; five published servers is the maximum credible claim for a single-developer project

### Negative
- Five packages is five maintenance surfaces; each needs semver, CHANGELOG, and compatibility testing when MCP spec updates
- Publishing to both npm and PyPI means two package registries, two auth setups, and two publish workflows
- The five-server limit (SRS CON-008) means a sixth tool domain requires either folding into an existing server or writing a new ADR

---

## Server Design Constraints

All five servers must satisfy:

| Constraint | Enforcement |
|---|---|
| Pydantic v2 `model_config = ConfigDict(extra="forbid")` on all tool input/output schemas | `mcp-server-validator` blocks merge if missing |
| `model_json_schema()` produces `additionalProperties: false` | Automated test in each package |
| FastMCP server entrypoint over stdio | Manual test: connect MCP Inspector |
| Apache 2.0 license in `pyproject.toml` and `package.json` | license-checker in CI |
| README with one-command install + quick start | `mcp-server-validator` checks README completeness |
| Tests with ≥ 80% branch coverage | pytest coverage gate in CI |
| MCP spec 2025-11-25 compliance | `mcp-server-validator` full pass |

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Direct Python function calls** | No portability. No published artifacts. No MCP protocol signal. The orchestrator becomes a monolith. Other projects cannot consume the tools. |
| **Single monolithic MCP server** | One published package instead of five. No separation of concerns. Cannot install `compliance-kb-mcp` without installing the evidence store and questionnaire parser. Weaker artifact for forks that only need part of the surface. |
| **Third-party MCP servers for compliance tools** | No suitable open-source MCP server for SOC 2 TSC knowledge, evidence storage with pgvector, or SIG-Lite parsing exists as of May 2026. Using third-party servers for commodity tools (file system, search) is fine but none of the five domains have appropriate existing servers. |
| **LangChain tools (not MCP)** | LangChain tools are not portable across runtimes. MCP tools work in Claude Desktop, Cursor, and any MCP-compatible host. MCP is the right abstraction for 2026. |
| **Fewer than five servers** | Three servers was considered. Rejected because `policy-template-mcp` and `drift-watcher-mcp` have distinct data access patterns (template rendering vs. time-series diffing) that belong in separate packages. Five is the honest count; forcing three would produce one overloaded server. |

---

