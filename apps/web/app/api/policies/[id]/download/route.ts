/**
 * GET /api/policies/:id/download?format=md|docx — proxy to FastAPI.
 *
 * Refs: PLAN.md Sprint 6 chunk 6.15; ADR-0007.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest } from "next/server"
import { z } from "zod"

const apiBase = () => process.env.API_URL ?? "http://localhost:8000"
const IdSchema = z.string().regex(/^[0-9a-f\-]{1,64}$/, "Invalid policy ID format")

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

  const format = req.nextUrl.searchParams.get("format") ?? "md"
  if (format !== "md" && format !== "docx") {
    return new Response(
      JSON.stringify({ detail: "format must be 'md' or 'docx'" }),
      { status: 422, headers: { "Content-Type": "application/json" } }
    )
  }

  try {
    const upstream = await fetch(
      `${apiBase()}/api/policies/${idResult.data}/download?format=${format}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: req.signal,
      }
    )

    const headers = new Headers()
    const ct = upstream.headers.get("Content-Type")
    if (ct) headers.set("Content-Type", ct)
    const cd = upstream.headers.get("Content-Disposition")
    if (cd) headers.set("Content-Disposition", cd)

    return new Response(upstream.body, {
      status: upstream.status,
      headers,
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
