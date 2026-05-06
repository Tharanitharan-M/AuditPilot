/**
 * ControlPostureGrid — unit tests (chunk 4.6).
 *
 * Covers:
 *   - Snapshot: representative fixture with all 4 statuses across 3 categories.
 *   - Empty state renders when assessments=[].
 *   - Clicking a chip reveals the detail panel.
 *   - Clicking the same chip again collapses the detail panel.
 *   - Clicking a different chip switches the open panel.
 *   - aria-labels include the status word for each status variant.
 *   - NIST refs, rationale, and evidence_ids render in the detail panel.
 *   - Null rationale renders "No rationale" italic text.
 *
 * No mocks needed — ControlPostureGrid has no external deps (no Clerk,
 * no router, no AI SDK).
 *
 * Refs: PLAN.md Sprint 4 chunk 4.6, ADR-0013, US-006.
 */

import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import {
  ControlPostureGrid,
  type ControlAssessment,
} from "@/components/control-posture-grid"

// ── Fixtures ──────────────────────────────────────────────────────────────────

const ASSESSMENTS: ControlAssessment[] = [
  // CC category — three sub-clauses covering all 4 status variants
  {
    tsc_id: "CC6.1",
    status: "passing",
    confidence: 0.92,
    nist_800_53_refs: ["AC-2", "AC-3", "SC-7"],
    evidence_ids: ["ev-001", "ev-002"],
    rationale: "All access control policies are documented and enforced.",
  },
  {
    tsc_id: "CC6.2",
    status: "failing",
    confidence: 0.21,
    nist_800_53_refs: ["AC-6"],
    evidence_ids: [],
    rationale: "Least-privilege review has not been completed this quarter.",
  },
  {
    tsc_id: "CC7.1",
    status: "partial",
    confidence: 0.55,
    nist_800_53_refs: ["SI-2", "RA-5"],
    evidence_ids: ["ev-010"],
    rationale: null,
  },
  // A category
  {
    tsc_id: "A1.1",
    status: "unknown",
    confidence: 0,
    nist_800_53_refs: [],
    evidence_ids: [],
    rationale: null,
  },
  // PI category
  {
    tsc_id: "PI1.2",
    status: "passing",
    confidence: 0.88,
    nist_800_53_refs: ["SI-10"],
    evidence_ids: ["ev-020"],
    rationale: "Input validation controls are in place and tested.",
  },
]

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ControlPostureGrid", () => {
  // ── Empty state ─────────────────────────────────────────────────────────────

  it("renders empty state when assessments=[]", () => {
    render(<ControlPostureGrid assessments={[]} />)
    expect(screen.getByTestId("control-posture-empty")).toBeInTheDocument()
    expect(
      screen.getByText(/no scan run yet/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/run readiness scan/i)
    ).toBeInTheDocument()
    // Grid should NOT be present.
    expect(screen.queryByTestId("control-posture-grid")).not.toBeInTheDocument()
  })

  it("renders empty state when assessments prop is omitted (default)", () => {
    render(<ControlPostureGrid />)
    expect(screen.getByTestId("control-posture-empty")).toBeInTheDocument()
  })

  // ── Grid renders ────────────────────────────────────────────────────────────

  it("renders the grid container when assessments are provided", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    expect(screen.getByTestId("control-posture-grid")).toBeInTheDocument()
    expect(screen.queryByTestId("control-posture-empty")).not.toBeInTheDocument()
  })

  it("renders chips for all provided tsc_ids", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    for (const a of ASSESSMENTS) {
      // aria-label includes the tsc_id
      expect(
        screen.getByRole("button", { name: new RegExp(a.tsc_id) })
      ).toBeInTheDocument()
    }
  })

  // ── Category grouping ────────────────────────────────────────────────────────

  it("groups CC6.1 and CC6.2 under the same CC6 row", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const cc6Row = screen.getByTestId("control-row-CC6")
    expect(cc6Row).toBeInTheDocument()
    // Both chips should be inside this row.
    expect(cc6Row.querySelector('[aria-label*="CC6.1"]')).not.toBeNull()
    expect(cc6Row.querySelector('[aria-label*="CC6.2"]')).not.toBeNull()
  })

  it("renders CC7.1 in its own CC7 row, separate from CC6", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    expect(screen.getByTestId("control-row-CC7")).toBeInTheDocument()
    expect(screen.getByTestId("control-row-CC6")).toBeInTheDocument()
  })

  // ── Aria-label status encoding ───────────────────────────────────────────────

  it("aria-label includes 'passing' for a passing chip", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const btn = screen.getByRole("button", { name: /CC6\.1/i })
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("passing"))
  })

  it("aria-label includes 'failing' for a failing chip", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const btn = screen.getByRole("button", { name: /CC6\.2/i })
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("failing"))
  })

  it("aria-label includes 'partial' for a partial chip", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const btn = screen.getByRole("button", { name: /CC7\.1/i })
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("partial"))
  })

  it("aria-label includes 'unknown' for an unknown chip", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const btn = screen.getByRole("button", { name: /A1\.1/i })
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("unknown"))
  })

  it("aria-label includes confidence percentage", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    // CC6.1 confidence = 0.92 → 92%
    const btn = screen.getByRole("button", { name: /CC6\.1/i })
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("92%"))
  })

  // ── Chip → detail panel interaction ─────────────────────────────────────────

  it("detail panel is not visible before any chip is clicked", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    expect(screen.queryByTestId("control-detail-panel")).not.toBeInTheDocument()
  })

  it("clicking a chip opens the detail panel for that control", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const cc61Btn = screen.getByRole("button", { name: /CC6\.1/i })

    fireEvent.click(cc61Btn)

    const panel = screen.getByTestId("control-detail-panel")
    expect(panel).toBeInTheDocument()
    // Panel header should contain the tsc_id.
    expect(panel).toHaveTextContent("CC6.1")
  })

  it("clicking the same chip again collapses the detail panel", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const cc61Btn = screen.getByRole("button", { name: /CC6\.1/i })

    fireEvent.click(cc61Btn)
    expect(screen.getByTestId("control-detail-panel")).toBeInTheDocument()

    fireEvent.click(cc61Btn)
    expect(screen.queryByTestId("control-detail-panel")).not.toBeInTheDocument()
  })

  it("clicking a different chip switches the open panel", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const cc61Btn = screen.getByRole("button", { name: /CC6\.1/i })
    const cc62Btn = screen.getByRole("button", { name: /CC6\.2/i })

    fireEvent.click(cc61Btn)
    expect(screen.getByTestId("control-detail-panel")).toHaveTextContent("CC6.1")

    fireEvent.click(cc62Btn)
    const panel = screen.getByTestId("control-detail-panel")
    expect(panel).toHaveTextContent("CC6.2")
    // Old panel is gone — only one panel at a time.
    expect(screen.getAllByTestId("control-detail-panel")).toHaveLength(1)
  })

  it("chip aria-expanded=true when open, false when closed", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    const btn = screen.getByRole("button", { name: /CC6\.1/i })

    expect(btn).toHaveAttribute("aria-expanded", "false")
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-expanded", "false")
  })

  // ── Detail panel content ─────────────────────────────────────────────────────

  it("detail panel shows NIST 800-53 refs", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    fireEvent.click(screen.getByRole("button", { name: /CC6\.1/i }))

    const panel = screen.getByTestId("control-detail-panel")
    expect(panel).toHaveTextContent("AC-2")
    expect(panel).toHaveTextContent("AC-3")
    expect(panel).toHaveTextContent("SC-7")
  })

  it("detail panel shows rationale text when present", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    fireEvent.click(screen.getByRole("button", { name: /CC6\.1/i }))

    expect(
      screen.getByText("All access control policies are documented and enforced.")
    ).toBeInTheDocument()
  })

  it("detail panel shows 'No rationale' italic text when rationale is null", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    // CC7.1 has rationale: null
    fireEvent.click(screen.getByRole("button", { name: /CC7\.1/i }))

    expect(screen.getByText(/no rationale/i)).toBeInTheDocument()
  })

  it("detail panel shows evidence IDs when present", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    fireEvent.click(screen.getByRole("button", { name: /CC6\.1/i }))

    const panel = screen.getByTestId("control-detail-panel")
    expect(panel).toHaveTextContent("ev-001")
    expect(panel).toHaveTextContent("ev-002")
  })

  it("close button collapses the detail panel", () => {
    render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    fireEvent.click(screen.getByRole("button", { name: /CC6\.1/i }))
    expect(screen.getByTestId("control-detail-panel")).toBeInTheDocument()

    const closeBtn = screen.getByRole("button", { name: /close details for CC6\.1/i })
    fireEvent.click(closeBtn)
    expect(screen.queryByTestId("control-detail-panel")).not.toBeInTheDocument()
  })

  // ── Snapshot ─────────────────────────────────────────────────────────────────

  it("matches snapshot with representative fixture (all 4 statuses, 3 categories)", () => {
    const { container } = render(<ControlPostureGrid assessments={ASSESSMENTS} />)
    expect(container).toMatchSnapshot()
  })
})
