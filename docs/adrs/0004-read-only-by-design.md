# ADR-0004: Read-Only-by-Design

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS CON-001, CON-002, FR-040, FR-044; PRD NG-3, NG-4

---

## Context and Problem Statement

AuditPilot connects to source tools — GitHub, Gmail, Slack, Calendar — to collect evidence for SOC 2 readiness work. An early design option was to give the agent write access so it could automatically remediate gaps: flip branch protection on, enforce MFA, send access-review emails, post Slack reminders. This is the "fully autonomous" model.

The question: should AuditPilot request write OAuth scopes and apply fixes automatically, or restrict itself to read-only scopes and produce suggested fixes for humans to apply?

---

## Decision

**AuditPilot requests read-only OAuth scopes for every connector. It never calls a write API on any source tool. All output is either a downloadable file or a Pending Action card the human applies in the source tool.**

This is not a temporary limitation — it is a permanent, intentional architectural constraint documented at the ADR level so that no future contributor accidentally adds write access.

---

## Rationale

### Legal constraint: AICPA UPAct

The AICPA Uniform Practice Act (UPAct) reserves certain compliance and assurance activities for licensed CPA firms. An AI agent that autonomously applies security controls and produces a readiness report without human review creates meaningful ambiguity about whether it is performing an assurance function. The read-only model removes that ambiguity: the system reads, analyzes, and suggests; the licensed professional or the responsible engineer decides and acts.

Every doc, README, and external-facing string in AuditPilot uses `draft`, `readiness`, `reference architecture`, or similar qualifiers before any regulated term. The read-only-by-design principle is the architectural expression of the same discipline.

### Vanta precedent (the commercial incumbent)

The most successful commercial tool in this problem space makes the same design choice. From Vanta's own SOC 2 product page:

> "Vanta connects read-only to your cloud, identity, code, and device tools."

For remediation, Vanta generates "remediation snippets so developers can resolve failing tests fast." The developers apply the snippet. Vanta does not. If the market leader with $300M ARR and a dedicated security team chose read-only, the design decision is de-risked.

### Blast-radius argument

A bug in an agent with write access to GitHub could:
- Disable branch protection on a production repository
- Delete a security policy file
- Remove a team member from a security group
- Revoke a deploy key

These are irreversible or difficult-to-reverse actions that could take a production system offline or create a real security gap in an otherwise healthy posture. A bug in an agent with read-only access can:
- Produce a wrong gap report
- Draft an incorrect policy
- Miss a control

The second list is embarrassing. The first list is a security incident. Read-only removes the entire first category.

### Write OAuth scopes slow user acquisition

When a user sees a GitHub OAuth dialog requesting `repo:write` or `admin:org`, they pause. Enterprise security teams require longer approval cycles for write-access integrations. Read-only dialogs are one-click. For an open-source project that needs public adoption, the friction difference is significant.

### Compliance change management requirements

SOC 2 CC8 (Change Management) requires that changes to production systems be authorized, tested, and documented by a human. An AI agent that autonomously flips security settings would fail a CC8 review because there is no documented human authorization for the change. AuditPilot's Pending Action model — the agent suggests, the human authorizes, the human applies — is explicitly CC8-compliant.

---

## The Output Model

AuditPilot produces two categories of output:

**Downloadable files** — the agent produces the file and the human uses it at their discretion:
- SIG-Lite XLSX with draft answers
- Policy documents (Markdown + DOCX)
- Gap reports (Markdown)

**Pending Action cards** — the agent creates a card, the human applies the fix in the source tool:
- "Branch protection disabled on `main`. Setting to enable: [GitHub link]. Click to open."
- "MFA not enforced at org level. Setting: [GitHub link]."
- "Access review overdue. Draft email to managers: [inline draft]. Copy and send."

The human marks each card done after applying the fix. AuditPilot logs the timestamp and user ID (FR-039). It does not verify that the fix was actually applied — the human self-confirms. This matches how Vanta's remediation workflow operates.

---

## Consequences

### Positive
- Zero write-API blast radius; no agent bug can damage a production system
- Read-only OAuth dialogs are one-click; no enterprise approval friction
- CC8-compliant by design: every change has a documented human authorization
- Legal shield under AICPA UPAct: the system never performs an autonomous assurance action
- Clear, memorable product story: "reads your tools, drafts the fixes, you apply them"

### Negative
- Reduces the automation "wow factor" compared to a fully autonomous agent; sophisticated users may find the Pending Actions queue tedious for high-volume gap lists
- Cannot demonstrate automated remediation in the demo video; the demo must show the suggestion flow rather than the fix being applied
- Future contributors may be tempted to add "just one" write API call; the architectural constraint must be enforced via code review and CI (security-reviewer sub-agent on every PR)

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Full read-write automation** | Blast radius on agent bugs, AICPA UPAct ambiguity, CC8 non-compliance, slow enterprise OAuth approval. Rejected permanently. |
| **Selective write access for specific low-risk actions** | "Low-risk" is a judgment call that erodes over time. The architectural rule must be binary to be enforceable. If it is "no write except for X," the next PR adds Y, then Z. |
| **User-delegated write (user provides a PAT with write scope)** | The user delegates write access to the agent, which then acts autonomously. This preserves the legal ambiguity and the blast-radius problem. The delegation model does not change the risk. |
| **Write access with a mandatory approval step before execution** | This is essentially the Pending Action model but with the agent holding the write credential. If the approval step fails (network error, user closes browser), the agent has an unused write credential that could be exploited. Read-only is safer. |

---

