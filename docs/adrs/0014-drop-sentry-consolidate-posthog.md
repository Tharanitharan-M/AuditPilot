# ADR-0014: Drop Sentry, Consolidate Error Tracking into PostHog

**Date:** 2026-05-04
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Amends:** [ADR-0009](0009-observability-stack.md) (seven-layer stack → five-layer stack)
**Refs:** ADR-0009; PLAN.md Sprint 2 (chunk 2.13), Sprint 3 (chunk 3.10)

---

## Context and Problem Statement

ADR-0009 established a seven-layer observability stack including both Sentry (error tracking) and PostHog (product analytics + session replay). The original rationale highlighted the Sentry + PostHog auto-correlation as a "killer combination" — errors in Sentry linked to session replays in PostHog and vice versa.

In 2025, PostHog shipped consolidated error tracking with auto-correlated session replays natively. PostHog now captures frontend JavaScript exceptions and backend Python errors, attaches them to session replay timelines, and provides stack traces with source-map support — capabilities that previously required Sentry as a separate tool.

The question: for a single-tenant portfolio project on free tier, does running Sentry alongside PostHog still add signal, or does it duplicate the error-tracking surface?

---

## Decision

**Drop Sentry from the observability stack. Use PostHog as the single error tracking + product analytics + session replay tool.**

The stack moves from seven tools to five:


| Layer                                               | Tool                              | Free tier                                   |
| --------------------------------------------------- | --------------------------------- | ------------------------------------------- |
| LLM observability                                   | Langfuse Cloud Hobby              | 50,000 traces/month                         |
| Error tracking + product analytics + session replay | PostHog Cloud Free                | 1,000,000 events/month; 5,000 replays/month |
| Infrastructure metrics                              | Grafana Cloud Free                | 10,000 series, 50 GB logs/month             |
| Web analytics + vitals                              | Vercel Analytics + Speed Insights | Free with Hobby                             |
| Uptime + status page                                | Better Stack Free                 | 10 monitors, public status page             |


**Total: $0/month.**

### What changes

- **PLAN.md Sprint 2 chunk 2.13:** Sentry Python SDK init replaced with PostHog Python SDK init for backend error tracking.
- **PLAN.md Sprint 3 chunk 3.10:** Sentry browser SDK removed from `instrumentation-client.ts`. PostHog client handles error capture + product analytics + session replay.
- `**.env.example`:** `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` removed. `POSTHOG_API_KEY` and `POSTHOG_HOST` added for backend Python SDK usage.
- `**SERVICE_SETUP.md`:** Sentry signup step removed from Phase 3.
- **Context docs:** All seven-tool references updated to five-tool stack.

---

## Rationale

### Why PostHog alone is sufficient for this project

1. **PostHog consolidated error tracking in 2025.** PostHog now captures JS exceptions and Python errors with stack traces, source maps, and auto-correlation to session replays — the exact capabilities that justified Sentry in ADR-0009.
2. **Single-tenant portfolio project.** AuditPilot is a reference architecture with one maintainer. There is no on-call rotation, no error-triage team, no Slack integration for error alerts to multiple channels. Sentry's strengths — issue grouping, assignment workflows, release tracking, performance monitoring with distributed tracing — are designed for multi-team production deployments. They add configuration overhead without adding signal at this scale.
3. **Error-to-replay correlation is now native in PostHog.** The original "killer combination" was cross-tool correlation between Sentry errors and PostHog replays. PostHog now provides this within a single tool. The cross-tool integration is no longer the differentiator it was when ADR-0009 was written.
4. **One fewer vendor to configure and monitor.** Dropping Sentry removes three environment variables (`SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_AUTH_TOKEN`), two Sentry projects to maintain, source-map upload configuration, and the Sentry free-tier budget (5,000 errors/month shared between frontend and backend).

### When Sentry is still the right choice

Sentry remains the better choice for:

- **Multi-team production deployments** where dedicated error triage tooling, issue assignment, and release tracking matter
- **High-volume error environments** where Sentry's deduplication and grouping algorithms outperform PostHog's
- **Performance monitoring** where Sentry's distributed tracing and transaction-level profiling add value beyond OTel + Grafana

If AuditPilot evolves beyond a single-tenant reference architecture into a multi-team production deployment, re-evaluate this decision.

---

## Consequences

### Positive

- Five tools instead of seven — less configuration surface, fewer accounts to monitor
- Three fewer environment variables to manage
- No Sentry free-tier budget to watch (the shared 5,000 errors/month limit was a potential source of silent data loss)
- Error-to-replay correlation stays within one tool — simpler mental model for debugging
- PostHog's 1,000,000 events/month free tier is generous enough to absorb the error-tracking load

### Negative

- PostHog's error grouping and deduplication is less mature than Sentry's — noisy error sources may be harder to triage
- No Sentry-style release tracking (which version introduced this error?) — must rely on Langfuse trace metadata or git sha in error context
- If PostHog's error tracking regresses or their pricing changes, the project has no fallback error tracker without re-adding a vendor
- The "Sentry + PostHog killer combo" narrative from ADR-0009 was a strong portfolio talking point — replaced with "PostHog as single pane of glass" which is a valid but different story

---

## Alternatives Considered


| Option                        | Why rejected                                                                                                                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep Sentry + PostHog**     | Duplicates error-tracking surface. Two tools to configure, two free tiers to watch, two dashboards to check. The cross-tool correlation that justified the pairing is now available natively in PostHog. |
| **Drop PostHog, keep Sentry** | Loses product analytics (funnels, retention), session replay volume (5,000 vs PostHog's 5,000 — tie), and feature flags. PostHog's free tier is more generous overall.                                   |
| **Replace both with Datadog** | $31/host/month minimum. Violates $0/month constraint (SRS CON-005).                                                                                                                                      |


---

