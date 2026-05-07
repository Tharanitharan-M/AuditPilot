"use client"

import Link from "next/link"
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
} from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import type { LucideIcon } from "lucide-react"

interface StatusCardsProps {
  passing: number
  failing: number
  partial: number
  notAssessed: number
}

const STATUS_CONFIG: {
  key: string
  label: string
  description: string
  colorClass: string
  iconColor: string
  icon: LucideIcon
  filter: string
}[] = [
  {
    key: "passing",
    label: "Passing",
    description: "Controls fully met",
    colorClass: "text-emerald-700 dark:text-emerald-400",
    iconColor: "text-emerald-500",
    icon: CheckCircle2,
    filter: "passing",
  },
  {
    key: "failing",
    label: "Failing",
    description: "Needs remediation",
    colorClass: "text-red-700 dark:text-red-400",
    iconColor: "text-red-500",
    icon: XCircle,
    filter: "failing",
  },
  {
    key: "partial",
    label: "Partial",
    description: "Partially implemented",
    colorClass: "text-amber-700 dark:text-amber-400",
    iconColor: "text-amber-500",
    icon: AlertTriangle,
    filter: "partial",
  },
  {
    key: "notAssessed",
    label: "Not assessed",
    description: "Awaiting scan",
    colorClass: "text-zinc-600 dark:text-zinc-400",
    iconColor: "text-zinc-400",
    icon: HelpCircle,
    filter: "unknown",
  },
]

export function StatusCards({ passing, failing, partial, notAssessed }: StatusCardsProps) {
  const counts: Record<string, number> = {
    passing,
    failing,
    partial,
    notAssessed,
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {STATUS_CONFIG.map((cfg) => {
        const Icon = cfg.icon
        return (
          <Link
            key={cfg.key}
            href={`/dashboard/controls?status=${cfg.filter}`}
            className="group block"
          >
            <Card className="transition-all group-hover:shadow-md group-hover:border-border">
              <CardContent className="flex items-start gap-3 p-4">
                <div className={`mt-0.5 ${cfg.iconColor}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className={`text-2xl font-semibold tracking-tight ${cfg.colorClass}`}>
                    {counts[cfg.key]}
                  </p>
                  <p className="text-sm font-medium leading-none">{cfg.label}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">{cfg.description}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        )
      })}
    </div>
  )
}
