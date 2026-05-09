/**
 * GET /api/questionnaire/:id/download — proxy to FastAPI download endpoint.
 *
 * The upstream returns 302 to a 15-minute pre-signed R2 URL when the run is
 * ready; we follow the redirect and stream the body back to the browser so
 * the client can use a regular fetch + Blob download flow.
 *
 * Refs: PLAN.md Sprint 7 chunk 7.11.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest } from "next/server"
import { z } from "zod"

const apiBase = () => process.env.API_URL ?? "http://localhost:8000"
const IdSchema = z.string().regex(/^[0-9a-f\-]{1,64}$/, "Invalid run ID")

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
    return new Response(JSON.stringify({ detail: "Invalid run ID" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }
  try {
    const upstream = await fetch(
      `${apiBase()}/api/questionnaire/${idResult.data}/download`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: req.signal,
        redirect: "follow",
      }
    )
    const ct =
      upstream.headers.get("Content-Type") ??
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": ct,
        "Content-Disposition":
          upstream.headers.get("Content-Disposition") ??
          'attachment; filename="questionnaire_filled.xlsx"',
      },
    })
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return new Response(null, { status: 499 })
    }
    return new Response(JSON.stringify({ detail: "Upstream error" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    })
  }
}
