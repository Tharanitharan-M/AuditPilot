"use client"

import { MessageSquare } from "lucide-react"
import { ScanWorkspace } from "@/components/scan-workspace"
import { PageHeader } from "@/components/page-header"
import { EmptyState } from "@/components/empty-state"
import { IslandErrorBoundary } from "@/components/error-boundary"

interface ChatClientProps {
  connectorId: string | null
  scopedRepoIds: string[]
}

export function ChatClient({ connectorId, scopedRepoIds }: ChatClientProps) {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Chat"
        description="Run a readiness scan or ask questions about your SOC 2 posture."
      />

      {connectorId ? (
        <IslandErrorBoundary name="ScanWorkspace">
          <ScanWorkspace
            connectorId={connectorId}
            repoIncludeList={scopedRepoIds}
          />
        </IslandErrorBoundary>
      ) : (
        <EmptyState
          icon={MessageSquare}
          title="No connector available"
          description="Connect your GitHub account first, then come back to run a readiness scan."
          actionLabel="Connect GitHub"
          actionHref="/dashboard/integrations"
        />
      )}
    </div>
  )
}
