import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { TimedSkeleton } from "@/components/ui/timed-skeleton";
import { QA_TIMEOUT_MESSAGE, useQASignal } from "@/hooks/use-qa-signal";

/**
 * QA Health card. Status, label and figures all come from useQASignal(), the
 * same selector the dashboard's "Needs attention" panel reads, so the two can
 * never contradict each other. Unknown figures render as unknown, not 0.
 */
export function QAHealthWidget() {
  const qa = useQASignal();

  if (qa.status === "disabled") return null;

  if (qa.status === "loading") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>QA Health</CardTitle>
        </CardHeader>
        <CardContent>
          <TimedSkeleton onRetry={() => void qa.refetch()} errorMessage={QA_TIMEOUT_MESSAGE}>
            <div className="space-y-3">
              <Skeleton className="h-7 w-36" />
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          </TimedSkeleton>
        </CardContent>
      </Card>
    );
  }

  const readyPercent = qa.readyPercent;

  return (
    <Card>
      <CardHeader>
        <CardTitle>QA Health</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusBadge state={qa.state} label={qa.label} size="sm" />
          <span className="text-small tabular-nums text-re-text-tertiary">
            {readyPercent === null ? "Readiness unknown" : `${readyPercent}% ready`}
          </span>
        </div>

        {readyPercent !== null && (
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
        )}

        {qa.status === "failed" ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" size="sm" onClick={() => void qa.refetch()}>
              Retry
            </Button>
            <a href="/settings/support" className="text-small underline">
              Contact support
            </a>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-title tabular-nums text-re-text-primary">{qa.blockingCount ?? "Unknown"}</p>
              <p className="text-label text-re-text-muted">Blocking</p>
            </div>
            <div>
              <p className="text-title tabular-nums text-re-text-primary">{qa.advisoryCount ?? "Unknown"}</p>
              <p className="text-label text-re-text-muted">Advisory</p>
            </div>
          </div>
        )}

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
