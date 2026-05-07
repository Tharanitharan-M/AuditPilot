"use client"

import Link from "next/link"
import { AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface FailingControl {
  tsc_id: string
  label: string
}

interface AttentionSectionProps {
  failingControls: FailingControl[]
  unresolvedActionCount: number
}

export function AttentionSection({
  failingControls,
  unresolvedActionCount,
}: AttentionSectionProps) {
  if (failingControls.length === 0 && unresolvedActionCount === 0) return null

  const top3 = failingControls.slice(0, 3)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          Needs Attention
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {top3.length > 0 && (
          <div className="space-y-1.5">
            {top3.map((c) => (
              <Link
                key={c.tsc_id}
                href={`/dashboard/controls?highlight=${c.tsc_id}`}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors hover:bg-muted/60"
              >
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
                <span className="font-mono text-xs text-muted-foreground">{c.tsc_id}</span>
                <span className="truncate">{c.label}</span>
              </Link>
            ))}
            {failingControls.length > 3 && (
              <Link
                href="/dashboard/controls?status=failing"
                className="block px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                +{failingControls.length - 3} more failing controls
              </Link>
            )}
          </div>
        )}

        {unresolvedActionCount > 0 && (
          <div className="flex items-center justify-between rounded-md border border-border/60 bg-muted/30 px-3 py-2">
            <span className="text-[13px]">
              {unresolvedActionCount} unresolved action{unresolvedActionCount !== 1 ? "s" : ""}
            </span>
            <Link
              href="/dashboard/actions"
              className={cn(buttonVariants({ variant: "outline", size: "xs" }))}
            >
              Review
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
