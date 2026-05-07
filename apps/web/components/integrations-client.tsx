"use client"

import { Plug } from "lucide-react"
import { ConnectorCard } from "@/components/connector-card"
import { RepoList } from "@/components/repo-list"
import { IslandErrorBoundary } from "@/components/error-boundary"
import { EmptyState } from "@/components/empty-state"
import { PageHeader } from "@/components/page-header"
import type { Connector, Repo } from "@/lib/me"

interface IntegrationsClientProps {
  connector: Connector | null
  repos: Repo[]
  scopedRepoIds: string[]
}

export function IntegrationsClient({
  connector,
  repos,
  scopedRepoIds,
}: IntegrationsClientProps) {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Integrations"
        description="Connect your tools. AuditPilot reads your GitHub repositories to collect evidence. All access is read-only."
      />

      <section aria-label="Connectors">
        <h2 className="mb-4 text-lg font-semibold">Connectors</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <IslandErrorBoundary name="ConnectorCard">
            <ConnectorCard
              connector={connector}
              debug={process.env.NEXT_PUBLIC_CONNECTOR_DEBUG === "true"}
            />
          </IslandErrorBoundary>
        </div>
      </section>

      {repos.length > 0 && (
        <section aria-label="Connected repositories">
          <h2 className="mb-4 text-lg font-semibold">Connected repositories</h2>
          <IslandErrorBoundary name="RepoList">
            <RepoList repos={repos} />
          </IslandErrorBoundary>
        </section>
      )}

      {!connector && (
        <EmptyState
          icon={Plug}
          title="No integrations connected"
          description="Connect your GitHub account to get started with evidence collection."
        />
      )}
    </div>
  )
}
