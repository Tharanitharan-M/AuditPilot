"use client"

import { useUser, useClerk } from "@clerk/nextjs"
import { LogOut, User } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function SidebarUserMenu() {
  const { user } = useUser()
  const { signOut } = useClerk()

  const displayName =
    user?.fullName ?? user?.primaryEmailAddress?.emailAddress ?? "User"
  const initials = displayName.slice(0, 2).toUpperCase()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full min-w-0 items-center gap-2 overflow-hidden rounded-md px-2 py-1.5 text-left text-sm hover:bg-sidebar-accent">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground">
          {user?.imageUrl ? (
            <img
              src={user.imageUrl}
              alt=""
              className="h-6 w-6 rounded-full"
            />
          ) : (
            initials
          )}
        </div>
        <span className="min-w-0 flex-1 truncate text-sm group-data-[collapsible=icon]:hidden">
          {displayName}
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-48">
        <DropdownMenuItem disabled>
          <User className="mr-2 h-4 w-4" />
          {displayName}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => signOut({ redirectUrl: "/" })}
          data-testid="sidebar-sign-out"
        >
          <LogOut className="mr-2 h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
