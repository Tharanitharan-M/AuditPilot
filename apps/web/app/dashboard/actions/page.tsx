"use client"

import { CheckSquare } from "lucide-react"
import { PendingActions } from "@/components/pending-actions"
import { PageHeader } from "@/components/page-header"
import { IslandErrorBoundary } from "@/components/error-boundary"

export default function ActionsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Actions"
        description="Review and address suggested fixes. Each action links to the control it resolves."
      />
      <IslandErrorBoundary name="PendingActions">
        <PendingActions />
      </IslandErrorBoundary>
    </div>
  )
}
