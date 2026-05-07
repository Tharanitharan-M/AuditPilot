"use client"

import { useMemo } from "react"
import { Card, CardContent } from "@/components/ui/card"

interface ReadinessDonutProps {
  passing: number
  failing: number
  partial: number
  notAssessed: number
}

const SEGMENTS = [
  { key: "passing", color: "rgb(16 185 129)", label: "Passing" },
  { key: "failing", color: "rgb(239 68 68)", label: "Failing" },
  { key: "partial", color: "rgb(245 158 11)", label: "Partial" },
  { key: "notAssessed", color: "rgb(161 161 170)", label: "Not assessed" },
] as const

export function ReadinessDonut({
  passing,
  failing,
  partial,
  notAssessed,
}: ReadinessDonutProps) {
  const counts: Record<string, number> = {
    passing,
    failing,
    partial,
    notAssessed,
  }

  const total = passing + failing + partial + notAssessed
  const assessed = passing + failing + partial
  const percentage = total > 0 ? Math.round((passing / total) * 100) : 0

  const paths = useMemo(() => {
    if (total === 0) return []

    const radius = 40
    const circumference = 2 * Math.PI * radius
    let cumulativeOffset = 0
    const result: { key: string; color: string; dasharray: string; dashoffset: number }[] = []

    for (const seg of SEGMENTS) {
      const count = counts[seg.key]
      if (count === 0) continue
      const fraction = count / total
      const arcLength = fraction * circumference

      result.push({
        key: seg.key,
        color: seg.color,
        dasharray: `${arcLength} ${circumference - arcLength}`,
        dashoffset: -cumulativeOffset,
      })
      cumulativeOffset += arcLength
    }
    return result
  }, [total, passing, failing, partial, notAssessed])

  const radius = 40

  return (
    <Card>
      <CardContent className="flex items-center gap-8 py-6">
        <div className="relative h-36 w-36 shrink-0">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
            {total === 0 ? (
              <circle
                cx="50"
                cy="50"
                r={radius}
                fill="none"
                stroke="currentColor"
                className="text-muted/60"
                strokeWidth="10"
              />
            ) : (
              paths.map((seg) => (
                <circle
                  key={seg.key}
                  cx="50"
                  cy="50"
                  r={radius}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="10"
                  strokeDasharray={seg.dasharray}
                  strokeDashoffset={seg.dashoffset}
                  strokeLinecap="butt"
                  className="animate-[donut-grow_600ms_ease-out_both]"
                />
              ))
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold tracking-tight" aria-label={`${percentage}% readiness`}>
              {percentage}%
            </span>
            <span className="text-[11px] text-muted-foreground">passing</span>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <p className="text-sm font-medium">Readiness Score</p>
            <p className="text-xs text-muted-foreground">
              {assessed} of {total} controls assessed
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
            {SEGMENTS.map((seg) => (
              <div key={seg.key} className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ backgroundColor: seg.color }}
                  aria-hidden="true"
                />
                <span className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{counts[seg.key]}</span>{" "}
                  {seg.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
