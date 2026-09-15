import * as React from "react"
import { Container, type ContainerWidth } from "@/components/layout/container"
import { cn } from "@/lib/utils"

/**
 * Section — SPEC §3.2.
 *
 * Marketing sections are separated by a hairline rule, not a tinted band. At
 * most one inset band per page; the page ground stays flat. This is what makes
 * a marketing page read as one document rather than a stack of cards.
 */
export interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, "title"> {
  eyebrow?: React.ReactNode
  title?: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  spacing?: "marketing" | "app"
  width?: ContainerWidth
  /** One inset band per page, maximum. */
  tone?: "default" | "inset"
  /** Suppresses the top hairline (e.g. the first section after a hero). */
  flush?: boolean
  headingLevel?: "h2" | "h3"
}

export function Section({
  eyebrow,
  title,
  description,
  actions,
  spacing = "marketing",
  width,
  tone = "default",
  flush,
  headingLevel: Heading = "h2",
  className,
  children,
  ...props
}: SectionProps) {
  const header = (eyebrow || title || description || actions) && (
    <div
      className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between",
        spacing === "marketing" ? "mb-10" : "mb-4"
      )}
    >
      <div className="max-w-[68ch] space-y-3">
        {eyebrow && <p className="text-label text-re-text-muted">{eyebrow}</p>}
        {title && (
          <Heading
            className={cn(
              "text-re-text-primary",
              spacing === "marketing" ? "font-display text-heading-lg" : "text-heading"
            )}
          >
            {title}
          </Heading>
        )}
        {description && (
          <p className="text-ui text-re-text-secondary sm:text-body">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )

  const body = (
    <>
      {header}
      {children}
    </>
  )

  return (
    <section
      className={cn(
        spacing === "marketing" ? "py-16 sm:py-20" : "space-y-4",
        spacing === "marketing" && !flush && "border-t border-re-border-subtle",
        tone === "inset" && "bg-re-surface-inset",
        className
      )}
      {...props}
    >
      {width ? <Container width={width}>{body}</Container> : body}
    </section>
  )
}
