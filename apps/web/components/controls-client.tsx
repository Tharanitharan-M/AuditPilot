"use client"

import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/page-header"
import { EmptyState } from "@/components/empty-state"
import { ControlDetailPanel } from "@/components/control-detail-panel"
import type { ControlAssessment, AssessmentStatus } from "@/components/control-posture-grid"

// Same key ``useScanStream`` writes to. The Controls page hydrates from
// localStorage instead of a server endpoint because control assessments
// are produced by the SSE-streamed scan turn (``/api/chat``), not by a
// CRUD endpoint. Reads on mount + listens to ``storage`` events so the
// scan running in the Chat page updates this view live.
const STORAGE_KEY_CONTROL_MAP = "auditpilot:controlMap"
const STATUS_VALUES: ReadonlySet<AssessmentStatus> = new Set([
  "passing",
  "failing",
  "partial",
  "unknown",
])

function loadAssessmentsFromStorage(): ControlAssessment[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CONTROL_MAP)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.flatMap((row): ControlAssessment[] => {
      if (typeof row !== "object" || row === null) return []
      const r = row as Record<string, unknown>
      if (typeof r.tsc_id !== "string") return []
      const rawStatus = typeof r.status === "string" ? r.status : "unknown"
      const status: AssessmentStatus = STATUS_VALUES.has(
        rawStatus as AssessmentStatus
      )
        ? (rawStatus as AssessmentStatus)
        : "unknown"
      return [
        {
          tsc_id: r.tsc_id,
          status,
          confidence: typeof r.confidence === "number" ? r.confidence : 0,
          nist_800_53_refs: Array.isArray(r.nist_800_53_refs)
            ? (r.nist_800_53_refs.filter((x) => typeof x === "string") as string[])
            : [],
          evidence_ids: Array.isArray(r.evidence_ids)
            ? (r.evidence_ids.filter((x) => typeof x === "string") as string[])
            : [],
          rationale: typeof r.rationale === "string" ? r.rationale : null,
        },
      ]
    })
  } catch {
    return []
  }
}

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
  "CC6.7": "Access Restriction to Assets",
  "CC6.8": "Malicious Software Prevention",
  "CC7.1": "Detection of Changes",
  "CC7.2": "Monitoring for Anomalies",
  "CC7.3": "Incident Response",
  "CC7.4": "Incident Recovery",
  "CC8.1": "Change Management",
  "CC9.1": "Risk Mitigation — Vendors",
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

const STATUS_VARIANT: Record<string, "passing" | "failing" | "partial" | "not-assessed"> = {
  passing: "passing",
  failing: "failing",
  partial: "partial",
  unknown: "not-assessed",
}

const STATUS_TEXT: Record<string, string> = {
  passing: "Passing",
  failing: "Failing",
  partial: "Partial",
  unknown: "Not assessed",
}

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

function parentOf(tscId: string): string {
  const dot = tscId.indexOf(".")
  return dot === -1 ? tscId : tscId.slice(0, dot)
}

interface ControlsClientProps {
  assessments?: ControlAssessment[]
}

export function ControlsClient({ assessments: assessmentsProp }: ControlsClientProps = {}) {
  const searchParams = useSearchParams()
  const statusFilter = searchParams?.get("status") ?? null
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState<ControlAssessment[]>(() =>
    assessmentsProp && assessmentsProp.length > 0
      ? assessmentsProp
      : loadAssessmentsFromStorage()
  )

  // Re-hydrate when the scan running on the Chat page updates the
  // ``auditpilot:controlMap`` localStorage entry. ``storage`` events fire
  // on OTHER tabs/windows; ``focus`` covers same-tab updates after the
  // user navigates back from /dashboard/chat.
  useEffect(() => {
    if (assessmentsProp && assessmentsProp.length > 0) return
    const refresh = () => setHydrated(loadAssessmentsFromStorage())
    window.addEventListener("storage", refresh)
    window.addEventListener("focus", refresh)
    return () => {
      window.removeEventListener("storage", refresh)
      window.removeEventListener("focus", refresh)
    }
  }, [assessmentsProp])

  const assessments = useMemo(
    () =>
      assessmentsProp && assessmentsProp.length > 0 ? assessmentsProp : hydrated,
    [assessmentsProp, hydrated]
  )

  const filtered = useMemo(() => {
    if (!statusFilter) return assessments
    return assessments.filter((a) => a.status === statusFilter)
  }, [assessments, statusFilter])

  const { byParent, presentParents } = useMemo(() => {
    const byParentMap = new Map<string, ControlAssessment[]>()
    for (const a of filtered) {
      const parent = parentOf(a.tsc_id)
      const list = byParentMap.get(parent) ?? []
      list.push(a)
      byParentMap.set(parent, list)
    }
    return {
      byParent: byParentMap,
      presentParents: new Set(byParentMap.keys()),
    }
  }, [filtered])

  const selectedAssessment = useMemo(
    () => assessments.find((a) => a.tsc_id === selectedId) ?? null,
    [assessments, selectedId]
  )

  if (assessments.length === 0) {
    return (
      <div className="space-y-8">
        <PageHeader
          title="Controls"
          description="Review your SOC 2 readiness posture. Click any control to see evidence, linked policies, and suggested actions."
        />
        <EmptyState
          icon={ShieldCheck}
          title="No controls assessed yet"
          description="Run a readiness scan to populate your control posture."
          actionLabel="Run scan"
          actionHref="/dashboard/chat"
        />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Controls"
        description="Review your SOC 2 readiness posture. Click any control to see evidence, linked policies, and suggested actions."
      />

      <div className="space-y-6" data-testid="control-posture-grid">
        {TSC_CATEGORIES.map((category) => {
          const relevantParents = category.parents.filter((p) => presentParents.has(p))
          if (relevantParents.length === 0) return null

          return (
            <Card key={category.key}>
              <CardHeader>
                <CardTitle className="text-base">{category.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {relevantParents.map((parent) => {
                  const controls = byParent.get(parent) ?? []
                  return (
                    <div key={parent} className="space-y-2">
                      <p className="text-xs font-semibold text-muted-foreground">{parent}</p>
                      <div className="flex flex-wrap gap-2">
                        {controls.sort((a, b) => a.tsc_id.localeCompare(b.tsc_id)).map((a) => (
                          <button
                            key={a.tsc_id}
                            onClick={() => setSelectedId(a.tsc_id)}
                            className="flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-all duration-300 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label={`${a.tsc_id} ${CONTROL_LABELS[a.tsc_id] ?? ""} — ${STATUS_TEXT[a.status]}`}
                          >
                            <div className="flex flex-col">
                              <span className="font-mono text-xs font-medium">{a.tsc_id}</span>
                              <span className="text-xs text-muted-foreground">
                                {CONTROL_LABELS[a.tsc_id] ?? a.tsc_id}
                              </span>
                            </div>
                            <Badge variant={STATUS_VARIANT[a.status] ?? "not-assessed"} className="ml-auto shrink-0">
                              {STATUS_TEXT[a.status]}
                            </Badge>
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {selectedAssessment && (
        <ControlDetailPanel
          assessment={selectedAssessment}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  )
}
