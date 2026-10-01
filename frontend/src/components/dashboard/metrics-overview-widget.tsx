"use client";

import { useSystemMetrics } from "@/hooks/use-api";
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
  const { data: rawMetrics, isLoading, isError } = useSystemMetrics();
  const metrics = isError ? undefined : rawMetrics;
  const score = metrics?.compliance_score;
  const events = metrics?.events_ingested;
  const chainLen = metrics?.chain_length;
  const chainOk = metrics?.chain_valid;
  const alerts = metrics?.open_alerts;
  const assessed = typeof score === "number";
  const chainLabel = chainOk === true ? "Verified" : chainOk === false ? "Broken" : "Verification unavailable";

  const openFixes = readiness?.unresolved_fix_count;
  const exportEligible = readiness?.export_eligible;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr] lg:grid-rows-2">
      <StatTile
        className="sm:col-span-2 lg:col-span-1 lg:row-span-2"
        hero
        label="FSMA readiness score"
        value={assessed ? score : ""}
        unit={assessed ? "/100" : undefined}
        loading={isLoading}
        empty={!isLoading && !assessed}
        emptyCaption={metrics?.score_assessment_status === "unassessed" ? "Not assessed" : "Score unavailable"}
        status={
          assessed && typeof exportEligible === "boolean" ? (
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
        value={typeof events === "number" ? events.toLocaleString() : ""}
        loading={isLoading}
        empty={!isLoading && typeof events !== "number"}
        emptyCaption="Event count unavailable"
      />
      <StatTile
        label="Hash chain"
        value={chainLabel}
        loading={isLoading}
        empty={false}
        status={
          typeof chainLen === "number" && typeof chainOk === "boolean" ? (
            <StatusBadge
              state={chainOk ? "committed" : "non-compliant"}
              label={`${chainLen.toLocaleString()} entries`}
              size="sm"
            />
          ) : undefined
        }
      >
        <p className="text-small text-re-text-tertiary">
          {metrics?.chain_verified_scope ?? "Verification scope unavailable"}
        </p>
      </StatTile>
      <StatTile
        label="Open alerts"
        value={typeof alerts === "number" ? alerts : ""}
        empty={typeof alerts !== "number"}
        loading={isLoading}
        emptyCaption="Alert count unavailable"
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
