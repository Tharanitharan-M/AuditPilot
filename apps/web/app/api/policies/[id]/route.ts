/**
 * GET + PATCH /api/policies/:id — proxy to FastAPI.
 *
 * Refs: PLAN.md Sprint 6 chunk 6.10; ADR-0007.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest } from "next/server"
import { z } from "zod"

const apiBase = () => process.env.API_URL ?? "http://localhost:8000"

const IdSchema = z.string().regex(/^[0-9a-f\-]{1,64}$/, "Invalid policy ID format")

const PatchSchema = z.object({
  content: z.string().max(100_000),
  title: z.string().max(200).optional(),
})

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { userId, getToken } = await auth()
  if (!userId) {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  const token = await getToken()
  if (!token) {
    return new Response(JSON.stringify({ detail: "Session expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  const { id } = await params
  const idResult = IdSchema.safeParse(id)
  if (!idResult.success) {
    return new Response(JSON.stringify({ detail: "Invalid policy ID" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }

  try {
    const upstream = await fetch(`${apiBase()}/api/policies/${idResult.data}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: req.signal,
    })
    const ct = upstream.headers.get("Content-Type") ?? "application/json"
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": ct },
    })
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return new Response(null, { status: 499 })
    }
    return new Response(
      JSON.stringify({ detail: "Upstream error" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    )
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { userId, getToken } = await auth()
  if (!userId) {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  const token = await getToken()
  if (!token) {
    return new Response(JSON.stringify({ detail: "Session expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  let rawBody: unknown
  try {
    rawBody = await req.json()
  } catch {
    return new Response(JSON.stringify({ detail: "Invalid JSON" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }

  const parsed = PatchSchema.safeParse(rawBody)
  if (!parsed.success) {
    return new Response(
      JSON.stringify({ detail: parsed.error.errors[0]?.message ?? "Invalid body" }),
      { status: 422, headers: { "Content-Type": "application/json" } }
    )
  }

  const { id } = await params
  const idResult = IdSchema.safeParse(id)
  if (!idResult.success) {
    return new Response(JSON.stringify({ detail: "Invalid policy ID" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }

  try {
    const upstream = await fetch(`${apiBase()}/api/policies/${idResult.data}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(parsed.data),
      signal: req.signal,
    })
    const ct = upstream.headers.get("Content-Type") ?? "application/json"
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": ct },
    })
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return new Response(null, { status: 499 })
    }
    return new Response(
      JSON.stringify({ detail: "Upstream error" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    )
  }
}
