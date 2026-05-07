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

// ── Control plain-English labels ──────────────────────────────────────────────

const CONTROL_LABELS: Record<string, string> = {
  "CC1.1": "Control Environment",
  "CC1.2": "Board Oversight",
  "CC1.3": "Management Structure",
  "CC1.4": "Competence Commitment",
  "CC1.5": "Accountability",
  "CC2.1": "Information Flow",
  "CC2.2": "Internal Communication",
  "CC2.3": "External Communication",
  "CC3.1": "Risk Assessment Objectives",
  "CC3.2": "Risk Identification",
  "CC3.3": "Fraud Risk",
  "CC3.4": "Change Impact Analysis",
  "CC4.1": "Monitoring Activities",
  "CC4.2": "Deficiency Evaluation",
  "CC5.1": "Control Activities Selection",
  "CC5.2": "Technology Controls",
  "CC5.3": "Policy-based Controls",
  "CC6.1": "Access Controls",
  "CC6.2": "Access Provisioning",
  "CC6.3": "Access Removal",
  "CC6.4": "Access Review",
  "CC6.5": "Physical Access",
  "CC6.6": "Logical Access Security",
  "CC6.7": "Access Restriction",
  "CC6.8": "Malware Prevention",
  "CC7.1": "Detection of Changes",
  "CC7.2": "Monitoring for Anomalies",
  "CC7.3": "Incident Response",
  "CC7.4": "Incident Recovery",
  "CC8.1": "Change Management",
  "CC9.1": "Vendor Risk Mitigation",
  "CC9.2": "Vendor Risk Assessment",
  "A1.1": "Capacity Management",
  "A1.2": "Recovery Planning",
  "A1.3": "Recovery Testing",
  "C1.1": "Data Classification",
  "C1.2": "Data Disposal",
  "PI1.1": "Processing Accuracy",
  "PI1.2": "Input Validation",
  "P1.1": "Privacy Notice",
}

// ── Colour / label helpers ────────────────────────────────────────────────────

const STATUS_CLASSES: Record<AssessmentStatus, string> = {
  passing: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  failing: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  unknown: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
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
  const label = CONTROL_LABELS[tsc_id] ?? tsc_id
  const ariaLabel = `${tsc_id} — ${label} — ${STATUS_LABELS[status]} — confidence ${pct}%`

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-expanded={isOpen}
      onClick={onClick}
      className={[
        "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm",
        "transition-all duration-300 hover:bg-muted/50 active:opacity-90",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
      ].join(" ")}
    >
      <div className="flex flex-col min-w-0">
        <span className="font-mono text-xs font-medium">{tsc_id}</span>
        <span className="text-xs text-muted-foreground truncate">{label}</span>
      </div>
      <span
        className={[
          "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
          STATUS_CLASSES[status],
        ].join(" ")}
      >
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
                        {[...subClauses].sort().map((tscId) => {
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
