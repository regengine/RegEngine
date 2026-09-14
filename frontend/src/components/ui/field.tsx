"use client"

import * as React from "react"
import { AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Field — SPEC §4.
 *
 * Wraps a control with a real <label htmlFor>, an optional hint and an error,
 * wiring aria-describedby and aria-invalid so the association exists without
 * every page author remembering it. The inventory found labels not bound to
 * their inputs on most forms in the app.
 */
export interface FieldProps {
  label: string
  /** Must match the control's `id`. */
  htmlFor: string
  hint?: string
  error?: string
  required?: boolean
  className?: string
  children: React.ReactNode
}

export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  const hintId = hint ? `${htmlFor}-hint` : undefined
  const errorId = error ? `${htmlFor}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-ui font-medium text-re-text-primary">
        {label}
        {required && (
          <span className="ml-0.5 text-re-danger" aria-hidden="true">
            *
          </span>
        )}
      </label>

      {/* The control receives the wiring without the caller repeating it. */}
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
          id: htmlFor,
          "aria-describedby": describedBy,
          "aria-invalid": error ? true : undefined,
          required: required || undefined,
          ...(children.props as Record<string, unknown>),
        })
        : children}

      {hint && !error && (
        <p id={hintId} className="text-small text-re-text-tertiary">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="flex items-center gap-1.5 text-small text-re-danger">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  )
}
