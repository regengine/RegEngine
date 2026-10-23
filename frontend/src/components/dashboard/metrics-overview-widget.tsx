"use client";

import Link from "next/link";
import { useSystemMetrics, useSystemStatus } from "@/hooks/use-api";
import { ErrorState } from "@/components/ui/error-state";
import { StatTile } from "@/components/ui/stat-tile";
import { StatusBadge } from "@/components/ui/status-badge";
import { TimedSkeleton } from "@/components/ui/timed-skeleton";
import type { WorkbenchReadinessSnapshot } from "@/lib/api-hooks";
import { isExperimentalPageEnabled } from "@/lib/experimental-features";

/** Where an empty tile sends the operator: the CSV tab of the import page. */
export const CSV_UPLOAD_HREF = "/ingest?tab=file";

const EMPTY_LABEL = "No data yet";

function UploadCsvLink() {
  return (
    <Link href={CSV_UPLOAD_HREF} className="text-re-brand underline underline-offset-[3px]">
      Upload a CSV
    </Link>
  );
}

/**
 * The dashboard's figure row: one hero stat and four KPIs.
 *
 * Follows the data-viz rules (SPEC §4, §7.1): exactly one hero figure per view;
 * a tile is label / value / delta / trend with no icon; the value is never
 * coloured; only the delta arrow carries sentiment. The readiness score appears
 * here and nowhere else on the page — it used to be rendered twice, once in
 * this row and again in the "Traceability Readiness" card below it.
 *
 * An empty tile says "No data yet" and links to CSV upload. A failed load is
 * shown as failed with Retry — never as zeros, because useSystemMetrics()
 * substitutes zeroed placeholder metrics when the backend is unreachable.
 */
export function MetricsOverviewWidget({
  readiness,
  readinessFailed = false,
}: {
  readiness?: WorkbenchReadinessSnapshot;
  readinessFailed?: boolean;
}) {
  const { data: metrics, isLoading, error: metricsError, refetch } = useSystemMetrics();
  const { data: systemStatus } = useSystemStatus();

  if (isLoading) {
    return (
      <TimedSkeleton onRetry={() => void refetch()} errorMessage="Dashboard metrics did not respond.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr] lg:grid-rows-2">
          <StatTile className="sm:col-span-2 lg:col-span-1 lg:row-span-2" hero label="FSMA readiness score" value="" loading />
          <StatTile label="CTE events" value="" loading />
          <StatTile label="Hash chain" value="" loading />
          <StatTile label="Open alerts" value="" loading />
          <StatTile label="Open fixes" value="" loading />
        </div>
      </TimedSkeleton>
    );
  }

  if (metricsError) {
    return (
      <ErrorState
        title="Couldn't load dashboard metrics"
        message="Readiness score, events, hash chain and alerts are unavailable right now."
        onRetry={() => void refetch()}
      />
    );
  }

  const score = metrics?.compliance_score ?? 0;
  const events = metrics?.events_ingested ?? 0;
  const chainLen = metrics?.chain_length ?? 0;
  const chainOk = metrics?.chain_valid ?? false;
  const alerts = metrics?.open_alerts;
  const alertsEnabled = isExperimentalPageEnabled("/dashboard/alerts");
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
        empty={score <= 0}
        emptyLabel={EMPTY_LABEL}
        emptyAction={<UploadCsvLink />}
        emptyCaption={
          servicesDown
            ? "Services unreachable"
            : "No saved Inflow Workbench run yet"
        }
        status={
          score > 0 ? (
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
        empty={events <= 0}
        emptyLabel={EMPTY_LABEL}
        emptyAction={<UploadCsvLink />}
        emptyCaption="Traceability events tracked"
      />
      <StatTile
        label="Hash chain"
        value={chainLen > 0 ? (chainOk ? "Verified" : "Broken") : ""}
        empty={chainLen <= 0}
        emptyLabel={EMPTY_LABEL}
        emptyAction={<UploadCsvLink />}
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
        value={alertsEnabled ? alerts ?? "" : "Alerts are off"}
        empty={alertsEnabled && typeof alerts !== "number"}
        emptyLabel={alertsEnabled ? EMPTY_LABEL : undefined}
        emptyAction={alertsEnabled ? <UploadCsvLink /> : undefined}
        emptyCaption={alertsEnabled ? "Compliance issues to resolve" : undefined}
      />
      <StatTile
        label="Open fixes"
        value={typeof openFixes === "number" ? openFixes : ""}
        empty={typeof openFixes !== "number"}
        emptyLabel={readinessFailed ? "Couldn't load" : EMPTY_LABEL}
        emptyAction={readinessFailed ? undefined : <UploadCsvLink />}
        emptyCaption="From the Inflow Workbench run"
      />
    </div>
  );
}
