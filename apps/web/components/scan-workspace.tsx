"use client"

/**
 * ScanWorkspace — owns one ``useScanStream`` hook and renders the three
 * dashboard surfaces that need its live state:
 *
 *   1. Control Posture grid  ← state.control_map (data-control-map chunks)
 *   2. Pending Actions       ← /api/actions (still self-fetching)
 *   3. Readiness Scan chat   ← messages + status + handlers
 *
 * Why a single client component?
 *
 *   ScanChat used to own the hook. ControlPostureGrid sat next to it as
 *   ``<ControlPostureGrid assessments={[]} />`` — empty by construction.
 *   Sprint 5 chunks 5.8 + 5.23 require the grid + evidence cards to
 *   render off the same scan turn that produces the chat reply, so we
 *   lift the hook here and feed the children. The dashboard server
 *   component fetches scoped repo ids and hands them to this client
 *   wrapper; the wrapper does the rest.
 *
 * Refs: PLAN.md Sprint 5 chunks 5.8 + 5.23; ADR-0003 (AI SDK 6 wire format).
 */

import { ControlPostureGrid } from "@/components/control-posture-grid"
import { PendingActions } from "@/components/pending-actions"
import { ScanChat } from "@/components/scan-chat"
import type { EvidenceRow } from "@/components/evidence-cards"
import { useScanStream } from "@/lib/use-scan-stream"
import { useMemo } from "react"

interface ScanWorkspaceProps {
  connectorId: string
  repoIncludeList: string[]
}

export function ScanWorkspace({
  connectorId,
  repoIncludeList,
}: ScanWorkspaceProps) {
  // One stream, lifted up. Both ScanChat and ControlPostureGrid below
  // render off this single source of truth.
  const stream = useScanStream({
    api: "/api/chat",
    body: {
      intent: "run_readiness_scan",
      repo_include_list: repoIncludeList,
      connector_id: connectorId,
    },
  })

  // Build the evidence_id → EvidenceRow lookup the grid's detail panel
  // needs. typescript-reviewer M-4 — memoise so re-renders driven by
  // `openId` state inside the grid do not rebuild this Map.
  const evidenceMap = useMemo(() => {
    const m = new Map<string, EvidenceRow>()
    for (const row of stream.evidenceRows) {
      m.set(row.id, row as EvidenceRow)
    }
    return m
  }, [stream.evidenceRows])

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
      <div className="space-y-6">
        <section aria-label="SOC 2 TSC control posture">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Control Posture
          </h2>
          <ControlPostureGrid
            assessments={stream.controlMap}
            evidenceMap={evidenceMap}
          />
        </section>

        <section aria-label="Pending actions">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Pending Actions
          </h2>
          <PendingActions />
        </section>
      </div>

      <div className="xl:sticky xl:top-6 xl:self-start">
        <ScanChat
          connectorId={connectorId}
          repoIncludeList={repoIncludeList}
          stream={stream}
        />
      </div>
    </div>
  )
}
