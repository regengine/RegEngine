import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Input — SPEC §4. Textarea, Select and any native control share this recipe.
 *
 * In dark mode fields sit on `surface-inset`, i.e. *below* the card, so they
 * read as wells rather than slabs. `border-default` at rest is a decorative
 * boundary; hover and focus promote it to `border-strong` plus a 2px ring, so
 * the control's edge is always identifiable at 3:1 when it matters.
 */
export const fieldControlClasses =
  "flex h-9 w-full rounded-md border border-re-border bg-re-surface-card px-3 text-ui text-re-text-primary placeholder:text-re-text-muted transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:border-re-brand focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 disabled:cursor-not-allowed disabled:bg-re-surface-inset disabled:text-re-text-disabled aria-[invalid=true]:border-re-danger aria-[invalid=true]:focus-visible:ring-re-danger/25 motion-reduce:transition-none dark:bg-re-surface-inset"

export interface InputProps
  // `size` is overridden: the native attribute is a character count, which no
  // call site uses, and the design system needs the control-height token.
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  invalid?: boolean
  size?: "md" | "lg"
  leadingIcon?: React.ReactNode
  mono?: boolean
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, invalid, size = "md", leadingIcon, mono, ...props }, ref) => {
    const control = (
      <input
        type={type}
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          fieldControlClasses,
          size === "lg" && "h-11",
          mono && "font-mono text-[0.8125rem]",
          leadingIcon && "pl-9",
          className
        )}
        {...props}
      />
    )

    if (!leadingIcon) return control

    return (
      <div className="relative w-full">
        <span
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-re-text-muted [&_svg]:size-4"
          aria-hidden="true"
        >
          {leadingIcon}
        </span>
        {control}
      </div>
    )
  }
)
Input.displayName = "Input"

export { Input }
