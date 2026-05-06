"""PostHog integration — backend error tracking + server-side events.

Per ADR-0014, PostHog is the single error-tracking + product-analytics +
session-replay tool for AuditPilot. This module owns:

* Client init / shutdown driven from the FastAPI lifespan.
* A FastAPI middleware that captures any unhandled request exception
  into PostHog before re-raising (so ``/health`` and 404s stay silent
  while a real 500 ends up in the PostHog inbox).
* A thin :func:`capture_event` helper callers pass to downstream
  modules (PromptLoader, JobQueue DLQ handlers) so they can emit
  operator-facing observability events without importing PostHog
  directly.

No-op mode: if ``settings.posthog_api_key`` is absent, :func:`init_posthog`
returns ``None`` and :func:`capture_event` becomes a silent no-op. Tests
and the demo path both rely on that.
"""

from __future__ import annotations

import atexit
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, Request
from posthog import Posthog
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.config import Settings

logger = logging.getLogger(__name__)

_SERVER_DISTINCT_ID = "server"

# Sprint 4 chunk 4.17 — connection-string redaction.
#
# When psycopg / asyncpg / redis-py / httpx raise an error, the exception
# repr commonly embeds the full connection URI (DSN) — including the
# password — into ``str(exc)``. PostHog's ``$exception`` event captures
# ``exception_message`` verbatim, so without scrubbing we leak credentials
# into the operator inbox the moment a DB connection flaps.
#
# The redactor matches three shapes:
#   1. URI userinfo:    ``scheme://user:password@host`` → ``scheme://user:***@host``
#   2. KV password:     ``password=secret`` / ``passwd=...`` → ``password=***``
#   3. Bearer headers:  ``Bearer xxxxx`` → ``Bearer ***``
#
# Patterns are intentionally narrow — over-redaction would mask useful
# debugging info; the goal is "scrub the credential surface, leave the
# error context."
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # URI with userinfo: scheme://user:password@host
        re.compile(r"(?i)([a-z][a-z0-9+.\-]*://)([^:/\s@]+):([^@\s]+)@"),
        r"\1\2:***@",
    ),
    (
        # password=... / passwd=... (case-insensitive, common DSN style)
        re.compile(r"(?i)\b(password|passwd|pwd)\s*=\s*[^&\s\"';]+"),
        r"\1=***",
    ),
    (
        # Bearer / api-key-style tokens
        re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+"),
        r"\1 ***",
    ),
)


def _redact(value: Any) -> Any:
    """Return ``value`` with credential-shaped substrings replaced.

    Scalar strings are scrubbed via the patterns above; dicts and lists
    are recursed; everything else is returned unchanged. The redactor
    never raises — a regex hiccup must not abort error capture.
    """

    try:
        if isinstance(value, str):
            out = value
            for pattern, replacement in _REDACT_PATTERNS:
                out = pattern.sub(replacement, out)
            return out
        if isinstance(value, dict):
            return {k: _redact(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_redact(v) for v in value]
        return value
    except Exception:  # noqa: BLE001 — never let scrubbing break capture
        return "<redaction-failed>"


def init_posthog(settings: Settings) -> Posthog | None:
    """Return a configured :class:`posthog.Posthog` client or ``None``.

    A no-op client is never returned — the caller is expected to guard
    its own event calls with ``if client is not None`` (or go through
    :func:`capture_event`, which handles the ``None`` case already).
    """

    api_key = settings.posthog_api_key
    if not api_key:
        logger.info("posthog.disabled reason=no-api-key")
        return None

    client = Posthog(
        project_api_key=api_key,
        host=settings.posthog_host,
        enable_exception_autocapture=True,
    )

    # Best-effort shutdown if the process exits without hitting lifespan
    # teardown (e.g. uvicorn --reload during dev).
    atexit.register(lambda: shutdown_posthog(client))
    logger.info("posthog.initialised host=%s", settings.posthog_host)
    return client


def shutdown_posthog(client: Posthog | None) -> None:
    if client is None:
        return
    with suppress(Exception):
        client.flush()
    with suppress(Exception):
        client.shutdown()


def capture_event(
    client: Posthog | None,
    event: str,
    *,
    properties: dict[str, Any] | None = None,
    distinct_id: str | None = None,
) -> None:
    """Fire a server-side event; silent no-op if PostHog is not configured.

    Properties pass through ``_redact`` so connection strings, passwords,
    and Bearer tokens are scrubbed before they hit PostHog (Sprint 4.17).
    """

    if client is None:
        return
    safe_props = _redact(properties or {})
    with suppress(Exception):
        client.capture(
            distinct_id=distinct_id or _SERVER_DISTINCT_ID,
            event=event,
            properties=safe_props,
        )


def capture_exception(
    client: Posthog | None,
    exc: BaseException,
    *,
    distinct_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Attach an exception to PostHog with a consistent property shape.

    ``str(exc)`` and ``properties`` are both passed through ``_redact``
    so a leaked DSN in a psycopg / redis-py error message does not
    surface in the PostHog inbox (Sprint 4.17).
    """

    if client is None:
        return
    payload: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "exception_message": _redact(str(exc)),
    }
    if properties:
        payload.update(_redact(properties))
    with suppress(Exception):
        client.capture(
            distinct_id=distinct_id or _SERVER_DISTINCT_ID,
            event="$exception",
            properties=payload,
        )


class PostHogExceptionMiddleware(BaseHTTPMiddleware):
    """Capture unhandled exceptions from any route into PostHog.

    The middleware wraps the dispatcher, so it runs *before* FastAPI's
    built-in exception handler converts a 500 into a JSON response. That
    ordering is important: if we captured inside an exception handler,
    client-raised ``HTTPException`` (4xx) would end up in the inbox.
    """

    def __init__(self, app, client: Posthog | None) -> None:
        super().__init__(app)
        self._client = client

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — by design, we re-raise
            capture_exception(
                self._client,
                exc,
                properties={
                    "request_path": request.url.path,
                    "request_method": request.method,
                },
            )
            raise


def install_middleware(app: FastAPI, client: Posthog | None) -> None:
    """Mount the exception-capture middleware on ``app``."""

    app.add_middleware(PostHogExceptionMiddleware, client=client)


def make_observability_hook(
    client: Posthog | None,
) -> Callable[[str, str, dict[str, Any]], None]:
    """Return a 3-arg observability hook compatible with PromptLoader.

    Maps ``(event_name, subject_name, context) → PostHog capture``. Tests
    that want to assert a fallback event fired can pass the same callable
    and inspect the PostHog mock.
    """

    def _hook(event: str, name: str, context: dict[str, Any]) -> None:
        capture_event(
            client,
            f"auditpilot.{event}",
            properties={"subject": name, **context},
        )

    return _hook
