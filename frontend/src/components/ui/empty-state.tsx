import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * EmptyState — SPEC §4.
 *
 * One shape for every "nothing here yet" across the app. No illustrations, no
 * coloured icon discs: a muted glyph, a sentence, and the action that fixes it.
 * Inside a DataTable the dashed border is dropped, because the table shell
 * already draws one.
 */
export interface EmptyStateProps {
  icon?: React.ComponentType<{ className?: string }>
  title: string
  description?: string
  action?: React.ReactNode
  secondaryAction?: React.ReactNode
  size?: "sm" | "md"
  /** Set when rendered inside a bordered shell (e.g. DataTable). */
  bare?: boolean
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  size = "md",
  bare,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 text-center",
        size === "sm" ? "py-8" : "py-14",
        !bare && "rounded-lg border border-dashed border-re-border bg-re-surface-card",
        className
      )}
    >
      {Icon && <Icon className="h-6 w-6 text-re-text-muted" aria-hidden="true" />}
      <p className="text-subheading text-re-text-primary">{title}</p>
      {description && (
        <p className="max-w-[48ch] text-ui text-re-text-tertiary">{description}</p>
      )}
      {(action || secondaryAction) && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  )
}
