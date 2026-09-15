import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * PageHeader — SPEC §3.4. One header anatomy for every surface.
 *
 * Rules the primitive enforces by shape:
 *   · exactly one primary action (the slot is singular);
 *   · no icon before the H1 — the icon-tile-before-title pattern the inventory
 *     found on ten app pages is gone; a meaningful icon moves to the eyebrow;
 *   · the header is never boxed — the hairline under it is the only rule.
 */
export interface PageHeaderProps {
  title: React.ReactNode
  eyebrow?: React.ReactNode
  description?: React.ReactNode
  /** StatusBadge, timestamps — right-aligned above the actions. */
  meta?: React.ReactNode
  /** Exactly one <Button variant="primary">. */
  primaryAction?: React.ReactNode
  secondaryActions?: React.ReactNode
  /** A <Tabs> list, rendered under the header. */
  tabs?: React.ReactNode
  /** Marketing / tools / docs only — the app uses the status strip. */
  breadcrumbs?: React.ReactNode
  size?: "page" | "hero"
  className?: string
  id?: string
}

export function PageHeader({
  title,
  eyebrow,
  description,
  meta,
  primaryAction,
  secondaryActions,
  tabs,
  breadcrumbs,
  size = "page",
  className,
  id,
}: PageHeaderProps) {
  const hasActions = Boolean(primaryAction || secondaryActions)

  return (
    <div className={cn(tabs ? "mb-6" : "mb-6 border-b border-re-border-subtle pb-5", className)}>
      {breadcrumbs}
      <div
        className={cn(
          "flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between",
          breadcrumbs && "mt-4"
        )}
      >
        <div className="min-w-0">
          {eyebrow && <p className="mb-2 text-label text-re-text-muted">{eyebrow}</p>}
          <h1
            id={id}
            className={cn(
              "text-re-text-primary",
              size === "hero" ? "font-display text-display" : "text-title"
            )}
          >
            {title}
          </h1>
          {description && (
            <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">{description}</p>
          )}
        </div>

        {(meta || hasActions) && (
          <div className="flex flex-col items-stretch gap-2 sm:items-end">
            {meta && (
              <div className="flex flex-wrap items-center gap-2 text-small text-re-text-tertiary sm:justify-end">
                {meta}
              </div>
            )}
            {hasActions && (
              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                {secondaryActions}
                {primaryAction}
              </div>
            )}
          </div>
        )}
      </div>

      {tabs && <div className="mt-5 border-b border-re-border-subtle">{tabs}</div>}
    </div>
  )
}
