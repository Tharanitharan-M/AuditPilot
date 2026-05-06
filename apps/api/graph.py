"""
LangGraph graph assembly
========================
Sprint 4 expands the Sprint-2 single-node graph into a four-node pipeline
for ``run_readiness_scan`` runs while keeping the free-chat path single-
node. The graph layout is:

  START
    └── validate_scope          (chunk 4.4a — empty-scope refusal)
          ├── (intent=free_chat) ──→ orchestrator ──→ END
          ├── (empty scope)      ──→ END (refusal already in state)
          └── (scoped scan)      ──→ collect_evidence  (chunk 4.4b)
                                       └── map_controls (chunk 4.5)
                                             └── orchestrator ──→ END

Single-writer invariant (ADR-0002): every node returns a *delta* — never
mutates ``state`` in place. The reducer on ``messages`` appends; other
fields use last-writer-wins. The orchestrator agent itself remains the
only node that talks to the LLM.

Refs: PLAN.md chunks 2.6, 4.4a, 4.4b, 4.5; ADR-0001; ADR-0002; ADR-0007;
ADR-0013; system-design.md 3.2, 6.4.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model

from apps.api.agents.orchestrator import (
    OrchestratorDeps,
    build_orchestrator_agent,
)
from apps.api.services.control_mapping import map_evidence_to_controls
from apps.api.services.evidence_collector import (
    EvidenceCollector,
    default_evidence_collector,
)
from apps.api.state import (
    SCOPE_REQUIRED_INTENTS,
    AuditPilotState,
    ControlAssessment,
    Evidence,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_EMPTY_SCOPE_REFUSAL_TEXT = (
    "Pick at least one repo to scan. Open the connector card on your "
    "dashboard and click \"Configure scope\" to choose the repos you want "
    "AuditPilot to read."
)


def build_graph(
    checkpointer: BaseCheckpointSaver,
    *,
    model: Model | str = "test",
    mcp_toolset: bool = False,
    evidence_collector: EvidenceCollector | None = None,
):
    """Compile the orchestrator graph against the given checkpointer.

    The returned `CompiledGraph` exposes async APIs (`ainvoke`, `astream`,
    `astream_events`) that chunk 2.7's SSE endpoint consumes. Checkpointing
    is automatic when the caller supplies a ``thread_id`` in the config.

    Parameters
    ----------
    mcp_toolset : bool
        Sprint 4 chunk 4.3. When True, the orchestrator's underlying
        Pydantic AI agent registers ``compliance-kb-mcp`` as a stdio
        MCP toolset. The /chat handler in ``apps.api.main`` sets this
        to True in production; unit tests leave it False so they don't
        spawn a subprocess.
    evidence_collector : EvidenceCollector | None
        Sprint 4 chunk 4.4b. Per-repo evidence-fetch coroutine.
        Defaults to the Sprint-4 stub that returns a placeholder
        Evidence row per repo; Sprint 5 chunk 5.3+ replaces this with
        real GitHub MCP calls (branch protection, MFA, code scanning,
        secret scanning, Dependabot).
    """

    collector: EvidenceCollector = evidence_collector or default_evidence_collector
    graph: StateGraph[AuditPilotState] = StateGraph(AuditPilotState)

    # ────────────────────────────────────────────────────────────────────
    # validate_scope (chunk 4.4a)
    # ────────────────────────────────────────────────────────────────────

    async def validate_scope_node(state: AuditPilotState) -> dict[str, Any]:
        """Refuse the run when the intent requires scope and none is set.

        Replaces the inline Sprint-3.5 guard previously inside
        ``orchestrator_node``. Lifting it into its own node lets the
        graph branch early — for ``run_readiness_scan``, downstream
        nodes (collect_evidence, map_controls) only run after this
        guard has cleared.

        python-reviewer F3 — every node opens a span on every path so
        observability covers the happy case as well as the refusal.
        """

        if not state.messages:
            return {}

        with tracer.start_as_current_span("graph.validate_scope") as span:
            span.set_attribute("scope.intent", state.intent or "")
            span.set_attribute(
                "scope.repo_include_count", len(state.repo_include_list)
            )
            scope_required = state.intent in SCOPE_REQUIRED_INTENTS
            span.set_attribute("scope.required", scope_required)

            if scope_required and not state.repo_include_list:
                span.set_attribute("scope.result", "refused")
                return {
                    "messages": [AIMessage(content=_EMPTY_SCOPE_REFUSAL_TEXT)],
                    "current_step": "empty_scope_refusal",
                    "rejection_reasons": [
                        *state.rejection_reasons,
                        "empty_repo_scope",
                    ],
                }
            span.set_attribute("scope.result", "validated")
            return {"current_step": "scope_validated"}

    # ────────────────────────────────────────────────────────────────────
    # collect_evidence (chunk 4.4b)
    # ────────────────────────────────────────────────────────────────────

    async def collect_evidence_node(state: AuditPilotState) -> dict[str, Any]:
        """Collect evidence in parallel across the user's scoped repos.

        Sprint 4 contract:
        - Iterates ONLY over ``state.repo_include_list`` — never the
          full org inventory (ADR-0015).
        - Concurrent dispatch via ``asyncio.gather`` so the wall-clock
          time for N repos is dominated by the slowest single fetch.
        - Per-repo failures are isolated (``return_exceptions=True``).
          A single 404 on one repo does not abort the whole scan.

        Returns a delta with the new evidence rows. The reducer
        appends to ``state.evidence`` because LangGraph's default merge
        for list fields is overwrite — we therefore return the FULL
        composed evidence list (existing + new) so the next node sees
        everything from this run.
        """

        with tracer.start_as_current_span("graph.collect_evidence") as span:
            span.set_attribute(
                "scope.repo_include_count", len(state.repo_include_list)
            )
            span.set_attribute("scan_run_id", state.scan_run_id or "")

            tasks = [
                collector(repo_id=repo_id, scan_run_id=state.scan_run_id)
                for repo_id in state.repo_include_list
            ]
            results: list[list[Evidence] | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            collected: list[Evidence] = []
            failed_repos: list[str] = []
            for repo_id, outcome in zip(
                state.repo_include_list, results, strict=False
            ):
                if isinstance(outcome, BaseException):
                    logger.warning(
                        "evidence.collect_failed repo_id=%s err=%r",
                        repo_id,
                        outcome,
                    )
                    failed_repos.append(repo_id)
                    continue
                collected.extend(outcome)

            span.set_attribute("evidence.collected_count", len(collected))
            span.set_attribute("evidence.failed_repo_count", len(failed_repos))

            return {
                "evidence": [*state.evidence, *collected],
                "current_step": "evidence_collected",
            }

    # ────────────────────────────────────────────────────────────────────
    # map_controls (chunk 4.5 — KEYSTONE)
    # ────────────────────────────────────────────────────────────────────

    async def map_controls_node(state: AuditPilotState) -> dict[str, Any]:
        """Map collected evidence to SOC 2 TSC clauses (NIST 800-53 backed).

        Sprint 4 chunk 4.5 — the first eval-measured node. Delegates
        the per-evidence retrieval + LLM-free mapping to
        ``apps.api.services.control_mapping.map_evidence_to_controls``,
        which uses BM25 over the curated NIST 800-53 catalog and the
        ADR-0013 SOC 2 TSC mapping table. The orchestrator does NOT
        call the LLM here; the cost story stays $0 for Sprint 4 unless
        a future eval shows we need re-ranking.

        Sprint 10 will add a per-evidence cache keyed on
        ``(user_id, content_hash, control_id, prompt_version, kb_version)``
        once Sprint 5 stands up the evidence-store-mcp persistence layer.
        """

        with tracer.start_as_current_span("graph.map_controls") as span:
            span.set_attribute("evidence.count", len(state.evidence))

            # python-reviewer F1 — `map_evidence_to_controls` is a
            # synchronous CPU-bound function (BM25 over a 1.17 MB
            # in-memory catalog). Even at moderate evidence counts the
            # inner loop blocks the event loop long enough to starve
            # the chunk-4.9 disconnect watcher (python-reviewer F2).
            # Push the work onto the thread pool so the loop stays
            # responsive.
            assessments = await asyncio.to_thread(
                map_evidence_to_controls, state.evidence
            )

            # Merge with anything already in state.control_map: later
            # writes override earlier ones BUT we accumulate
            # nist_800_53_refs and evidence_ids so re-runs grow the
            # provenance chain.
            merged: dict[str, ControlAssessment] = dict(state.control_map)
            for tsc_id, new_assessment in assessments.items():
                existing = merged.get(tsc_id)
                if existing is None:
                    merged[tsc_id] = new_assessment
                    continue
                merged[tsc_id] = ControlAssessment(
                    tsc_id=tsc_id,
                    status=new_assessment.status,
                    confidence=max(
                        existing.confidence, new_assessment.confidence
                    ),
                    nist_800_53_refs=_dedupe(
                        existing.nist_800_53_refs
                        + new_assessment.nist_800_53_refs
                    ),
                    evidence_ids=_dedupe(
                        existing.evidence_ids + new_assessment.evidence_ids
                    ),
                    rationale=new_assessment.rationale or existing.rationale,
                )

            span.set_attribute("control_map.tsc_clauses", len(merged))
            return {
                "control_map": merged,
                "current_step": "controls_mapped",
            }

    # ────────────────────────────────────────────────────────────────────
    # orchestrator (Sprint 2 + chunk 4.3 retained)
    # ────────────────────────────────────────────────────────────────────

    async def orchestrator_node(state: AuditPilotState) -> dict[str, Any]:
        """Run the Pydantic AI orchestrator agent for the current turn.

        Reads the latest human message from state, invokes the agent
        (with the MCP toolset when ``mcp_toolset`` is True), and returns
        the LangChain message delta.

        For ``run_readiness_scan`` runs the agent has already received
        ``state.evidence`` and ``state.control_map`` summaries through
        the system prompt; its job is to surface the scan summary the
        user reads in chat. For free chat the agent is a general
        readiness assistant.
        """

        if not state.messages:
            return {}

        with tracer.start_as_current_span("graph.orchestrator_node") as span:
            user_input = cast(str, state.messages[-1].content)
            deps = OrchestratorDeps(
                user_id=state.user_id,
                scan_run_id=state.scan_run_id,
            )

            # Sprint 4 polish — for the run_readiness_scan flow,
            # collect_evidence + map_controls have already populated
            # state.evidence and state.control_map. The SYSTEM_PROMPT in
            # apps/api/agents/orchestrator.py promises the LLM a
            # `SCAN CONTEXT` block summarising what the system prepared.
            # Build that block here and prepend it to the user input so
            # the LLM has something concrete to summarise instead of
            # inventing a phantom `run_readiness_scan` tool call.
            if (
                state.intent == "run_readiness_scan"
                and (state.control_map or state.evidence)
            ):
                scan_context = _format_scan_context(state)
                user_input = (
                    f"SCAN CONTEXT\n============\n{scan_context}\n\n"
                    f"USER REQUEST\n============\n{user_input}"
                )
                span.set_attribute("orchestrator.scan_context.injected", True)
                span.set_attribute(
                    "orchestrator.scan_context.evidence_count",
                    len(state.evidence),
                )
                span.set_attribute(
                    "orchestrator.scan_context.tsc_count",
                    len(state.control_map),
                )

            agent = build_orchestrator_agent(model, mcp_toolset=mcp_toolset)
            if mcp_toolset:
                async with agent:
                    result = await agent.run(user_input, deps=deps)
            else:
                result = await agent.run(user_input, deps=deps)

            span.set_attribute("orchestrator.output_preview", result.output[:120])
            span.set_attribute(
                "orchestrator.tools_used",
                len(deps.looked_up_controls),
            )

        new_lc_messages = _pydantic_ai_to_langchain_messages(result.new_messages())

        # The orchestrator's lookup_control calls produce additional
        # ControlAssessment rows; fold them into whatever map_controls
        # already produced upstream (run_readiness_scan path) or
        # state.control_map (free-chat path).
        control_map_delta: dict[str, ControlAssessment] = dict(state.control_map)
        for control in deps.looked_up_controls:
            for tsc_id in control.soc2_tsc_mappings:
                existing = control_map_delta.get(tsc_id)
                nist_refs = list(existing.nist_800_53_refs) if existing else []
                if control.id not in nist_refs:
                    nist_refs.append(control.id)
                control_map_delta[tsc_id] = ControlAssessment(
                    tsc_id=tsc_id,
                    status=existing.status if existing else "unknown",
                    confidence=existing.confidence if existing else 0.0,
                    nist_800_53_refs=nist_refs,
                    evidence_ids=list(existing.evidence_ids) if existing else [],
                    rationale=existing.rationale if existing else None,
                )

        return {
            "messages": new_lc_messages,
            "control_map": control_map_delta or state.control_map,
            "current_step": "orchestrator_complete",
        }

    # ────────────────────────────────────────────────────────────────────
    # Wire nodes
    # ────────────────────────────────────────────────────────────────────

    graph.add_node("validate_scope", validate_scope_node)
    graph.add_node("collect_evidence", collect_evidence_node)
    graph.add_node("map_controls", map_controls_node)
    graph.add_node("orchestrator", orchestrator_node)

    def _route_after_scope(state: AuditPilotState) -> str:
        """Conditional edge from validate_scope.

        Branches:
          - Refusal already minted → END.
          - run_readiness_scan with non-empty scope → collect_evidence.
          - Anything else (free chat, or scoped intent that passed) → orchestrator.
        """

        if state.current_step == "empty_scope_refusal":
            return END
        if (
            state.intent in SCOPE_REQUIRED_INTENTS
            and state.repo_include_list
        ):
            return "collect_evidence"
        return "orchestrator"

    graph.add_edge(START, "validate_scope")
    graph.add_conditional_edges(
        "validate_scope",
        _route_after_scope,
        {
            "collect_evidence": "collect_evidence",
            "orchestrator": "orchestrator",
            END: END,
        },
    )
    graph.add_edge("collect_evidence", "map_controls")
    graph.add_edge("map_controls", "orchestrator")
    graph.add_edge("orchestrator", END)

    return graph.compile(checkpointer=checkpointer)


def _dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving insertion order."""

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _format_scan_context(state: AuditPilotState) -> str:
    """Render evidence + control_map into a readable context block.

    The orchestrator's SYSTEM_PROMPT (Sprint 4 polish) describes a
    SCAN CONTEXT section the LLM should read in run_readiness_scan
    mode. This helper formats state.evidence and state.control_map
    into a deterministic block — sorted by TSC id, top control_map
    entries first — so the LLM can produce a faithful summary instead
    of hallucinating tool calls.
    """

    lines: list[str] = []

    # Evidence summary (compact — the LLM doesn't need every raw row).
    repo_uris = sorted(
        {ev.source_uri for ev in state.evidence if ev.source_uri is not None}
    )
    lines.append(f"Evidence collected: {len(state.evidence)} rows")
    if repo_uris:
        # Cap the list so a 500-repo scan doesn't blow up the prompt.
        head = ", ".join(repo_uris[:10])
        suffix = f", … (+{len(repo_uris) - 10} more)" if len(repo_uris) > 10 else ""
        lines.append(f"Source repos: {head}{suffix}")

    # Control assessments grouped by status, sorted by TSC id within each.
    if state.control_map:
        lines.append("")
        lines.append(
            f"Control assessments: {len(state.control_map)} TSC clauses populated"
        )
        by_status: dict[str, list[ControlAssessment]] = {}
        for assessment in state.control_map.values():
            by_status.setdefault(assessment.status, []).append(assessment)
        for status in ("failing", "partial", "passing", "unknown"):
            entries = by_status.get(status, [])
            if not entries:
                continue
            entries.sort(key=lambda a: a.tsc_id)
            lines.append(f"\n[{status.upper()}] ({len(entries)} clauses)")
            # Cap rendering at 12 entries per status to bound prompt size.
            for assessment in entries[:12]:
                refs = ", ".join(assessment.nist_800_53_refs[:6])
                if len(assessment.nist_800_53_refs) > 6:
                    refs += f", … (+{len(assessment.nist_800_53_refs) - 6} more)"
                lines.append(
                    f"  - {assessment.tsc_id} "
                    f"(confidence {assessment.confidence:.2f}, "
                    f"NIST 800-53 refs: {refs or 'none'})"
                )
            if len(entries) > 12:
                lines.append(f"  - … (+{len(entries) - 12} more {status})")

    return "\n".join(lines)


def _pydantic_ai_to_langchain_messages(pai_msgs: list) -> list[BaseMessage]:
    """Translate `result.new_messages()` into LangChain primitives.

    Pydantic AI message model:
      ModelRequest(UserPromptPart)  -> skip (user already in graph state)
      ModelResponse(ToolCallPart)   -> AIMessage(content="", tool_calls=[...])
      ModelRequest(ToolReturnPart)  -> ToolMessage(content=..., tool_call_id=...)
      ModelResponse(TextPart)       -> AIMessage(content=...)

    Multiple parts on one message get merged — a single AIMessage carries the
    full tool_calls array so LangChain's `add_messages` reducer preserves the
    tool-call/text ordering the UI expects.
    """

    out: list[BaseMessage] = []
    for m in pai_msgs:
        if isinstance(m, ModelResponse):
            tool_calls: list[dict[str, Any]] = []
            text_chunks: list[str] = []
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    tool_calls.append(
                        {
                            "id": p.tool_call_id,
                            "name": p.tool_name,
                            "args": p.args if isinstance(p.args, dict) else _safe_json(p.args),
                        }
                    )
                elif isinstance(p, TextPart):
                    text_chunks.append(p.content)
            if tool_calls or text_chunks:
                out.append(
                    AIMessage(
                        content="".join(text_chunks),
                        tool_calls=tool_calls,
                    )
                )
        elif isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    out.append(
                        ToolMessage(
                            content=_coerce_tool_return_content(p.content),
                            tool_call_id=p.tool_call_id,
                            name=p.tool_name,
                        )
                    )
                # UserPromptPart is already in state; don't duplicate it.
    return out


def _safe_json(value: Any) -> dict[str, Any]:
    """Coerce a tool-call args payload into a dict for the LangChain tool_calls schema."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    return {"raw": value}


def _coerce_tool_return_content(value: Any) -> str:
    """LangChain's ToolMessage content is a string; serialise JSON-ish returns."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return str(value)


__all__ = ["build_graph"]
