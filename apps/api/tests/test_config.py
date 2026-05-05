"""
Tests for the Pydantic v2 Settings loader.

Acceptance (PLAN.md chunk 2.3):
- Missing DATABASE_URL (and other required fields) raises ValidationError
  with a clear field-by-field list so the operator can diagnose it.
- A fully populated environment constructs Settings() without error.

Refs: PLAN.md 0F.4, 2.3; ADR-0008.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from apps.api.config import Settings

_REQUIRED_KEYS = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "REDIS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_PUBLISHABLE_KEY",
    "GEMINI_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)

_VALID_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgres://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CLERK_SECRET_KEY": "sk_test_fake",
    "CLERK_PUBLISHABLE_KEY": "pk_test_fake",
    "GEMINI_API_KEY": "fake-gemini-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-fake",
    "LANGFUSE_SECRET_KEY": "sk-lf-fake",
}


@pytest.fixture
def blanked_env():
    """Run a test with every AuditPilot env var removed.

    pydantic-settings also reads from `.env` by default; we point it at an empty
    file to make sure the test is deterministic regardless of the repo .env.
    """
    keys_to_clear = list(_REQUIRED_KEYS) + [
        "DIRECT_URL",
        "LOG_LEVEL",
        "GIT_SHA",
        "POSTHOG_API_KEY",
        "POSTHOG_HOST",
        "OTLP_ENDPOINT",
        "OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
    ]
    with patch.dict(os.environ, {}, clear=False) as env:
        for k in keys_to_clear:
            env.pop(k, None)
        yield env


def test_missing_database_url_raises_clear_validation_error(blanked_env, tmp_path):
    """A missing DATABASE_URL must produce a ValidationError that names the field."""
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=str(empty_env_file))

    errors = excinfo.value.errors()
    missing_fields = {tuple(e["loc"]) for e in errors if e["type"] == "missing"}
    assert ("database_url",) in missing_fields, (
        f"Expected 'database_url' in missing-field list, got {missing_fields}"
    )
    assert len(errors) >= 4, (
        "ValidationError should enumerate every missing required field so the "
        f"operator can fix them in one pass; got only {len(errors)}"
    )


def test_valid_env_constructs_settings(blanked_env, tmp_path):
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    with patch.dict(os.environ, _VALID_ENV, clear=False):
        settings = Settings(_env_file=str(empty_env_file))

    assert settings.environment == "development"
    # database_url and redis_url are SecretStr (Sprint 3 day-0 chunk 3.0c) —
    # callers must explicitly unwrap.
    assert settings.database_url.get_secret_value() == _VALID_ENV["DATABASE_URL"]
    assert settings.redis_url.get_secret_value() == _VALID_ENV["REDIS_URL"]
    assert settings.gemini_api_key.get_secret_value() == "fake-gemini-key"
    assert settings.is_production is False


def test_posthog_key_alias_recognised(blanked_env, tmp_path):
    """NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN must populate posthog_api_key too.

    This is the env var shape the operator's .env already ships with (frontend
    and backend share the same PostHog project API key, `phc_...`).
    """
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    combined = dict(_VALID_ENV)
    combined["NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN"] = "phc_test_fake"

    with patch.dict(os.environ, combined, clear=False):
        settings = Settings(_env_file=str(empty_env_file))

    assert settings.posthog_api_key == "phc_test_fake"


def test_otel_exporter_alias_recognised(blanked_env, tmp_path):
    """OTEL_EXPORTER_OTLP_ENDPOINT must populate Settings.otlp_endpoint.

    This is the canonical OpenTelemetry SDK variable name; the operator's
    .env uses it so config.py has to recognise it.
    """
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    combined = dict(_VALID_ENV)
    combined["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://otlp.example/otlp"
    combined["OTEL_EXPORTER_OTLP_HEADERS"] = "Authorization=Basic deadbeef"

    with patch.dict(os.environ, combined, clear=False):
        settings = Settings(_env_file=str(empty_env_file))

    assert settings.otlp_endpoint == "https://otlp.example/otlp"
    assert settings.otlp_headers == "Authorization=Basic deadbeef"


def test_effective_direct_url_falls_back_to_database_url(blanked_env, tmp_path):
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    with patch.dict(os.environ, _VALID_ENV, clear=False):
        settings = Settings(_env_file=str(empty_env_file))

    assert (
        settings.effective_direct_url.get_secret_value()
        == settings.database_url.get_secret_value()
    )


def test_repr_redacts_database_and_redis_url_passwords(blanked_env, tmp_path):
    """Sprint 3 day-0 chunk 3.0c — verify SecretStr typing actually redacts.

    Pydantic redacts ``SecretStr`` in ``repr()`` and ``model_dump()``.
    This test pins the contract so a future refactor that changes
    ``database_url`` / ``redis_url`` back to plain ``str`` would fail loudly.
    """

    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")

    leaky_env = dict(_VALID_ENV)
    leaky_env["DATABASE_URL"] = "postgres://user:supersecretpassword@host/db"
    leaky_env["REDIS_URL"] = "rediss://default:redispassword123@host:6379"

    with patch.dict(os.environ, leaky_env, clear=False):
        settings = Settings(_env_file=str(empty_env_file))

    rendered = repr(settings)
    assert "supersecretpassword" not in rendered, (
        "database_url password leaked into repr(Settings)"
    )
    assert "redispassword123" not in rendered, (
        "redis_url password leaked into repr(Settings)"
    )

    dumped = str(settings.model_dump())
    assert "supersecretpassword" not in dumped, (
        "database_url password leaked into model_dump()"
    )
    assert "redispassword123" not in dumped, (
        "redis_url password leaked into model_dump()"
    )
