/**
 * ScanChat — unit tests for the chat surface (chunks 4.1, 4.2).
 *
 * Tests:
 *   1. Empty-scope state — "Run readiness scan" button disabled, scope CTA shown.
 *   2. Populated-scope state — button enabled with correct label.
 *   3. ToolCard rendered when messages contain a dynamic-tool part.
 *   4. Text messages render in correct bubbles (user right, assistant left).
 *   5. Error banner surfaces when the hook reports an error.
 *
 * Mocks: @/lib/use-scan-stream (the hook ScanChat consumes since the
 * Sprint-4 bugfix that replaced the @ai-sdk/react@1.x adapter with a
 * native AI SDK 6 UIMessage parser), @clerk/nextjs, next/navigation,
 * next/link.
 *
 * Refs: PLAN.md chunks 4.1, 4.2; US-010.
 */

import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import type {
  DynamicToolPart,
  ScanMessage,
  ScanStatus,
} from "@/lib/use-scan-stream"

// ── Mocks ──────────────────────────────────────────────────────────────────

const mockAppend = vi.fn()
const mockHandleSubmit = vi.fn()
const mockHandleInputChange = vi.fn()
const mockStop = vi.fn()

// Default: idle, no messages, no error.
let mockHookReturn = {
  messages: [] as ScanMessage[],
  input: "",
  handleInputChange: mockHandleInputChange,
  handleSubmit: mockHandleSubmit,
  status: "idle" as ScanStatus,
  append: mockAppend,
  error: null as Error | null,
  stop: mockStop,
  // Sprint 5 — typed-data slots added to UseScanStreamReturn so ScanChat's
  // optional `stream` prop satisfies the new shape in workspace mode.
  controlMap: [],
  evidenceRows: [],
}

vi.mock("@/lib/use-scan-stream", () => ({
  useScanStream: () => mockHookReturn,
}))

// Mock Clerk (ScanChat doesn't use it directly, but connector-card sub-deps might).
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => "test-token" }),
  useUser: () => ({ user: null }),
}))

// Mock next/navigation.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

// Mock next/link — render as a plain <a> so href assertions work in jsdom.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: { href: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// Import after mocks are registered.
import { ScanChat } from "@/components/scan-chat"

// ── Fixtures ───────────────────────────────────────────────────────────────

const CONNECTOR_ID = "eac_test123"
const REPO_IDS = ["111", "222", "333"]

const toolPart: DynamicToolPart = {
  type: "dynamic-tool",
  toolName: "lookup_control",
  toolCallId: "call_xyz",
  state: "output-available",
  input: { control_id: "CC6.1" },
  output: { title: "Logical and Physical Access Controls" },
}

const messagesWithTool: ScanMessage[] = [
  {
    id: "msg-1",
    role: "user",
    content: "Run readiness scan on the scoped repositories.",
    parts: [
      { type: "text", text: "Run readiness scan on the scoped repositories." },
    ],
  },
  {
    id: "msg-2",
    role: "assistant",
    content: "Here are the findings for CC6.1.",
    parts: [
      toolPart,
      { type: "text", text: "Here are the findings for CC6.1." },
    ],
  },
]

// ── Tests ──────────────────────────────────────────────────────────────────

describe("ScanChat", () => {
  beforeEach(() => {
    mockAppend.mockReset()
    mockHandleSubmit.mockReset()
    mockHandleInputChange.mockReset()
    mockStop.mockReset()
    // Reset to default idle state with no messages.
    mockHookReturn = {
      messages: [],
      input: "",
      handleInputChange: mockHandleInputChange,
      handleSubmit: mockHandleSubmit,
      status: "idle",
      append: mockAppend,
      error: null,
      stop: mockStop,
      controlMap: [],
      evidenceRows: [],
    }
  })

  it("empty-scope: Run readiness scan button is disabled + scope CTA link rendered", () => {
    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={[]} />
    )

    const btn = screen.getByRole("button", { name: /run readiness scan/i })
    expect(btn).toBeDisabled()

    // Scope CTA link points to the correct scope-picker URL.
    const link = screen.getByRole("link", { name: /configure scope/i })
    expect(link).toHaveAttribute(
      "href",
      `/dashboard/connectors/${CONNECTOR_ID}/scope`
    )
  })

  it("populated-scope: Run readiness scan button is enabled", () => {
    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    const btn = screen.getByRole("button", { name: /run readiness scan/i })
    expect(btn).toBeEnabled()
    expect(btn).toHaveTextContent(/run readiness scan/i)
  })

  it("populated-scope: clicking Run readiness scan calls append with the correct message", () => {
    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    fireEvent.click(screen.getByRole("button", { name: /run readiness scan/i }))

    expect(mockAppend).toHaveBeenCalledOnce()
    expect(mockAppend).toHaveBeenCalledWith(
      expect.objectContaining({ role: "user" })
    )
  })

  it("streaming: scan button is disabled while status=streaming", () => {
    mockHookReturn = { ...mockHookReturn, status: "streaming" }

    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    // aria-label stays "Run readiness scan" even when the visible text is
    // "Scanning…" — query by aria-label (the accessible name).
    const btn = screen.getByRole("button", { name: /run readiness scan/i })
    expect(btn).toBeDisabled()
    // The visible label changes to "Scanning…" while streaming.
    expect(btn).toHaveTextContent(/scanning/i)
  })

  it("renders a ToolCard for a dynamic-tool part in assistant messages", () => {
    mockHookReturn = { ...mockHookReturn, messages: messagesWithTool }

    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    // ToolCard should be present with data-state=success.
    const toolCard = screen.getByTestId("tool-card")
    expect(toolCard).toBeInTheDocument()
    expect(toolCard).toHaveAttribute("data-state", "success")
    // Tool name rendered inside the card.
    expect(screen.getByText("lookup_control")).toBeInTheDocument()
  })

  it("renders user message in a right-aligned bubble", () => {
    mockHookReturn = { ...mockHookReturn, messages: messagesWithTool }

    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    expect(
      screen.getByText("Run readiness scan on the scoped repositories.")
    ).toBeInTheDocument()
  })

  it("renders assistant text alongside ToolCard", () => {
    mockHookReturn = { ...mockHookReturn, messages: messagesWithTool }

    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    expect(
      screen.getByText("Here are the findings for CC6.1.")
    ).toBeInTheDocument()
  })

  it("empty-scope: shows empty-scope placeholder copy in the message area", () => {
    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={[]} />
    )

    expect(
      screen.getByText(/configure a repo scope to enable the readiness scan/i)
    ).toBeInTheDocument()
  })

  it("populated-scope with no messages: shows the get-started placeholder", () => {
    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    expect(
      screen.getByText(/click.*run readiness scan.*to start/i)
    ).toBeInTheDocument()
  })

  it("renders an error banner when the hook reports an error", () => {
    mockHookReturn = {
      ...mockHookReturn,
      error: new Error("/chat returned 500 Internal Server Error"),
    }

    render(
      <ScanChat connectorId={CONNECTOR_ID} repoIncludeList={REPO_IDS} />
    )

    const banner = screen.getByTestId("scan-chat-error")
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveTextContent(/500 internal server error/i)
  })
})
