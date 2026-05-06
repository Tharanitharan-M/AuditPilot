"use client"

/**
 * ControlPostureGrid — SOC 2 TSC control posture grid.
 *
 * Renders TSC clauses grouped by category (CC, A, C, PI, P), with per-clause
 * status chips that expand into a detail panel on click. No modal library;
 * uses a controlled <details>-style inline expansion.
 *
 * Sprint 5 chunk 5.8: the detail panel now accepts an optional `evidenceMap`
 * prop (evidence_id → EvidenceRow) so collected evidence rows render inline
 * as `EvidenceCards` beneath the NIST 800-53 reference list.
 *
 * Accessibility: WCAG 2.2 AA colour + status encoded in text (WCAG 1.4.1).
 * Each chip carries an aria-label that screen readers announce in full.
 *
 * Refs: PLAN.md Sprint 4 chunk 4.6, Sprint 5 chunk 5.8, ADR-0013, US-006.
 */

import { useMemo, useState } from "react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EvidenceCards, type EvidenceRow } from "./evidence-cards"

// ── Types ─────────────────────────────────────────────────────────────────────

export type AssessmentStatus = "passing" | "failing" | "partial" | "unknown"

export interface ControlAssessment {
  tsc_id: string
  status: AssessmentStatus
  confidence: number
  nist_800_53_refs: string[]
  evidence_ids: string[]
  rationale: string | null
}

// ── TSC category / parent map (ordered) ──────────────────────────────────────

interface TscCategory {
  key: string
  label: string
  parents: string[]
}

const TSC_CATEGORIES: TscCategory[] = [
  {
    key: "CC",
    label: "CC — Common Criteria",
    parents: ["CC1", "CC2", "CC3", "CC4", "CC5", "CC6", "CC7", "CC8", "CC9"],
  },
  { key: "A", label: "A — Availability", parents: ["A1"] },
  { key: "C", label: "C — Confidentiality", parents: ["C1"] },
  { key: "PI", label: "PI — Processing Integrity", parents: ["PI1"] },
  { key: "P", label: "P — Privacy", parents: ["P1"] },
]

/** Derive the parent id from a tsc_id like "CC6.1" → "CC6". */
function parentOf(tscId: string): string {
  const dot = tscId.indexOf(".")
  return dot === -1 ? tscId : tscId.slice(0, dot)
}

/** True when a parent string belongs to a category key (prefix match). */
function parentBelongsTo(parent: string, categoryKey: string): boolean {
  return parent.startsWith(categoryKey)
}

// ── Colour / label helpers ────────────────────────────────────────────────────

const STATUS_CLASSES: Record<AssessmentStatus, string> = {
  passing: "bg-green-700 text-white",
  failing: "bg-red-700 text-white",
  partial: "bg-amber-600 text-black",
  unknown: "bg-zinc-300 text-zinc-900",
}

const STATUS_LABELS: Record<AssessmentStatus, string> = {
  passing: "passing",
  failing: "failing",
  partial: "partial",
  unknown: "unknown",
}

function statusFocusRing(status: AssessmentStatus): string {
  switch (status) {
    case "passing":
      return "focus-visible:ring-green-500"
    case "failing":
      return "focus-visible:ring-red-500"
    case "partial":
      return "focus-visible:ring-amber-500"
    default:
      return "focus-visible:ring-zinc-400"
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface ChipProps {
  assessment: ControlAssessment
  isOpen: boolean
  onClick: () => void
}

function ControlChip({ assessment, isOpen, onClick }: ChipProps) {
  const { tsc_id, status, confidence } = assessment
  const pct = Math.round(confidence * 100)
  const ariaLabel = `${tsc_id} — ${STATUS_LABELS[status]} — confidence ${pct}%`

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-expanded={isOpen}
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium",
        "transition-opacity hover:opacity-90 active:opacity-80",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1",
        STATUS_CLASSES[status],
        statusFocusRing(status),
      ].join(" ")}
    >
      <span aria-hidden="true">{tsc_id}</span>
      {/* Text-encoded status satisfies WCAG 1.4.1 (not colour alone) */}
      <span className="sr-only">{STATUS_LABELS[status]}</span>
      <span aria-hidden="true" className="opacity-75 text-[10px]">
        {STATUS_LABELS[status]}
      </span>
    </button>
  )
}

interface DetailPanelProps {
  assessment: ControlAssessment
  onClose: () => void
  /** Sprint 5.8: map of evidence_id → EvidenceRow for inline rendering. */
  evidenceMap?: Map<string, EvidenceRow>
}

function DetailPanel({ assessment, onClose, evidenceMap }: DetailPanelProps) {
  const { tsc_id, status, confidence, nist_800_53_refs, evidence_ids, rationale } =
    assessment
  const pct = Math.round(confidence * 100)

  // Resolve evidence rows that belong to this assessment.
  const linkedRows: EvidenceRow[] = evidenceMap
    ? evidence_ids.flatMap((eid) => {
        const row = evidenceMap.get(eid)
        return row ? [row] : []
      })
    : []

  return (
    <div
      role="region"
      aria-label={`Details for ${tsc_id}`}
      data-testid="control-detail-panel"
      className="mt-2 rounded-lg border border-border bg-muted/50 p-4 text-sm"
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{tsc_id}</span>
          <span
            className={[
              "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
              STATUS_CLASSES[status],
            ].join(" ")}
          >
            <span className="sr-only">Status: </span>
            {STATUS_LABELS[status]}
          </span>
          <span className="text-xs text-muted-foreground">
            Confidence: {pct}%
          </span>
        </div>
        <Button
          variant="ghost"
          size="xs"
          onClick={onClose}
          aria-label={`Close details for ${tsc_id}`}
        >
          ✕
        </Button>
      </div>

      {/* NIST 800-53 refs */}
      {nist_800_53_refs.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            NIST 800-53 References
          </p>
          <div className="flex flex-wrap gap-1">
            {nist_800_53_refs.map((ref) => (
              <code
                key={ref}
                className="rounded bg-zinc-200 px-1.5 py-0.5 text-[11px] font-mono text-zinc-800 dark:bg-zinc-700 dark:text-zinc-200"
              >
                {ref}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Rationale */}
      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Rationale
        </p>
        {rationale ? (
          <p className="text-sm">{rationale}</p>
        ) : (
          <p className="text-sm italic text-muted-foreground">No rationale</p>
        )}
      </div>

      {/* Evidence rows (Sprint 5.8) — inline cards when evidenceMap provided */}
      {linkedRows.length > 0 ? (
        <div className="mt-3">
          <EvidenceCards
            rows={linkedRows}
            heading={`Evidence (${linkedRows.length} row${linkedRows.length !== 1 ? "s" : ""})`}
            initialVisible={3}
          />
        </div>
      ) : evidence_ids.length > 0 ? (
        /* Fallback: plain ID list when no map was supplied */
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Evidence IDs
          </p>
          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
            {evidence_ids.map((eid) => (
              <li key={eid}>{eid}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <Card data-testid="control-posture-empty">
      <CardContent className="py-10 text-center">
        <p className="text-sm text-muted-foreground">
          No scan run yet — click{" "}
          <span className="font-medium">&ldquo;Run readiness scan&rdquo;</span>{" "}
          to populate this grid.
        </p>
      </CardContent>
    </Card>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface ControlPostureGridProps {
  assessments?: ControlAssessment[]
  /** Sprint 5.8: map of evidence_id → EvidenceRow. When provided, detail panels
   *  render inline EvidenceCards instead of bare ID lists. */
  evidenceMap?: Map<string, EvidenceRow>
}

export function ControlPostureGrid({
  assessments = [],
  evidenceMap,
}: ControlPostureGridProps) {
  /** tsc_id of the currently open detail panel, or null. */
  const [openId, setOpenId] = useState<string | null>(null)

  // typescript-reviewer M-4 / Sprint 4 chunk 4.15 — memoise the lookup
  // structures keyed on assessments. Re-renders triggered by ``openId``
  // state changes (every chip click) used to rebuild these Maps; with
  // 80+ TSC clauses live, that is wasted work and a measurable jank
  // hazard. ``useMemo`` recomputes only when ``assessments`` changes.
  const { byId, byParent, presentParents } = useMemo(() => {
    const byIdMap = new Map<string, ControlAssessment>(
      assessments.map((a) => [a.tsc_id, a])
    )
    const byParentMap = new Map<string, string[]>()
    for (const a of assessments) {
      const parent = parentOf(a.tsc_id)
      const list = byParentMap.get(parent) ?? []
      list.push(a.tsc_id)
      byParentMap.set(parent, list)
    }
    return {
      byId: byIdMap,
      byParent: byParentMap,
      presentParents: new Set(byParentMap.keys()),
    }
  }, [assessments])

  if (assessments.length === 0) {
    return <EmptyState />
  }

  function toggle(tscId: string) {
    setOpenId((prev) => (prev === tscId ? null : tscId))
  }

  return (
    <div
      data-testid="control-posture-grid"
      className="space-y-6"
      aria-label="SOC 2 TSC control posture grid"
    >
      {TSC_CATEGORIES.map((category) => {
        // Only render categories that have at least one assessment.
        const relevantParents = category.parents.filter((p) => {
          // Check if any sub-clause or the parent itself is in assessments.
          if (presentParents.has(p)) return true
          // Also check if any assessment's parent matches this parent.
          for (const parent of presentParents) {
            if (parentBelongsTo(parent, category.key) && parent === p)
              return true
          }
          return false
        })

        if (relevantParents.length === 0) return null

        return (
          <section
            key={category.key}
            aria-label={category.label}
          >
            <Card>
              <CardHeader>
                <CardTitle>{category.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {relevantParents.map((parent) => {
                  const subClauses = byParent.get(parent) ?? []
                  if (subClauses.length === 0) return null

                  // Determine if any chip in this row has an open panel.
                  const openInRow = subClauses.find((id) => id === openId)
                  const openAssessment = openInRow ? byId.get(openInRow) : undefined

                  return (
                    <div key={parent} data-testid={`control-row-${parent}`}>
                      {/* Row header + chips */}
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="min-w-[3rem] text-xs font-semibold text-muted-foreground">
                          {parent}
                        </span>
                        {subClauses.sort().map((tscId) => {
                          const assessment = byId.get(tscId)
                          if (!assessment) return null
                          return (
                            <ControlChip
                              key={tscId}
                              assessment={assessment}
                              isOpen={openId === tscId}
                              onClick={() => toggle(tscId)}
                            />
                          )
                        })}
                      </div>

                      {/* Inline detail panel — expands below the row */}
                      {openAssessment && (
                        <DetailPanel
                          assessment={openAssessment}
                          onClose={() => setOpenId(null)}
                          evidenceMap={evidenceMap}
                        />
                      )}
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          </section>
        )
      })}
    </div>
  )
}
