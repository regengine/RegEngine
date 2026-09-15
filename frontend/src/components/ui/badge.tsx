import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * Badge — SPEC §4.
 *
 * Pills, per the brand guidelines. The pill shape is load-bearing: it is what
 * stops a *state* from reading as an *action* (buttons are 6px).
 *
 * The legacy `variant` prop is mapped onto tones. `default` maps to **neutral**,
 * never brand: 89 call sites pass no variant, and `--primary` now resolves to
 * brand green, so a brand default would turn 89 badges solid green sitewide.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[0.75rem] font-medium leading-4 transition-colors duration-120 focus:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none",
  {
    variants: {
      tone: {
        neutral: "border-re-border bg-re-surface-inset text-re-text-secondary",
        success: "border-re-success-border bg-re-success-bg text-re-success",
        warning: "border-re-warning-border bg-re-warning-bg text-re-warning",
        danger: "border-re-danger-border bg-re-danger-bg text-re-danger",
        info: "border-re-info-border bg-re-info-bg text-re-info",
        corrected: "border-re-state-corrected-border bg-re-state-corrected-bg text-re-state-corrected",
        /** Reserved for "Free tool — no login", "Sandbox", and plan names. */
        brand: "border-re-brand-muted bg-re-brand-muted text-re-brand",
      },
      size: {
        sm: "h-5 px-2 text-[0.6875rem]",
        md: "h-6 px-2.5",
      },
      mono: {
        true: "font-mono tracking-[0.02em]",
        false: "",
      },
    },
    defaultVariants: {
      tone: "neutral",
      size: "md",
      mono: false,
    },
  }
)

/** Legacy `variant` values, mapped onto tones. */
const VARIANT_TO_TONE = {
  default: "neutral",
  secondary: "neutral",
  outline: "neutral",
  destructive: "danger",
  warning: "warning",
} as const

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>

export interface BadgeProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "color">,
  Omit<VariantProps<typeof badgeVariants>, "tone"> {
  tone?: BadgeTone
  /** @deprecated Use `tone`. Kept so existing call sites and tests keep working. */
  variant?: keyof typeof VARIANT_TO_TONE
}

function Badge({ className, tone, variant, size, mono, ...props }: BadgeProps) {
  const resolved: BadgeTone = tone ?? (variant ? VARIANT_TO_TONE[variant] : "neutral")
  return <span className={cn(badgeVariants({ tone: resolved, size, mono }), className)} {...props} />
}

export { Badge, badgeVariants }
