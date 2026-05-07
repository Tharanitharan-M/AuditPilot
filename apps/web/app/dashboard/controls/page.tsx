import { Suspense } from "react"
import { ControlsClient } from "@/components/controls-client"

export default function ControlsPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><p className="text-muted-foreground">Loading controls...</p></div>}>
      <ControlsClient />
    </Suspense>
  )
}
