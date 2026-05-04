"""Opt-in integration test: PromptLoader against the live Langfuse API.

Proves ADR-0011's "source of truth is YAML, Langfuse holds the same
content" claim against real Langfuse Cloud. Creates a throwaway prompt
named ``auditpilot-sprint2-probe-<uuid>`` with the ``production`` label,
reads it back through :class:`PromptLoader`, and asserts the returned
payload round-trips cleanly.

Skipped unless::

    pytest apps/api/tests/test_prompt_loader_langfuse.py -m integration

and the ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` env vars are
present. The test cleans up after itself where the SDK supports it; on
Langfuse the prompt remains in the project's prompt table (versions are
append-only).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from apps.api.agents.prompts import PromptLoader, PromptSource

pytestmark = pytest.mark.integration


@pytest.fixture
def langfuse_client():
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
    if not public_key or not secret_key:
        pytest.skip("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set")

    from langfuse import Langfuse

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    try:
        yield client
    finally:
        client.flush()


async def test_round_trip_prompt_through_langfuse_cloud(
    langfuse_client, tmp_path: Path
) -> None:
    probe_name = f"auditpilot-sprint2-probe-{uuid.uuid4().hex[:8]}"

    langfuse_client.create_prompt(
        name=probe_name,
        type="text",
        prompt="Sprint 2 probe — {{subject}}",
        labels=["production"],
        config={
            "name": probe_name,
            "version": 1,
            "model": "gemini-2.5-flash-lite",
            "temperature": 0.0,
            "max_tokens": 1024,
        },
    )

    loader = PromptLoader(langfuse_client, local_dir=tmp_path)
    compiled = await loader.load(probe_name)

    assert compiled.source == PromptSource.LANGFUSE
    assert compiled.definition.name == probe_name
    assert "Sprint 2 probe" in compiled.system
    rendered = compiled.definition.format_system({"subject": "readiness"})
    assert "readiness" in rendered
