import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useSystemStatus } from "@/hooks/use-api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type ComplianceState } from "@/components/ui/status-badge";
import { Callout } from "@/components/ui/callout";

interface ServiceStatusProps {
  name: string;
  status: "healthy" | "unhealthy" | "degraded";
  details?: Record<string, unknown>;
}

/** Service health speaks the same state vocabulary as the rest of the app. */
const OVERALL_STATE: Record<string, ComplianceState> = {
  healthy: "compliant",
  degraded: "at-risk",
  unhealthy: "non-compliant",
  unknown: "unknown",
};

const SERVICE_STATE: Record<ServiceStatusProps["status"], ComplianceState> = {
  healthy: "compliant",
  degraded: "at-risk",
  unhealthy: "non-compliant",
};

const ServiceStatus = ({ name, status, details }: ServiceStatusProps) => (
  <div className="flex min-h-[48px] items-center justify-between gap-3 border-b border-re-border-subtle py-2.5 last:border-0">
    <div className="min-w-0">
      <p className="truncate text-ui font-medium capitalize text-re-text-primary">{name}</p>
      {status !== "healthy" && details?.error != null && (
        <p className="truncate text-small text-re-text-tertiary">
          This service is not responding right now. Check again shortly.
        </p>
      )}
    </div>
    <StatusBadge
      state={SERVICE_STATE[status] ?? "unknown"}
      label={status}
      size="sm"
      className="shrink-0 capitalize"
    />
  </div>
);

export function SystemHealthWidget() {
  const { data: systemStatus, isLoading, error } = useSystemStatus();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">System Health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </CardContent>
      </Card>
    );
  }

  // When demo fallback data is present, skip the error state and render normally
  if (error && !systemStatus) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>System Health</CardTitle>
        </CardHeader>
        <CardContent>
          <Callout tone="danger" role="alert">Failed to load system status</Callout>
        </CardContent>
      </Card>
    );
  }

  const services = systemStatus?.services || [];
  const overallStatus = systemStatus?.overall_status || "unknown";

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Health</CardTitle>
        <StatusBadge
          state={OVERALL_STATE[overallStatus] ?? "unknown"}
          label={overallStatus}
          size="sm"
          className="capitalize"
        />
      </CardHeader>
      <CardContent>
        {services.length === 0 ? (
          <p className="text-ui text-re-text-tertiary">
            No services monitored.
          </p>
        ) : (
          services.map((service: ServiceStatusProps) => (
            <ServiceStatus
              key={service.name}
              name={service.name}
              status={service.status}
              details={service.details}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}
