"use client"

import { usePathname } from "next/navigation"
import Link from "next/link"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"

const ROUTE_LABELS: Record<string, string> = {
  "/dashboard": "Overview",
  "/dashboard/integrations": "Integrations",
  "/dashboard/controls": "Controls",
  "/dashboard/policies": "Policies",
  "/dashboard/actions": "Actions",
  "/dashboard/chat": "Chat",
}

interface PageHeaderProps {
  title: string
  description?: string
  breadcrumbExtra?: { label: string; href?: string }
}

export function PageHeader({ title, description, breadcrumbExtra }: PageHeaderProps) {
  const pathname = usePathname() ?? "/dashboard"

  const parentPath = Object.keys(ROUTE_LABELS)
    .filter((r) => r !== "/dashboard")
    .find((r) => pathname.startsWith(r))

  const crumbs: { label: string; href?: string }[] = [
    { label: "Overview", href: "/dashboard" },
  ]

  if (parentPath && parentPath !== "/dashboard") {
    crumbs.push({
      label: ROUTE_LABELS[parentPath],
      href: parentPath,
    })
  }

  if (breadcrumbExtra) {
    crumbs.push(breadcrumbExtra)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            {crumbs.map((crumb, i) => {
              const isLast = i === crumbs.length - 1
              return (
                <span key={crumb.label} className="contents">
                  {i > 0 && <BreadcrumbSeparator />}
                  <BreadcrumbItem>
                    {isLast ? (
                      <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink render={<Link href={crumb.href!} />}>
                        {crumb.label}
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                </span>
              )
            })}
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
    </div>
  )
}
