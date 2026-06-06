import Link from "next/link";
import { AlertTriangle, CheckCircle2, ShieldAlert, WifiOff, ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";
import { useQAHealth } from "@/hooks/use-api";
import type { QAHealthStatus } from "@/types/api";

function statusConfig(status: QAHealthStatus | undefined) {
  switch (status) {
    case "passing":
      return {
        label: "Release gate passing",
        tone: "text-re-success",
        badge: "bg-re-success-muted text-re-success border-re-success/40",
        icon: CheckCircle2,
      };
    case "degraded":
      return {
        label: "Advisory issues",
        tone: "text-re-warning",
        badge: "bg-re-warning-muted text-re-warning border-re-warning/40",
        icon: AlertTriangle,
      };
    case "unavailable":
      return {
        label: "QA signal unavailable",
        tone: "text-muted-foreground",
        badge: "bg-re-surface-elevated text-muted-foreground border-[var(--re-surface-border)]",
        icon: WifiOff,
      };
    case "invalid_artifact":
      return {
        label: "QA artifact invalid",
        tone: "text-re-danger",
        badge: "bg-re-danger-muted text-re-danger border-re-danger/40",
        icon: ShieldAlert,
      };
    case "failing":
    default:
      return {
        label: "Release gate failing",
        tone: "text-re-danger",
        badge: "bg-re-danger-muted text-re-danger border-re-danger/40",
        icon: ShieldAlert,
      };
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
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">QA Health</CardTitle>
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
  const Icon = config.icon;
  const readyPercent = data?.overall.ready_percent ?? 0;
  const blockingCount = data?.overall.blocking_count ?? 0;
  const advisoryCount = data?.overall.advisory_count ?? 0;

  return (
    <Card className="border-[var(--re-surface-border)]">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">QA Health</CardTitle>
        <Icon className={`h-4 w-4 ${config.tone}`} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Badge variant="outline" className={`${config.badge} text-[11px]`}>
            {error ? "QA signal failed" : config.label}
          </Badge>
          <span className="text-xs text-muted-foreground tabular-nums">
            {readyPercent}% ready
          </span>
        </div>

        <div
          className="h-2 overflow-hidden rounded-sm bg-[var(--re-surface-elevated)]"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={readyPercent}
          aria-label="QA release readiness"
        >
          <div
            className="h-full bg-[var(--re-brand)] transition-all"
            style={{ width: `${readyPercent}%` }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xl font-bold tabular-nums">{blockingCount}</p>
            <p className="text-xs text-muted-foreground">Blocking</p>
          </div>
          <div>
            <p className="text-xl font-bold tabular-nums">{advisoryCount}</p>
            <p className="text-xs text-muted-foreground">Advisory</p>
          </div>
        </div>

        <Link
          href="/dashboard/qa-health"
          className="flex min-h-[40px] items-center justify-between rounded-md border border-[var(--re-surface-border)] px-3 text-sm font-medium text-[var(--re-text-secondary)] transition-colors hover:border-[var(--re-brand)] hover:text-foreground"
        >
          Open QA Health
          <ArrowRight className="h-4 w-4" />
        </Link>
      </CardContent>
    </Card>
  );
}
