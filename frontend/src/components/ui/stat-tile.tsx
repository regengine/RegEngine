import * as React from "react"
import Link from "next/link"
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

/**
 * StatTile — SPEC §4, following the data-viz rules.
 *
 * Anatomy is fixed: label / value / optional delta / optional trend. There is
 * deliberately **no icon slot** — an icon slot is what let three competing tile
 * styles grow across the dashboard last time.
 *
 * Colour rules:
 *   · the value is never coloured — it is always `text-re-text-primary`;
 *   · the delta *text* stays secondary; only the arrow carries sentiment colour,
 *     with an sr-only word so the direction is not colour-only;
 *   · the sparkline is aria-hidden and decorative — the delta carries the
 *     meaning — and is `text-tertiary` on every tile except the hero, which is
 *     the one place a brand stroke is allowed.
 *
 * Exactly one `hero` tile per view.
 */
export interface StatTileDelta {
  value: string
  direction: "up" | "down" | "flat"
  /** Whether this direction is good news. Drives the arrow colour, not the number. */
  sentiment?: "good" | "bad" | "neutral"
  period?: string
}

export interface StatTileProps {
  label: string
  value: React.ReactNode
  unit?: string
  delta?: StatTileDelta
  /** 8–30 points. Omit for no chart. */
  trend?: number[]
  /** A StatusBadge, typically. */
  status?: React.ReactNode
  hero?: boolean
  href?: string
  loading?: boolean
  /** Renders an em-dash. `emptyCaption` is required so a blank tile explains itself. */
  empty?: boolean
  emptyCaption?: string
  /** Replaces the em-dash with words (e.g. "No data yet"), set at body size. */
  emptyLabel?: string
  /** A link that fixes the empty state (e.g. go upload a CSV). */
  emptyAction?: React.ReactNode
  className?: string
  children?: React.ReactNode
}

const DIRECTION_ICON = { up: ArrowUpRight, down: ArrowDownRight, flat: Minus } as const
const SENTIMENT_COLOR = {
  good: "text-re-success",
  bad: "text-re-danger",
  neutral: "text-re-text-tertiary",
} as const

function Sparkline({ points, hero }: { points: number[]; hero?: boolean }) {
  if (points.length < 2) return null
  const w = hero ? 96 : 64
  const h = hero ? 28 : 20
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w
      const y = h - ((p - min) / span) * h
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(" ")

  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      fill="none"
      aria-hidden="true"
      className={cn("overflow-visible", hero ? "text-re-brand" : "text-re-text-tertiary")}
    >
      <path d={d} stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function StatTile({
  label,
  value,
  unit,
  delta,
  trend,
  status,
  hero,
  href,
  loading,
  empty,
  emptyCaption,
  emptyLabel,
  emptyAction,
  className,
  children,
}: StatTileProps) {
  const DeltaIcon = delta ? DIRECTION_ICON[delta.direction] : null

  const body = (
    <div className="flex h-full flex-col gap-2">
      <p className="text-label text-re-text-muted">{label}</p>

      {loading ? (
        <>
          <Skeleton className={cn(hero ? "h-14 w-32" : "h-7 w-20")} />
          <Skeleton className="h-3.5 w-28" />
        </>
      ) : (
        <>
          {empty && emptyLabel ? (
            <p className="text-subheading text-re-text-secondary">{emptyLabel}</p>
          ) : (
          <div className="flex items-baseline gap-1.5">
            <span
              className={cn(
                "tabular-nums text-re-text-primary",
                hero ? "text-[3.5rem] leading-none tracking-[-0.02em]" : "text-title",
                empty && "text-re-text-disabled"
              )}
            >
              {empty ? "—" : value}
            </span>
            {unit && !empty && <span className="text-ui text-re-text-tertiary">{unit}</span>}
            {trend && trend.length > 1 && !empty && (
              <span className="ml-auto hidden self-center sm:block">
                <Sparkline points={trend} hero={hero} />
              </span>
            )}
          </div>
          )}

          {empty && emptyCaption && (
            <p className="text-small text-re-text-tertiary">{emptyCaption}</p>
          )}
          {empty && emptyAction && <div className="text-small">{emptyAction}</div>}

          {delta && !empty && DeltaIcon && (
            <p className="flex items-center gap-1 text-small text-re-text-secondary">
              <DeltaIcon
                className={cn("h-3.5 w-3.5 shrink-0", SENTIMENT_COLOR[delta.sentiment ?? "neutral"])}
                aria-hidden="true"
              />
              <span className="sr-only">
                {delta.direction === "up" ? "increased" : delta.direction === "down" ? "decreased" : "unchanged"}
              </span>
              {delta.value}
              {delta.period && <span className="text-re-text-tertiary"> {delta.period}</span>}
            </p>
          )}

          {status && <div className="mt-auto pt-1">{status}</div>}
          {children}
        </>
      )}
    </div>
  )

  const card = (
    <Card
      variant={href ? "interactive" : "default"}
      padding="compact"
      className={cn("h-full", className)}
    >
      {body}
    </Card>
  )

  if (!href) return card
  return (
    <Link href={href} className="block h-full no-underline">
      {card}
    </Link>
  )
}
