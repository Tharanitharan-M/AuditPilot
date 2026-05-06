/**
 * GET /api/actions — Next.js proxy to FastAPI pending-actions endpoint.
 *
 * Authenticates via Clerk session, forwards an optional ?status= query param,
 * and proxies to ${API_URL}/api/actions. Returns the upstream JSON verbatim.
 *
 * Cache: no-store so the Pending Actions queue is always fresh (revalidate: 0
 * is only available in the `fetch` options; export const revalidate = 0 handles
 * the RSC layer — this is a Route Handler so we use no-store).
 *
 * Refs: PLAN.md chunk 4.7; US-007; ADR-0008.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest, NextResponse } from "next/server"
import { z } from "zod"

export const revalidate = 0

// typescript-reviewer H-2 — Zod-validate ``?status=`` so the proxy
// returns a clean 422 to malformed input rather than letting the
// FastAPI backend produce a 500. Mirrors the validation surface of
// every other AuditPilot proxy.
const StatusFilterSchema = z
  .enum([
    "pending_review",
    "approved",
    "rejected",
    "completed",
    "revoked",
  ])
  .optional()

export async function GET(req: NextRequest) {
  const { userId, getToken } = await auth()
  if (!userId) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })
  }

  const token = await getToken()
  if (!token) {
    return NextResponse.json({ detail: "Session expired" }, { status: 401 })
  }

  const apiBase = process.env.API_URL ?? "http://localhost:8000"

  // Forward the ?status= query param if present, only after Zod validation.
  const rawStatus = req.nextUrl.searchParams.get("status")
  const parsed = StatusFilterSchema.safeParse(rawStatus ?? undefined)
  if (!parsed.success) {
    return NextResponse.json(
      {
        detail: parsed.error.errors[0]?.message ?? "Invalid status filter",
      },
      { status: 422 }
    )
  }
  const statusParam = parsed.data
  const upstreamUrl = statusParam
    ? `${apiBase}/api/actions?status=${encodeURIComponent(statusParam)}`
    : `${apiBase}/api/actions`

  try {
    const res = await fetch(upstreamUrl, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10000),
      cache: "no-store",
    })

    const text = await res.text()
    return new NextResponse(text || null, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    })
  } catch (err) {
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : "Upstream error" },
      { status: 502 }
    )
  }
}
