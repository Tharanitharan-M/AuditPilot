"use client"

import { useState } from "react"
import Link from "next/link"
import { Check, ChevronDown, ChevronRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"

export interface OnboardingStep {
  id: string
  label: string
  done: boolean
  href?: string
}

interface OnboardingChecklistProps {
  steps: OnboardingStep[]
}

export function OnboardingChecklist({ steps }: OnboardingChecklistProps) {
  const [expanded, setExpanded] = useState(true)

  const doneCount = steps.filter((s) => s.done).length
  const total = steps.length

  if (doneCount === total) return null

  const pct = Math.round((doneCount / total) * 100)
  const nextStep = steps.find((s) => !s.done)

  return (
    <Card>
      <CardHeader className="pb-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-between text-left"
          aria-expanded={expanded}
        >
          <CardTitle className="text-sm font-medium">Getting Started</CardTitle>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {doneCount}/{total}
            </span>
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </div>
        </button>
        <Progress value={pct} className="mt-2 h-1" />
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-0.5 pt-1">
          {steps.map((step) => {
            const isNext = step.id === nextStep?.id
            const content = (
              <div
                className={[
                  "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px]",
                  step.done ? "text-muted-foreground line-through decoration-muted-foreground/40" : "",
                  isNext ? "font-medium bg-muted/50" : "",
                ].join(" ")}
              >
                {step.done ? (
                  <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                ) : (
                  <span
                    className={[
                      "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border",
                      isNext ? "border-foreground" : "border-muted-foreground/30",
                    ].join(" ")}
                  />
                )}
                <span>{step.label}</span>
              </div>
            )

            if (step.href && !step.done) {
              return (
                <Link key={step.id} href={step.href} className="block rounded-md transition-colors hover:bg-muted/60">
                  {content}
                </Link>
              )
            }
            return <div key={step.id}>{content}</div>
          })}
        </CardContent>
      )}
    </Card>
  )
}
