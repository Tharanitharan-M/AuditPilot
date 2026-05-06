"use client"

/**
 * useScanStream — focused replacement for AI SDK 4/5's useChat hook.
 *
 * Why a custom hook?
 *   The installed `@ai-sdk/react@1.2.x` is the AI SDK 4/5 React adapter; it
 *   parses the legacy data-stream protocol (`0:`, `2:`, `9:` prefix codes).
 *   FastAPI emits the AI SDK 6 UIMessage SSE format (plain `data: <json>`
 *   frames with `type: 'start' | 'text-delta' | 'tool-input-available' |
 *   ...`). The two formats are incompatible, which is why useChat was
 *   silently producing no messages on the dashboard.
 *
 *   Rather than upgrade `@ai-sdk/react` (and risk lockfile churn while
 *   Sprint 4 is mid-merge), this hook parses the actual chunk format
 *   directly. Surface matches the subset of useChat the dashboard uses.
 *
 * Wire format (verified against `apps/api/sse/ai_sdk_v6.py`):
 *
 *     data: {"type":"start","messageId":"msg_xxx","messageMetadata":{...}}
 *     data: {"type":"start-step"}
 *     data: {"type":"tool-input-available","toolCallId":"...","toolName":"...","input":{...}}
 *     data: {"type":"tool-output-available","toolCallId":"...","output":{...}}
 *     data: {"type":"text-start","id":"txt_xxx"}
 *     data: {"type":"text-delta","id":"txt_xxx","delta":"..."}
 *     data: {"type":"text-end","id":"txt_xxx"}
 *     data: {"type":"finish-step"}
 *     data: {"type":"finish","finishReason":"stop","messageMetadata":{...}}
 *     data: [DONE]
 *
 * Refs: PLAN.md chunks 4.1, 4.2 (Sprint 4 dashboard wiring + bugfix);
 *       apps/api/sse/ai_sdk_v6.py for the canonical chunk shapes.
 */

import { useCallback, useRef, useState } from "react"

// ── Public types ─────────────────────────────────────────────────────────────

export type Role = "user" | "assistant" | "system"

export type TextPart = { type: "text"; text: string }

export type DynamicToolPart = {
  type: "dynamic-tool"
  toolCallId: string
  toolName: string
  state:
    | "input-streaming"
    | "input-available"
    | "output-available"
    | "output-error"
  input?: unknown
  output?: unknown
  errorText?: string
}

export type Part = TextPart | DynamicToolPart

export type ScanMessage = {
  id: string
  role: Role
  content: string
  parts: Part[]
}

export type ScanStatus = "idle" | "submitted" | "streaming" | "error"

// Sprint 5 chunks 5.8 / 5.23 — typed-data part shapes flowing from the
// FastAPI SSE bridge (see ``apps/api/sse/ai_sdk_v6.py``: DataControlMapChunk
// and DataEvidenceRowsChunk). Kept as a thin alias of the runtime JSON shape
// so the dashboard wires straight through to ``<ControlPostureGrid>`` and
// ``<EvidenceCards>`` without an adapter layer.
export type StreamControlAssessment = {
  tsc_id: string
  status: "passing" | "failing" | "partial" | "unknown"
  confidence: number
  nist_800_53_refs: string[]
  evidence_ids: string[]
  rationale: string | null
}

export type StreamEvidenceRow = {
  id: string
  source_type: "github" | "clerk" | "manual" | "mock"
  source_uri: string | null
  raw: Record<string, unknown>
  content_hash: string | null
  collected_at: string
  scan_run_id: string | null
}

export interface UseScanStreamOptions {
  /** POST endpoint. Defaults to "/api/chat". */
  api?: string
  /** Static body fields merged into every POST. */
  body?: Record<string, unknown>
}

export interface UseScanStreamReturn {
  messages: ScanMessage[]
  input: string
  handleInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void
  append: (msg: { role: Role; content: string }) => Promise<void>
  status: ScanStatus
  error: Error | null
  /** Cancel the in-flight stream (no-op when idle). */
  stop: () => void
  /** Sprint 5 — live ControlAssessment[] from the most recent scan turn. */
  controlMap: StreamControlAssessment[]
  /** Sprint 5 — live Evidence rows from the most recent scan turn. */
  evidenceRows: StreamEvidenceRow[]
}

// ── SSE chunk types we consume ──────────────────────────────────────────────

type SseChunk =
  | { type: "start"; messageId: string; messageMetadata?: Record<string, unknown> }
  | { type: "start-step" }
  | { type: "finish-step" }
  | { type: "text-start"; id: string }
  | { type: "text-delta"; id: string; delta: string }
  | { type: "text-end"; id: string }
  | {
      type: "tool-input-available"
      toolCallId: string
      toolName: string
      input: unknown
    }
  | { type: "tool-output-available"; toolCallId: string; output: unknown }
  | { type: "tool-output-error"; toolCallId: string; errorText: string }
  | {
      type: "finish"
      finishReason?: string
      messageMetadata?: Record<string, unknown>
    }
  | { type: "error"; errorText: string }
  | { type: "abort"; reason?: string }
  // Sprint 5 typed-data chunks emitted by ``apps/api/sse/ai_sdk_v6.py``.
  | { type: "data-control-map"; id: string; data: StreamControlAssessment[] }
  | { type: "data-evidence-rows"; id: string; data: StreamEvidenceRow[] }

// ── Hook ─────────────────────────────────────────────────────────────────────

let _idCounter = 0
function _nextId(prefix: string): string {
  _idCounter += 1
  return `${prefix}_${Date.now().toString(36)}_${_idCounter}`
}

export function useScanStream(
  options: UseScanStreamOptions = {}
): UseScanStreamReturn {
  const api = options.api ?? "/api/chat"
  const staticBody = options.body ?? {}

  const [messages, setMessages] = useState<ScanMessage[]>([])
  const [input, setInput] = useState("")
  const [status, setStatus] = useState<ScanStatus>("idle")
  const [error, setError] = useState<Error | null>(null)
  // Sprint 5 — live state lifted out of the message stream so siblings of
  // ScanChat (the Control Posture grid, Evidence cards) can render the
  // current scan without re-parsing the chat transcript.
  const [controlMap, setControlMap] = useState<StreamControlAssessment[]>([])
  const [evidenceRows, setEvidenceRows] = useState<StreamEvidenceRow[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setInput(e.target.value)
    },
    []
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const submit = useCallback(
    async (
      userMessage: { role: Role; content: string },
      historySnapshot: ScanMessage[]
    ) => {
      setError(null)
      setStatus("submitted")

      const controller = new AbortController()
      abortRef.current?.abort()
      abortRef.current = controller

      // Sprint 5 — clear stale streamed data so a re-scan does not flash
      // the previous run's grid/evidence while the new stream warms up.
      setControlMap([])
      setEvidenceRows([])

      // Optimistically push the user turn into the transcript.
      const userMsg: ScanMessage = {
        id: _nextId("user"),
        role: userMessage.role,
        content: userMessage.content,
        parts: [{ type: "text", text: userMessage.content }],
      }
      const transcript = [...historySnapshot, userMsg]
      setMessages(transcript)

      // POST the full transcript so the server has the conversation history.
      const wireMessages = transcript.map((m) => ({
        role: m.role,
        content: m.content,
        parts: m.parts,
      }))

      let response: Response
      try {
        response = await fetch(api, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...staticBody, messages: wireMessages }),
          signal: controller.signal,
        })
      } catch (fetchErr) {
        if ((fetchErr as Error).name === "AbortError") {
          setStatus("idle")
          return
        }
        setError(fetchErr as Error)
        setStatus("error")
        return
      }

      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`
        try {
          const body = await response.json()
          if (body && typeof body.detail === "string") detail = body.detail
        } catch {
          // upstream may not have returned JSON; keep the status-line detail.
        }
        setError(new Error(`/${api.split("/").pop()} returned ${detail}`))
        setStatus("error")
        return
      }

      if (response.body == null) {
        setError(new Error("Server returned an empty stream"))
        setStatus("error")
        return
      }

      setStatus("streaming")

      const assistantId = _nextId("asst")
      const assistant: ScanMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        parts: [],
      }

      // Append a fresh assistant message that we'll mutate as chunks arrive.
      setMessages((prev) => [...prev, assistant])

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          // SSE frames are separated by a blank line.
          let separatorIdx = buffer.indexOf("\n\n")
          while (separatorIdx !== -1) {
            const frame = buffer.slice(0, separatorIdx)
            buffer = buffer.slice(separatorIdx + 2)
            separatorIdx = buffer.indexOf("\n\n")

            for (const line of frame.split("\n")) {
              if (!line.startsWith("data: ")) continue
              const payload = line.slice("data: ".length)
              if (payload === "[DONE]") {
                setStatus("idle")
                return
              }
              let parsed: SseChunk
              try {
                parsed = JSON.parse(payload) as SseChunk
              } catch {
                continue
              }
              // Sprint 5 — typed-data parts are siblings of message parts;
              // hoist them into their own state slots and skip the message
              // mutator so they don't accidentally land in the transcript.
              if (parsed.type === "data-control-map") {
                setControlMap(parsed.data)
                continue
              }
              if (parsed.type === "data-evidence-rows") {
                setEvidenceRows(parsed.data)
                continue
              }
              applyChunk(setMessages, assistantId, parsed)
              if (parsed.type === "error") {
                setError(new Error(parsed.errorText))
                setStatus("error")
                return
              }
              if (parsed.type === "abort") {
                setStatus("idle")
                return
              }
              if (parsed.type === "finish") {
                // Don't break — the [DONE] sentinel still needs to land
                // (or the connection close will end the loop normally).
              }
            }
          }
        }
        setStatus("idle")
      } catch (streamErr) {
        if ((streamErr as Error).name === "AbortError") {
          setStatus("idle")
          return
        }
        setError(streamErr as Error)
        setStatus("error")
      }
    },
    [api, staticBody]
  )

  const append = useCallback(
    async (msg: { role: Role; content: string }) => {
      // Use the latest messages snapshot at call time.
      // setMessages with a function getter is the safe React pattern, but
      // submit() needs the value synchronously — so we read from a ref-like
      // closure by capturing during the previous render. The simpler form:
      // use a functional updater that calls submit from inside.
      setMessages((current) => {
        // Fire-and-forget; submit handles its own errors via state.
        void submit(msg, current).catch((e) =>
          console.error("scan_stream.submit_error", e)
        )
        return current
      })
    },
    [submit]
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault()
      const trimmed = input.trim()
      if (!trimmed) return
      setInput("")
      void append({ role: "user", content: trimmed })
    },
    [input, append]
  )

  return {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    append,
    status,
    error,
    stop,
    controlMap,
    evidenceRows,
  }
}

// ── Chunk → message mutator ─────────────────────────────────────────────────

function applyChunk(
  setMessages: React.Dispatch<React.SetStateAction<ScanMessage[]>>,
  assistantId: string,
  chunk: SseChunk
): void {
  setMessages((prev) =>
    prev.map((msg) => {
      if (msg.id !== assistantId) return msg
      return mutateAssistant(msg, chunk)
    })
  )
}

function mutateAssistant(msg: ScanMessage, chunk: SseChunk): ScanMessage {
  switch (chunk.type) {
    case "text-start": {
      // Begin a new text part with an empty buffer.
      return {
        ...msg,
        parts: [...msg.parts, { type: "text", text: "" }],
      }
    }
    case "text-delta": {
      // Append the delta to the LAST text part (they arrive in order).
      const parts = [...msg.parts]
      for (let i = parts.length - 1; i >= 0; i -= 1) {
        const p = parts[i]
        if (p.type === "text") {
          parts[i] = { type: "text", text: p.text + chunk.delta }
          break
        }
      }
      return {
        ...msg,
        parts,
        content: msg.content + chunk.delta,
      }
    }
    case "text-end": {
      // No structural change; the buffered text is already in place.
      return msg
    }
    case "tool-input-available": {
      // Append (or update) a dynamic-tool part keyed on toolCallId.
      const existingIdx = msg.parts.findIndex(
        (p) =>
          p.type === "dynamic-tool" && p.toolCallId === chunk.toolCallId
      )
      const next: DynamicToolPart = {
        type: "dynamic-tool",
        toolCallId: chunk.toolCallId,
        toolName: chunk.toolName,
        state: "input-available",
        input: chunk.input,
      }
      if (existingIdx >= 0) {
        const parts = [...msg.parts]
        parts[existingIdx] = next
        return { ...msg, parts }
      }
      return { ...msg, parts: [...msg.parts, next] }
    }
    case "tool-output-available": {
      const parts = msg.parts.map((p) => {
        if (p.type !== "dynamic-tool") return p
        if (p.toolCallId !== chunk.toolCallId) return p
        return { ...p, state: "output-available" as const, output: chunk.output }
      })
      return { ...msg, parts }
    }
    case "tool-output-error": {
      const parts = msg.parts.map((p) => {
        if (p.type !== "dynamic-tool") return p
        if (p.toolCallId !== chunk.toolCallId) return p
        return {
          ...p,
          state: "output-error" as const,
          errorText: chunk.errorText,
        }
      })
      return { ...msg, parts }
    }
    default:
      return msg
  }
}
