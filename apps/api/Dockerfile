# syntax=docker/dockerfile:1.7
# =============================================================================
# AuditPilot API — multi-stage Dockerfile
# =============================================================================
# Build context is the repo root (see docker-compose.yml `context: .`), so
# paths are relative to /path/to/auditpilot/.
#
# Stages:
#   base  — Python 3.12-slim with uv installed, nothing project-specific
#   deps  — resolved Python dependencies shared between dev and prod
#   dev   — hot-reload uvicorn for `docker compose up api` during development
#   prod  — minimal non-root runtime for Cloud Run (Sprint 11)
#
# Refs: PLAN.md chunk 2.2, ADR-0008.
# =============================================================================

# ─── base ────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /app

# ─── deps ────────────────────────────────────────────────────────────────────
# Install only pyproject.toml first so Docker layer caching works: changes to
# source code don't invalidate the dependency layer.
FROM base AS deps
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
WORKDIR /app/apps/api
RUN uv pip install --system --no-cache \
    'fastapi>=0.115' \
    'uvicorn[standard]>=0.30' \
    'pydantic>=2.0' \
    'pydantic-settings>=2.0' \
    'pydantic-ai>=1.0,<2.0' \
    'langgraph>=1.0,<2.0' \
    'langgraph-checkpoint-postgres>=1.0' \
    'litellm>=1.50' \
    'langfuse>=3.0' \
    'opentelemetry-sdk>=1.25' \
    'opentelemetry-exporter-otlp>=1.25' \
    'opentelemetry-exporter-otlp-proto-http>=1.25' \
    'opentelemetry-instrumentation-fastapi>=0.46b0' \
    'posthog>=3.0' \
    'psycopg[binary]>=3.1' \
    'redis>=5.0' \
    'httpx>=0.27' \
    'boto3>=1.34' \
    'python-multipart>=0.0.9' \
    'python-jose[cryptography]>=3.3' \
    'pyyaml>=6.0'

# ─── dev ─────────────────────────────────────────────────────────────────────
FROM deps AS dev
RUN uv pip install --system --no-cache \
    'pytest>=8.0' \
    'pytest-asyncio>=0.23' \
    'pytest-cov>=5.0' \
    'ruff>=0.6' \
    'mypy>=1.10' \
    'fakeredis[lua]>=2.26' \
    'respx>=0.21'
WORKDIR /app
COPY apps/api ./apps/api
COPY packages ./packages
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/apps/api"]

# ─── prod ────────────────────────────────────────────────────────────────────
FROM base AS prod
RUN groupadd -r appuser -g 1001 \
    && useradd -r -u 1001 -g appuser -m -d /home/appuser appuser

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

WORKDIR /app
COPY --chown=appuser:appuser apps/api ./apps/api
COPY --chown=appuser:appuser packages ./packages

USER appuser
ENV PYTHONPATH=/app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
