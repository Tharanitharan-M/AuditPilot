"use client"

import { useEffect, useState, useRef, useCallback, useMemo } from "react"
import { ScanLine } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/page-header"
import { ReadinessDonut } from "@/components/readiness-donut"
import { StatusCards } from "@/components/status-cards"
import { OnboardingChecklist, type OnboardingStep } from "@/components/onboarding-checklist"
import { AttentionSection } from "@/components/attention-section"
import { EmptyState } from "@/components/empty-state"
import type { Connector } from "@/lib/me"

interface ControlSummary {
  tsc_id: string
  status: string
  label?: string
}

interface ActionSummary {
  id: string
  status: string
  tsc_id: string | null
}

interface OverviewClientProps {
  connector: Connector | null
  hasRepos: boolean
  scopedRepoCount: number
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

// Same key the ``useScanStream`` hook writes to — the Overview page reads
// from there instead of a server endpoint, because control assessments are
// produced by the SSE-streamed scan turn (``/api/chat``), not by a CRUD
// endpoint. Hydrating from localStorage on mount means the Overview shows
// the most recent scan's posture even after navigation.
const STORAGE_KEY_CONTROL_MAP = "auditpilot:controlMap"

interface StoredAssessment {
  tsc_id: string
  status: string
  evidence_ids?: string[]
}

function loadControlsFromStorage(): ControlSummary[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CONTROL_MAP)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (a): a is StoredAssessment =>
          typeof a === "object" &&
          a !== null &&
          typeof (a as StoredAssessment).tsc_id === "string" &&
          typeof (a as StoredAssessment).status === "string"
      )
      .map((a) => ({ tsc_id: a.tsc_id, status: a.status }))
  } catch {
    return []
  }
}

export function OverviewClient({ connector, hasRepos, scopedRepoCount }: OverviewClientProps) {
  const [controls, setControls] = useState<ControlSummary[]>(() =>
    loadControlsFromStorage()
  )
  const [actions, setActions] = useState<ActionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  const load = useCallback(async (signal: AbortSignal) => {
    setLoading(true)
    try {
      const actionsRes = await fetch("/api/actions", {
        cache: "no-store",
        signal,
      })
      if (!mountedRef.current || signal.aborted) return
      if (actionsRes.ok) {
        const data = await actionsRes.json()
        setActions(data.actions ?? [])
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return
      // surface to console; non-blocking for the rest of the page
      console.error("overview.actions_fetch_failed", err)
    } finally {
      if (mountedRef.current && !signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    const controller = new AbortController()
    load(controller.signal)
    // Keep controls in sync if a scan completes in another tab.
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY_CONTROL_MAP) {
        setControls(loadControlsFromStorage())
      }
    }
    window.addEventListener("storage", onStorage)
    return () => {
      mountedRef.current = false
      controller.abort()
      window.removeEventListener("storage", onStorage)
    }
  }, [load])

  const passing = controls.filter((c) => c.status === "passing").length
  const failing = controls.filter((c) => c.status === "failing").length
  const partial = controls.filter((c) => c.status === "partial").length
  const notAssessed = controls.filter((c) => c.status === "unknown").length

  const failingControls = controls
    .filter((c) => c.status === "failing")
    .map((c) => ({
      tsc_id: c.tsc_id,
      label: c.label ?? CONTROL_LABELS[c.tsc_id] ?? c.tsc_id,
    }))

  const unresolvedActionCount = actions.filter(
    (a) => a.status === "pending_review" || a.status === "approved"
  ).length

  const hasConnector = connector?.status === "connected"
  const hasScopedRepos = scopedRepoCount > 0
  const hasScanRun = controls.length > 0
  const hasPolicies = false // will be wired in 6.5.5b
  const hasReviewedControls = controls.some(
    (c) => c.status === "passing" || c.status === "failing" || c.status === "partial"
  )
  const hasAddressedActions = actions.some((a) => a.status === "completed")

  const onboardingSteps: OnboardingStep[] = useMemo(
    () => [
      { id: "connect", label: "Connect GitHub", done: hasConnector, href: "/dashboard/integrations" },
      { id: "scope", label: "Select repositories", done: hasScopedRepos, href: connector ? `/dashboard/connectors/${connector.id}/scope` : "/dashboard/integrations" },
      { id: "scan", label: "Run first readiness scan", done: hasScanRun, href: "/dashboard/chat" },
      { id: "review", label: "Review control posture", done: hasReviewedControls, href: "/dashboard/controls" },
      { id: "policies", label: "Draft policies for failing controls", done: hasPolicies, href: "/dashboard/policies" },
      { id: "actions", label: "Address pending actions", done: hasAddressedActions, href: "/dashboard/actions" },
    ],
    [
      hasConnector,
      hasScopedRepos,
      hasScanRun,
      hasReviewedControls,
      hasPolicies,
      hasAddressedActions,
      connector,
    ]
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Your SOC 2 readiness at a glance."
      />

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-xl" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
        </div>
      ) : controls.length === 0 ? (
        <div className="space-y-6">
          <OnboardingChecklist steps={onboardingSteps} />

          <EmptyState
            icon={ScanLine}
            title="No scan data yet"
            description="Connect your GitHub, scope your repos, and run a readiness scan to see your posture here."
            actionLabel="Run readiness scan"
            actionHref="/dashboard/chat"
          />
        </div>
      ) : (
        <div className="space-y-6">
          <ReadinessDonut
            passing={passing}
            failing={failing}
            partial={partial}
            notAssessed={notAssessed}
          />

          <StatusCards
            passing={passing}
            failing={failing}
            partial={partial}
            notAssessed={notAssessed}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <OnboardingChecklist steps={onboardingSteps} />
            <AttentionSection
              failingControls={failingControls}
              unresolvedActionCount={unresolvedActionCount}
            />
          </div>
        </div>
      )}
    </div>
  )
}
