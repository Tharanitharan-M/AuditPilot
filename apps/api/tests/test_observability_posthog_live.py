"""Opt-in integration test: actually POST an event to PostHog.

Skipped unless:

* ``pytest -m integration`` is passed (default pytest run excludes this).
* ``POSTHOG_API_KEY`` / ``NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN`` is set.

The test does not read the event back (PostHog's query API is rate-
limited and eventually-consistent), so the assertion is "capture did
not raise and ``flush()`` returned" — i.e. the SDK accepted the payload.
Operator verification of the event reaching the UI is documented in
the Step Report.
"""

from __future__ import annotations

import os
import uuid

import pytest

from apps.api.config import Settings
from apps.api.observability.posthog import (
    capture_event,
    init_posthog,
    shutdown_posthog,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    required_envs = [
        "ENVIRONMENT",
        "DATABASE_URL",
        "REDIS_URL",
        "CLERK_SECRET_KEY",
        "CLERK_PUBLISHABLE_KEY",
        "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ]
    for key in required_envs:
        os.environ.setdefault(key, "test-value")
    posthog_key = (
        os.environ.get("POSTHOG_API_KEY")
        or os.environ.get("NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN")
        or os.environ.get("NEXT_PUBLIC_POSTHOG_KEY")
    )
    if not posthog_key:
        pytest.skip("No PostHog project token available.")
    os.environ["POSTHOG_API_KEY"] = posthog_key
    return Settings()


def test_capture_event_reaches_posthog(settings: Settings) -> None:
    client = init_posthog(settings)
    assert client is not None, "init_posthog should return a client when key is set"

    try:
        capture_event(
            client,
            "auditpilot.sprint2.smoke",
            properties={
                "probe_id": uuid.uuid4().hex,
                "environment": settings.environment,
                "component": "apps/api",
            },
        )
        client.flush()
    finally:
        shutdown_posthog(client)
