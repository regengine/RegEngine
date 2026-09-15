import * as React from "react"
import { cn } from "@/lib/utils"
import type { IconComponent } from "@/components/ui/icon"

/**
 * EmptyState — SPEC §4.
 *
 * One shape for every "nothing here yet" across the app. No illustrations, no
 * coloured icon discs: a muted glyph, a sentence, and the action that fixes it.
 * Inside a DataTable the dashed border is dropped, because the table shell
 * already draws one.
 */
export interface EmptyStateProps {
  icon?: IconComponent
  title: string
  /**
   * Element for the title. An empty state that replaces a section with its own
   * heading must keep that heading level, or the document outline loses a node
   * and screen-reader users lose the landmark. Defaults to `p` because most
   * empty states sit inside a card that already has one.
   */
  titleAs?: "p" | "h2" | "h3" | "h4"
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
  titleAs: TitleTag = "p",
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
      <TitleTag className="text-subheading text-re-text-primary">{title}</TitleTag>
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
