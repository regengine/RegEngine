import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemMetrics, useSystemStatus } from "@/hooks/use-api";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, FileCheck, Link2, AlertTriangle } from "lucide-react";

export function MetricsOverviewWidget() {
  const { data: metrics, isLoading, error } = useSystemMetrics();
  const { data: systemStatus } = useSystemStatus();
  const systemHealthy = systemStatus?.overall_status === "healthy";

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 p-3 sm:p-6 sm:pb-2">
              <Skeleton className="h-4 w-[80px] sm:w-[100px]" />
              <Skeleton className="h-4 w-4 rounded-full" />
            </CardHeader>
            <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
              <Skeleton className="h-7 sm:h-8 w-[50px] sm:w-[60px] mb-1" />
              <Skeleton className="h-3 w-[70px] sm:w-[80px]" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const isDemo = !!(metrics as unknown as Record<string, unknown>)?._demo;
  const score = metrics?.compliance_score ?? 0;
  const grade = metrics?.compliance_grade ?? "—";
  const events = metrics?.events_ingested ?? 0;
  const chainLen = metrics?.chain_length ?? 0;
  const chainOk = metrics?.chain_valid ?? false;
  const alerts = metrics?.open_alerts ?? 0;

  // Color grade badge
  const gradeColor =
    score >= 90
      ? "text-re-brand-dark"
      : score >= 70
        ? "text-re-warning"
        : "text-re-danger";

  return (
    <div className="space-y-3">
      {isDemo && (
        <div className="flex items-center gap-2 border border-re-warning/40 bg-[var(--re-surface-card)] px-3 py-2 text-xs text-re-warning">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
          <span>
            {systemHealthy
              ? "Sample data shown — connect a supplier feed to see live metrics."
              : "Backend services unreachable — data will appear once services are connected."}
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-3 pb-1 sm:p-6 sm:pb-2">
            <CardTitle className="text-xs font-medium sm:text-sm">
              Compliance Score
            </CardTitle>
            <Shield className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground sm:h-4 sm:w-4" />
          </CardHeader>
          <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
            <div className="flex flex-wrap items-baseline gap-1 sm:gap-2">
              <span className={`text-xl font-bold sm:text-2xl ${gradeColor}`}>
                {score > 0 ? `${score}%` : "—"}
              </span>
              {grade !== "—" && (
                <span
                  className={`text-sm font-semibold sm:text-lg ${gradeColor}`}
                >
                  ({grade})
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              FSMA 204 readiness
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-3 pb-1 sm:p-6 sm:pb-2">
            <CardTitle className="text-xs font-medium sm:text-sm">
              CTE Events
            </CardTitle>
            <FileCheck className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground sm:h-4 sm:w-4" />
          </CardHeader>
          <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
            <div className="truncate text-xl font-bold sm:text-2xl">
              {events > 0 ? events.toLocaleString() : "—"}
            </div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              Traceability events tracked
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-3 pb-1 sm:p-6 sm:pb-2">
            <CardTitle className="text-xs font-medium sm:text-sm">
              Hash Chain
            </CardTitle>
            <Link2 className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground sm:h-4 sm:w-4" />
          </CardHeader>
          <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
            <div className="flex flex-wrap items-baseline gap-1 sm:gap-2">
              <span className="text-xl font-bold sm:text-2xl">
                {chainLen > 0 ? chainLen : "—"}
              </span>
              {chainLen > 0 && (
                <span
                  className={`text-[10px] font-medium sm:text-xs ${
                    chainOk ? "text-re-brand-dark" : "text-re-danger"
                  }`}
                >
                  {chainOk ? "Valid" : "Broken"}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              Tamper-evident ledger entries
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 p-3 pb-1 sm:p-6 sm:pb-2">
            <CardTitle className="text-xs font-medium sm:text-sm">
              Open Alerts
            </CardTitle>
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground sm:h-4 sm:w-4" />
          </CardHeader>
          <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
            <div className="text-xl font-bold sm:text-2xl">{alerts}</div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              Compliance issues to resolve
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
