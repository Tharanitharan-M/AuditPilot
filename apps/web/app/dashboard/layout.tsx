import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"

/**
 * Dashboard shell.
 *
 * shadcn's ``SidebarProvider`` ships a ``flex`` wrapper that relies on a
 * sibling "gap" div inside ``AppSidebar`` (``w-(--sidebar-width)``) to
 * reserve the sidebar column while the visible sidebar itself is rendered
 * with ``position: fixed``. In Tailwind v4 + Next.js 15 that pattern is
 * unreliable: flex-basis on ``SidebarInset`` (``flex-1`` ⇒ ``flex-basis:
 * 0%``) together with ``w-full`` lets the inset claim the full container
 * width and the gap div collapses, so the main content renders underneath
 * the fixed sidebar at ``z-10``.
 *
 * Override the wrapper to use CSS Grid at ``md+``: explicit
 * ``grid-cols-[var(--sidebar-width)_minmax(0,1fr)]`` guarantees the first
 * track always reserves 16rem and the second track always takes the
 * remaining space — no flex-shrink race, no overlap. Below ``md`` the
 * desktop sidebar is ``display: none`` and we want the content to take
 * the full viewport, so we stay with ``flex`` there (the original
 * shadcn behaviour) and the mobile Sheet handles the nav.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider className="md:grid md:grid-cols-[var(--sidebar-width)_minmax(0,1fr)] md:has-[[data-state=collapsed][data-collapsible=icon]]:grid-cols-[var(--sidebar-width-icon)_minmax(0,1fr)]">
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <main className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 md:px-8 lg:px-10">
          <div className="mx-auto w-full max-w-[1200px]">{children}</div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
