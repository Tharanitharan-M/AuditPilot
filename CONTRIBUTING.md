# Contributing to AuditPilot

Thank you for your interest in contributing. AuditPilot is an open-source multi-agent SOC 2 readiness reference architecture published under the Apache 2.0 license.

---

## Before you start

Read the following documents in order:

1. [`context/AUDITPILOT_CONTEXT.md`](./context/AUDITPILOT_CONTEXT.md) - AuditPilot context
2. [`docs/system-design.md`](./docs/system-design.md) — fifteen-section system design
3. [`docs/adrs/`](./docs/adrs/) — architectural decision records
4. [`docs/runbooks`](./docs/runbooks/) — runbooks

If a change contradicts an ADR, write a superseding ADR first.

---

## Non-negotiable rules for contributors

These rules are enforced by CI and reviewed by maintainers. PRs that violate them will not be merged.

1. **Read-only on the way in.** No write API calls to GitHub, Gmail, Slack, or Calendar. Read-only OAuth scopes only.
2. **LangGraph 1.x + Pydantic AI.** Never import `google.adk`. Never use bare `langchain` for orchestration.
3. **Three agents.** AuditOrchestrator, AdversarialAuditor, HumanReviewGate. Write an ADR before adding a fourth.
4. **Five MCP servers.** `compliance-kb`, `evidence-store`, `questionnaire`, `policy-template`, `drift-watcher`. Write an ADR before adding a sixth.
5. **Apache 2.0 license on every new file.** Never AGPLv3.
6. **Pydantic v2 everywhere.** `model_config = ConfigDict(extra="forbid")` on every public schema.
7. **AICPA language guard.** Never write `audit`, `attest`, `certify`, or `SOC 2 report` without a `draft`, `readiness`, or `reference architecture` qualifier. CI runs the compliance check on every PR.
8. **No personal or career framing in public files.** Keep it out of public files entirely.

---

## Local development setup

### Prerequisites

- Node.js 22+, pnpm 9+
- Python 3.12+, [uv](https://github.com/astral-sh/uv)
- Docker + Docker Compose

### One-command quickstart (Sprint 1 and later)

```bash
cp .env.example .env        # fill in required values
docker compose up -d postgres redis
pnpm install
pnpm -r build
```

See [`docs/runbooks/local-dev.md`](./docs/runbooks/local-dev.md) (Sprint 11) for the full walkthrough.

---

## Branch and PR conventions

- Branch off `main`. Name your branch `feat/<slug>`, `fix/<slug>`, or `chore/<slug>`.
- One logical change per PR. Describe the feature area and relevant ADR or sprint in the PR description.
- Every PR must pass all four CI workflows: `lint`, `test`, `eval`, `deploy` (dry run).
- The `eval` workflow blocks merge on a regression > 2% in any category (active from Sprint 10).

---

## Commit message format

[Conventional Commits](https://www.conventionalcommits.org/) with the following types:

```
feat(scope): subject under 72 chars

optional body, wrap at 72 chars

Refs: ADR-NNNN
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `ci`.

---

## Adding a new MCP server

The five sanctioned server names are: `compliance-kb-mcp`, `evidence-store-mcp`, `questionnaire-mcp`, `policy-template-mcp`, `drift-watcher-mcp`. Write an ADR before adding a sixth.

---

## Security vulnerabilities

Do not open a public issue. Email `security@auditpilot.dev` (Sprint 11 — address will be live at launch).

---

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
