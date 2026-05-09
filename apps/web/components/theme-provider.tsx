"use client"

import * as React from "react"
import { ThemeProvider as NextThemesProvider } from "next-themes"

/**
 * App-wide theme provider — wraps `next-themes` so the dashboard can flip
 * between light and dark modes via CSS classes on `<html>`.
 *
 * Refs: PLAN.md chunk 6.5.6c.
 */
export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>
}
