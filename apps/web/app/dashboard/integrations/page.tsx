import { auth } from "@clerk/nextjs/server"
import { getMeData } from "@/lib/me"
import { IntegrationsClient } from "@/components/integrations-client"

export default async function IntegrationsPage() {
  const me = await getMeData()
  const { getToken } = await auth()
  const githubConnector =
    me?.connectors?.find((c) => c.provider === "github") ?? null
  const repos = me?.repos ?? []

  let scopedRepoIds: string[] = []
  if (githubConnector?.status === "connected" && githubConnector.id) {
    const apiBase = process.env.API_URL ?? "http://localhost:8000"
    const token = await getToken()
    if (token) {
      try {
        const res = await fetch(
          `${apiBase}/api/connectors/${githubConnector.id}/scoped-repos`,
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: AbortSignal.timeout(5000),
            next: { revalidate: 30 },
          }
        )
        if (res.ok) {
          const data = await res.json()
          if (Array.isArray(data?.repos)) {
            scopedRepoIds = data.repos.map(
              (r: { provider_repo_id: string }) => r.provider_repo_id
            )
          }
        }
      } catch {
        // degrade gracefully
      }
    }
  }

  return (
    <IntegrationsClient
      connector={githubConnector}
      repos={repos}
      scopedRepoIds={scopedRepoIds}
    />
  )
}
