/**
 * POST /api/questionnaire/upload — proxy to FastAPI; forwards multipart body.
 *
 * Refs: PLAN.md Sprint 7 chunk 7.6.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest } from "next/server"

const apiBase = () => process.env.API_URL ?? "http://localhost:8000"
const MAX_BYTES = 10 * 1024 * 1024 // FE-side guard mirrors the API limit.

export async function POST(req: NextRequest) {
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

  // Cheap header check to short-circuit oversized bodies before they cross
  // the proxy boundary. FastAPI re-validates with a precise count.
  const contentLength = req.headers.get("content-length")
  if (contentLength && Number(contentLength) > MAX_BYTES + 64 * 1024) {
    return new Response(JSON.stringify({ detail: "File exceeds 10 MB" }), {
      status: 413,
      headers: { "Content-Type": "application/json" },
    })
  }

  try {
    const contentType = req.headers.get("content-type") ?? "multipart/form-data"
    const upstream = await fetch(`${apiBase()}/api/questionnaire/upload`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": contentType,
      },
      body: req.body,
      // @ts-expect-error duplex is required for streaming bodies in Node 18+
      duplex: "half",
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
    return new Response(JSON.stringify({ detail: "Upstream error" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    })
  }
}
