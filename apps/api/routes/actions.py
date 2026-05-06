"""
Pending Actions queue routes — Sprint 4 chunks 4.7 + 4.8.
=========================================================
GET   /api/actions             — list the authenticated user's actions
PATCH /api/actions/{id}        — apply a state-machine transition

State machine (US-007 + US-032):

    pending_review ──┬──→ approved   ──→ completed ──→ revoked
                     ├──→ rejected   (terminal until re-opened)
                     └──→ completed  (skip-approve shortcut)

Any transition outside this graph returns HTTP 409 Conflict with a
typed body so the FE can render a useful error. Sprint 4 ships the
``approved``, ``rejected``, ``completed`` transitions; the
``completed → revoked`` transition lands in Sprint 9 chunk 9.14 and
the underlying state-machine table already accommodates it.

Refs: PLAN.md chunks 4.7, 4.8, 9.14, 9.15; ADR-0004 (read-only on
input — these endpoints write only AuditPilot's own state, never a
third-party API); ADR-0008 (Neon Postgres); US-007, US-032.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from apps.api.auth.clerk import ClerkUser, verify_clerk_token
from apps.api.db import AppDbPool, AppDbPoolDep

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/api", tags=["actions"])

# security-reviewer F1 — slowapi rate limit on the actions routes.
# These run AFTER Clerk auth, so the key surrogate ``user_id`` is the
# right grouping. Falls back to remote address when the dependency is
# overridden in tests. Limits read from env so the eval suite can
# tighten the cap.
def _actions_list_rate_limit() -> str:
    return os.environ.get("ACTIONS_LIST_RATE_LIMIT", "120/minute")


def _actions_patch_rate_limit() -> str:
    return os.environ.get("ACTIONS_PATCH_RATE_LIMIT", "60/minute")


_actions_limiter = Limiter(key_func=get_remote_address, default_limits=[])


# ── State machine ────────────────────────────────────────────────────────────

ActionStatus = Literal[
    "pending_review", "approved", "rejected", "completed", "revoked"
]

# Allowed transitions: source status → set of valid destinations.
# Read this dict to understand the contract; do not duplicate the
# logic into the handler.
_ALLOWED_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    "pending_review": frozenset({"approved", "rejected", "completed"}),
    "approved": frozenset({"completed"}),
    "completed": frozenset({"revoked"}),
    "rejected": frozenset(),  # terminal
    "revoked": frozenset(),  # terminal
}


def _is_transition_allowed(
    from_status: ActionStatus, to_status: ActionStatus
) -> bool:
    """Pure predicate: return True if from→to is a legal state edge."""

    return to_status in _ALLOWED_TRANSITIONS.get(from_status, frozenset())


# ── Schemas ──────────────────────────────────────────────────────────────────


class ActionOut(BaseModel):
    """One row of the Pending Actions queue."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Action UUID.")
    user_id: str
    scan_run_id: str | None
    kind: str = Field(
        description="Machine-readable action kind, e.g. 'enable_branch_protection'."
    )
    title: str
    description: str
    status: ActionStatus
    tsc_id: str | None = Field(
        default=None,
        description="SOC 2 Trust Services Criteria id this action is tied to (e.g. 'CC6.1').",
    )
    source_link: str | None = Field(
        default=None,
        description="Deep link to the underlying source-system setting.",
    )
    rejected_reason: str | None = None
    revoked_reason: str | None = None
    revoked_at: str | None = None
    created_at: str
    updated_at: str


class ActionsListOut(BaseModel):
    """Response shape for ``GET /api/actions``."""

    model_config = ConfigDict(extra="forbid")

    actions: list[ActionOut] = Field(default_factory=list)
    count: int = 0


class ActionPatch(BaseModel):
    """Request body for ``PATCH /api/actions/{id}``.

    ``reason`` is required for the ``rejected`` and ``revoked`` transitions
    so the user records WHY the action was dismissed/undone. The handler
    enforces this at runtime; Pydantic alone cannot model "required
    conditional on status" cleanly without a discriminated union.
    """

    model_config = ConfigDict(extra="forbid")

    status: ActionStatus
    reason: str | None = Field(
        default=None,
        description=(
            "Free-text reason. Required when transitioning to "
            "'rejected' (recorded as rejected_reason) or 'revoked' "
            "(recorded as revoked_reason)."
        ),
        max_length=2000,
    )


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _fetch_action_for_user(
    pool: AppDbPool, *, user_id: str, action_id: str
) -> ActionOut | None:
    """Read an action by id, scoped to the user. ``None`` = not found."""

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id::text, user_id, scan_run_id, kind, title, description,
                       status, tsc_id, source_link, rejected_reason,
                       revoked_reason,
                       revoked_at, created_at, updated_at
                FROM actions
                WHERE user_id = %s AND id::text = %s
                """,
                (user_id, action_id),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_action(row)


async def _list_actions_for_user(
    pool: AppDbPool,
    *,
    user_id: str,
    status_filter: ActionStatus | None,
    limit: int,
) -> list[ActionOut]:
    """List actions scoped to the user, newest first.

    LIMIT 501 surfaces a write-cap-bypass condition (caller treats
    >500 as a degraded read) — same pattern as
    ``_list_scoped_repos`` in connectors.py per database-reviewer H-3.
    """

    sql_base = (
        "SELECT id::text, user_id, scan_run_id, kind, title, description, "
        "status, tsc_id, source_link, rejected_reason, revoked_reason, "
        "revoked_at, created_at, updated_at "
        "FROM actions WHERE user_id = %s"
    )
    params: tuple = (user_id,)
    if status_filter is not None:
        sql_base += " AND status = %s"
        params = (*params, status_filter)
    sql_base += " ORDER BY created_at DESC LIMIT %s"
    params = (*params, limit)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql_base, params)
            rows = await cur.fetchall()
            return [_row_to_action(row) for row in rows]


async def _apply_transition(
    pool: AppDbPool,
    *,
    user_id: str,
    action_id: str,
    new_status: ActionStatus,
    reason: str | None,
) -> ActionOut | None:
    """Apply the state machine transition. Returns the new row or None.

    Runs the read-current-status, validate-transition, write-new-status
    sequence inside a single transaction with ``SELECT ... FOR UPDATE``
    so two concurrent PATCHes don't both see ``pending_review`` and
    both transition the row (closes the TOCTOU window in the same
    pattern as Sprint 3.5's scoped-repos handler).

    Returns ``None`` when the row does not exist; raises
    :class:`HTTPException` 409 on an invalid transition.
    """

    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT status FROM actions
                    WHERE user_id = %s AND id::text = %s
                    FOR UPDATE
                    """,
                    (user_id, action_id),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                current_status: ActionStatus = row[0]
                if not _is_transition_allowed(current_status, new_status):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "invalid_transition",
                            "from_status": current_status,
                            "to_status": new_status,
                            "allowed": sorted(
                                _ALLOWED_TRANSITIONS.get(
                                    current_status, frozenset()
                                )
                            ),
                        },
                    )

                # The two transitions that require a reason gate it
                # here. Pydantic cannot easily express
                # "required-conditional-on-value" without a
                # discriminated union, so we keep the runtime check
                # next to the state machine.
                if new_status in {"rejected", "revoked"} and not (
                    reason and reason.strip()
                ):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "error": "reason_required",
                            "to_status": new_status,
                        },
                    )

                if new_status == "rejected":
                    await cur.execute(
                        """
                        UPDATE actions
                        SET status = %s,
                            rejected_reason = %s,
                            updated_at = now()
                        WHERE user_id = %s AND id::text = %s
                        """,
                        (new_status, reason, user_id, action_id),
                    )
                elif new_status == "revoked":
                    await cur.execute(
                        """
                        UPDATE actions
                        SET status = %s,
                            revoked_reason = %s,
                            revoked_at = now(),
                            updated_at = now()
                        WHERE user_id = %s AND id::text = %s
                        """,
                        (new_status, reason, user_id, action_id),
                    )
                else:
                    # approved or completed — no extra columns.
                    await cur.execute(
                        """
                        UPDATE actions
                        SET status = %s, updated_at = now()
                        WHERE user_id = %s AND id::text = %s
                        """,
                        (new_status, user_id, action_id),
                    )

                # Re-read inside the transaction so the response body
                # matches the committed state.
                await cur.execute(
                    """
                    SELECT id::text, user_id, scan_run_id, kind, title,
                           description, status, tsc_id, source_link,
                           rejected_reason, revoked_reason, revoked_at,
                           created_at, updated_at
                    FROM actions
                    WHERE user_id = %s AND id::text = %s
                    """,
                    (user_id, action_id),
                )
                fresh = await cur.fetchone()
                return _row_to_action(fresh) if fresh is not None else None


def _row_to_action(row: tuple) -> ActionOut:
    """Coerce a SELECT * row into an :class:`ActionOut`."""

    (
        id_,
        user_id,
        scan_run_id,
        kind,
        title,
        description,
        status_,
        tsc_id,
        source_link,
        rejected_reason,
        revoked_reason,
        revoked_at,
        created_at,
        updated_at,
    ) = row
    return ActionOut(
        id=id_,
        user_id=user_id,
        scan_run_id=scan_run_id,
        kind=kind,
        title=title,
        description=description or "",
        status=status_,
        tsc_id=tsc_id,
        source_link=source_link,
        rejected_reason=rejected_reason,
        revoked_reason=revoked_reason,
        revoked_at=_iso_or_none(revoked_at),
        created_at=_iso(created_at),
        updated_at=_iso(updated_at),
    )


def _iso(dt: datetime) -> str:
    """Format a non-null timestamp as ISO 8601 UTC."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _iso_or_none(dt: datetime | None) -> str | None:
    return _iso(dt) if dt is not None else None


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/actions", response_model=ActionsListOut)
@_actions_limiter.limit(_actions_list_rate_limit)
async def list_actions(
    request: Request,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
    status_filter: Annotated[
        ActionStatus | None,
        Query(
            alias="status",
            description="Filter to one status. Omit for all statuses.",
        ),
    ] = None,
) -> ActionsListOut:
    """Return the authenticated user's Pending Actions, newest first.

    Default page size 500; the FE always loads the full set for now
    because the dashboard view is a simple grouping. Sprint 5+ may
    paginate as actions accumulate from real scans.
    """

    with tracer.start_as_current_span("actions.list") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("status.filter", status_filter or "")
        actions = await _list_actions_for_user(
            pool,
            user_id=user.user_id,
            status_filter=status_filter,
            limit=500,
        )
        span.set_attribute("actions.count", len(actions))
        return ActionsListOut(actions=actions, count=len(actions))


@router.patch("/actions/{action_id}", response_model=ActionOut)
@_actions_limiter.limit(_actions_patch_rate_limit)
async def patch_action(
    request: Request,
    action_id: str,
    body: ActionPatch,
    pool: AppDbPoolDep,
    user: Annotated[ClerkUser, Depends(verify_clerk_token)],
) -> ActionOut:
    """Apply a state-machine transition to a single action.

    Returns:
      200 + updated row on success.
      404 if the action does not exist or is owned by another user
          (RLS + explicit WHERE on user_id).
      409 if the transition is not allowed from the current status.
      422 if a reason is required for the requested transition and was
          omitted.
    """

    with tracer.start_as_current_span("actions.patch") as span:
        span.set_attribute("user.id", user.user_id)
        span.set_attribute("action.id", action_id)
        span.set_attribute("transition.to", body.status)

        updated = await _apply_transition(
            pool,
            user_id=user.user_id,
            action_id=action_id,
            new_status=body.status,
            reason=body.reason,
        )
        if updated is None:
            span.set_attribute("action.not_found", True)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action not found",
            )
        span.set_attribute("action.new_status", updated.status)
        return updated


__all__ = [
    "ActionOut",
    "ActionPatch",
    "ActionStatus",
    "ActionsListOut",
    "router",
]
