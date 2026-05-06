"""Test-suite-wide fixtures and environment seeding.

Sprint 5 follow-up — robust test env setup
==========================================
``Settings`` (pydantic-settings v2) requires a handful of fields with
no defaults: ``REDIS_URL``, ``DATABASE_URL``, ``CLERK_*``, ``GEMINI_*``,
``LANGFUSE_*``. Without them, the model raises ``ValidationError`` at
construction time, which propagates through ``get_settings()``
(``@lru_cache(maxsize=1)``) into every test that touches ``/chat``.

Several test modules (``test_chat_sse.py``, ``test_chat_rate_limit.py``,
``test_langfuse_sse.py``) used per-test ``patch.dict(os.environ, ...)``
to provide these. That was fragile — ``patch.dict`` runs at fixture
setup, AFTER pytest has already collected the module and AFTER any
top-level import of ``apps.api.main`` (which itself imports
``apps.api.config``). When pytest is invoked without the env vars
already exported in the shell, ``Settings`` instantiation during
``ASGITransport`` lifespan can race with the patch and fail.

This conftest seeds ``os.environ`` at COLLECTION time (before any test
module is imported) with safe placeholder values. Tests that need to
override specific keys still can — the ``setdefault`` semantics mean
a real shell-exported value wins. Tests that need to *unset* a value
must use ``monkeypatch.delenv`` explicitly.

Refs: PLAN.md Sprint 5 follow-up — test env hygiene.
"""

from __future__ import annotations

import os

# Seed BEFORE pytest imports any test module — collection happens after
# this file is parsed but before test modules are.
_DEFAULT_TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgres://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CLERK_SECRET_KEY": "sk_test_fake",
    "CLERK_PUBLISHABLE_KEY": "pk_test_fake",
    "CLERK_JWKS_URL": "https://example.clerk.accounts.dev/.well-known/jwks.json",
    "CLERK_ISSUER_URL": "https://example.clerk.accounts.dev",
    "GEMINI_API_KEY": "fake-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-fake",
    "LANGFUSE_SECRET_KEY": "sk-lf-fake",
    # Disable Langfuse OTel exporter in tests (no live endpoint).
    "LANGFUSE_HOST": "https://example.invalid",
}

for _k, _v in _DEFAULT_TEST_ENV.items():
    os.environ.setdefault(_k, _v)
