import * as React from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react"
import { Badge, type BadgeTone } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { IconComponent } from "@/components/ui/icon"

/**
 * StatusBadge — SPEC §4.
 *
 * The single vocabulary for compliance state across all 163 pages. A state
 * always ships as icon + text label, never colour alone, so it survives
 * greyscale, colour-blindness and forced-colours mode. The icons are
 * deliberately distinct *glyphs* (check / triangle / cross / clock / spinner /
 * refresh), not the same dot in different hues.
 *
 * `corrected` keeps its own violet: without it, "corrected" and "event" would
 * differ only by a 14px glyph in a dense STATE column.
 */
export type ComplianceState =
  | "compliant"
  | "at-risk"
  | "non-compliant"
  | "pending"
  | "in-progress"
  | "blocked"
  | "needs-correction"
  | "corrected"
  | "committed"
  | "exported"
  | "unknown"

type StateConfig = {
  tone: BadgeTone
  icon: IconComponent
  label: string
  spin?: boolean
}

const STATE_CONFIG: Record<ComplianceState, StateConfig> = {
  compliant: { tone: "success", icon: CheckCircle2, label: "Compliant" },
  committed: { tone: "success", icon: CheckCircle2, label: "Committed" },
  exported: { tone: "success", icon: CheckCircle2, label: "Exported" },
  "at-risk": { tone: "warning", icon: AlertTriangle, label: "At risk" },
  "needs-correction": { tone: "warning", icon: AlertTriangle, label: "Needs correction" },
  "non-compliant": { tone: "danger", icon: XCircle, label: "Non-compliant" },
  blocked: { tone: "danger", icon: XCircle, label: "Blocked" },
  pending: { tone: "neutral", icon: Clock, label: "Pending" },
  "in-progress": { tone: "info", icon: Loader2, label: "In progress", spin: true },
  corrected: { tone: "corrected", icon: RefreshCw, label: "Corrected" },
  unknown: { tone: "neutral", icon: HelpCircle, label: "Unknown" },
}

export interface StatusBadgeProps {
  state: ComplianceState
  /** Overrides the default label. The label is the accessible name — it is never omitted. */
  label?: string
  size?: "sm" | "md"
  mono?: boolean
  className?: string
}

export function StatusBadge({ state, label, size = "md", mono, className }: StatusBadgeProps) {
  const config = STATE_CONFIG[state] ?? STATE_CONFIG.unknown
  const Icon = config.icon
  return (
    <Badge tone={config.tone} size={size} mono={mono} className={cn(className)}>
      <Icon
        className={cn("h-3.5 w-3.5 shrink-0", config.spin && "animate-spin motion-reduce:animate-none")}
        aria-hidden="true"
      />
      {label ?? config.label}
    </Badge>
  )
}

export { STATE_CONFIG }
