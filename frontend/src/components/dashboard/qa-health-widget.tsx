import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type ComplianceState } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth-context";
import { useQAHealth } from "@/hooks/use-api";
import type { QAHealthStatus } from "@/types/api";

/**
 * Each QA status maps onto the shared compliance-state vocabulary, so the same
 * state looks identical here and everywhere else in the app.
 */
function statusConfig(status: QAHealthStatus | undefined): { label: string; state: ComplianceState } {
  switch (status) {
    case "passing":
      return { label: "Release gate passing", state: "compliant" };
    case "degraded":
      return { label: "Advisory issues", state: "at-risk" };
    case "unavailable":
      return { label: "QA signal unavailable", state: "unknown" };
    case "invalid_artifact":
      return { label: "QA artifact invalid", state: "non-compliant" };
    case "failing":
    default:
      return { label: "Release gate failing", state: "non-compliant" };
  }
}

export function QAHealthWidget() {
  const { user } = useAuth();
  const isSysadmin = Boolean(user?.is_sysadmin);
  const { data, isLoading, error } = useQAHealth(isSysadmin);

  if (!isSysadmin) return null;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>QA Health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-7 w-36" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }

  const config = statusConfig(data?.overall.status);
  const readyPercent = data?.overall.ready_percent ?? 0;
  const blockingCount = data?.overall.blocking_count ?? 0;
  const advisoryCount = data?.overall.advisory_count ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>QA Health</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusBadge
            state={error ? "unknown" : config.state}
            label={error ? "QA signal failed" : config.label}
            size="sm"
          />
          <span className="text-small tabular-nums text-re-text-tertiary">
            {readyPercent}% ready
          </span>
        </div>

        <div
          className="h-1.5 overflow-hidden rounded-full bg-re-surface-inset"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={readyPercent}
          aria-label="QA release readiness"
        >
          <div
            className="h-full bg-re-text-primary transition-all duration-180 motion-reduce:transition-none"
            style={{ width: `${readyPercent}%` }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-title tabular-nums text-re-text-primary">{blockingCount}</p>
            <p className="text-label text-re-text-muted">Blocking</p>
          </div>
          <div>
            <p className="text-title tabular-nums text-re-text-primary">{advisoryCount}</p>
            <p className="text-label text-re-text-muted">Advisory</p>
          </div>
        </div>

        <Button variant="secondary" className="w-full justify-between" asChild>
          <Link href="/dashboard/qa-health">
            Open QA Health
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
