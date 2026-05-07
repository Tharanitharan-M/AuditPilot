import { getMeData } from "@/lib/me"
import { OverviewClient } from "@/components/overview-client"

export default async function OverviewPage() {
  const me = await getMeData()
  const githubConnector =
    me?.connectors?.find((c) => c.provider === "github") ?? null
  const hasRepos = (me?.repos?.length ?? 0) > 0
  const scopedRepoCount = githubConnector?.scoped_repo_count ?? 0

  return (
    <OverviewClient
      connector={githubConnector}
      hasRepos={hasRepos}
      scopedRepoCount={scopedRepoCount}
    />
  )
}
