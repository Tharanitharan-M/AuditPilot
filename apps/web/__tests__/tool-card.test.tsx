/**
 * ToolCard — snapshot + state tests (chunks 4.1, 4.2).
 *
 * Tests all three visible states: pending, success, failure.
 * Uses DynamicToolUIPart fixtures that match the AI SDK 6 wire shape
 * produced by FastAPI's sse/ai_sdk_v6.py (lookup_control tool).
 *
 * No network calls. No Clerk or Next.js navigation needed.
 *
 * Refs: PLAN.md chunk 4.2; US-010.
 */

import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import type { DynamicToolUIPart } from "ai"
import { ToolCard } from "@/components/tool-card"

// ── Fixtures ───────────────────────────────────────────────────────────────

const pendingInputStreaming: DynamicToolUIPart = {
  type: "dynamic-tool",
  toolName: "lookup_control",
  toolCallId: "call_abc123",
  state: "input-streaming",
  input: undefined,
}

const pendingInputAvailable: DynamicToolUIPart = {
  type: "dynamic-tool",
  toolName: "lookup_control",
  toolCallId: "call_abc124",
  state: "input-available",
  input: { control_id: "CC6.1" },
}

const successPart: DynamicToolUIPart = {
  type: "dynamic-tool",
  toolName: "lookup_control",
  toolCallId: "call_abc125",
  state: "output-available",
  input: { control_id: "CC6.1" },
  output: {
    control_id: "CC6.1",
    title: "Logical and Physical Access Controls",
    nist_refs: ["AC-2", "AC-3"],
  },
}

const failurePart: DynamicToolUIPart = {
  type: "dynamic-tool",
  toolName: "lookup_control",
  toolCallId: "call_abc126",
  state: "output-error",
  input: { control_id: "CC9.9" },
  errorText: "Control CC9.9 not found in knowledge base",
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe("ToolCard", () => {
  it("renders pending state (input-streaming) — data-state=pending, spinner visible", () => {
    render(<ToolCard part={pendingInputStreaming} />)
    const card = screen.getByTestId("tool-card")
    expect(card).toHaveAttribute("data-state", "pending")
    expect(card).toHaveAttribute("aria-live", "polite")
    // Tool name displayed
    expect(screen.getByText("lookup_control")).toBeInTheDocument()
    // Running badge
    expect(screen.getByText("running")).toBeInTheDocument()
    // No error text
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("renders pending state (input-available) — data-state=pending, input shown in details", () => {
    render(<ToolCard part={pendingInputAvailable} />)
    const card = screen.getByTestId("tool-card")
    expect(card).toHaveAttribute("data-state", "pending")
    // Both the <summary> label and the inner section heading say "Input" —
    // use getAllByText and assert at least one is present.
    expect(screen.getAllByText("Input").length).toBeGreaterThanOrEqual(1)
  })

  it("renders success state — data-state=success, done badge, input+output in details", () => {
    render(<ToolCard part={successPart} />)
    const card = screen.getByTestId("tool-card")
    expect(card).toHaveAttribute("data-state", "success")
    expect(screen.getByText("done")).toBeInTheDocument()
    expect(screen.getByText("lookup_control")).toBeInTheDocument()
    // Details summary label
    expect(screen.getByText("Input / Output")).toBeInTheDocument()
    // No error alert
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("renders failure state — data-state=failure, error badge, errorText in alert", () => {
    render(<ToolCard part={failurePart} />)
    const card = screen.getByTestId("tool-card")
    expect(card).toHaveAttribute("data-state", "failure")
    expect(screen.getByText("error")).toBeInTheDocument()
    const alert = screen.getByRole("alert")
    expect(alert).toHaveTextContent("Control CC9.9 not found in knowledge base")
  })

  it("snapshot — pending (input-streaming)", () => {
    const { container } = render(<ToolCard part={pendingInputStreaming} />)
    expect(container.firstChild).toMatchSnapshot()
  })

  it("snapshot — success (output-available)", () => {
    const { container } = render(<ToolCard part={successPart} />)
    expect(container.firstChild).toMatchSnapshot()
  })

  it("snapshot — failure (output-error)", () => {
    const { container } = render(<ToolCard part={failurePart} />)
    expect(container.firstChild).toMatchSnapshot()
  })
})
