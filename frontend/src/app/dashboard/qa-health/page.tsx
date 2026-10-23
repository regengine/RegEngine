"use client";

import { useMemo } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  WifiOff,
  XCircle,
} from "lucide-react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ErrorState } from "@/components/ui/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/ui/stat-tile";
import { StatusBadge, type ComplianceState } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQAHealth } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth-context";
import type {
  QAHealthArtifactRef,
  QADecisionStatus,
  QAHealthCluster,
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

/* ── State vocabulary ──
   Every status below ships as a StatusBadge / Callout (icon + label), never as
   a bare colour: the compliance-state vocabulary is the only place these hues
   are allowed to appear (SPEC §1.6). */

function overallConfig(status: QAHealthStatus): { label: string; state: ComplianceState } {
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

function suiteState(status: QASuiteStatus): ComplianceState {
  switch (status) {
    case "passed":
      return "compliant";
    case "degraded":
    case "skipped":
      return "at-risk";
    case "unavailable":
      return "unknown";
    case "failed":
    default:
      return "non-compliant";
  }
}

function severityTone(severity: QASeverity): BadgeTone {
  switch (severity) {
    case "critical":
      return "danger";
    case "high":
    case "medium":
      return "warning";
    case "low":
      return "info";
    case "info":
    default:
      return "neutral";
  }
}

const DECISION_ICON = {
  passed: CheckCircle2,
  unavailable: WifiOff,
  advisory: AlertTriangle,
  blocking: XCircle,
} as const;

function decisionIcon(status: QADecisionStatus) {
  return DECISION_ICON[status as keyof typeof DECISION_ICON] ?? XCircle;
}

function decisionTone(status: QADecisionStatus) {
  if (status === "passed") return "success" as const;
  if (status === "unavailable") return "neutral" as const;
  if (status === "advisory") return "warning" as const;
  return "danger" as const;
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
    <PageContainer>
      <div aria-busy="true" className="space-y-6">
        <div className="flex items-center justify-between gap-4 border-b border-re-border-subtle pb-5">
          <div className="space-y-2">
            <Skeleton className="h-8 w-36" />
            <Skeleton className="h-4 w-72" />
          </div>
          <Skeleton className="h-9 w-32" />
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

  const clusterColumns: DataTableColumn<QAHealthCluster>[] = [
    {
      key: "title",
      header: "Cluster",
      width: "26%",
      cell: (cluster) => (
        <div className="space-y-1.5">
          <p className="break-words font-medium text-re-text-primary">{cluster.title}</p>
          <Badge tone={severityTone(cluster.severity)} size="sm" className="capitalize">
            {cluster.severity}
          </Badge>
        </div>
      ),
    },
    { key: "impact", header: "Impact", width: "23%" },
    {
      key: "affected_suites",
      header: "Suites",
      width: "13%",
      cell: (cluster) => cluster.affected_suites.join(", "),
    },
    {
      key: "owner_lane",
      header: "Owner",
      width: "14%",
      cell: (cluster) => formatOwnerLane(cluster.owner_lane),
    },
    { key: "next_action", header: "Next action", width: "24%" },
  ];

  const suiteColumns: DataTableColumn<QAHealthSuite>[] = [
    { key: "label", header: "Suite", width: "12rem" },
    {
      key: "command",
      header: "Command",
      width: "17rem",
      mono: true,
      cell: (suite) => (
        <span className="block max-w-[17rem] truncate" title={suite.command}>
          {suite.command}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "10rem",
      cell: (suite) => (
        <StatusBadge state={suiteState(suite.status)} label={suite.status} className="capitalize" />
      ),
    },
    { key: "passed", header: "Passed", align: "right", cell: (s) => s.passed.toLocaleString() },
    { key: "failed", header: "Failed", align: "right", cell: (s) => s.failed.toLocaleString() },
    { key: "skipped", header: "Skipped", align: "right", cell: (s) => s.skipped.toLocaleString() },
    { key: "errors", header: "Errors", align: "right", cell: (s) => s.errors.toLocaleString() },
    {
      key: "duration_seconds",
      header: "Duration",
      align: "right",
      mono: true,
      cell: (s) => formatDuration(s.duration_seconds),
    },
  ];

  const artifactColumns: DataTableColumn<QAHealthArtifactRef>[] = [
    { key: "label", header: "Artifact", width: "16rem" },
    {
      key: "type",
      header: "Type",
      width: "8rem",
      cell: (artifact) => <span className="uppercase">{artifact.type}</span>,
    },
    { key: "path", header: "Path", mono: true },
  ];

  if (!isHydrated) return <QAPageSkeleton />;

  if (!isSysadmin) {
    return (
      <PageContainer>
        <PageHeader
          title="Sysadmin access required"
          description="QA Health contains internal release and test-run details."
        />
      </PageContainer>
    );
  }

  if (isLoading) return <QAPageSkeleton />;

  if (error) {
    return (
      <PageContainer>
        <PageHeader title="QA health request failed" />
        <ErrorState message="We could not load this page." onRetry={() => refetch()} retrying={isRefetching} />
      </PageContainer>
    );
  }

  if (!data) return <QAPageSkeleton />;

  const config = overallConfig(data.overall.status);

  return (
    <PageContainer>
      <PageHeader
        title="QA Health"
        description={`Latest CI artifact: ${formatDate(data.generated_at)}${data.source.workflow ? ` - ${data.source.workflow}` : ""}`}
        meta={<StatusBadge state={config.state} label={config.label} />}
        secondaryActions={
          <Button
            variant="outline"
            onClick={() => refetch()}
            disabled={isRefetching}
            leadingIcon={
              <RefreshCw
                className={isRefetching ? "animate-spin motion-reduce:animate-none" : undefined}
                strokeWidth={1.75}
                aria-hidden="true"
              />
            }
          >
            Refresh
          </Button>
        }
      />

      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {summarySuites.map((suite) => (
            <StatTile
              key={suite.id}
              label={suite.label}
              value={`${suite.passed.toLocaleString()} pass`}
              status={<StatusBadge state={suiteState(suite.status)} label={suite.status} size="sm" className="capitalize" />}
            >
              <p className="text-small text-re-text-tertiary">
                {suite.failed.toLocaleString()} fail / {suite.errors.toLocaleString()} errors
              </p>
              <p className="truncate font-mono text-label text-re-text-muted" title={suite.command}>
                {suite.command}
              </p>
            </StatTile>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Card>
            <CardHeader>
              <CardTitle>Failure clusters</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <DataTable
                caption="Failure clusters in the latest QA artifact, with owner and next action"
                columns={clusterColumns}
                data={data.clusters}
                rowKey={(cluster) => cluster.title}
                empty={{ title: "No failure clusters in the latest QA artifact." }}
                minWidth="720px"
                stickyFirstColumn
                className="rounded-none border-0"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Release decision</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <div className="flex items-end justify-between gap-3">
                  <div>
                    <p className="text-title tabular-nums text-re-text-primary">
                      {data.overall.ready_percent}%
                    </p>
                    <p className="text-small text-re-text-tertiary">Ready to ship</p>
                  </div>
                  <div className="text-right text-small text-re-text-tertiary">
                    <p>{data.overall.blocking_count} blocking</p>
                    <p>{data.overall.advisory_count} advisory</p>
                  </div>
                </div>
                <div
                  className="h-2 overflow-hidden rounded-sm bg-re-surface-inset"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={data.overall.ready_percent}
                  aria-label="QA release readiness"
                >
                  <div
                    className="h-full bg-re-brand transition-all duration-180 motion-reduce:transition-none"
                    style={{ width: `${data.overall.ready_percent}%` }}
                  />
                </div>
              </div>

              <div className="space-y-3">
                {data.decision_checks.map((check) => (
                  <Callout
                    key={`${check.status}-${check.label}`}
                    tone={decisionTone(check.status)}
                    icon={decisionIcon(check.status)}
                    title={check.label}
                  >
                    {check.detail && (
                      <p className="text-small text-re-text-tertiary">{check.detail}</p>
                    )}
                  </Callout>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="suites">
          <TabsList>
            <TabsTrigger value="suites">Suites</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
            <TabsTrigger value="trends">Trends</TabsTrigger>
          </TabsList>

          <TabsContent value="suites">
            <DataTable
              caption="Every QA suite in the latest artifact with its counts and duration"
              columns={suiteColumns}
              data={data.suites}
              rowKey={(suite) => suite.id}
              empty={{ title: "No suites were reported." }}
              minWidth="880px"
              stickyFirstColumn
            />
          </TabsContent>

          <TabsContent value="artifacts">
            <Card>
              <CardHeader>
                <CardTitle>Artifact references</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <DataTable
                  caption="Artifact references included with the latest QA run"
                  columns={artifactColumns}
                  data={data.artifact_refs}
                  rowKey={(artifact) => artifact.id}
                  empty={{ title: "No artifact references were included." }}
                  minWidth="640px"
                  stickyFirstColumn
                  className="rounded-none border-0"
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="trends">
            <div className="grid gap-4 md:grid-cols-3">
              <StatTile label="Current readiness" value={`${data.overall.ready_percent}%`} />
              <StatTile label="Suites reported" value={data.suites.length} />
              <StatTile label="Source branch" value={data.source.branch || "-"} />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </PageContainer>
  );
}
