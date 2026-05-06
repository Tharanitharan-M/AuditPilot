/**
 * Dashboard page — connector grid + repo list + readiness scan chat.
 *
 * Server Component. Uses the shared getMeData() helper which:
 *   - tries FastAPI /api/me first (with Clerk session JWT), and
 *   - falls back to the Clerk Backend SDK if FastAPI is offline / 401.
 *
 * The Clerk fallback prevents the UI from silently showing "Not connected"
 * when only the API tier is mis-configured (e.g. missing CLERK_JWKS_URL).
 *
 * Chunk 4.1/4.2: when a connected GitHub connector is present, we fetch the
 * user's scoped repo ids from the existing /api/connectors/:id/scoped-repos
 * proxy and pass them into <ScanChat> as the client island. ScanChat is only
 * rendered when a connector exists (connected or error) so the fetch is never
 * made for unauthenticated or unconnected users.
 *
 * Refs: PLAN.md chunks 3.6, 3.7, 3.9, 4.1, 4.2; US-002, US-004, US-005, US-010.
 */

import { auth } from "@clerk/nextjs/server"
import { ConnectorCard } from "@/components/connector-card"
import { RepoList } from "@/components/repo-list"
import { ScanChat } from "@/components/scan-chat"
import { ControlPostureGrid } from "@/components/control-posture-grid"
import { PendingActions } from "@/components/pending-actions"
import { getMeData } from "@/lib/me"

/**
 * Fetch scoped repo ids for a connector by calling FastAPI directly.
 *
 * typescript-reviewer H-1 — the original implementation issued a
 * server-to-self HTTP round-trip via NEXT_PUBLIC_APP_URL, which is a
 * client-exposed env var and an SSRF vector if mis-configured. The
 * Server Component has direct access to the FastAPI origin via the
 * server-only ``API_URL`` (or its default) — call it directly. The
 * Next.js proxy at ``/api/connectors/[id]/scoped-repos`` is still
 * available for the picker's client-side reads.
 */
async function getScopedRepoIds(
  connectorId: string,
  token: string
): Promise<string[]> {
  const apiBase = process.env.API_URL ?? "http://localhost:8000"
  try {
    const res = await fetch(
      `${apiBase}/api/connectors/${connectorId}/scoped-repos`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(5000),
        next: { revalidate: 30 },
      }
    )
    if (!res.ok) return []
    const data = await res.json()
    // The scoped-repos GET returns { repos: Array<{ provider_repo_id, ... }> }
    if (Array.isArray(data?.repos)) {
      return data.repos.map((r: { provider_repo_id: string }) => r.provider_repo_id)
    }
    return []
  } catch {
    return []
  }
}

export default async function DashboardPage() {
  const me = await getMeData()
  const { getToken } = await auth()

  const githubConnector =
    me?.connectors?.find((c) => c.provider === "github") ?? null

  const repos = me?.repos ?? []

  // Fetch scoped repo ids server-side so ScanChat has them on first render.
  // Only attempt if a connector exists and is connected.
  let scopedRepoIds: string[] = []
  if (githubConnector?.status === "connected" && githubConnector.id) {
    const token = await getToken()
    if (token) {
      scopedRepoIds = await getScopedRepoIds(githubConnector.id, token)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="mt-1 text-muted-foreground">
          Connect your GitHub organization to start a readiness scan.
        </p>
      </div>

      {/* Connectors section — chunk 3.6, 3.9. Debug flag flips both Connect
          and Disconnect to always-enabled and renders a raw-payload panel. */}
      <section aria-label="Connectors">
        <h2 className="mb-4 text-lg font-semibold">Connectors</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ConnectorCard
            connector={githubConnector}
            debug={process.env.NEXT_PUBLIC_CONNECTOR_DEBUG === "true"}
          />
        </div>
      </section>

      {/* Repos section — chunk 3.7 */}
      {repos.length > 0 && (
        <section aria-label="Connected repositories">
          <h2 className="mb-4 text-lg font-semibold">Connected repositories</h2>
          <RepoList repos={repos} />
        </section>
      )}

      {/* Control posture grid — chunk 4.6.
          Sprint 4: passes empty assessments (shows "No scan run yet" empty
          state). Sprint 5 wires live ControlAssessments from the SSE stream. */}
      <section aria-label="SOC 2 TSC control posture">
        <h2 className="mb-4 text-lg font-semibold">Control Posture</h2>
        <ControlPostureGrid assessments={[]} />
      </section>

      {/* Pending Actions queue — chunk 4.7. US-007.
          PendingActions is a client island; it fetches /api/actions on mount. */}
      <section aria-label="Pending actions">
        <h2 className="mb-4 text-lg font-semibold">Pending Actions</h2>
        <PendingActions />
      </section>

      {/* Readiness scan chat — chunks 4.1, 4.2.
          Rendered whenever a connector exists (connected or error state) so
          the user can still ask free-form questions. When scope is empty the
          ScanChat island shows the disabled state + scope CTA. */}
      {githubConnector && (
        <ScanChat
          connectorId={githubConnector.id}
          repoIncludeList={scopedRepoIds}
        />
      )}
    </div>
  )
}
