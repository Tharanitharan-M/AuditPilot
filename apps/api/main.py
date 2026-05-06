"""
AuditPilot API — FastAPI entrypoint
====================================
Initialises PostHog (if API key configured), mounts the SSE chat bridge,
and exposes a /health probe.

Refs: PLAN.md chunks 2.1, 2.7, 2.13, 2.14, 3.7, 3.8; ADR-0003, ADR-0009, ADR-0014.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from posthog import Posthog
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models import Model
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from apps.api.agents.models import build_model
from apps.api.agents.prompts import PromptLoader
from apps.api.checkpointer import memory_checkpointer
from apps.api.config import Settings
from apps.api.db import close_pool, init_pool
from apps.api.graph import build_graph
from apps.api.jobs import (
    JobQueue,
    JobType,
    RedisLike,
    make_dispatcher,
    make_redis_client,
    reclaim_stale_messages,
    run_worker,
)
from apps.api.observability.langfuse import (
    init_langfuse,
    shutdown_langfuse,
    traced_chat,
)
from apps.api.observability.metrics import (
    init_metrics,
    record_chat_request,
    record_job_processed,
    shutdown_metrics,
)
from apps.api.observability.posthog import (
    capture_event,
    capture_exception,
    init_posthog,
    make_observability_hook,
    shutdown_posthog,
)
from apps.api.routes import actions_router, connectors_router
from apps.api.sse.ai_sdk_v6 import (
    AI_SDK_V6_HEADER,
    AI_SDK_V6_VERSION,
    ui_message_stream_from_graph_updates,
)

logger = logging.getLogger(__name__)
posthog_client: Posthog | None = None
prompt_loader: PromptLoader | None = None

# Background workers. The lifespan owns these; tests can monkeypatch
# ``_job_queue_factory`` / ``_redis_client_factory`` to route around Redis.
_background_tasks: list[asyncio.Task[Any]] = []
_redis_client: RedisLike | None = None
_job_queue: JobQueue | None = None


def _redis_client_factory(settings: Settings) -> RedisLike:
    return make_redis_client(settings)


def _job_queue_factory(redis: RedisLike) -> JobQueue:
    return JobQueue(redis)


async def _noop_questionnaire_fill(message: Any) -> None:
    logger.info("job.handler.stub questionnaire.fill user_id=%s", message.user_id)


async def _noop_policy_finalize(message: Any) -> None:
    logger.info("job.handler.stub policy.finalize user_id=%s", message.user_id)


async def _noop_mock_audit_run(message: Any) -> None:
    logger.info("job.handler.stub mock_audit.run user_id=%s", message.user_id)


async def _noop_drift_scan(message: Any) -> None:
    logger.info("job.handler.stub drift.scan user_id=%s", message.user_id)


async def _noop_evidence_compact(message: Any) -> None:
    logger.info("job.handler.stub evidence.compact user_id=%s", message.user_id)


def _build_default_handlers() -> dict[JobType, Any]:
    """Sprint 2 handlers are logging stubs.

    Chunk 5.x (evidence-store-mcp wiring), 6.x (policy export), 7.x
    (questionnaire), 8.x (AdversarialAuditor), and 9.x (drift-watcher)
    replace these one at a time. Keeping the registry in ``main`` means
    the Sprint-4 orchestrator can see the full job-type surface today
    without inventing no-op handlers of its own.
    """

    return {
        JobType.QUESTIONNAIRE_FILL: _noop_questionnaire_fill,
        JobType.POLICY_FINALIZE: _noop_policy_finalize,
        JobType.MOCK_AUDIT_RUN: _noop_mock_audit_run,
        JobType.DRIFT_SCAN: _noop_drift_scan,
        JobType.EVIDENCE_COMPACT: _noop_evidence_compact,
    }


_job_handlers_factory = _build_default_handlers


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _init_posthog(settings: Settings) -> None:
    global posthog_client
    posthog_client = init_posthog(settings)


def _init_prompt_loader(settings: Settings) -> None:  # noqa: ARG001
    """Construct the shared :class:`PromptLoader` for agent modules to consume."""

    global prompt_loader
    hook = make_observability_hook(posthog_client)
    # Langfuse client is wired into the loader lazily: if the Langfuse
    # exporter is up, ``init_langfuse`` has already created a process-
    # global singleton we can grab; otherwise we pass ``None`` and the
    # loader runs in local-YAML-only mode.
    try:
        from langfuse import Langfuse, get_client  # type: ignore[attr-defined]
        try:
            lf_client: Langfuse | None = get_client()  # v4 singleton accessor
        except Exception:  # noqa: BLE001
            lf_client = None
    except Exception:  # noqa: BLE001
        lf_client = None
    prompt_loader = PromptLoader(lf_client, observability_hook=hook)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _redis_client, _job_queue

    settings = get_settings()
    # Sprint 4 chunk 4.3a — the previous lifespan wrote
    # ``settings.gemini_api_key`` into ``os.environ["GOOGLE_API_KEY"]`` so
    # Pydantic AI's Google integration would pick it up implicitly. That is
    # subprocess-leakage by construction: every spawned process inherits the
    # secret. ``apps.api.agents.models.build_model`` now constructs the
    # matching ``Provider(api_key=...)`` directly from this ``Settings``
    # instance, so no environment write is required. Operators flip providers
    # via ``ORCHESTRATOR_MODEL=anthropic:claude-sonnet-4-6`` in ``.env`` —
    # zero code changes.
    _init_posthog(settings)
    init_langfuse(settings)
    init_metrics(settings)
    _init_prompt_loader(settings)
    # Application DB pool (Sprint 3.5 chunk 3.5.3). No-op when DATABASE_URL
    # is unset so the dev/test path still boots.
    try:
        await init_pool(settings)
    except Exception:  # noqa: BLE001
        logger.exception("db.pool.init_failed — DB-backed routes will return 503")
    capture_event(
        posthog_client,
        "api_started",
        properties={"version": "0.1.0", "environment": settings.environment},
    )

    try:
        _redis_client = _redis_client_factory(settings)
        _job_queue = _job_queue_factory(_redis_client)
        await _job_queue.ensure_group()
        base_dispatcher = make_dispatcher(_job_handlers_factory())

        async def metered_dispatcher(message):  # type: ignore[no-untyped-def]
            job_type = (
                message.type.value
                if hasattr(message.type, "value")
                else str(message.type)
            )
            try:
                await base_dispatcher(message)
            except Exception:
                record_job_processed(job_type=job_type, status="failed")
                raise
            record_job_processed(job_type=job_type, status="succeeded")

        _background_tasks.append(
            asyncio.create_task(
                run_worker(_job_queue, metered_dispatcher),
                name="auditpilot.worker",
            )
        )
        _background_tasks.append(
            asyncio.create_task(
                reclaim_stale_messages(_job_queue, metered_dispatcher),
                name="auditpilot.reclaim",
            )
        )
        logger.info(
            "background_tasks.started count=%d", len(_background_tasks)
        )
    except Exception:
        logger.exception(
            "background_tasks.start_failed — /chat will still work, jobs will not"
        )

    try:
        yield
    finally:
        for task in _background_tasks:
            task.cancel()
        for task in _background_tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        _background_tasks.clear()

        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:  # noqa: BLE001
                logger.exception("redis.close_failed")
            _redis_client = None
            _job_queue = None

        # Close the application DB pool (Sprint 3.5 chunk 3.5.3).
        await close_pool()

        await shutdown_langfuse()
        capture_event(
            posthog_client,
            "api_shutdown",
            properties={"version": "0.1.0", "environment": settings.environment},
        )
        shutdown_posthog(posthog_client)
        shutdown_metrics()


def get_job_queue() -> JobQueue:
    """Dependency injector: return the live job queue.

    Raises ``RuntimeError`` if called before ``lifespan`` starts the
    worker — useful for tests that mount the app without lifespan so they
    catch accidental enqueue calls.
    """

    if _job_queue is None:
        raise RuntimeError("JobQueue not initialised; app lifespan has not started")
    return _job_queue


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiting (Sprint 3 day-0 chunk 3.0a)
# ──────────────────────────────────────────────────────────────────────────────
# OWASP LLM10 — Unbounded Consumption. /chat is unauthenticated until Sprint 3
# chunk 3.5 wires Clerk JWT verification, so without this limiter any caller
# could drive unbounded Gemini API spend. Per-IP keying via
# ``get_remote_address`` is the right surrogate for "per-user" until auth lands.
# Limit string read from env (default 10/minute) so tests can override to a
# tight budget.
def _chat_rate_limit() -> str:
    return os.environ.get("CHAT_RATE_LIMIT", "10/minute")


limiter = Limiter(key_func=get_remote_address, default_limits=[])

app = FastAPI(
    title="AuditPilot API",
    version="0.1.0",
    description="Readiness reference architecture — orchestration backend",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(connectors_router)
app.include_router(actions_router)


@app.middleware("http")
async def _posthog_exception_middleware(request: Request, call_next):
    """Route-level unhandled-exception capture into PostHog (ADR-0014).

    Runs before FastAPI's built-in exception handling. Client-raised
    ``HTTPException`` is not caught here — only server-side failures.
    """

    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        capture_exception(
            posthog_client,
            exc,
            properties={
                "request_path": request.url.path,
                "request_method": request.method,
            },
        )
        raise


# ──────────────────────────────────────────────────────────────────────────────
# /health
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": "0.1.0",
        "git_sha": settings.git_sha,
    }


if not get_settings().is_production:

    @app.get("/debug/raise-500")
    async def debug_raise_500() -> None:
        """PostHog verification endpoint — raises an unhandled error on purpose.

        Mounted only when ``settings.environment != "production"``. This keeps
        the endpoint usable for verifying PostHog ingestion in dev/staging
        without exposing an unauthenticated 500-on-demand surface in prod.
        """

        capture_event(
            posthog_client,
            "debug_error_triggered",
            properties={"endpoint": "/debug/raise-500"},
        )
        _ = 1 / 0


# ──────────────────────────────────────────────────────────────────────────────
# /chat — AI SDK 6 UIMessage SSE bridge (ADR-0003, chunk 2.7)
# ──────────────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """One message in the AI SDK 6 `UIMessage` convention (minimal shape).

    The frontend sends text as a single `parts: [{type: "text", text}]` entry;
    we flatten to a plain content string for the Python-side LangGraph state.
    """

    model_config = ConfigDict(extra="allow")

    role: Literal["user", "assistant", "system"]
    content: str | None = None
    parts: list[dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """POST /chat body shape.

    ``messages`` is the running conversation history (AI SDK 6's `useChat`
    posts the full transcript every turn). ``thread_id`` pins the checkpoint
    row so resume-from-HITL works (Sprint 6 chunk 6.2).

    Sprint 4 chunk 4.4a — ``repo_include_list`` carries the user-chosen
    repo scope. The dashboard reads this from the picker (Sprint 3.5 chunk
    3.5.2) before opening the /chat stream and forwards it here. The
    orchestrator's ``validate_scope`` node refuses ``run_readiness_scan``
    when this list is empty (ADR-0015 default-deny).
    """

    model_config = ConfigDict(extra="ignore")

    messages: list[ChatMessage]
    thread_id: str | None = None
    intent: (
        Literal["free_chat", "run_readiness_scan", "draft_policy", "fill_questionnaire"]
        | None
    ) = "free_chat"
    # Sprint 4 chunk 4.4a — list of GitHub provider_repo_id strings the
    # user has scoped on their connector. The frontend populates this
    # from `/api/connectors/{id}/scoped-repos`. The backend trusts the
    # list — Sprint 6 chunk 6.2 wires Clerk auth on /chat which then
    # cross-checks against the persisted scope server-side.
    repo_include_list: list[str] = Field(
        default_factory=list,
        description=(
            "GitHub provider_repo_id strings the user has scoped on the "
            "active connector. Required when intent='run_readiness_scan'."
        ),
        max_length=500,
    )
    connector_id: str | None = Field(
        default=None,
        description=(
            "Clerk external_account.id (e.g. 'eac_*') the scan should "
            "operate on. Sprint 4 surfaces this in trace metadata; "
            "Sprint 6 server-side validates the scope against this id."
        ),
        max_length=64,
    )


def _flatten_content(msg: ChatMessage) -> str:
    """Pull text content out of either `.content` or the AI SDK 6 `.parts` array."""
    if msg.content:
        return msg.content
    for p in msg.parts or []:
        if p.get("type") == "text":
            return str(p.get("text", ""))
    return ""


def _to_langchain_messages(body_messages: list[ChatMessage]) -> list:
    """Translate AI SDK 6 wire messages into LangChain Human/AI/System messages."""
    out = []
    for m in body_messages:
        text = _flatten_content(m)
        if m.role == "user":
            out.append(HumanMessage(content=text))
        elif m.role == "assistant":
            out.append(AIMessage(content=text))
        else:  # system
            out.append(SystemMessage(content=text))
    return out


# Model injection lets tests supply FunctionModel; production uses the settings
# + LiteLLM + PromptLoader stack (wired in chunk 2.12). Sprint 4 chunk 4.3a:
# the factory now returns a fully-constructed ``Model`` instance instead of a
# string, so the provider's API key is threaded explicitly from ``Settings``
# rather than read from the process environment.
def _default_model() -> Model:
    """Return the default Pydantic AI :class:`Model` for /chat.

    Reads ``settings.orchestrator_model`` (default
    ``"google-gla:gemini-2.5-flash-lite"``) and constructs the matching
    provider with the API key wired in from :class:`Settings`. No
    environment-variable mutation: subprocess-leakage closed.

    Refs: PLAN.md Sprint 4 chunk 4.3a; ADR-0001.
    """

    settings = get_settings()
    return build_model(settings.orchestrator_model, settings)


def _default_mcp_toolset() -> bool:
    """Return ``True`` when /chat should attach the live MCP toolset.

    Sprint 4 chunk 4.3: the production /chat path spawns
    ``compliance-kb-mcp`` for every request so tools dispatch over the
    canonical stdio MCP transport. Tests override this hook to ``False``
    so they don't fork a subprocess on every assertion.
    """

    return True


# Module-level hooks tests can monkeypatch.
_chat_model_factory = _default_model
_chat_checkpointer_factory = memory_checkpointer
_chat_mcp_toolset = _default_mcp_toolset


async def _chat_stream_generator(
    *,
    req: ChatRequest,
    thread_id: str,
    request: Request | None = None,
    disconnect_poll_interval_s: float = 5.0,
) -> AsyncIterator[str]:
    """Open a Langfuse observation and stream SSE out of the graph.

    The Langfuse trace is opened BEFORE the stream starts and closed AFTER
    the last chunk. That keeps the whole invocation — including orchestrator
    tool calls and any adversarial dispatch — inside one trace id, so the
    deeplink returned in the `finish` chunk leads to a complete trace.

    Sprint 4 chunk 4.9 — client-disconnect cancellation. We poll
    ``request.is_disconnected()`` every 5 s in a sidecar task while the
    graph generator is running. When the client drops, the sidecar
    cancels the producer and the generator exits cleanly without emitting
    further chunks. The orchestrator's MCP subprocess (and any in-flight
    LLM call) is reaped through Pydantic AI's async-with binding because
    the cancellation propagates through the graph node that opened it.
    """

    lc_messages = _to_langchain_messages(req.messages)
    checkpointer = _chat_checkpointer_factory()
    # Sprint 4 chunk 4.3 — production /chat ALWAYS spawns the MCP server
    # subprocess so the orchestrator dispatches lookup_control over the
    # real stdio transport, the same way third-party consumers of
    # compliance-kb-mcp will. Tests opt out by replacing
    # ``_chat_model_factory`` AND ``_chat_mcp_toolset`` (the latter
    # defaults to False so pure FunctionModel tests never fork).
    graph = build_graph(
        checkpointer,
        model=_chat_model_factory(),
        mcp_toolset=_chat_mcp_toolset(),
    )
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    # Sprint 4 chunks 4.4a/4.4b — seed the graph state with the user's
    # repo scope and intent so validate_scope, collect_evidence, and
    # map_controls have what they need without re-reading the request.
    graph_input: dict[str, Any] = {
        "messages": lc_messages,
        "intent": req.intent,
        "repo_include_list": list(req.repo_include_list),
    }

    async with traced_chat(
        thread_id=thread_id,
        intent=req.intent,
    ) as handle:
        async def finish_metadata() -> dict[str, Any] | None:
            # Surface trace context inside the AI SDK 6 finish chunk so the
            # frontend can deeplink operators straight to the Langfuse trace.
            md: dict[str, Any] = {"thread_id": thread_id, "intent": req.intent}
            if handle.trace_id:
                md["trace_id"] = handle.trace_id
            if handle.trace_url:
                md["trace_url"] = handle.trace_url
            return md

        producer = ui_message_stream_from_graph_updates(
            graph,
            input=graph_input,
            config=config,
            message_metadata={"thread_id": thread_id, "intent": req.intent},
            finish_metadata_cb=finish_metadata,
        )

        # Sprint 4 chunk 4.9 — sidecar that watches the client connection.
        # Cancelled when the producer finishes normally; cancels the
        # producer when the client drops first. The sidecar does no work
        # when ``request`` is None (e.g. unit tests that bypass it).
        cancel_event = asyncio.Event()

        async def _disconnect_watcher() -> None:
            if request is None:
                return
            try:
                while not cancel_event.is_set():
                    if await request.is_disconnected():
                        logger.info(
                            "chat.client_disconnected thread_id=%s — "
                            "cancelling graph",
                            thread_id,
                        )
                        record_chat_request(intent=req.intent, outcome="cancelled")
                        cancel_event.set()
                        return
                    await asyncio.sleep(disconnect_poll_interval_s)
            except asyncio.CancelledError:
                # Producer finished first — nothing to clean up.
                raise

        watcher_task = asyncio.create_task(
            _disconnect_watcher(), name="auditpilot.chat.disconnect_watcher"
        )

        try:
            async for chunk in producer:
                if cancel_event.is_set():
                    # Client dropped — bail out before the next yield.
                    return
                yield chunk
        finally:
            watcher_task.cancel()
            try:
                await watcher_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


@app.post("/chat")
@limiter.limit(_chat_rate_limit)
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """Stream orchestrator output as AI SDK 6 UIMessage SSE.

    Headers:
      Content-Type: text/event-stream
      x-vercel-ai-ui-message-stream: v1  (handshake, required by useChat)

    Body: ChatRequest JSON, matching AI SDK 6's `useChat` POST shape.

    NOTE: Sprint 2 leaves this endpoint unauthenticated. Clerk JWT verification
    wires in at Sprint 3 chunk 3.5 via a FastAPI dependency. Until then, the
    ``@limiter.limit(_chat_rate_limit)`` decorator above caps requests at
    ``CHAT_RATE_LIMIT`` (default ``10/minute``) per remote IP — Sprint 3 day-0
    chunk 3.0a, OWASP LLM10 mitigation.
    """

    thread_id = req.thread_id or f"thread_{uuid.uuid4().hex}"
    record_chat_request(intent=req.intent, outcome="started")
    return StreamingResponse(
        # Sprint 4 chunk 4.9 — pass the request handle through so the
        # generator can poll ``request.is_disconnected()`` and cancel
        # the running graph if the client drops.
        _chat_stream_generator(req=req, thread_id=thread_id, request=request),
        media_type="text/event-stream",
        headers={
            AI_SDK_V6_HEADER: AI_SDK_V6_VERSION,
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # defeat nginx/Cloudflare buffering
        },
    )
