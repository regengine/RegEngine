"use client"

import * as React from "react"
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Callout — SPEC §4.
 *
 * Replaces the ad-hoc tinted notice strips ("API key required", "Billing
 * unavailable", "Backend services unreachable") that the inventory found in a
 * dozen different recipes.
 *
 * Callouts sit on the card surface with a 3px tone rail. Full-tint backgrounds
 * are reserved for badges, so a page carrying three notices does not turn into
 * a colour field. The one exception is a danger callout with role="alert": a
 * failure the operator must not miss gets a tinted ground.
 */
type CalloutTone = "info" | "success" | "warning" | "danger" | "neutral"

const TONE_RAIL: Record<CalloutTone, string> = {
  info: "border-l-re-info",
  success: "border-l-re-success",
  warning: "border-l-re-warning",
  danger: "border-l-re-danger",
  neutral: "border-l-re-border-strong",
}

const TONE_ICON_COLOR: Record<CalloutTone, string> = {
  info: "text-re-info",
  success: "text-re-success",
  warning: "text-re-warning",
  danger: "text-re-danger",
  neutral: "text-re-text-tertiary",
}

const TONE_DEFAULT_ICON: Record<CalloutTone, React.ComponentType<{ className?: string }>> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  neutral: Info,
}

export interface CalloutProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "role" | "title"> {
  tone?: CalloutTone
  title?: React.ReactNode
  icon?: React.ComponentType<{ className?: string }>
  action?: React.ReactNode
  dismissible?: boolean
  onDismiss?: () => void
  role?: "status" | "alert" | "note"
}

export function Callout({
  tone = "neutral",
  title,
  icon,
  action,
  dismissible,
  onDismiss,
  role,
  className,
  children,
  ...props
}: CalloutProps) {
  const Icon = icon ?? TONE_DEFAULT_ICON[tone]
  const isUrgent = tone === "danger" && role === "alert"

  return (
    <div
      role={role === "note" ? undefined : role}
      className={cn(
        "flex gap-3 rounded-md border border-l-[3px] border-re-border px-4 py-3 text-ui text-re-text-secondary",
        TONE_RAIL[tone],
        // A failure the operator must not miss is the one case that earns a tint.
        isUrgent ? "bg-re-danger-bg" : "bg-re-surface-card",
        className
      )}
      {...props}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", TONE_ICON_COLOR[tone])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium text-re-text-primary">{title}</p>}
        {children && <div className={cn(title && "mt-1")}>{children}</div>}
        {action && <div className="mt-3 flex flex-wrap items-center gap-2">{action}</div>}
      </div>
      {dismissible && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-mr-1 -mt-1 h-7 w-7 shrink-0 rounded-md text-re-text-muted transition-colors duration-120 hover:bg-re-surface-inset hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
        >
          <X className="mx-auto h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
