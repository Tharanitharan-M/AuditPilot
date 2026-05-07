import { auth } from "@clerk/nextjs/server"
import { getMeData } from "@/lib/me"
import { ChatClient } from "@/components/chat-client"

export default async function ChatPage() {
  const me = await getMeData()
  const { getToken } = await auth()
  const githubConnector =
    me?.connectors?.find((c) => c.provider === "github") ?? null

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
    <ChatClient
      connectorId={githubConnector?.id ?? null}
      scopedRepoIds={scopedRepoIds}
    />
  )
}
