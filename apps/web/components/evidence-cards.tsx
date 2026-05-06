"use client"

/**
 * EvidenceCards — renders a stack of collected evidence rows.
 *
 * Used by ControlPostureGrid's detail panel to show the raw evidence
 * that drove a TSC clause assessment, and by the dashboard's evidence
 * drawer for full-scan browsing.
 *
 * Design: each card is collapsed by default (shows source_type + uri).
 * Expand button reveals the raw payload in a scrollable code block.
 * No modal library — plain controlled state.
 *
 * Accessibility: WCAG 2.2 AA.  Expand/collapse button carries aria-expanded.
 *
 * Refs: PLAN.md Sprint 5 chunk 5.8; ADR-0008 (evidence schema).
 */

import { useState } from "react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface EvidenceRow {
  id: string
  source_type: "github" | "clerk" | "manual" | "mock"
  source_uri: string | null
  raw: Record<string, unknown>
  content_hash: string | null
  collected_at: string      // ISO-8601 string from JSON serialisation
  scan_run_id: string | null
  similarity?: number | null
}

// ── Source-type colours ───────────────────────────────────────────────────────

const SOURCE_BADGE_CLASS: Record<EvidenceRow["source_type"], string> = {
  github:  "bg-zinc-800 text-white",
  clerk:   "bg-indigo-700 text-white",
  manual:  "bg-sky-700 text-white",
  mock:    "bg-zinc-400 text-zinc-900",
}

// ── Single card ───────────────────────────────────────────────────────────────

interface EvidenceCardProps {
  row: EvidenceRow
}

function EvidenceCard({ row }: EvidenceCardProps) {
  const [open, setOpen] = useState(false)
  const { source_type, source_uri, raw, collected_at, similarity } = row

  const collectedLabel = new Date(collected_at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })

  // Flatten 1-level of raw for a quick preview (exclude large/nested values).
  const previewEntries = Object.entries(raw)
    .filter(([, v]) => typeof v !== "object" || v === null)
    .slice(0, 4)

  return (
    <div
      data-testid={`evidence-card-${row.id}`}
      className="rounded-lg border border-border bg-card text-sm shadow-sm"
    >
      {/* Collapsed header */}
      <div className="flex items-start justify-between gap-3 p-3">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span
            className={[
              "inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-xs font-medium",
              SOURCE_BADGE_CLASS[source_type],
            ].join(" ")}
          >
            {source_type}
          </span>
          {source_uri && (
            <span className="truncate text-xs text-muted-foreground max-w-[260px]" title={source_uri}>
              {source_uri}
            </span>
          )}
          {similarity != null && (
            <span className="text-[11px] text-muted-foreground">
              sim {Math.round(similarity * 100)}%
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[11px] text-muted-foreground whitespace-nowrap">
            {collectedLabel}
          </span>
          <Button
            variant="ghost"
            size="xs"
            aria-expanded={open}
            aria-label={open ? "Collapse evidence detail" : "Expand evidence detail"}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "▲" : "▼"}
          </Button>
        </div>
      </div>

      {/* Quick preview — always visible below header */}
      {previewEntries.length > 0 && !open && (
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 px-3 pb-2">
          {previewEntries.map(([k, v]) => (
            <span key={k} className="text-[11px] text-muted-foreground">
              <span className="font-medium">{k}:</span>{" "}
              <span>{String(v)}</span>
            </span>
          ))}
        </div>
      )}

      {/* Expanded — full raw payload */}
      {open && (
        <div className="border-t border-border px-3 pb-3 pt-2">
          <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-[11px] leading-relaxed">
            {JSON.stringify(raw, null, 2)}
          </pre>
          {row.content_hash && (
            <p className="mt-1.5 text-[10px] font-mono text-muted-foreground">
              hash: {row.content_hash.slice(0, 16)}…
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Stack component ───────────────────────────────────────────────────────────

interface EvidenceCardsProps {
  rows: EvidenceRow[]
  /** When provided, renders a section heading above the stack. */
  heading?: string
  /** Max rows to render before collapsing. Default 5. */
  initialVisible?: number
}

export function EvidenceCards({
  rows,
  heading,
  initialVisible = 5,
}: EvidenceCardsProps) {
  const [showAll, setShowAll] = useState(false)

  if (rows.length === 0) {
    return (
      <p className="text-xs italic text-muted-foreground">No evidence rows.</p>
    )
  }

  const visible = showAll ? rows : rows.slice(0, initialVisible)
  const hidden = rows.length - initialVisible

  return (
    <div data-testid="evidence-cards" className="space-y-2">
      {heading && (
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {heading}
        </p>
      )}
      {visible.map((row) => (
        <EvidenceCard key={row.id} row={row} />
      ))}
      {!showAll && hidden > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="w-full text-xs"
          onClick={() => setShowAll(true)}
        >
          Show {hidden} more evidence row{hidden !== 1 ? "s" : ""}
        </Button>
      )}
    </div>
  )
}
