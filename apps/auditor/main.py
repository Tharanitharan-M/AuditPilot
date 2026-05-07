"""AdversarialAuditor stub — health endpoint only until Sprint 7."""

from fastapi import FastAPI

app = FastAPI(title="auditpilot-auditor", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auditor"}
