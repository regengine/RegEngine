import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * Card — SPEC §4.
 *
 * Elevation is surface-step + border, never shadow: a card carries no shadow in
 * either theme, and on hover its border darkens rather than the card lifting.
 * A card never uses a coloured border to express state — state belongs in a
 * StatusBadge in its header.
 */
const cardVariants = cva("text-re-text-primary", {
  variants: {
    variant: {
      default: "rounded-lg border border-re-border bg-re-surface-card",
      inset: "rounded-lg border border-re-border-subtle bg-re-surface-inset",
      outline: "rounded-lg border border-re-border bg-transparent",
      interactive:
        "rounded-lg border border-re-border bg-re-surface-card transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none",
    },
    padding: {
      none: "",
      compact: "p-4",
      default: "",
      spacious: "p-6",
    },
  },
  defaultVariants: { variant: "default", padding: "none" },
})

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
  VariantProps<typeof cardVariants> { }

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, ...props }, ref) => (
    <div ref={ref} className={cn(cardVariants({ variant, padding }), className)} {...props} />
  )
)
Card.displayName = "Card"

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "flex items-start justify-between gap-4 border-b border-re-border-subtle px-5 py-4",
        className
      )}
      {...props}
    />
  )
)
CardHeader.displayName = "CardHeader"

/** Must stay an <h3> — src/__tests__/components/core.test.tsx asserts tagName === 'H3'. */
const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-subheading text-re-text-primary", className)} {...props} />
  )
)
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-small text-re-text-tertiary", className)} {...props} />
  )
)
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("p-5", className)} {...props} />
)
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex items-center gap-2 border-t border-re-border-subtle px-5 py-3", className)}
      {...props}
    />
  )
)
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent, cardVariants }
