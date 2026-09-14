"use client";

import Link from "next/link";
import { experimentalFeaturesEnabled } from "@/lib/experimental-features";
import { FSMA_ENFORCEMENT_DATE } from "@/lib/fsma-enforcement";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type ComplianceState } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth-context";
import { useTenant } from "@/lib/tenant-context";
import { useSystemStatus, useSystemMetrics } from "@/hooks/use-api";
import { MetricsOverviewWidget } from "@/components/dashboard/metrics-overview-widget";
import { SystemHealthWidget } from "@/components/dashboard/system-health-widget";
import { ScanHistoryWidget } from "@/components/dashboard/scan-history-widget";
import { QAHealthWidget } from "@/components/dashboard/qa-health-widget";
import { fetchWorkbenchReadinessSummary } from "@/lib/api-hooks";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { GettingStartedCard } from "@/components/dashboard/getting-started-card";
import { useOnboardingStatus } from "@/hooks/use-onboarding";

/**
 * Dashboard overview.
 *
 * An operator opens this page every morning and after every import. The first
 * viewport answers three questions without scrolling: where do we stand, what
 * is wrong, and what do I do next. Everything else is folded into those three
 * or demoted below the fold — see SPEC §7 for the mapping of every widget that
 * used to sit up here.
 */

/** The six quick actions, unchanged in label and href — now one link row. */
const QUICK_LINKS = [
  { title: "FSMA Readiness Score", href: "/dashboard/compliance" },
  { title: "Alerts", href: "/dashboard/alerts" },
  { title: "Import Data", href: "/ingest" },
  { title: "Supplier Network", href: "/dashboard/suppliers" },
  { title: "Product Catalog", href: "/dashboard/products" },
  { title: "Recall Readiness", href: "/dashboard/recall-report" },
];

type AttentionRow = {
  id: string;
  state: ComplianceState;
  item: string;
  source: string;
  href: string;
};

function DashboardPageSkeleton() {
  return (
    <div aria-busy="true">
      <PageContainer>
        <div className="space-y-6">
          <div className="space-y-2 border-b border-re-border-subtle pb-5">
            <Skeleton className="h-8 w-44" />
            <Skeleton className="h-4 w-[min(24rem,80vw)]" />
          </div>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr]">
            <Skeleton className="h-[172px]" />
            <div className="grid gap-4 sm:grid-cols-2 lg:contents">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-[92px]" />
              ))}
            </div>
          </div>
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Skeleton className="h-[240px]" />
            <Skeleton className="h-[240px]" />
          </div>
        </div>
      </PageContainer>
    </div>
  );
}

export default function DashboardPage() {
  const { user, isHydrated } = useAuth();
  const { tenantId, isTenantReady } = useTenant();
  const router = useRouter();
  const isAuthenticated = Boolean(user);

  const effectiveUser = user;
  const effectiveTenantId = tenantId;

  // Derive the health signal from the same useSystemStatus() data the widget
  // uses — one source of truth, so the strip and the widget never contradict.
  const { data: systemStatus, isLoading: statusLoading } = useSystemStatus();
  const { data: metrics } = useSystemMetrics();

  const healthStatus = useMemo(():
    | "loading"
    | "operational"
    | "degraded"
    | "disruption" => {
    if (statusLoading && !systemStatus) return "loading";
    if (!systemStatus) return "disruption";
    const s = systemStatus.overall_status;
    if (s === "healthy") return "operational";
    if (s === "degraded") return "degraded";
    return "disruption";
  }, [systemStatus, statusLoading]);

  useEffect(() => {
    if (isHydrated && !effectiveUser) {
      router.push(`/login?next=${encodeURIComponent("/dashboard")}`);
    }
  }, [isHydrated, effectiveUser, router]);

  // Check design partner status from tenant settings. Wait for tenant
  // hydration — pre-hydration the id is the DEFAULT_TENANT_ID placeholder
  // and every cold load fired a doomed onboarding call against it.
  const { data: onboardingData } = useOnboardingStatus(isTenantReady ? effectiveTenantId : null);
  const partnerTier = onboardingData?.partner_tier as string | undefined;

  const { data: workbenchReadiness } = useQuery({
    queryKey: ["dashboard-workbench-readiness", effectiveTenantId],
    queryFn: () => fetchWorkbenchReadinessSummary(effectiveTenantId || ""),
    enabled: !!effectiveTenantId && isAuthenticated && isTenantReady,
    staleTime: 60_000,
    retry: false,
  });

  /**
   * "Needs attention" absorbs what used to be three separate red widgets: the
   * System Health service list, the QA Health blocking count, and the open-fix
   * count from the workbench. One list, sorted worst-first.
   */
  const attentionRows = useMemo<AttentionRow[]>(() => {
    const rows: AttentionRow[] = [];

    for (const service of systemStatus?.services ?? []) {
      if (service.status !== "healthy") {
        rows.push({
          id: `service-${service.name}`,
          state: "non-compliant",
          item: `${service.name} service is not responding`,
          source: "System health",
          href: "/dashboard/settings",
        });
      }
    }

    const fixes = workbenchReadiness?.unresolved_fix_count ?? 0;
    if (fixes > 0) {
      rows.push({
        id: "workbench-fixes",
        state: "needs-correction",
        item: `${fixes} unresolved ${fixes === 1 ? "fix" : "fixes"} in the Inflow Workbench`,
        source: workbenchReadiness?.source && workbenchReadiness.source !== "none"
          ? workbenchReadiness.source
          : "Inflow Workbench",
        href: "/dashboard/inflow-lab",
      });
    }

    const openAlerts = metrics?.open_alerts ?? 0;
    if (openAlerts > 0) {
      rows.push({
        id: "open-alerts",
        state: "at-risk",
        item: `${openAlerts} open compliance ${openAlerts === 1 ? "alert" : "alerts"}`,
        source: "Alerts",
        href: "/dashboard/alerts",
      });
    }

    if (metrics && (metrics.chain_length ?? 0) > 0 && !metrics.chain_valid) {
      rows.push({
        id: "chain-broken",
        state: "blocked",
        item: "Hash chain verification failed",
        source: "Evidence ledger",
        href: "/dashboard/audit-log",
      });
    }

    return rows;
  }, [systemStatus, workbenchReadiness, metrics]);

  const attentionColumns: DataTableColumn<AttentionRow>[] = [
    {
      key: "state",
      header: "Status",
      width: "12rem",
      cell: (row) => <StatusBadge state={row.state} size="sm" />,
    },
    { key: "item", header: "Item" },
    { key: "source", header: "Source", width: "12rem" },
  ];

  /** The numbered next actions, derived from what is actually wrong. */
  const nextActions = useMemo(() => {
    const actions: { label: string; href: string; cta?: string }[] = [];
    const fixes = workbenchReadiness?.unresolved_fix_count ?? 0;
    if (fixes > 0) {
      actions.push({
        label: `Resolve ${fixes} open ${fixes === 1 ? "fix" : "fixes"} in the workbench`,
        href: "/dashboard/inflow-lab",
        cta: "Open",
      });
    }
    if ((metrics?.open_alerts ?? 0) > 0) {
      actions.push({ label: "Review open compliance alerts", href: "/dashboard/alerts", cta: "Review" });
    }
    if ((metrics?.events_ingested ?? 0) === 0) {
      actions.push({ label: "Import your first traceability records", href: "/ingest", cta: "Import" });
    }
    actions.push({ label: "Run a recall drill", href: "/dashboard/recall-drills" });
    return actions.slice(0, 4);
  }, [workbenchReadiness, metrics]);

  if (!isHydrated || !effectiveUser) {
    return <DashboardPageSkeleton />;
  }

  return (
    <PageContainer>
      <PageHeader
        title="Dashboard"
        description="Welcome to RegEngine. Here's your compliance overview."
        meta={
          <>
            {partnerTier === "founding" && <Badge tone="brand">Founding Partner</Badge>}
            {healthStatus === "loading" ? (
              <StatusBadge state="in-progress" label="Checking..." size="sm" />
            ) : healthStatus === "operational" ? (
              <StatusBadge state="compliant" label="All Systems Operational" size="sm" />
            ) : healthStatus === "degraded" ? (
              <StatusBadge state="at-risk" label="Degraded Performance" size="sm" />
            ) : (
              <StatusBadge state="non-compliant" label="Services Unreachable" size="sm" />
            )}
          </>
        }
        secondaryActions={
          <Button variant="secondary" asChild>
            <Link href="/ingest">Import data</Link>
          </Button>
        }
        primaryAction={
          experimentalFeaturesEnabled() ? (
            <Button asChild>
              <Link href="/dashboard/inflow-lab">
                Open Inflow Lab
                <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-6">
        {/* One notice when the backend is unreachable, instead of a red pill in
            each of three widgets. */}
        {healthStatus === "disruption" && (
          <Callout tone="danger" role="alert" title="Backend services unreachable">
            Data will appear once services are connected.
          </Callout>
        )}

        <MetricsOverviewWidget readiness={workbenchReadiness} />

        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <section aria-labelledby="needs-attention-heading" className="space-y-3">
            <h2 id="needs-attention-heading" className="text-subheading text-re-text-primary">
              Needs attention
              {attentionRows.length > 0 && (
                <Badge tone="neutral" size="sm" className="ml-2">
                  {attentionRows.length}
                </Badge>
              )}
            </h2>
            <DataTable
              caption="Items that need attention, worst first"
              columns={attentionColumns}
              data={attentionRows}
              rowKey={(row) => row.id}
              rowHref={(row) => row.href}
              density="medium"
              minWidth="480px"
              status={attentionRows.length === 0 ? "empty" : "idle"}
              empty={{
                icon: CheckCircle2,
                title: "Nothing needs attention",
                description: "Every check you have configured is currently passing.",
                size: "sm",
              }}
            />
          </section>

          <section aria-labelledby="next-actions-heading" className="space-y-3">
            <h2 id="next-actions-heading" className="text-subheading text-re-text-primary">
              Next actions
            </h2>
            <Card>
              <ol className="divide-y divide-re-border-subtle">
                {nextActions.map((action, i) => (
                  <li key={action.href + action.label} className="flex items-start gap-3 px-4 py-3">
                    <span className="mt-0.5 font-mono text-label text-re-text-muted">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <Link
                      href={action.href}
                      className="flex-1 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-brand"
                    >
                      {action.label}
                    </Link>
                  </li>
                ))}
              </ol>
            </Card>
            <GettingStartedCard />
          </section>
        </div>

        {/* ── Below the fold ─────────────────────────────────────────────── */}

        <section aria-labelledby="go-to-heading" className="border-t border-re-border-subtle pt-5">
          <h2 id="go-to-heading" className="sr-only">
            Quick Actions
          </h2>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <span className="text-label text-re-text-muted">Go to</span>
            {QUICK_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-brand"
              >
                {link.title}
              </Link>
            ))}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <SystemHealthWidget />
          {effectiveUser.is_sysadmin && <QAHealthWidget />}
          <ScanHistoryWidget />
        </div>

        <Card variant="interactive">
          <Link href="/dashboard/heartbeat" className="block no-underline">
            <CardContent className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <p className="text-subheading text-re-text-primary">Daily Compliance Heartbeat</p>
                <p className="text-ui text-re-text-tertiary">
                  Score, alerts, chain status &amp; next actions — your morning check
                </p>
              </div>
              <ArrowRight className="h-4 w-4 shrink-0 text-re-text-muted" aria-hidden="true" />
            </CardContent>
          </Link>
        </Card>

        {experimentalFeaturesEnabled() && (
          <Card>
            <CardContent className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <p className="text-subheading text-re-text-primary">FSMA 204 Compliance</p>
                <p className="text-ui text-re-text-tertiary">
                  FDA enforcement begins {FSMA_ENFORCEMENT_DATE} • Start tracking your readiness
                </p>
              </div>
              <Button variant="secondary" asChild>
                <Link href="/fsma">
                  View FSMA Dashboard
                  <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}
