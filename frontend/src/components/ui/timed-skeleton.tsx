"use client"

import * as React from "react"
import { ErrorState } from "@/components/ui/error-state"
import { useLoadingPhase } from "@/hooks/use-loading-phase"

/**
 * TimedSkeleton — wraps a skeleton so it never spins forever.
 *
 * After ~5s it adds a "Still loading" line; at the timeout it swaps the
 * skeleton for the shared ErrorState with a Retry button. With no `onRetry`
 * the retry reloads the page, which is the only honest recovery for
 * route-level skeletons (loading.tsx, the dashboard shell).
 */
export interface TimedSkeletonProps {
  children: React.ReactNode
  onRetry?: () => void
  errorMessage?: string
  slowMs?: number
  timeoutMs?: number
  className?: string
}

export function TimedSkeleton(props: TimedSkeletonProps) {
  // Each retry remounts the timer so the clock starts over.
  const [attempt, setAttempt] = React.useState(0)
  const { onRetry } = props
  const retry = React.useCallback(() => {
    if (!onRetry) {
      window.location.reload()
      return
    }
    onRetry()
    setAttempt((n) => n + 1)
  }, [onRetry])

  return <TimedSkeletonInner key={attempt} {...props} onRetry={retry} />
}

function TimedSkeletonInner({
  children,
  onRetry,
  errorMessage = "This is taking longer than expected. Check your connection and try again.",
  slowMs,
  timeoutMs,
  className,
}: TimedSkeletonProps) {
  const phase = useLoadingPhase(true, { slowMs, timeoutMs })

  if (phase === "timeout") {
    return (
      <ErrorState
        className={className}
        title="Loading timed out"
        message={errorMessage}
        onRetry={onRetry}
      />
    )
  }

  return (
    <div className={className} aria-busy="true">
      {children}
      {phase === "slow" && (
        <p role="status" className="mt-3 text-small text-re-text-tertiary">
          Still loading…
        </p>
      )}
    </div>
  )
}
