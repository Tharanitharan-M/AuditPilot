"""AuditPilot orchestration agents.

The LangGraph graph coordinates these three agents (ADR-0002):
- AuditOrchestrator (this package, `orchestrator.py`)
- AdversarialAuditor (separate service, `apps/auditor/`)
- HumanReviewGate (a graph node, not an LLM-powered agent)

Sprint 2 scope: orchestrator stub that wires Pydantic AI to the
compliance-kb-mcp.lookup_control tool. Full MCP transport via
`langchain-mcp-adapters` ships in Sprint 4 chunk 4.3.
"""
