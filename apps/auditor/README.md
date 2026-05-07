# auditor

AdversarialAuditor service for AuditPilot. Runs the read-only LLM agent that
challenges weak evidence in a readiness scan and returns findings to the
AuditOrchestrator.

This package is read-only by design: it never writes to LangGraph state and
never calls write APIs on connected systems.
