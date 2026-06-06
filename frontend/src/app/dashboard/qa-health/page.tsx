"use client";

import { useMemo } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  FileJson,
  RefreshCw,
  ShieldAlert,
  WifiOff,
  XCircle,
} from "lucide-react";

import { PageContainer } from "@/components/layout/page-container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQAHealth } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth-context";
import type {
  QADecisionStatus,
  QAHealthResponse,
  QAHealthStatus,
  QAHealthSuite,
  QASeverity,
  QASuiteStatus,
} from "@/types/api";

const SUMMARY_SUITE_ORDER = [
  "backend-pytest",
  "frontend-vitest",
  "frontend-e2e",
  "frontend-install",
];

function overallConfig(status: QAHealthStatus) {
  switch (status) {
    case "passing":
      return {
        label: "Release gate passing",
        badge: "bg-re-success-muted text-re-success border-re-success/40",
        icon: CheckCircle2,
      };
    case "degraded":
      return {
        label: "Advisory issues",
        badge: "bg-re-warning-muted text-re-warning border-re-warning/40",
        icon: AlertTriangle,
      };
    case "unavailable":
      return {
        label: "QA signal unavailable",
        badge: "bg-re-surface-elevated text-muted-foreground border-[var(--re-surface-border)]",
        icon: WifiOff,
      };
    case "invalid_artifact":
      return {
        label: "QA artifact invalid",
        badge: "bg-re-danger-muted text-re-danger border-re-danger/40",
        icon: ShieldAlert,
      };
    case "failing":
    default:
      return {
        label: "Release gate failing",
        badge: "bg-re-danger-muted text-re-danger border-re-danger/40",
        icon: ShieldAlert,
      };
  }
}

function suiteTone(status: QASuiteStatus) {
  switch (status) {
    case "passed":
      return "text-re-success";
    case "degraded":
    case "skipped":
      return "text-re-warning";
    case "unavailable":
      return "text-muted-foreground";
    case "failed":
    default:
      return "text-re-danger";
  }
}

function severityBadge(severity: QASeverity) {
  switch (severity) {
    case "critical":
      return "bg-re-danger-muted text-re-danger border-re-danger/40";
    case "high":
      return "bg-orange-500/10 text-orange-400 border-orange-500/40";
    case "medium":
      return "bg-re-warning-muted text-re-warning border-re-warning/40";
    case "low":
      return "bg-re-info-muted text-re-info border-re-info/40";
    case "info":
    default:
      return "bg-re-surface-elevated text-muted-foreground border-[var(--re-surface-border)]";
  }
}

function decisionIcon(status: QADecisionStatus) {
  if (status === "passed") return CheckCircle2;
  if (status === "unavailable") return WifiOff;
  if (status === "advisory") return AlertTriangle;
  return XCircle;
}

function decisionTone(status: QADecisionStatus) {
  if (status === "passed") return "text-re-success";
  if (status === "unavailable") return "text-muted-foreground";
  if (status === "advisory") return "text-re-warning";
  return "text-re-danger";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(value: number | null) {
  if (value == null) return "-";
  if (value >= 60) return `${(value / 60).toFixed(1)}m`;
  return `${value.toFixed(1)}s`;
}

function formatOwnerLane(value: string) {
  if (value.toLowerCase() === "qa") return "QA";
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function suiteById(data: QAHealthResponse, id: string): QAHealthSuite | undefined {
  return data.suites.find((suite) => suite.id === id);
}

function QAPageSkeleton() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]" aria-busy="true">
      <PageContainer>
        <div className="space-y-6 animate-pulse">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-2">
              <Skeleton className="h-8 w-36" />
              <Skeleton className="h-4 w-72" />
            </div>
            <Skeleton className="h-10 w-32" />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[1, 2, 3, 4].map((item) => (
              <Skeleton key={item} className="h-[132px] w-full" />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <Skeleton className="h-[360px] w-full" />
            <Skeleton className="h-[360px] w-full" />
          </div>
        </div>
      </PageContainer>
    </div>
  );
}

export default function QAHealthPage() {
  const { user, isHydrated } = useAuth();
  const isSysadmin = Boolean(user?.is_sysadmin);
  const { data, isLoading, error, refetch, isRefetching } = useQAHealth(isSysadmin);

  const summarySuites = useMemo(() => {
    if (!data) return [];
    const ordered = SUMMARY_SUITE_ORDER
      .map((id) => suiteById(data, id))
      .filter((suite): suite is QAHealthSuite => Boolean(suite));
    const remaining = data.suites.filter((suite) => !SUMMARY_SUITE_ORDER.includes(suite.id));
    return [...ordered, ...remaining].slice(0, 4);
  }, [data]);

  if (!isHydrated) return <QAPageSkeleton />;

  if (!isSysadmin) {
    return (
      <div className="min-h-screen bg-[var(--re-surface-base)]">
        <PageContainer>
          <Card>
            <CardContent className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
              <ShieldAlert className="h-8 w-8 text-re-warning" />
              <div>
                <h1 className="text-xl font-semibold">Sysadmin access required</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  QA Health contains internal release and test-run details.
                </p>
              </div>
            </CardContent>
          </Card>
        </PageContainer>
      </div>
    );
  }

  if (isLoading) return <QAPageSkeleton />;

  if (error && !data) {
    return (
      <div className="min-h-screen bg-[var(--re-surface-base)]">
        <PageContainer>
          <Card>
            <CardContent className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
              <WifiOff className="h-8 w-8 text-re-danger" />
              <div>
                <h1 className="text-xl font-semibold">QA health request failed</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  The sysadmin QA endpoint did not return a dashboard summary.
                </p>
              </div>
              <Button onClick={() => refetch()} variant="outline">
                <RefreshCw className="mr-2 h-4 w-4" />
                Retry
              </Button>
            </CardContent>
          </Card>
        </PageContainer>
      </div>
    );
  }

  if (!data) return <QAPageSkeleton />;

  const config = overallConfig(data.overall.status);
  const OverallIcon = config.icon;

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <PageContainer>
        <div className="space-y-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold sm:text-3xl">QA Health</h1>
                <Badge variant="outline" className={config.badge}>
                  <OverallIcon className="mr-1 h-3.5 w-3.5" />
                  {config.label}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Latest CI artifact: {formatDate(data.generated_at)}
                {data.source.workflow ? ` - ${data.source.workflow}` : ""}
              </p>
            </div>
            <Button
              variant="outline"
              className="min-h-[40px] w-full sm:w-auto"
              onClick={() => refetch()}
              disabled={isRefetching}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isRefetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {summarySuites.map((suite) => (
              <Card key={suite.id}>
                <CardContent className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">{suite.label}</p>
                    <Badge variant="outline" className={`capitalize ${suiteTone(suite.status)}`}>
                      {suite.status}
                    </Badge>
                  </div>
                  <div>
                    <p className={`text-2xl font-bold tabular-nums ${suiteTone(suite.status)}`}>
                      {suite.passed.toLocaleString()} pass
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {suite.failed.toLocaleString()} fail / {suite.errors.toLocaleString()} errors
                    </p>
                  </div>
                  <p className="truncate font-mono text-[11px] text-muted-foreground" title={suite.command}>
                    {suite.command}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ClipboardList className="h-4 w-4 text-re-brand" />
                  Failure clusters
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.clusters.length === 0 ? (
                  <div className="flex min-h-[180px] items-center justify-center border border-[var(--re-surface-border)] text-sm text-muted-foreground">
                    No failure clusters in the latest QA artifact.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <Table className="table-fixed">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[26%]">Cluster</TableHead>
                        <TableHead className="w-[23%]">Impact</TableHead>
                        <TableHead className="w-[13%]">Suites</TableHead>
                        <TableHead className="w-[14%]">Owner</TableHead>
                        <TableHead className="w-[24%]">Next action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.clusters.map((cluster) => (
                        <TableRow key={cluster.title}>
                          <TableCell className="align-top">
                            <div className="space-y-1">
                              <p className="break-words font-semibold">{cluster.title}</p>
                              <Badge variant="outline" className={`capitalize ${severityBadge(cluster.severity)}`}>
                                {cluster.severity}
                              </Badge>
                            </div>
                          </TableCell>
                          <TableCell className="break-words align-top text-sm text-muted-foreground">
                            {cluster.impact}
                          </TableCell>
                          <TableCell className="break-words align-top text-xs text-muted-foreground">
                            {cluster.affected_suites.join(", ")}
                          </TableCell>
                          <TableCell className="whitespace-nowrap align-top text-sm">
                            {formatOwnerLane(cluster.owner_lane)}
                          </TableCell>
                          <TableCell className="break-words align-top text-sm">{cluster.next_action}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity className="h-4 w-4 text-re-brand" />
                  Release decision
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-2">
                  <div className="flex items-end justify-between gap-3">
                    <div>
                      <p className="text-3xl font-bold tabular-nums">
                        {data.overall.ready_percent}%
                      </p>
                      <p className="text-xs text-muted-foreground">Ready to ship</p>
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      <p>{data.overall.blocking_count} blocking</p>
                      <p>{data.overall.advisory_count} advisory</p>
                    </div>
                  </div>
                  <div
                    className="h-2 overflow-hidden rounded-sm bg-[var(--re-surface-elevated)]"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={data.overall.ready_percent}
                    aria-label="QA release readiness"
                  >
                    <div
                      className="h-full bg-[var(--re-brand)] transition-all"
                      style={{ width: `${data.overall.ready_percent}%` }}
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  {data.decision_checks.map((check) => {
                    const Icon = decisionIcon(check.status);
                    return (
                      <div
                        key={`${check.status}-${check.label}`}
                        className="flex min-h-[48px] items-start gap-3 border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-3"
                      >
                        <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${decisionTone(check.status)}`} />
                        <div className="min-w-0">
                          <p className="text-sm font-medium">{check.label}</p>
                          {check.detail && (
                            <p className="mt-0.5 text-xs text-muted-foreground">{check.detail}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          <Tabs defaultValue="suites" className="space-y-3">
            <TabsList className="h-10 rounded-md">
              <TabsTrigger value="suites">Suites</TabsTrigger>
              <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
              <TabsTrigger value="trends">Trends</TabsTrigger>
            </TabsList>

            <TabsContent value="suites">
              <Card>
                <CardContent className="overflow-x-auto p-0">
                  <Table className="min-w-[760px]">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Suite</TableHead>
                        <TableHead>Command</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Passed</TableHead>
                        <TableHead>Failed</TableHead>
                        <TableHead>Skipped</TableHead>
                        <TableHead>Errors</TableHead>
                        <TableHead>Duration</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.suites.map((suite) => (
                        <TableRow key={suite.id}>
                          <TableCell className="font-medium">{suite.label}</TableCell>
                          <TableCell className="max-w-[280px] truncate font-mono text-xs text-muted-foreground">
                            {suite.command}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`capitalize ${suiteTone(suite.status)}`}>
                              {suite.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="tabular-nums">{suite.passed.toLocaleString()}</TableCell>
                          <TableCell className="tabular-nums">{suite.failed.toLocaleString()}</TableCell>
                          <TableCell className="tabular-nums">{suite.skipped.toLocaleString()}</TableCell>
                          <TableCell className="tabular-nums">{suite.errors.toLocaleString()}</TableCell>
                          <TableCell className="tabular-nums">{formatDuration(suite.duration_seconds)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="artifacts">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FileJson className="h-4 w-4 text-re-brand" />
                    Artifact references
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.artifact_refs.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No artifact references were included.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <Table className="min-w-[640px]">
                      <TableHeader>
                        <TableRow>
                          <TableHead>Artifact</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Path</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.artifact_refs.map((artifact) => (
                          <TableRow key={artifact.id}>
                            <TableCell className="font-medium">{artifact.label}</TableCell>
                            <TableCell className="uppercase text-xs text-muted-foreground">
                              {artifact.type}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-muted-foreground">
                              {artifact.path}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="trends">
              <Card>
                <CardContent className="grid gap-4 p-4 md:grid-cols-3">
                  <div>
                    <p className="text-2xl font-bold tabular-nums">{data.overall.ready_percent}%</p>
                    <p className="text-xs text-muted-foreground">Current readiness</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold tabular-nums">{data.suites.length}</p>
                    <p className="text-xs text-muted-foreground">Suites reported</p>
                  </div>
                  <div>
                    <p className="truncate text-2xl font-bold">{data.source.branch || "-"}</p>
                    <p className="text-xs text-muted-foreground">Source branch</p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </PageContainer>
    </div>
  );
}
