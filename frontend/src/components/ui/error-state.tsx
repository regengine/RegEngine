import * as React from "react"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"

/**
 * ErrorState — the one shape for "this failed to load". Same recipe as the
 * DataTable error row: a danger callout with a Retry button, so a timed-out
 * card and a failed table read the same.
 */
export interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  retryLabel?: string
  requestId?: string
  retrying?: boolean
  className?: string
}

export function ErrorState({
  title = "Couldn't load this",
  message,
  onRetry,
  retryLabel = "Retry",
  requestId,
  retrying = false,
  className,
}: ErrorStateProps) {
  return (
    <Callout
      tone="danger"
      role="alert"
      title={title}
      className={className}
      action={
        <>
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry} disabled={retrying}>
              {retrying ? "Retrying…" : retryLabel}
            </Button>
          )}
          <a href="/settings/support" className="text-small underline">Contact support</a>
        </>
      }
    >
      {message}
      {requestId && <p className="mt-2 text-small">Request ID: {requestId}</p>}
    </Callout>
  )
}
