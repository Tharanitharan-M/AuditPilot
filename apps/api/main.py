"""
AuditPilot API — FastAPI entrypoint
====================================
Initialises PostHog (if API key configured), then creates the FastAPI app
with a /health probe and observability middleware.

Refs: PLAN.md chunk 2.1, chunk 2.13, ADR-0009, ADR-0014.
"""

from __future__ import annotations

import atexit
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from posthog import Posthog
from fastapi import FastAPI

from apps.api.config import Settings

posthog_client: Posthog | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _init_posthog(settings: Settings) -> None:
    global posthog_client
    api_key = settings.posthog_api_key or os.environ.get("POSTHOG_API_KEY")
    if api_key:
        posthog_client = Posthog(
            project_api_key=api_key,
            host=settings.posthog_host,
            enable_exception_autocapture=True,
        )
        atexit.register(posthog_client.shutdown)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _init_posthog(settings)
    if posthog_client:
        posthog_client.capture(
            distinct_id="server",
            event="api_started",
            properties={"version": "0.1.0", "environment": settings.environment},
        )
    yield
    if posthog_client:
        posthog_client.capture(
            distinct_id="server",
            event="api_shutdown",
            properties={"version": "0.1.0", "environment": settings.environment},
        )
        posthog_client.flush()


app = FastAPI(
    title="AuditPilot API",
    version="0.1.0",
    description="SOC 2 readiness reference architecture — orchestration backend",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": "0.1.0",
        "git_sha": settings.git_sha,
    }


@app.get("/debug/raise-500")
async def debug_raise_500() -> None:
    """PostHog verification endpoint — raises an unhandled error on purpose."""
    if posthog_client:
        posthog_client.capture(
            distinct_id="server",
            event="debug_error_triggered",
            properties={"endpoint": "/debug/raise-500"},
        )
    division_by_zero = 1 / 0  # noqa: F841
