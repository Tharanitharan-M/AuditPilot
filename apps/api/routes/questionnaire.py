"""
Questionnaire routes — Sprint 7 chunks 7.6, 7.8, 7.10, 7.11.
=============================================================
POST   /api/questionnaire/upload         — multipart XLSX upload, enqueues fill job
GET    /api/questionnaire                 — list runs for the current user
GET    /api/questionnaire/{run_id}        — full run with questions + answers
GET    /api/questionnaire/{run_id}/events — SSE stream of questionnaire_run updates
GET    /api/questionnaire/{run_id}/poll   — JSON polling fallback for SSE
PATCH  /api/questionnaire/questions/{id}  — edit answer + clear flag
GET    /api/questionnaire/{run_id}/download — 302 to pre-signed R2 download URL

Refs: PLAN.md chunks 7.6, 7.8, 7.10, 7.11; ADR-0008, ADR-0010; system-design 3.4, 11.7;
US-016, US-017, US-018.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from apps.api.auth.clerk import ClerkUser, verify_clerk_token
from apps.api.db import AppDbPool, AppDbPoolDep
from apps.api.jobs import JobMessage, JobQueue, JobType
from apps.api.services.object_storage import ObjectStorage, get_object_storage

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["questionnaire"])

_questionnaire_limiter = Limiter(key_func=get_remote_address, default_limits=[])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per FR-030 / chunk 7.6
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",  # some browsers omit the precise type
}


def _questionnaire_rate_limit() -> str:
    return os.environ.get("QUESTIONNAIRE_RATE_LIMIT", "30/minute")


# ── Schemas ──────────────────────────────────────────────────────────────────


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    task_id: str
    status: str = "queued"
    deduplicated: bool = False
    filename: str
    size_bytes: int


class QuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    run_id: str
    question_id: str
    sheet: str
    row: int
    column: int
    section: str
    domain: str
    answer_type: str
    question_text: str
    answer_text: str
    confidence: float
    flagged: bool
    citations: list[dict[str, Any]] = Field(default_factory=list)
    edited_by_user: bool = False


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    user_id: str
    filename: str
    format: str
    status: str
    question_count: int
    answered_count: int
    flagged_count: int
    cluster_count: int
    output_r2_key: str | None = None
    failure_reason: str | None = None
    created_at: str
    updated_at: str


class RunListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runs: list[RunSummary] = Field(default_factory=list)
    count: int = 0


class RunDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: RunSummary
    questions: list[QuestionOut] = Field(default_factory=list)


class QuestionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_text: str = Field(max_length=20_000)
    citations: list[dict[str, Any]] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    clear_flag: bool = True


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _set_user_scope(conn: Any, user_id: str) -> None:
    await conn.execute("SELECT set_config('app.current_user_id', %s, true)", (user_id,))


async def _insert_run(
    pool: AppDbPool,
    *,
    user_id: str,
    filename: str,
    fmt: str,
    source_r2_key: str,
    job_idempotency_key: str,
) -> str:
    run_id = str(uuid.uuid4())
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            await conn.execute(
                """
                INSERT INTO questionnaire_runs
                    (id, user_id, filename, format, status, source_r2_key, job_idempotency_key)
                VALUES
                    (%s::uuid, %s, %s, %s, 'queued', %s, %s)
                """,
                (run_id, user_id, filename, fmt, source_r2_key, job_idempotency_key),
            )
    return run_id


async def _find_run_by_idempotency_key(
    pool: AppDbPool, *, user_id: str, job_idempotency_key: str
) -> str | None:
    """Return the most-recent run id with this idempotency key, if any.

    Used to short-circuit duplicate uploads — when the queue dedup cache
    holds the same key, we point the client at the existing run instead
    of stranding a fresh DB row that no worker will ever process.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id::text FROM questionnaire_runs
                    WHERE user_id = %s AND job_idempotency_key = %s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (user_id, job_idempotency_key),
                )
                row = await cur.fetchone()
    return row[0] if row else None


async def _list_runs(pool: AppDbPool, *, user_id: str) -> list[RunSummary]:
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id::text, user_id, filename, format, status,
                           question_count, answered_count, flagged_count, cluster_count,
                           output_r2_key, failure_reason, created_at, updated_at
                    FROM questionnaire_runs
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    (user_id,),
                )
                rows = await cur.fetchall()
    return [_row_to_run_summary(r) for r in rows]


async def _fetch_run(
    pool: AppDbPool, *, user_id: str, run_id: str
) -> RunSummary | None:
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id::text, user_id, filename, format, status,
                           question_count, answered_count, flagged_count, cluster_count,
                           output_r2_key, failure_reason, created_at, updated_at
                    FROM questionnaire_runs
                    WHERE user_id = %s AND id = %s::uuid
                    """,
                    (user_id, run_id),
                )
                row = await cur.fetchone()
    return _row_to_run_summary(row) if row else None


async def _list_questions(
    pool: AppDbPool, *, user_id: str, run_id: str
) -> list[QuestionOut]:
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id::text, run_id::text, question_id, sheet, row_idx, column_idx,
                           section, domain, answer_type, question_text, answer_text,
                           confidence, flagged, citations, edited_by_user
                    FROM questionnaire_questions
                    WHERE user_id = %s AND run_id = %s::uuid
                    ORDER BY sheet ASC, row_idx ASC, column_idx ASC
                    """,
                    (user_id, run_id),
                )
                rows = await cur.fetchall()
    return [_row_to_question(r) for r in rows]


async def _patch_question(
    pool: AppDbPool,
    *,
    user_id: str,
    question_pk: str,
    answer_text: str,
    citations: list[dict[str, Any]] | None,
    confidence: float | None,
    clear_flag: bool,
) -> QuestionOut | None:
    async with pool.connection() as conn:
        async with conn.transaction():
            await _set_user_scope(conn, user_id)
            async with conn.cursor() as cur:
                fields = ["answer_text = %s", "edited_by_user = TRUE", "updated_at = now()"]
                params: list[Any] = [answer_text]
                if citations is not None:
                    fields.append("citations = %s::jsonb")
                    params.append(json.dumps(citations))
                if confidence is not None:
                    fields.append("confidence = %s")
                    params.append(confidence)
                if clear_flag:
                    fields.append("flagged = FALSE")
                params.extend([user_id, question_pk])
                await cur.execute(
                    f"""
                    UPDATE questionnaire_questions
                    SET {", ".join(fields)}
                    WHERE user_id = %s AND id = %s::uuid
                    RETURNING id::text, run_id::text, question_id, sheet, row_idx, column_idx,
                              section, domain, answer_type, question_text, answer_text,
                              confidence, flagged, citations, edited_by_user
                    """,
                    tuple(params),
                )
                row = await cur.fetchone()
    return _row_to_question(row) if row else None


def _row_to_run_summary(row: tuple) -> RunSummary:
    (
        id_,
        user_id,
        filename,
        fmt,
        run_status,
        question_count,
        answered_count,
        flagged_count,
        cluster_count,
        output_r2_key,
        failure_reason,
        created_at,
        updated_at,
    ) = row
    return RunSummary(
        id=id_,
        user_id=user_id,
        filename=filename or "",
        format=fmt,
        status=run_status,
        question_count=question_count or 0,
        answered_count=answered_count or 0,
        flagged_count=flagged_count or 0,
        cluster_count=cluster_count or 0,
        output_r2_key=output_r2_key,
        failure_reason=failure_reason,
        created_at=_iso(created_at),
        updated_at=_iso(updated_at),
    )


def _row_to_question(row: tuple) -> QuestionOut:
    (
        id_,
        run_id,
        question_id,
        sheet,
        row_idx,
        column_idx,
        section,
        domain,
        answer_type,
        question_text,
        answer_text,
        confidence,
        flagged,
        citations,
        edited_by_user,
    ) = row
    if isinstance(citations, str):
        try:
            citations_list = json.loads(citations)
        except (json.JSONDecodeError, TypeError):
            citations_list = []
    elif citations is None:
        citations_list = []
    else:
        citations_list = list(citations)
    return QuestionOut(
        id=id_,
        run_id=run_id,
        question_id=question_id,
        sheet=sheet,
        row=row_idx,
        column=column_idx,
        section=section or "",
        domain=domain or "uncategorized",
        answer_type=answer_type or "unknown",
        question_text=question_text or "",
        answer_text=answer_text or "",
        confidence=float(confidence or 0.0),
        flagged=bool(flagged),
        citations=citations_list,
        edited_by_user=bool(edited_by_user),
    )


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


# ── Routes ───────────────────────────────────────────────────────────────────


def _get_storage() -> ObjectStorage:
    """FastAPI dependency wrapper around the module-level singleton."""
    return get_object_storage()


def _get_job_queue() -> JobQueue:
    """Indirection so tests can override via dependency_overrides."""
    from apps.api.main import get_job_queue as _gjq

    return _gjq()


@router.post("/api/questionnaire/upload", response_model=UploadResponse)
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def upload_questionnaire(
    request: Request,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
    file: Annotated[UploadFile, File(description="SIG-Lite XLSX (max 10 MB)")],
    storage: Annotated[ObjectStorage, Depends(_get_storage)],
    queue: Annotated[JobQueue, Depends(_get_job_queue)],
    fmt: Annotated[str, Form(alias="format")] = "sig-lite",
) -> UploadResponse:
    """Accept a SIG-Lite XLSX, persist it, and enqueue the fill job (chunk 7.6)."""

    with tracer.start_as_current_span("questionnaire.upload") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("filename", file.filename or "")
        # Read body up to MAX + 1 to detect overflow precisely.
        body = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds {MAX_UPLOAD_BYTES} bytes",
            )
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported content type: {file.content_type}",
            )
        if not body:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Empty file",
            )

        digest = hashlib.sha256(body).hexdigest()
        idempotency_key = f"questionnaire.fill:{user.user_id}:{digest}"

        # If this exact file content has already been uploaded, point the
        # client at the existing run instead of stranding a new DB row that
        # the queue's idempotency cache would silently dedup.
        existing_run_id = await _find_run_by_idempotency_key(
            pool, user_id=user.user_id, job_idempotency_key=idempotency_key
        )
        if existing_run_id is not None:
            return UploadResponse(
                run_id=existing_run_id,
                task_id=f"dedup:{idempotency_key}",
                status="queued",
                deduplicated=True,
                filename=file.filename or "questionnaire.xlsx",
                size_bytes=len(body),
            )

        object_key = storage.make_key(
            user_id=user.user_id, kind="questionnaires", suffix=".xlsx"
        )
        # ``put_bytes`` may issue a blocking R2 PUT — run off the event loop.
        stored = await asyncio.to_thread(
            storage.put_bytes,
            object_key,
            body,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        run_id = await _insert_run(
            pool,
            user_id=user.user_id,
            filename=file.filename or "questionnaire.xlsx",
            fmt=fmt if fmt in ("sig-lite", "custom") else "sig-lite",
            source_r2_key=stored.key,
            job_idempotency_key=idempotency_key,
        )
        message = JobMessage(
            type=JobType.QUESTIONNAIRE_FILL,
            user_id=user.user_id,
            idempotency_key=idempotency_key,
            payload={
                "run_id": run_id,
                "source_r2_key": stored.key,
                "filename": file.filename or "questionnaire.xlsx",
                "format": fmt,
                "size_bytes": stored.size_bytes,
            },
        )
        result = await queue.enqueue(message)
        return UploadResponse(
            run_id=run_id,
            task_id=result.message_id,
            status="queued",
            deduplicated=result.deduplicated,
            filename=file.filename or "questionnaire.xlsx",
            size_bytes=stored.size_bytes,
        )


@router.get("/api/questionnaire", response_model=RunListOut)
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def list_runs(
    request: Request,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> RunListOut:
    with tracer.start_as_current_span("questionnaire.list") as span:
        span.set_attribute("user.id", user.user_id)
        runs = await _list_runs(pool, user_id=user.user_id)
        return RunListOut(runs=runs, count=len(runs))


@router.get("/api/questionnaire/{run_id}", response_model=RunDetailOut)
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def get_run(
    request: Request,
    run_id: str,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> RunDetailOut:
    with tracer.start_as_current_span("questionnaire.get") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("run.id", run_id)
        run = await _fetch_run(pool, user_id=user.user_id, run_id=run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            )
        questions = await _list_questions(pool, user_id=user.user_id, run_id=run_id)
        return RunDetailOut(run=run, questions=questions)


@router.get("/api/questionnaire/{run_id}/poll")
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def poll_run(
    request: Request,
    run_id: str,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> RunSummary:
    """Polling fallback for clients that cannot hold an SSE connection (chunk 7.8)."""
    with tracer.start_as_current_span("questionnaire.poll") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("run.id", run_id)
        run = await _fetch_run(pool, user_id=user.user_id, run_id=run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            )
        return run


@router.get("/api/questionnaire/{run_id}/events")
async def stream_run_events(
    request: Request,
    run_id: str,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> StreamingResponse:
    """SSE stream of questionnaire_run updates (chunk 7.8).

    The handler subscribes to the Postgres ``questionnaire_run_updates``
    channel via asyncpg LISTEN. Every NOTIFY whose payload has a matching
    ``run_id`` and ``user_id`` is forwarded as an SSE ``data:`` frame. A
    keep-alive ping is emitted every 15 seconds. The handler closes when
    the run reaches a terminal status (``ready`` or ``failed``) or when the
    client disconnects.
    """
    run = await _fetch_run(pool, user_id=user.user_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def event_stream():
        # Initial snapshot frame so the client renders immediately.
        yield _sse_frame("data-questionnaire-status", run.model_dump())
        terminal = {"ready", "failed"}
        if run.status in terminal:
            yield "data: [DONE]\n\n"
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        listener = await _start_pg_listener(pool, user_id=user.user_id, run_id=run_id, queue=queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse_frame("data-questionnaire-status", payload)
                if payload.get("status") in terminal:
                    break
        finally:
            await listener.stop()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.patch(
    "/api/questionnaire/questions/{question_pk}", response_model=QuestionOut
)
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def patch_question(
    request: Request,
    question_pk: str,
    body: QuestionPatch,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> QuestionOut:
    """Edit a drafted answer; clears the flag by default (chunk 7.10)."""
    with tracer.start_as_current_span("questionnaire.patch_question") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("question.id", question_pk)
        updated = await _patch_question(
            pool,
            user_id=user.user_id,
            question_pk=question_pk,
            answer_text=body.answer_text,
            citations=body.citations,
            confidence=body.confidence,
            clear_flag=body.clear_flag,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
            )
        return updated


@router.get("/api/questionnaire/{run_id}/download", response_model=None)
@_questionnaire_limiter.limit(_questionnaire_rate_limit)
async def download_run(
    request: Request,
    run_id: str,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
    storage: Annotated[ObjectStorage, Depends(_get_storage)],
) -> RedirectResponse | StreamingResponse:
    """Return the assembled XLSX. R2-backed runs 302 to a pre-signed URL (15 min TTL).

    Local-fs-backed runs (dev / tests) stream the bytes directly so the
    browser does not have to follow a ``file://`` redirect, which fetch
    cannot do.
    """
    with tracer.start_as_current_span("questionnaire.download") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("run.id", run_id)
        run = await _fetch_run(pool, user_id=user.user_id, run_id=run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            )
        if run.status != "ready" or not run.output_r2_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run is not ready (status={run.status})",
            )
        # Local fallback: stream bytes directly. R2: 302 to pre-signed URL.
        if storage.backend == "local":
            body = await asyncio.to_thread(storage.get_bytes, run.output_r2_key)
            filename = (run.filename or "questionnaire").rsplit(".", 1)[0] + "_filled.xlsx"
            return StreamingResponse(
                io.BytesIO(body),
                media_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        url = await asyncio.to_thread(
            storage.presigned_get_url, run.output_r2_key, ttl_seconds=900
        )
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


# ── Postgres LISTEN/NOTIFY bridge ────────────────────────────────────────────


class _PgListener:
    """Tiny wrapper that holds the LISTEN connection and shuts it down cleanly."""

    def __init__(self, conn_ctx: Any, task: asyncio.Task) -> None:
        self._conn_ctx = conn_ctx
        self._task = task

    async def stop(self) -> None:
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await self._conn_ctx.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            logger.exception("pg_listener.close_failed")


async def _start_pg_listener(
    pool: AppDbPool,
    *,
    user_id: str,
    run_id: str,
    queue: asyncio.Queue,
) -> _PgListener:
    """Open a dedicated connection, ``LISTEN``, and forward matching events.

    psycopg's async connection exposes ``conn.notifies()`` as an async
    iterator. We filter by ``user_id`` and ``run_id`` server-side using the
    payload JSON the trigger emits. Each filtered event is parsed, verified
    against the user, and pushed into ``queue``.
    """
    conn_ctx = pool.connection()
    conn = await conn_ctx.__aenter__()
    await conn.execute("LISTEN questionnaire_run_updates")
    await conn.commit()

    async def reader_loop() -> None:
        try:
            async for notify in conn.notifies():
                try:
                    data = json.loads(notify.payload)
                except (ValueError, AttributeError):
                    continue
                if data.get("user_id") != user_id:
                    continue
                if data.get("run_id") != run_id:
                    continue
                await queue.put(data)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("pg_listener.reader_failed run_id=%s", run_id)

    task = asyncio.create_task(reader_loop(), name=f"pg-listen-{run_id}")
    return _PgListener(conn_ctx, task)


def _sse_frame(channel: str, data: dict[str, Any]) -> str:
    """Encode a single SSE frame as a `data:` line of JSON.

    The frontend expects the AI SDK 6 plain-JSON format: each frame is one
    line of `data: {...}` with a typed ``type`` field, followed by a blank
    line.
    """
    payload = {"type": channel, **data}
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


__all__ = [
    "MAX_UPLOAD_BYTES",
    "QuestionOut",
    "QuestionPatch",
    "RunDetailOut",
    "RunListOut",
    "RunSummary",
    "UploadResponse",
    "router",
]
