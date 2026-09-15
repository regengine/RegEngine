import * as React from "react"
import { cn } from "@/lib/utils"

import { fieldControlClasses } from "@/components/ui/field-control"

/** Re-exported so the many `from "@/components/ui/input"` call sites keep working. */
export { fieldControlClasses }

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
