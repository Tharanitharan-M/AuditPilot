"""Background worker handler for ``questionnaire.fill`` jobs (Sprint 7 chunk 7.7).

Workflow:
  1. Fetch the source XLSX from object storage to a local path.
  2. Parse it into typed questions via ``questionnaire_mcp.tools.parse_xlsx``.
  3. Cluster by SIG-Lite domain.
  4. Draft an answer for each question (heuristic stub — real Pydantic AI
     agent plugs in via a drafter callable in Sprint 8).
  5. Bulk-insert ``questionnaire_questions`` rows.
  6. Assemble the filled XLSX and upload it back to storage.
  7. Move ``questionnaire_runs.status`` through ``parsing`` -> ``drafting``
     -> ``ready``. Each UPDATE fires the Postgres NOTIFY trigger that
     the SSE bridge in ``routes/questionnaire.py`` forwards to the client.

Refs: PLAN.md chunk 7.7; ADR-0010; system-design 3.4, 11.7.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from opentelemetry import trace
from psycopg_pool import AsyncConnectionPool
from questionnaire_mcp.schemas import (
    Answer,
    Citation,
    ParsedQuestionnaire,
    Question,
)
from questionnaire_mcp.tools import (
    FLAG_THRESHOLD,
    assemble_filled_xlsx,
    cluster_questions,
    parse_xlsx,
)

from apps.api.jobs import JobMessage
from apps.api.jobs.exceptions import FatalError, RetryableError
from apps.api.services.object_storage import ObjectStorage

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# A drafter takes a question + retrieval context and returns (text, confidence, citations).
# In Sprint 8 this is replaced by a Pydantic AI agent call. Sprint 7 ships
# with a deterministic heuristic so tests do not need an LLM.
DrafterFn = Callable[[Question, list[dict[str, Any]]], tuple[str, float, list[Citation]]]


# Map SIG-Lite question domains to the SOC 2 TSC clauses scored by the
# readiness scan. The drafter looks up the user's ``control_map_cache``
# entries for these clauses and answers questions based on the
# observed status — never on canned templates that could mis-state the
# user's posture.
_DOMAIN_TO_TSC: dict[str, list[str]] = {
    "access_control": ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC6.7", "CC6.8"],
    "asset_management": ["CC1.5"],
    "business_resiliency": ["A1.1", "A1.2", "A1.3"],
    "compliance": ["CC1.1", "CC1.2"],
    "data_handling": ["CC6.7", "C1.1", "C1.2"],
    "endpoint_security": ["CC6.8"],
    "human_resources": ["CC1.4"],
    "incident_response": ["CC7.1", "CC7.2", "CC7.3", "CC7.4"],
    "network_security": ["CC6.6"],
    "operations_management": ["CC4.1", "CC4.2"],
    "risk_management": ["CC3.1", "CC3.2", "CC3.3"],
    "third_party_management": ["CC9.1", "CC9.2"],
    "training_and_awareness": ["CC1.4", "CC2.1"],
    "uncategorized": [],
}


def _dominant_status(evidence: list[dict[str, Any]]) -> str | None:
    """Pick the worst-case (most conservative) status from the rows.

    ``failing`` outranks ``partial``, which outranks ``unknown``, which
    outranks ``passing``. Worst-case priority means the drafter never
    over-claims based on a single passing row when other rows show gaps.
    """
    statuses = [e.get("status") for e in evidence if e.get("status")]
    if not statuses:
        return None
    for tier in ("failing", "partial", "unknown", "passing"):
        if tier in statuses:
            return tier
    return None


def _summarise_rationales(evidence: list[dict[str, Any]], limit: int = 2) -> str:
    """Concatenate the first ``limit`` non-empty rationale strings, capped."""
    rats = [
        str(e.get("rationale", "")).strip()
        for e in evidence
        if str(e.get("rationale", "")).strip()
    ]
    if not rats:
        return ""
    return " | ".join(rats[:limit])[:300]


def heuristic_drafter(
    question: Question, evidence: list[dict[str, Any]]
) -> tuple[str, float, list[Citation]]:
    """Conservative, evidence-grounded drafter (Sprint 7 stub).

    Behaviour:
      - **Defers to human review whenever no evidence is available.**
        The drafter never invents a "Yes" or fabricates numbers / dates
        from nothing. Cells stay below ``FLAG_THRESHOLD`` so the user
        sees them in the Filter-flagged view.
      - For yes/no questions WITH evidence, the answer follows the
        dominant control status (``failing`` -> "No, this is a gap"; etc.).
      - For numeric / date questions, the drafter ALWAYS defers — those
        require ground-truth data the readiness scan does not collect.
        Sprint 8 wires a real Pydantic AI agent that can reason over
        evidence and either supply or honestly decline numeric answers.

    ``evidence`` is a list of ``control_map_cache`` rows projected by
    the worker's evidence lookup. Each row has at least ``status``,
    ``rationale``, ``control_id``, and ``evidence_ids``.
    """
    citations = [
        Citation(
            evidence_id=str(e.get("control_id", e.get("id", ""))),
            snippet=str(e.get("rationale", e.get("snippet", "")))[:240],
            source_uri=str(e.get("source_uri", "")),
        )
        for e in evidence[:3]
    ]

    dominant = _dominant_status(evidence)
    rationale = _summarise_rationales(evidence)

    # Numeric / date questions: never invent ground truth.
    if question.answer_type in ("numeric", "date"):
        return (
            "Pending human review — this question requires specific data the "
            "readiness scan does not collect.",
            0.4,
            citations,
        )

    # No evidence at all -> honest deferral, low confidence so it flags.
    if dominant is None:
        return (
            "Pending human review — no automated evidence collected for this "
            "question.",
            0.4,
            citations,
        )

    # Yes/no questions: status drives the wording.
    if question.answer_type in ("yes_no", "yes_no_partial"):
        if dominant == "passing":
            text = (
                "Yes. Readiness scan reports the related control(s) as passing"
                + (f". Evidence: {rationale}" if rationale else ".")
            )
            return text[:600], 0.85, citations
        if dominant == "failing":
            text = (
                "No — this is currently a gap in the readiness posture"
                + (f". Detail: {rationale}" if rationale else "")
                + ". Tracked in the remediation backlog."
            )
            return text[:600], 0.85, citations
        if dominant == "partial":
            text = (
                "Partial. The related control(s) are partially implemented"
                + (f". Detail: {rationale}" if rationale else "")
                + ". The remaining work is tracked in the remediation backlog."
            )
            return text[:600], 0.7, citations
        # unknown
        return (
            "Pending human review — control mapped but status is unknown until the next scan.",
            0.45,
            citations,
        )

    # Free text: same logic but with longer prose.
    if dominant == "passing":
        text = (
            "Per the most recent readiness scan, the related control(s) are passing"
            + (f". {rationale}" if rationale else ".")
        )
        return text[:600], 0.78, citations
    if dominant == "failing":
        text = (
            "Currently a gap in the readiness posture; tracked in the "
            "remediation backlog"
            + (f". Detail: {rationale}" if rationale else ".")
        )
        return text[:600], 0.78, citations
    if dominant == "partial":
        text = (
            "Partially implemented"
            + (f". Detail: {rationale}" if rationale else "")
            + ". Remaining work is tracked in the remediation backlog."
        )
        return text[:600], 0.65, citations
    return (
        "Pending human review — no automated evidence available for this question.",
        0.4,
        citations,
    )


EvidenceLookupFn = Callable[[str, str], "Awaitable[list[dict[str, Any]]]"]


def make_db_evidence_lookup(
    pool_factory: Callable[[], AsyncConnectionPool | None],
) -> EvidenceLookupFn:
    """Build an async lookup that returns ``control_map_cache`` rows for
    the relevant TSC clauses of a SIG-Lite cluster.

    The drafter consumes the returned rows as its evidence. Each row has
    ``status`` (passing / failing / partial / unknown), ``confidence``,
    ``rationale``, ``control_id``, and ``evidence_ids`` — exactly the
    fields the readiness scan persists.
    """

    async def _lookup(user_id: str, query: str) -> list[dict[str, Any]]:
        # ``query`` is the cluster label (e.g. "Access Control" or
        # "Data Handling"). Normalise to the SIG-Lite domain key so we
        # can look up the relevant TSC clauses.
        domain_key = query.strip().lower().replace(" ", "_").replace("-", "_")
        clauses = _DOMAIN_TO_TSC.get(domain_key, [])
        if not clauses:
            return []

        pool = pool_factory()
        if pool is None:
            return []
        try:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_user_id', %s, true)",
                        (user_id,),
                    )
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT control_id, status, confidence, rationale,
                                   evidence_ids
                            FROM control_map_cache
                            WHERE user_id = %s AND control_id = ANY(%s)
                            ORDER BY computed_at DESC
                            """,
                            (user_id, clauses),
                        )
                        rows = await cur.fetchall()
        except Exception:  # noqa: BLE001
            logger.exception(
                "questionnaire.evidence_lookup_failed user=%s query=%s",
                user_id,
                query,
            )
            return []

        return [
            {
                "control_id": row[0],
                "id": row[0],
                "status": row[1],
                "confidence": float(row[2]),
                "rationale": row[3] or "",
                "snippet": (row[3] or "")[:240],
                "evidence_ids": list(row[4]) if row[4] else [],
            }
            for row in rows
        ]

    return _lookup


async def _empty_evidence_lookup(user_id: str, query: str) -> list[dict[str, Any]]:
    """Default no-op when the worker is constructed without a lookup
    (used by tests). Returns no evidence so the drafter falls through to
    its honest "pending human review" branch."""
    return []


class QuestionnaireFillHandler:
    """Async handler for ``questionnaire.fill`` job messages."""

    def __init__(
        self,
        *,
        pool_factory: Callable[[], AsyncConnectionPool | None],
        storage: ObjectStorage,
        drafter: DrafterFn = heuristic_drafter,
        evidence_lookup: EvidenceLookupFn | None = None,
    ) -> None:
        self._pool_factory = pool_factory
        self._storage = storage
        self._drafter = drafter
        # Default to ``make_db_evidence_lookup`` so the worker grounds
        # answers in the user's real ``control_map_cache`` rows. Tests
        # override with ``_empty_evidence_lookup`` (or a custom mock) so
        # the heuristic drafter falls through to its honest
        # "pending human review" branch.
        self._evidence_lookup: EvidenceLookupFn = (
            evidence_lookup or make_db_evidence_lookup(pool_factory)
        )

    async def __call__(self, message: JobMessage) -> None:
        with tracer.start_as_current_span("questionnaire.fill") as span:
            span.set_attribute("user.id", message.user_id)
            payload = message.payload
            run_id = str(payload.get("run_id", ""))
            source_key = str(payload.get("source_r2_key", ""))
            if not run_id or not source_key:
                raise FatalError("questionnaire.fill payload missing run_id or source_r2_key")
            try:
                await self._run(message.user_id, run_id, source_key)
            except FatalError:
                raise
            except RetryableError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("questionnaire.fill failed run_id=%s", run_id)
                await self._mark_failed(message.user_id, run_id, str(exc)[:500])
                # XLSX parse errors are unlikely to recover on retry.
                raise FatalError(str(exc)) from exc

    async def _run(self, user_id: str, run_id: str, source_key: str) -> None:
        await self._update_status(user_id, run_id, "parsing")

        # Materialise the XLSX to a local temp dir so openpyxl can read it.
        # ``ObjectStorage.local_path`` handles both the R2 fetch and the
        # local-fallback path.
        local_path = await asyncio.to_thread(self._storage.local_path, source_key)
        parsed: ParsedQuestionnaire = await asyncio.to_thread(parse_xlsx, str(local_path))

        clusters = await asyncio.to_thread(cluster_questions, parsed)
        await self._update_run_counts(
            user_id,
            run_id,
            question_count=parsed.question_count,
            cluster_count=clusters.cluster_count,
        )

        await self._update_status(user_id, run_id, "drafting")

        # Concurrent draft within each cluster, sequential across clusters
        # so we never blow past a per-cluster retrieval batch budget.
        answers: list[Answer] = []
        flagged_count = 0
        answered_count = 0
        questions_by_id = {q.id: q for q in parsed.questions}

        for cluster in clusters.clusters:
            evidence = await self._evidence_lookup(user_id, cluster.label)
            tasks = [
                self._draft_one(questions_by_id[qid], evidence)
                for qid in cluster.question_ids
                if qid in questions_by_id
            ]
            cluster_answers = await asyncio.gather(*tasks)
            answers.extend(cluster_answers)
            answered_count += len(cluster_answers)
            flagged_count += sum(1 for a in cluster_answers if a.confidence < FLAG_THRESHOLD)
            await self._update_run_counts(
                user_id,
                run_id,
                question_count=parsed.question_count,
                cluster_count=clusters.cluster_count,
                answered_count=answered_count,
                flagged_count=flagged_count,
            )

        # Persist per-question rows so the UI can render the grid even
        # before assembly finishes.
        await self._bulk_insert_questions(
            user_id, run_id, questions_by_id, answers, parsed
        )

        # Assemble the filled XLSX in a tmp dir, then upload back.
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "filled.xlsx"
            await asyncio.to_thread(
                assemble_filled_xlsx,
                answers,
                str(local_path),
                str(out_path),
            )
            output_key = self._storage.make_key(
                user_id=user_id, kind="questionnaires/filled", suffix=".xlsx"
            )
            body = out_path.read_bytes()
            await asyncio.to_thread(
                self._storage.put_bytes,
                output_key,
                body,
                content_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            )
        await self._mark_ready(user_id, run_id, output_key, answered_count, flagged_count)

    async def _draft_one(
        self, question: Question, evidence: list[dict[str, Any]]
    ) -> Answer:
        text, confidence, citations = await asyncio.to_thread(
            self._drafter, question, evidence
        )
        return Answer(
            question_id=question.id,
            sheet=question.sheet,
            row=question.row,
            column=question.column,
            text=text,
            confidence=confidence,
            citations=citations,
        )

    # ─── DB helpers ──────────────────────────────────────────────────────────

    def _pool(self) -> AsyncConnectionPool:
        pool = self._pool_factory()
        if pool is None:
            raise RetryableError("DB pool not available")
        return pool

    async def _update_status(self, user_id: str, run_id: str, new_status: str) -> None:
        pool = self._pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_user_id', %s, true)", (user_id,)
                )
                await conn.execute(
                    """
                    UPDATE questionnaire_runs
                    SET status = %s, updated_at = now()
                    WHERE user_id = %s AND id = %s::uuid
                    """,
                    (new_status, user_id, run_id),
                )

    async def _update_run_counts(
        self,
        user_id: str,
        run_id: str,
        *,
        question_count: int,
        cluster_count: int,
        answered_count: int = 0,
        flagged_count: int = 0,
    ) -> None:
        pool = self._pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_user_id', %s, true)", (user_id,)
                )
                await conn.execute(
                    """
                    UPDATE questionnaire_runs
                    SET question_count = %s,
                        cluster_count = %s,
                        answered_count = %s,
                        flagged_count = %s,
                        updated_at = now()
                    WHERE user_id = %s AND id = %s::uuid
                    """,
                    (
                        question_count,
                        cluster_count,
                        answered_count,
                        flagged_count,
                        user_id,
                        run_id,
                    ),
                )

    async def _bulk_insert_questions(
        self,
        user_id: str,
        run_id: str,
        questions_by_id: dict[str, Question],
        answers: list[Answer],
        parsed: ParsedQuestionnaire,
    ) -> None:
        pool = self._pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_user_id', %s, true)", (user_id,)
                )
                # Wipe any prior partial state for this run, then insert fresh.
                await conn.execute(
                    "DELETE FROM questionnaire_questions WHERE user_id = %s AND run_id = %s::uuid",
                    (user_id, run_id),
                )
                async with conn.cursor() as cur:
                    for ans in answers:
                        q = questions_by_id.get(ans.question_id)
                        if q is None:
                            continue
                        flagged = ans.confidence < FLAG_THRESHOLD
                        citations_json = json.dumps(
                            [c.model_dump() for c in ans.citations]
                        )
                        await cur.execute(
                            """
                            INSERT INTO questionnaire_questions
                                (id, run_id, user_id, question_id, sheet, row_idx, column_idx,
                                 section, domain, answer_type, question_text, answer_text,
                                 confidence, flagged, citations)
                            VALUES
                                (%s::uuid, %s::uuid, %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s,
                                 %s, %s, %s::jsonb)
                            """,
                            (
                                str(uuid.uuid4()),
                                run_id,
                                user_id,
                                q.id,
                                q.sheet,
                                q.row,
                                q.column,
                                q.section,
                                q.domain,
                                q.answer_type,
                                q.text,
                                ans.text,
                                ans.confidence,
                                flagged,
                                citations_json,
                            ),
                        )
        # Touch parent row to fire NOTIFY for the SSE bridge.
        await self._update_run_counts(
            user_id,
            run_id,
            question_count=parsed.question_count,
            cluster_count=0
            if parsed.question_count == 0
            else max(1, len({q.domain for q in parsed.questions})),
            answered_count=len(answers),
            flagged_count=sum(1 for a in answers if a.confidence < FLAG_THRESHOLD),
        )

    async def _mark_ready(
        self,
        user_id: str,
        run_id: str,
        output_key: str,
        answered: int,
        flagged: int,
    ) -> None:
        pool = self._pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_user_id', %s, true)", (user_id,)
                )
                await conn.execute(
                    """
                    UPDATE questionnaire_runs
                    SET status = 'ready',
                        output_r2_key = %s,
                        answered_count = %s,
                        flagged_count = %s,
                        updated_at = now()
                    WHERE user_id = %s AND id = %s::uuid
                    """,
                    (output_key, answered, flagged, user_id, run_id),
                )

    async def _mark_failed(self, user_id: str, run_id: str, reason: str) -> None:
        try:
            pool = self._pool()
        except RetryableError:
            return
        try:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_user_id', %s, true)", (user_id,)
                    )
                    await conn.execute(
                        """
                        UPDATE questionnaire_runs
                        SET status = 'failed', failure_reason = %s, updated_at = now()
                        WHERE user_id = %s AND id = %s::uuid
                        """,
                        (reason, user_id, run_id),
                    )
        except Exception:  # noqa: BLE001
            logger.exception("questionnaire.fill mark_failed_failed run_id=%s", run_id)


__all__ = [
    "DrafterFn",
    "QuestionnaireFillHandler",
    "heuristic_drafter",
]
