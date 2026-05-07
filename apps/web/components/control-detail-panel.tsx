"use client"

import { useEffect, useCallback } from "react"
import Link from "next/link"
import { X, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Separator } from "@/components/ui/separator"
import type { ControlAssessment } from "@/components/control-posture-grid"

const STATUS_VARIANT: Record<string, "passing" | "failing" | "partial" | "not-assessed"> = {
  passing: "passing",
  failing: "failing",
  partial: "partial",
  unknown: "not-assessed",
}

const CONTROL_DESCRIPTIONS: Record<string, string> = {
  "CC6.1": "Logical and physical access controls restrict access to information assets. This control ensures only authorized individuals can access systems and data.",
  "CC6.2": "Prior to issuing system credentials, registered and authorized users are assigned access based on job responsibilities and business requirements.",
  "CC6.3": "Access credentials are removed when no longer needed, ensuring former employees and transferred personnel cannot access systems.",
  "CC6.6": "System boundaries are secured against unauthorized logical access using firewalls, encryption, and network segmentation.",
  "CC6.8": "Controls detect and prevent malicious software including viruses, malware, and ransomware from impacting systems.",
  "CC7.1": "Configuration changes and anomalies are monitored and detected in a timely manner to identify potential security incidents.",
  "CC7.2": "System monitoring detects anomalies indicative of threats including insider threats, external attacks, and unauthorized access.",
  "CC7.3": "When incidents are detected, a defined response process is executed to contain, mitigate, and resolve the incident.",
  "CC7.4": "Recovery procedures restore system functionality and data integrity after a security incident.",
  "CC8.1": "Changes to infrastructure, data, software, and procedures are authorized, designed, developed, tested, and approved before implementation.",
  "CC9.1": "Vendor and business partner risks are assessed and mitigated to maintain the security and availability of the system.",
  "CC9.2": "Vendor compliance with security requirements is monitored through regular assessments and contractual obligations.",
}

const POLICY_TYPE_MAP: Record<string, string> = {
  CC7: "irp",
  CC6: "access_control",
  CC8: "change_management",
  CC9: "vendor_management",
}

interface ControlDetailPanelProps {
  assessment: ControlAssessment
  onClose: () => void
}

export function ControlDetailPanel({ assessment, onClose }: ControlDetailPanelProps) {
  const { tsc_id, status, confidence, nist_800_53_refs, evidence_ids, rationale } = assessment
  const pct = Math.round(confidence * 100)
  const parentKey = tsc_id.replace(/\.\d+$/, "")
  const policyType = POLICY_TYPE_MAP[parentKey]

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    },
    [onClose]
  )

  useEffect(() => {
    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [handleEscape])

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-label={`Details for ${tsc_id}`}
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[480px] flex-col border-l bg-background shadow-lg md:max-w-[480px]"
        data-testid="control-detail-panel"
      >
        <div className="flex items-center justify-between border-b p-4">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold">{tsc_id}</span>
            <Badge variant={STATUS_VARIANT[status] ?? "not-assessed"}>
              {status === "unknown" ? "Not assessed" : status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Close detail panel"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <ScrollArea className="flex-1 p-4">
          <div className="space-y-6">
            {CONTROL_DESCRIPTIONS[tsc_id] && (
              <section>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  What this means
                </h3>
                <p className="text-sm">{CONTROL_DESCRIPTIONS[tsc_id]}</p>
              </section>
            )}

            <Separator />

            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Assessment
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Confidence</span>
                  <span className="font-medium">{pct}%</span>
                </div>
                {rationale && (
                  <div>
                    <span className="text-muted-foreground">Rationale</span>
                    <p className="mt-1">{rationale}</p>
                  </div>
                )}
              </div>
            </section>

            <Separator />

            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Evidence collected ({evidence_ids.length})
              </h3>
              {evidence_ids.length > 0 ? (
                <ul className="space-y-1">
                  {evidence_ids.map((eid) => (
                    <li key={eid} className="truncate rounded bg-muted px-2 py-1 text-xs font-mono">
                      {eid}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No evidence collected yet.</p>
              )}
            </section>

            <Separator />

            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Linked policies
              </h3>
              {policyType ? (
                <Link
                  href={`/dashboard/policies?template=${policyType}&control=${tsc_id}`}
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                >
                  Draft policy for {tsc_id}
                </Link>
              ) : (
                <p className="text-sm text-muted-foreground">No policy template available for this control.</p>
              )}
            </section>

            <Separator />

            {nist_800_53_refs.length > 0 && (
              <Collapsible>
                <CollapsibleTrigger className="flex w-full items-center justify-between text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground">
                  <span>NIST 800-53 References ({nist_800_53_refs.length})</span>
                  <ExternalLink className="h-3 w-3" />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-2">
                  <div className="flex flex-wrap gap-1">
                    {nist_800_53_refs.map((ref) => (
                      <code
                        key={ref}
                        className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono"
                      >
                        {ref}
                      </code>
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )}
          </div>
        </ScrollArea>
      </div>
    </>
  )
}
