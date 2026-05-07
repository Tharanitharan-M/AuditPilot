"use client"

/**
 * ScanChat — AI SDK 6 useChat client island for the dashboard.
 *
 * Renders the readiness-scan chat surface: user bubbles (right-aligned),
 * assistant text bubbles (left-aligned), and tool invocations as <ToolCard>.
 * Connects to the Next.js proxy at /api/chat which forwards to FastAPI /chat.
 *
 * Props:
 *   connectorId      — Clerk external-account id (eac_*). Forwarded to backend.
 *   repoIncludeList  — provider_repo_id strings from the scoped-repos picker.
 *                      When empty, the "Run readiness scan" button is disabled
 *                      and a CTA links to the scope-picker page.
 *
 * Refs: PLAN.md chunks 4.1, 4.2; US-010; ADR-0003.
 */

import { useRef, useEffect } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { ToolCard } from "@/components/tool-card"
import {
  useScanStream,
  type DynamicToolPart,
  type ScanMessage,
  type UseScanStreamReturn,
} from "@/lib/use-scan-stream"

interface ScanChatProps {
  connectorId: string
  repoIncludeList: string[]
  /**
   * Sprint 5 — when supplied, the chat uses an externally-owned stream
   * (so siblings like the Control Posture grid render off the same
   * single source of truth). When omitted, the component falls back to
   * its self-contained Sprint 4 behaviour and owns its own hook.
   */
  stream?: UseScanStreamReturn
}

export function ScanChat({
  connectorId,
  repoIncludeList,
  stream,
}: ScanChatProps) {
  const hasScope = repoIncludeList.length > 0
  const scrollRef = useRef<HTMLDivElement>(null)

  const ownStream = useScanStream({
    api: "/api/chat",
    body: {
      intent: "run_readiness_scan",
      repo_include_list: repoIncludeList,
      connector_id: connectorId,
    },
  })

  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    status,
    append,
    error,
  } = stream ?? ownStream

  const isStreaming = status === "submitted" || status === "streaming"

  // Auto-scroll to bottom on new chunks.
  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages])

  function handleScanClick() {
    if (!hasScope || isStreaming) return
    append({
      role: "user",
      content: "Run readiness scan on the scoped repositories.",
    })
  }

  return (
    <section
      aria-label="Readiness scan chat"
      className="flex flex-col rounded-xl border bg-card"
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-medium">Readiness Scan</h2>

        {hasScope ? (
          <Button
            size="xs"
            onClick={handleScanClick}
            disabled={isStreaming}
            aria-label="Run readiness scan"
          >
            {isStreaming ? "Scanning…" : "Run scan"}
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">
            No repos scoped.{" "}
            <Link
              href={`/dashboard/connectors/${connectorId}/scope`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              Configure →
            </Link>
          </p>
        )}
      </div>

      {error && (
        <div
          role="alert"
          aria-live="assertive"
          aria-atomic="true"
          data-testid="scan-chat-error"
          className="mx-4 mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </div>
      )}

      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-busy={isStreaming}
        className="flex min-h-[300px] max-h-[60vh] flex-col gap-3 overflow-y-auto px-4 py-4"
        aria-label="Chat messages"
      >
        {messages.length === 0 && !isStreaming && (
          <div className="m-auto flex flex-col items-center gap-2 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
              <svg className="h-5 w-5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
              </svg>
            </div>
            <p className="text-sm text-muted-foreground">
              {hasScope
                ? "Run a scan or ask a question to get started."
                : "Configure a repo scope to enable scanning."}
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageRow key={msg.id} message={msg} />
        ))}

        {isStreaming && messages.length === 0 && (
          <div
            role="status"
            aria-label="Streaming readiness scan response"
            className="space-y-2"
          >
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex gap-2 border-t px-4 py-3"
        aria-label="Chat input"
      >
        <Input
          value={input}
          onChange={handleInputChange}
          placeholder="Ask about your readiness…"
          disabled={isStreaming}
          aria-label="Chat message input"
          className="h-9 text-sm"
        />
        <Button type="submit" size="sm" disabled={isStreaming || !input.trim()}>
          Send
        </Button>
      </form>
    </section>
  )
}

// ── MessageRow ────────────────────────────────────────────────────────────────

// useScanStream emits a discriminated union of TextPart | DynamicToolPart so
// the duck-type guards below resolve without `as unknown` widening.
function MessageRow({ message }: { message: ScanMessage }) {
  const isUser = message.role === "user"

  if (isUser) {
    const text =
      message.parts
        .filter((p): p is { type: "text"; text: string } => p.type === "text")
        .map((p) => p.text)
        .join("") || message.content

    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-xl rounded-tr-sm bg-primary px-3 py-2 text-sm text-primary-foreground">
          {text}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {message.parts.map((part, i) => {
        if (part.type === "text") {
          if (!part.text) return null
          return (
            <div
              key={`${message.id}-text-${i}`}
              className="max-w-[85%] rounded-xl rounded-tl-sm bg-muted px-3 py-2 text-sm"
            >
              {part.text}
            </div>
          )
        }

        if (part.type === "dynamic-tool") {
          // typescript-reviewer H-4 — toolCallId is stable across the
          // pending → success/failure transitions, so React reconciles
          // the existing ToolCard instead of unmounting + remounting it.
          const toolPart: DynamicToolPart = part
          return <ToolCard key={toolPart.toolCallId} part={toolPart} />
        }

        return null
      })}
    </div>
  )
}
