# syntax=docker/dockerfile:1.7
# =============================================================================
# AuditPilot Auditor — stub Dockerfile (Sprint 7 will add real logic)
# =============================================================================
# Build context is the repo root (see docker-compose.yml `context: .`).
# Refs: PLAN.md Sprint 7.
# =============================================================================

# ── base ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1
RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /app

# ── deps ─────────────────────────────────────────────────────────────────────
FROM base AS deps
COPY apps/auditor/pyproject.toml ./apps/auditor/pyproject.toml
WORKDIR /app/apps/auditor
RUN uv pip install --system --no-cache \
    'fastapi>=0.115' \
    'uvicorn[standard]>=0.30'

# ── dev ──────────────────────────────────────────────────────────────────────
FROM deps AS dev
WORKDIR /app
COPY apps/auditor ./apps/auditor
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["uvicorn", "apps.auditor.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

# ── prod ─────────────────────────────────────────────────────────────────────
FROM base AS prod
RUN groupadd -r appuser -g 1001 \
    && useradd -r -u 1001 -g appuser -m -d /home/appuser appuser
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
WORKDIR /app
COPY --chown=appuser:appuser apps/auditor ./apps/auditor
USER appuser
ENV PYTHONPATH=/app
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8001/health || exit 1
CMD ["uvicorn", "apps.auditor.main:app", "--host", "0.0.0.0", "--port", "8001"]
