"use client";

import { useSystemMetrics, useSystemStatus } from "@/hooks/use-api";
import { StatTile } from "@/components/ui/stat-tile";
import { StatusBadge } from "@/components/ui/status-badge";
import type { WorkbenchReadinessSnapshot } from "@/lib/api-hooks";

/**
 * The dashboard's figure row: one hero stat and four KPIs.
 *
 * Follows the data-viz rules (SPEC §4, §7.1): exactly one hero figure per view;
 * a tile is label / value / delta / trend with no icon; the value is never
 * coloured; only the delta arrow carries sentiment. The readiness score appears
 * here and nowhere else on the page — it used to be rendered twice, once in
 * this row and again in the "Traceability Readiness" card below it.
 */
export function MetricsOverviewWidget({
  readiness,
}: {
  readiness?: WorkbenchReadinessSnapshot;
}) {
  const { data: metrics, isLoading } = useSystemMetrics();
  const { data: systemStatus } = useSystemStatus();

  const score = metrics?.compliance_score ?? 0;
  const events = metrics?.events_ingested ?? 0;
  const chainLen = metrics?.chain_length ?? 0;
  const chainOk = metrics?.chain_valid ?? false;
  const alerts = metrics?.open_alerts ?? 0;
  const hasMetrics = Boolean(metrics) && !isLoading;
  const servicesDown =
    systemStatus?.overall_status && systemStatus.overall_status !== "healthy";

  const openFixes = readiness?.unresolved_fix_count;
  const exportEligible = readiness?.export_eligible;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr] lg:grid-rows-2">
      <StatTile
        className="sm:col-span-2 lg:col-span-1 lg:row-span-2"
        hero
        label="FSMA readiness score"
        value={score > 0 ? score : ""}
        unit={score > 0 ? "/100" : undefined}
        loading={isLoading}
        empty={!isLoading && score <= 0}
        emptyCaption={
          servicesDown
            ? "No data: services unreachable"
            : "No saved Inflow Workbench run yet"
        }
        status={
          hasMetrics && score > 0 ? (
            <StatusBadge
              state={exportEligible ? "compliant" : "at-risk"}
              label={exportEligible ? "Export eligible" : "Not export eligible"}
              size="sm"
            />
          ) : undefined
        }
      />

      <StatTile
        label="CTE events"
        value={events > 0 ? events.toLocaleString() : ""}
        loading={isLoading}
        empty={!isLoading && events <= 0}
        emptyCaption="Traceability events tracked"
      />
      <StatTile
        label="Hash chain"
        value={chainLen > 0 ? (chainOk ? "Verified" : "Broken") : ""}
        loading={isLoading}
        empty={!isLoading && chainLen <= 0}
        emptyCaption="Tamper-evident ledger entries"
        status={
          chainLen > 0 ? (
            <StatusBadge
              state={chainOk ? "committed" : "non-compliant"}
              label={`${chainLen.toLocaleString()} entries`}
              size="sm"
            />
          ) : undefined
        }
      />
      <StatTile
        label="Open alerts"
        value={alerts}
        loading={isLoading}
        emptyCaption="Compliance issues to resolve"
      />
      <StatTile
        label="Open fixes"
        value={typeof openFixes === "number" ? openFixes : ""}
        empty={typeof openFixes !== "number"}
        emptyCaption="From the Inflow Workbench run"
      />
    </div>
  );
}
