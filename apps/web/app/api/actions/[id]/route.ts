/**
 * PATCH /api/actions/[id] — Next.js proxy for action state-machine transitions.
 *
 * Validates:
 *   - Clerk session (401 if absent)
 *   - Path id against /^[a-zA-Z0-9-]+$/ (422 on path traversal attempt)
 *   - Request body via Zod: { status: ActionStatus, reason?: string (max 2000) }
 *
 * Forwards the validated body to ${API_URL}/api/actions/{id} and returns the
 * upstream response verbatim — including 404, 409, 422 — so the frontend can
 * surface server-side error messages (e.g. "invalid transition").
 *
 * Refs: PLAN.md chunk 4.7; US-007; ADR-0008.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest, NextResponse } from "next/server"
import { z } from "zod"

// Alphanumeric + hyphens only — refuses path traversal via "../" etc.
const ActionIdSchema = z
  .string()
  .regex(/^[a-zA-Z0-9-]+$/, "Invalid action id format")
  .max(128)

const ActionStatusSchema = z.enum([
  "pending_review",
  "approved",
  "rejected",
  "completed",
  "revoked",
])

const PatchBodySchema = z
  .object({
    status: ActionStatusSchema,
    reason: z.string().max(2000).optional(),
  })
  .strict()

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { userId, getToken } = await auth()
  if (!userId) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })
  }

  const { id: rawId } = await params
  const idParse = ActionIdSchema.safeParse(rawId)
  if (!idParse.success) {
    return NextResponse.json(
      { detail: idParse.error.errors[0]?.message ?? "Invalid id" },
      { status: 422 }
    )
  }
  const id = idParse.data

  const json = await req.json().catch(() => null)
  const bodyParse = PatchBodySchema.safeParse(json)
  if (!bodyParse.success) {
    return NextResponse.json(
      { detail: bodyParse.error.errors[0]?.message ?? "Invalid body" },
      { status: 422 }
    )
  }

  const token = await getToken()
  if (!token) {
    return NextResponse.json({ detail: "Session expired" }, { status: 401 })
  }

  const apiBase = process.env.API_URL ?? "http://localhost:8000"

  try {
    const res = await fetch(`${apiBase}/api/actions/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(bodyParse.data),
      signal: AbortSignal.timeout(10000),
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
