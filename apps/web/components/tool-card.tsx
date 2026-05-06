"use client"

/**
 * ToolCard — renders an AI SDK 6 DynamicToolUIPart as a shadcn Card.
 *
 * Three states keyed off `part.state`:
 *   pending   — `input-streaming` | `input-available` — spinner, input known, no output yet
 *   success   — `output-available` — green check, expandable input + output JSON
 *   failure   — `output-error` — red icon, errorText shown
 *
 * AI SDK 6 (v6.0.57+) represents tool invocations that are not statically
 * typed on the useChat call-site as `DynamicToolUIPart` with:
 *   { type: 'dynamic-tool', toolName: string, toolCallId: string, state: ..., input?, output?, errorText? }
 *
 * Accessibility: aria-live="polite" so screen-reader announces state changes.
 * Test hooks: data-testid="tool-card", data-state="pending|success|failure".
 *
 * Refs: PLAN.md chunks 4.1, 4.2; US-010; ADR-0003.
 */

import { CheckCircle, Loader2, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

// The `state` discriminants from a dynamic-tool UI part that matter to us.
type ToolState = "pending" | "success" | "failure"

/** Structural shape of a dynamic-tool part — covers both AI SDK 6's
 * `DynamicToolUIPart` (from "ai") and our local `DynamicToolPart` (from
 * `lib/use-scan-stream`). Both expose the same five fields the card reads,
 * so the prop type stays decoupled from the producer. */
export interface ToolCardPart {
  type: "dynamic-tool"
  toolName: string
  toolCallId: string
  state: string
  input?: unknown
  output?: unknown
  errorText?: string
}

function resolveState(part: ToolCardPart): ToolState {
  if (part.state === "output-available") return "success"
  if (part.state === "output-error") return "failure"
  // input-streaming, input-available, approval-requested, approval-responded → pending
  return "pending"
}

interface ToolCardProps {
  part: ToolCardPart
  className?: string
}

export function ToolCard({ part, className }: ToolCardProps) {
  const toolState = resolveState(part)
  const hasOutput = toolState === "success" && "output" in part
  const hasInput = part.input !== undefined

  return (
    <div
      data-testid="tool-card"
      data-state={toolState}
      aria-live="polite"
      className={cn("w-full", className)}
    >
      <Card size="sm" className="border-dashed">
        <CardHeader className="flex flex-row items-center gap-2 pb-0">
          <StateIcon state={toolState} />
          <CardTitle className="text-xs font-mono font-semibold">
            {part.toolName}
          </CardTitle>
          <StateBadge state={toolState} />
        </CardHeader>

        <CardContent className="pt-2">
          {toolState === "failure" && "errorText" in part && part.errorText && (
            <p className="text-xs text-destructive" role="alert">
              {part.errorText}
            </p>
          )}

          {(hasInput || hasOutput) && (
            <details className="mt-1">
              <summary className="cursor-pointer select-none text-xs text-muted-foreground hover:text-foreground">
                {toolState === "success" ? "Input / Output" : "Input"}
              </summary>

              <div className="mt-2 space-y-2">
                {hasInput && (
                  <div>
                    <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Input
                    </p>
                    <pre className="overflow-auto rounded bg-muted p-2 text-[11px] leading-tight whitespace-pre-wrap break-all">
                      {JSON.stringify(part.input, null, 2)}
                    </pre>
                  </div>
                )}

                {hasOutput && (
                  <div>
                    <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Output
                    </p>
                    <pre className="overflow-auto rounded bg-muted p-2 text-[11px] leading-tight whitespace-pre-wrap break-all">
                      {JSON.stringify(part.output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StateIcon({ state }: { state: ToolState }) {
  if (state === "success") {
    return (
      <CheckCircle
        className="size-3.5 shrink-0 text-green-600 dark:text-green-400"
        aria-hidden
      />
    )
  }
  if (state === "failure") {
    return (
      <XCircle
        className="size-3.5 shrink-0 text-destructive"
        aria-hidden
      />
    )
  }
  // pending
  return (
    <Loader2
      className="size-3.5 shrink-0 animate-spin text-muted-foreground"
      aria-hidden
    />
  )
}

function StateBadge({ state }: { state: ToolState }) {
  if (state === "success") {
    return <Badge variant="success" className="ml-auto text-[10px]">done</Badge>
  }
  if (state === "failure") {
    return <Badge variant="error" className="ml-auto text-[10px]">error</Badge>
  }
  return <Badge variant="outline" className="ml-auto text-[10px]">running</Badge>
}
