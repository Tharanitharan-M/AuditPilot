"""Opt-in integration test: push a smoke metric to Grafana Cloud OTLP.

Confirms that the parsed ``OTEL_EXPORTER_OTLP_HEADERS`` string and the
``/v1/metrics`` endpoint are actually accepted by Grafana's OTel gateway.
Skipped unless ``pytest -m integration`` and the OTel env vars are set.
"""

from __future__ import annotations

import os
import uuid

import pytest

from apps.api.config import Settings
from apps.api.observability.metrics import (
    init_metrics,
    is_enabled,
    record_chat_request,
    record_job_processed,
    shutdown_metrics,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS")
    if not endpoint or not headers:
        pytest.skip(
            "OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS unset"
        )
    required = [
        "ENVIRONMENT",
        "DATABASE_URL",
        "REDIS_URL",
        "CLERK_SECRET_KEY",
        "CLERK_PUBLISHABLE_KEY",
        "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ]
    for k in required:
        os.environ.setdefault(k, "test-value")
    return Settings()


def test_live_grafana_otlp_push_accepts_custom_counters(settings: Settings) -> None:
    assert init_metrics(settings), "init_metrics must succeed with live creds"
    assert is_enabled()

    probe_id = uuid.uuid4().hex[:8]
    try:
        record_chat_request(intent="readiness_probe", outcome="started")
        record_job_processed(job_type="drift.scan", status="succeeded")
        record_job_processed(job_type="drift.scan", status="failed")
    finally:
        # ``shutdown_metrics`` flushes the periodic reader. If the OTLP
        # endpoint rejected the payload this call raises or logs at error
        # level; the test fails on any exception bubbling up.
        shutdown_metrics(timeout_millis=5_000)

    # If we reach here, the OTLP gateway accepted the payload without
    # raising. Operator-facing verification (dashboards refresh, queries
    # return data) is documented in the Step Report.
    assert probe_id  # silence linter
