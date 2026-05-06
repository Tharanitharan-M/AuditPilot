/**
 * POST /api/chat — Next.js proxy to FastAPI /chat (AI SDK 6 SSE bridge).
 *
 * Responsibilities:
 *   1. Verify the Clerk session; return 401 if unauthenticated.
 *   2. Zod-validate the request body before forwarding.
 *   3. Forward the body to FastAPI /chat with Authorization header.
 *   4. Pipe the FastAPI SSE response body straight back to the browser,
 *      preserving the `x-vercel-ai-ui-message-stream: v1` header so that
 *      AI SDK 6's useChat hook can parse it.
 *   5. Forward req.signal so a client disconnect propagates upstream
 *      (FastAPI chunk 4.9 cancellation path).
 *
 * The proxy keeps API_URL server-side — it is never exposed to the browser.
 *
 * Refs: PLAN.md chunks 4.1, 4.2; ADR-0003, ADR-0004, ADR-0008.
 */

import { auth } from "@clerk/nextjs/server"
import { NextRequest } from "next/server"
import { z } from "zod"

// ── Request body schema ───────────────────────────────────────────────────────
//
// AI SDK 6's `useChat` posts a body that combines our `body` option with its
// own fields (top-level `id`, per-message `id` / `createdAt`, etc.) plus the
// full UIMessage parts shape (which carries `state`, `toolCallId`, etc. for
// dynamic-tool parts). We validate ONLY the fields the proxy forwards
// meaningfully and let everything else pass through to FastAPI, whose
// ChatRequest model uses `extra="ignore"` on the same fields. The narrow
// validation surface still catches the high-value attacks (intent enum,
// connector_id pattern, repo_include_list cap) without fighting the AI SDK
// version-to-version churn on incidental fields.
const ChatBodySchema = z
  .object({
    messages: z
      .array(
        z
          .object({
            role: z.enum(["user", "assistant", "system"]),
            content: z.string().optional(),
            parts: z.array(z.unknown()).optional(),
          })
          .passthrough()
      )
      .min(1, "messages must contain at least one entry"),
    thread_id: z.string().max(128).optional(),
    intent: z
      .enum(["free_chat", "run_readiness_scan", "draft_policy", "fill_questionnaire"])
      .optional()
      .default("free_chat"),
    repo_include_list: z.array(z.string().max(128)).max(500).default([]),
    connector_id: z
      .string()
      .regex(/^eac_[a-zA-Z0-9]+$/, "connector_id must match eac_* pattern")
      .max(64)
      .optional()
      .nullable(),
  })
  .passthrough()

// ── Handler ───────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  // 1. Auth check
  const { userId, getToken } = await auth()
  if (!userId) {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  // 2. Parse + validate body
  let rawBody: unknown
  try {
    rawBody = await req.json()
  } catch {
    return new Response(JSON.stringify({ detail: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }

  const parsed = ChatBodySchema.safeParse(rawBody)
  if (!parsed.success) {
    const detail = parsed.error.errors[0]?.message ?? "Invalid request body"
    return new Response(JSON.stringify({ detail }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    })
  }

  // 3. Get session token
  const token = await getToken()
  if (!token) {
    return new Response(JSON.stringify({ detail: "Session expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  // 4. Forward to FastAPI — pipe SSE response straight back.
  //    req.signal propagation lets FastAPI chunk 4.9 cancel the graph run
  //    when the browser tab closes or the user navigates away.
  const apiBase = process.env.API_URL ?? "http://localhost:8000"

  let upstream: Response
  try {
    upstream = await fetch(`${apiBase}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(parsed.data),
      signal: req.signal,
    })
  } catch (err) {
    // Client disconnected before FastAPI responded — req.signal aborted.
    if (err instanceof Error && err.name === "AbortError") {
      return new Response(null, { status: 499 })
    }
    return new Response(
      JSON.stringify({ detail: err instanceof Error ? err.message : "Upstream error" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    )
  }

  // 5. Build the piped response, preserving the AI SDK 6 stream header.
  const responseHeaders = new Headers()
  responseHeaders.set("Content-Type", "text/event-stream")
  responseHeaders.set("Cache-Control", "no-cache")
  responseHeaders.set("Connection", "keep-alive")

  // Forward the AI SDK 6 protocol header so useChat parses the stream correctly.
  const streamHeader = upstream.headers.get("x-vercel-ai-ui-message-stream")
  if (streamHeader) {
    responseHeaders.set("x-vercel-ai-ui-message-stream", streamHeader)
  } else {
    // FastAPI always emits this; set the default in case an intermediary strips it.
    responseHeaders.set("x-vercel-ai-ui-message-stream", "v1")
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  })
}
