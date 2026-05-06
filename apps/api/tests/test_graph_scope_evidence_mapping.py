"""
Sprint 4 chunks 4.4a + 4.4b + 4.5 — graph node integration tests.

These tests exercise the full ``run_readiness_scan`` path through the
new four-node graph (validate_scope → collect_evidence → map_controls →
orchestrator) without spawning the MCP subprocess. ``FunctionModel``
choreographs the LLM turns; an injected stub evidence collector
guarantees deterministic output.

Acceptance contracts:
- 4.4a: empty repo_include_list short-circuits the run with the
  refusal message and ``rejection_reasons`` updated.
- 4.4b: with N scoped repos, evidence collection produces N rows in
  parallel and each row's source_uri matches the requested repo.
- 4.5: control_map is non-empty after a scan and contains entries for
  the seeded TSC clauses (CC6.1 / CC6.2 / CC7.1 from the curated
  source-type → TSC seed map).
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.api.checkpointer import memory_checkpointer
from apps.api.graph import build_graph
from apps.api.services.evidence_collector import default_evidence_collector


@pytest.fixture
def constant_text_model() -> FunctionModel:
    """LLM stub that always emits a fixed assistant text — no tool calls."""

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[TextPart(content="Scan summary: 7 TSC clauses populated.")]
        )

    return FunctionModel(fn)


# ── 4.4a — empty-scope refusal ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chunk_4_4a_empty_scope_refuses_run_readiness_scan(
    constant_text_model: FunctionModel,
) -> None:
    """ScanRunValidationError flow: empty repo_include_list aborts the run."""

    graph = build_graph(memory_checkpointer(), model=constant_text_model)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="run my readiness scan")],
            "intent": "run_readiness_scan",
            "repo_include_list": [],
        },
        config={"configurable": {"thread_id": "test-empty-scope-4.4a"}},
    )

    assert result["current_step"] == "empty_scope_refusal"
    assert "empty_repo_scope" in result["rejection_reasons"]
    # No evidence was collected, no control_map was populated.
    assert result.get("evidence", []) == []
    assert result.get("control_map", {}) == {}
    # Refusal message reaches the user.
    last = result["messages"][-1]
    assert "Pick at least one repo" in str(last.content)


# ── 4.4b — parallel evidence collection over scoped repos ───────────────────


@pytest.mark.asyncio
async def test_chunk_4_4b_collects_evidence_for_each_scoped_repo(
    constant_text_model: FunctionModel,
) -> None:
    """Evidence rows materialise one-per-repo, source_uri ties to repo id."""

    repo_ids = ["111", "222", "333"]

    graph = build_graph(memory_checkpointer(), model=constant_text_model)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="run my readiness scan")],
            "intent": "run_readiness_scan",
            "repo_include_list": repo_ids,
        },
        config={"configurable": {"thread_id": "test-evidence-4.4b"}},
    )

    # The default stub collector emits exactly one row per repo.
    assert len(result["evidence"]) == len(repo_ids), (
        f"expected {len(repo_ids)} evidence rows; got {len(result['evidence'])}"
    )

    # Every row's source_uri must match a scoped repo, and every scoped
    # repo must appear at least once. This is the chunk 4.4b acceptance
    # criterion verbatim.
    repo_uris = {f"github://{rid}" for rid in repo_ids}
    seen_uris = {ev.source_uri for ev in result["evidence"]}
    assert seen_uris == repo_uris, (
        f"scope mismatch: scoped={repo_uris}, seen={seen_uris}"
    )


@pytest.mark.asyncio
async def test_chunk_4_4b_per_repo_failures_isolate(
    constant_text_model: FunctionModel,
) -> None:
    """A 404 on one repo must not abort the whole scan."""

    async def flaky_collector(*, repo_id: str, scan_run_id: str | None = None):
        if repo_id == "boom":
            raise RuntimeError("simulated GitHub 404")
        # Reuse the default stub for non-failing repos.
        return await default_evidence_collector(
            repo_id=repo_id, scan_run_id=scan_run_id
        )

    graph = build_graph(
        memory_checkpointer(),
        model=constant_text_model,
        evidence_collector=flaky_collector,
    )
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="run my readiness scan")],
            "intent": "run_readiness_scan",
            "repo_include_list": ["111", "boom", "333"],
        },
        config={"configurable": {"thread_id": "test-flaky-4.4b"}},
    )

    # Two rows, not three — the failing repo dropped out.
    assert len(result["evidence"]) == 2
    seen = {ev.source_uri for ev in result["evidence"]}
    assert seen == {"github://111", "github://333"}


# ── 4.5 — keystone: evidence → control assessments ─────────────────────────


@pytest.mark.asyncio
async def test_chunk_4_5_control_map_populated_per_active_tsc(
    constant_text_model: FunctionModel,
) -> None:
    """control_map contains one ControlAssessment per active TSC clause."""

    graph = build_graph(memory_checkpointer(), model=constant_text_model)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="run my readiness scan")],
            "intent": "run_readiness_scan",
            "repo_include_list": ["555"],
        },
        config={"configurable": {"thread_id": "test-mapping-4.5"}},
    )

    cm = result["control_map"]

    # The Sprint-4 stub evidence is source_type='mock', which seeds CC6.1,
    # CC6.2, CC7.1. All three must appear in the populated control_map.
    for tsc in ("CC6.1", "CC6.2", "CC7.1"):
        assert tsc in cm, f"expected TSC {tsc} in control_map; got {sorted(cm)}"
        assessment = cm[tsc]
        # Status promoted past unknown thanks to the seeded confidence.
        assert assessment.status == "partial", (
            f"{tsc} status should be 'partial' for stub evidence; got "
            f"{assessment.status!r}"
        )
        # Confidence above the seed floor.
        assert assessment.confidence >= 0.6, (
            f"{tsc} confidence {assessment.confidence} below seed floor"
        )
        # nist_800_53_refs is non-empty (lookup_by_soc2_tsc returned controls).
        assert assessment.nist_800_53_refs, (
            f"{tsc} has no supporting NIST refs; the lookup_by_soc2_tsc "
            f"call must have returned at least one control."
        )
        # The single evidence row's id appears in evidence_ids.
        assert len(assessment.evidence_ids) >= 1
        assert assessment.evidence_ids[0].startswith("ev_stub_")


@pytest.mark.asyncio
async def test_chunk_4_5_free_chat_skips_evidence_pipeline(
    constant_text_model: FunctionModel,
) -> None:
    """Free chat must NOT trigger evidence collection or control mapping."""

    graph = build_graph(memory_checkpointer(), model=constant_text_model)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="hello")],
            "intent": "free_chat",
            "repo_include_list": [],
        },
        config={"configurable": {"thread_id": "test-free-chat-4.5"}},
    )

    # The graph went directly to orchestrator without populating
    # evidence or control_map.
    assert result.get("evidence", []) == []
    assert result.get("control_map", {}) == {}
    assert result["current_step"] == "orchestrator_complete"
