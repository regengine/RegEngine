import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Button — SPEC §4.
 *
 * One `primary` per view region; everything else is `secondary` or `ghost`.
 * `primary` is one of only six places brand green is allowed to appear.
 *
 * Legacy variant names (`default`, `outline`, `destructive`) are kept as
 * aliases so the ~92 existing importers and the tests that mock this module
 * keep working unchanged.
 *
 * Touch targets: use `size="lg"` (44px) for mobile forms and page-header
 * actions. There is deliberately no blanket coarse-pointer height floor — it
 * would make a 32–40px dense table row containing a link impossible, and every
 * list page has one.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border text-ui font-medium transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "border-transparent bg-re-brand text-re-brand-foreground hover:bg-re-brand-dark active:bg-re-brand-dark",
        secondary:
          "border-re-border-strong bg-re-surface-card text-re-text-primary hover:bg-re-surface-inset active:bg-re-surface-inset",
        ghost:
          "border-transparent bg-transparent text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary",
        danger:
          "border-transparent bg-re-danger text-re-danger-foreground hover:opacity-90 active:opacity-90",
        link: "border-transparent bg-transparent px-0 text-re-brand underline-offset-[3px] hover:underline",

        // ── Legacy aliases — do not use in new code ──
        default:
          "border-transparent bg-re-brand text-re-brand-foreground hover:bg-re-brand-dark active:bg-re-brand-dark",
        outline:
          "border-re-border-strong bg-re-surface-card text-re-text-primary hover:bg-re-surface-inset active:bg-re-surface-inset",
        destructive:
          "border-transparent bg-re-danger text-re-danger-foreground hover:opacity-90 active:opacity-90",
      },
      size: {
        sm: "h-8 px-3 text-[0.8125rem]",
        md: "h-9 px-4",
        lg: "h-11 px-5",
        icon: "h-9 w-9 p-0",
        // Legacy alias
        default: "h-9 px-4",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
  VariantProps<typeof buttonVariants> {
  asChild?: boolean
  /** Renders a spinner, sets aria-busy, and keeps the button's width stable. */
  loading?: boolean
  leadingIcon?: React.ReactNode
  trailingIcon?: React.ReactNode
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant, size, asChild = false, loading, leadingIcon, trailingIcon, children, disabled, ...props },
    ref
  ) => {
    const Comp = asChild ? Slot : "button"

    // `asChild` forwards to a single child element (usually a Link), so the
    // decorations below would break Slot's single-child contract.
    if (asChild) {
      return (
        <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>
          {children}
        </Comp>
      )
    }

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : leadingIcon}
        {children}
        {!loading && trailingIcon}
      </Comp>
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
