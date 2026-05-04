"""
Tests for the /health endpoint.

Refs: PLAN.md chunk 2.1.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgres://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CLERK_SECRET_KEY": "sk_test_fake",
    "CLERK_PUBLISHABLE_KEY": "pk_test_fake",
    "GEMINI_API_KEY": "fake-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-fake",
    "LANGFUSE_SECRET_KEY": "sk-lf-fake",
}


@pytest.fixture(autouse=True)
def _env():
    """Inject required env vars and clear the settings cache between tests."""
    from apps.api.main import get_settings

    with patch.dict(os.environ, _TEST_ENV, clear=False):
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    from apps.api.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_health_body_shape(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "git_sha" in body


@pytest.mark.anyio
async def test_debug_raise_500(client: AsyncClient) -> None:
    resp = await client.get("/debug/raise-500")
    assert resp.status_code == 500
