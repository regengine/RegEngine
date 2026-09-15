import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Container — SPEC §3.1.
 *
 * Replaces the container zoo the inventory found: max-w-5xl (×23), max-w-7xl
 * (×14), max-w-6xl (×7), .re-container (×23), plus a handful of arbitrary
 * pixel widths — at least twelve distinct content widths across the site.
 */
export type ContainerWidth = "marketing" | "docs" | "tool" | "prose" | "app"

const WIDTH: Record<ContainerWidth, string> = {
  marketing: "mx-auto w-full max-w-[1120px] px-5 sm:px-8",
  docs: "mx-auto w-full max-w-[1200px] px-5 sm:px-8",
  tool: "mx-auto w-full max-w-[880px] px-5 sm:px-8",
  prose: "mx-auto w-full max-w-[720px] px-5 sm:px-8",
  app: "mx-auto w-full max-w-[1440px] px-4 sm:px-6",
}

export interface ContainerProps extends React.HTMLAttributes<HTMLElement> {
  width?: ContainerWidth
  as?: "div" | "main" | "section" | "article" | "header" | "footer"
}

export function Container({
  width = "marketing",
  as: Comp = "div",
  className,
  children,
  ...props
}: ContainerProps) {
  return (
    <Comp className={cn(WIDTH[width], className)} {...props}>
      {children}
    </Comp>
  )
}
