import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { EvidenceCards, type EvidenceRow } from "../components/evidence-cards"

const NOW = "2026-05-01T12:00:00.000Z"

function makeRow(overrides: Partial<EvidenceRow> = {}): EvidenceRow {
  return {
    id: "ev-001",
    source_type: "github",
    source_uri: "github://acme/repo",
    raw: { branch_protection_enabled: true, required_reviews: 2 },
    content_hash: "a".repeat(64),
    collected_at: NOW,
    scan_run_id: "sr-001",
    ...overrides,
  }
}

describe("EvidenceCards", () => {
  it("renders empty state when rows is empty", () => {
    render(<EvidenceCards rows={[]} />)
    expect(screen.getByText(/no evidence rows/i)).toBeInTheDocument()
  })

  it("renders a card for each row up to initialVisible", () => {
    const rows = [makeRow({ id: "ev-1" }), makeRow({ id: "ev-2" })]
    render(<EvidenceCards rows={rows} initialVisible={5} />)
    expect(screen.getByTestId("evidence-card-ev-1")).toBeInTheDocument()
    expect(screen.getByTestId("evidence-card-ev-2")).toBeInTheDocument()
  })

  it("shows 'show more' button when rows exceed initialVisible", () => {
    const rows = Array.from({ length: 6 }, (_, i) => makeRow({ id: `ev-${i}` }))
    render(<EvidenceCards rows={rows} initialVisible={3} />)
    expect(screen.getByText(/show 3 more/i)).toBeInTheDocument()
  })

  it("expands to show all rows after clicking show more", () => {
    const rows = Array.from({ length: 4 }, (_, i) => makeRow({ id: `ev-${i}` }))
    render(<EvidenceCards rows={rows} initialVisible={2} />)
    fireEvent.click(screen.getByText(/show 2 more/i))
    expect(screen.getByTestId("evidence-card-ev-3")).toBeInTheDocument()
  })

  it("renders heading when provided", () => {
    render(<EvidenceCards rows={[makeRow()]} heading="Evidence (1 row)" />)
    expect(screen.getByText("Evidence (1 row)")).toBeInTheDocument()
  })

  it("shows source_type badge", () => {
    render(<EvidenceCards rows={[makeRow({ source_type: "github" })]} />)
    expect(screen.getByText("github")).toBeInTheDocument()
  })

  it("shows source_uri when present", () => {
    render(<EvidenceCards rows={[makeRow()]} />)
    expect(screen.getByText("github://acme/repo")).toBeInTheDocument()
  })

  it("expands raw payload on expand button click", () => {
    render(<EvidenceCards rows={[makeRow()]} />)
    const expandBtn = screen.getByLabelText(/expand evidence detail/i)
    fireEvent.click(expandBtn)
    // Raw JSON should now appear in a pre block
    expect(screen.getByText(/"branch_protection_enabled"/)).toBeInTheDocument()
  })

  it("shows similarity score when present", () => {
    render(<EvidenceCards rows={[makeRow({ similarity: 0.87 })]} />)
    expect(screen.getByText(/sim 87%/i)).toBeInTheDocument()
  })
})
