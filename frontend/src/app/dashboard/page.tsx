"use client";

import Link from "next/link";
import { experimentalFeaturesEnabled } from "@/lib/experimental-features";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageContainer } from "@/components/layout/page-container";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth-context";
import { useTenant } from "@/lib/tenant-context";
import { useSystemStatus } from "@/hooks/use-api";
import { SystemHealthWidget } from "@/components/dashboard/system-health-widget";
import { MetricsOverviewWidget } from "@/components/dashboard/metrics-overview-widget";
import { ScanHistoryWidget } from "@/components/dashboard/scan-history-widget";
import { QAHealthWidget } from "@/components/dashboard/qa-health-widget";
import { fetchWorkbenchReadinessSummary } from "@/lib/api-hooks";
import {
  Shield,
  Upload,
  Search,
  FileCheck,
  AlertTriangle,
  TrendingUp,
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  Truck,
  Settings,
  CheckCircle2,
  WifiOff,
  ClipboardCheck,
} from "lucide-react";
import { GettingStartedCard } from "@/components/dashboard/getting-started-card";
import { useOnboardingStatus } from "@/hooks/use-onboarding";

// Base quick actions (overridden by tenant type)
const getQuickActions = (tenantType: "retailer" | "supplier" | "system") => {
  const commonActions = [
    {
      title: "FSMA Readiness Score",
      description: "View your advisory readiness indicator",
      icon: Shield,
      href: "/dashboard/compliance",
      color: "text-re-brand",
      bg: "bg-re-brand-muted dark:bg-re-brand/30",
    },
    {
      title: "Alerts",
      description: "Review compliance alerts",
      icon: AlertTriangle,
      href: "/dashboard/alerts",
      color: "text-re-warning",
      bg: "bg-re-warning-muted dark:bg-re-warning/30",
    },
    {
      title: "Import Data",
      description: "Documents, CSV, and file upload",
      icon: Upload,
      href: "/ingest",
      color: "text-re-info",
      bg: "bg-re-info-muted dark:bg-re-info/30",
    },
  ];

  if (tenantType === "retailer") {
    return [
      ...commonActions,
      {
        title: "Supplier Network",
        description: "Manage supplier compliance",
        icon: Building2,
        href: "/dashboard/suppliers",
        color: "text-re-warning",
        bg: "bg-re-warning-muted dark:bg-re-warning/30",
      },
      {
        title: "Product Catalog",
        description: "Product catalog management",
        icon: FileCheck,
        href: "/dashboard/products",
        color: "text-re-text-secondary",
        bg: "bg-re-surface-elevated",
      },
      {
        title: "Recall Readiness",
        description: "Preparedness assessment",
        icon: TrendingUp,
        href: "/dashboard/recall-report",
        color: "text-re-text-secondary",
        bg: "bg-re-surface-elevated",
      },
    ];
  }

  if (tenantType === "supplier") {
    return [
      ...commonActions,
      {
        title: "Recall Readiness",
        description: "Preparedness assessment",
        icon: TrendingUp,
        href: "/dashboard/recall-report",
        color: "text-re-warning",
        bg: "bg-re-warning-muted dark:bg-re-warning/30",
      },
      {
        title: "FDA Export",
        description: "Recurring export retention",
        icon: Upload,
        href: "/dashboard/export-jobs",
        color: "text-re-brand",
        bg: "bg-re-brand-muted dark:bg-re-brand/30",
      },
      {
        title: "Audit Log",
        description: "Immutable event history",
        icon: Search,
        href: "/dashboard/audit-log",
        color: "text-re-text-secondary",
        bg: "bg-re-surface-elevated",
      },
      {
        title: "Recall Drill",
        description: "FDA recall simulation",
        icon: Truck,
        href: "/dashboard/recall-drills",
        color: "text-re-text-secondary",
        bg: "bg-re-surface-elevated",
      },
    ];
  }

  // System admin
  return [
    {
      title: "System Settings",
      description: "Manage account & integrations",
      icon: Settings,
      href: "/dashboard/settings",
      color: "text-re-info",
      bg: "bg-re-info-muted dark:bg-re-info/30",
    },
    {
      title: "Team",
      description: "Manage team members & roles",
      icon: Building2,
      href: "/dashboard/team",
      color: "text-re-brand",
      bg: "bg-re-brand-muted dark:bg-re-brand/30",
    },
    {
      title: "Audit Log",
      description: "System event history",
      icon: Activity,
      href: "/dashboard/audit-log",
      color: "text-re-text-secondary",
      bg: "bg-re-surface-elevated",
    },
    {
      title: "FDA Export",
      description: "Retention & export scheduling",
      icon: Upload,
      href: "/dashboard/export-jobs",
      color: "text-re-warning",
      bg: "bg-re-warning-muted dark:bg-re-warning/30",
    },
  ];
};

function DashboardPageSkeleton() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]" aria-busy="true">
      <PageContainer>
        <div className="space-y-6 sm:space-y-8 animate-pulse">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-2">
              <div className="h-8 w-44 rounded bg-muted" />
              <div className="h-4 w-[min(24rem,80vw)] rounded bg-muted" />
            </div>
            <div className="h-7 w-40 rounded bg-muted" />
          </div>
          <div className="h-[244px] rounded-lg bg-muted" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className="h-[210px] rounded-lg bg-muted" />
              <div className="h-[136px] rounded-lg bg-muted" />
            </div>
            <div className="space-y-6">
              <div className="h-[220px] rounded-lg bg-muted" />
              <div className="h-[260px] rounded-lg bg-muted" />
            </div>
          </div>
          <div className="space-y-4">
            <div className="h-6 w-36 rounded bg-muted" />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {[1, 2, 3].map((item) => (
                <div key={item} className="h-[96px] rounded-lg bg-muted" />
              ))}
            </div>
          </div>
          <div className="h-[116px] rounded-lg bg-muted" />
          <div className="h-[116px] rounded-lg bg-muted" />
        </div>
      </PageContainer>
    </div>
  );
}

export default function DashboardPage() {
  const { user, isHydrated, isAuthenticated } = useAuth();
  const { tenantId, isTenantReady } = useTenant();
  const router = useRouter();

  const effectiveUser = user;
  const effectiveTenantId = tenantId;

  // Fetch real service health status
  // Derive health badge from the same useSystemStatus() data the widget uses
  // — single source of truth so badge and widget never contradict.
  const { data: systemStatus, isLoading: statusLoading } = useSystemStatus();

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

  // Default to 'retailer' quick actions. (Previously derived from a Supabase
  // org-plan lookup that resolved to undefined in production — the org id
  // space never matched tenant_id — so 'retailer' is the effective behavior.)
  const quickActions = useMemo(() => {
    return getQuickActions("retailer");
  }, []);

  const { data: workbenchReadiness } = useQuery({
    queryKey: ["dashboard-workbench-readiness", effectiveTenantId],
    queryFn: () => fetchWorkbenchReadinessSummary(effectiveTenantId || ""),
    enabled: !!effectiveTenantId && isAuthenticated && isTenantReady,
    staleTime: 60_000,
    retry: false,
  });

  if (!isHydrated || !effectiveUser) {
    return <DashboardPageSkeleton />;
  }

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <PageContainer>
        <div className="space-y-6 sm:space-y-8">
          {/* Welcome Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl sm:text-3xl font-bold">Dashboard</h1>
              </div>
              <p className="text-muted-foreground mt-1">
                Welcome to RegEngine. Here&apos;s your compliance overview.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {partnerTier === "founding" && (
                <Badge
                  variant="secondary"
                  className="bg-re-surface-elevated text-re-brand border border-[var(--re-surface-border)]"
                >
                  Founding Partner
                </Badge>
              )}
              {healthStatus === "loading" ? (
                <Badge
                  variant="outline"
                  className="bg-re-surface-elevated text-re-text-muted dark:bg-re-surface-base/30 dark:text-re-text-tertiary"
                >
                  <Activity className="w-3 h-3 mr-1 animate-pulse" />
                  Checking...
                </Badge>
              ) : healthStatus === "operational" ? (
                <Badge
                  variant="outline"
                  className="bg-re-success-muted text-re-success dark:bg-re-success/30 dark:text-re-success"
                >
                  <CheckCircle2 className="w-3 h-3 mr-1" />
                  All Systems Operational
                </Badge>
              ) : healthStatus === "degraded" ? (
                <Badge
                  variant="outline"
                  className="bg-re-warning-muted text-re-warning dark:bg-re-warning/30 dark:text-re-warning"
                >
                  <AlertTriangle className="w-3 h-3 mr-1" />
                  Degraded Performance
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="bg-re-danger-muted text-re-danger dark:bg-re-danger/30 dark:text-re-danger"
                >
                  <WifiOff className="w-3 h-3 mr-1" />
                  Services Unreachable
                </Badge>
              )}
            </div>
          </div>

          {/* Getting Started (new users) */}
          <GettingStartedCard />

          {/* Operational Widgets */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <MetricsOverviewWidget />

              <Card>
                <CardContent className="pt-4 sm:pt-5 pb-4">
                  <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2.5 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                        <ClipboardCheck className="h-5 w-5 text-re-brand" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-base sm:text-lg font-semibold">
                            Traceability Readiness
                          </h2>
                          {workbenchReadiness?.export_eligible ? (
                            <Badge
                              variant="outline"
                              className="bg-re-success-muted text-re-success border-re-success"
                            >
                              Export eligible
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="bg-re-surface-elevated text-muted-foreground"
                            >
                              Not export eligible
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                          {workbenchReadiness?.label ||
                            "No saved Inflow Workbench run yet."}
                        </p>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3 sm:gap-4 xl:min-w-[320px]">
                      <div>
                        <p className="text-xl sm:text-2xl font-bold">
                          {typeof workbenchReadiness?.score === "number"
                            ? workbenchReadiness.score
                            : "—"}
                        </p>
                        <p className="text-[11px] sm:text-xs text-muted-foreground">
                          Readiness
                        </p>
                      </div>
                      <div>
                        <p className="text-xl sm:text-2xl font-bold">
                          {workbenchReadiness?.unresolved_fix_count ?? "—"}
                        </p>
                        <p className="text-[11px] sm:text-xs text-muted-foreground">
                          Open Fixes
                        </p>
                      </div>
                      <div>
                        <p className="text-xl sm:text-2xl font-bold truncate">
                          {workbenchReadiness?.source &&
                          workbenchReadiness.source !== "none"
                            ? workbenchReadiness.source
                            : "—"}
                        </p>
                        <p className="text-[11px] sm:text-xs text-muted-foreground">
                          Source
                        </p>
                      </div>
                    </div>
                    {experimentalFeaturesEnabled() && (
                      <Link href="/dashboard/inflow-lab" className="w-full xl:w-auto">
                        <Button
                          variant="outline"
                          className="min-h-[44px] w-full xl:w-auto active:scale-[0.98] transition-transform"
                        >
                          Open Inflow Lab
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="space-y-6">
              <SystemHealthWidget />
              {effectiveUser.is_sysadmin && <QAHealthWidget />}
              <ScanHistoryWidget />
            </div>
          </div>

          {/* Quick Actions - Now tenant-type specific */}
          <div>
            <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {quickActions.map((action) => (
                <div
                  key={action.href}
                >
                  <Link href={action.href}>
                    <Card className="h-full hover:border-primary/50 active:scale-[0.98] transition-all cursor-pointer group">
                      <CardContent className="pt-4 sm:pt-6 pb-4 min-h-[48px]">
                        <div className="flex items-center gap-3 sm:gap-4">
                          <div
                            className={`p-2.5 sm:p-3 rounded-sm border border-[var(--re-surface-border)] ${action.bg} flex-shrink-0`}
                          >
                            <action.icon
                              className={`h-5 w-5 sm:h-6 sm:w-6 ${action.color}`}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-semibold text-sm sm:text-base group-hover:text-primary transition-colors">
                              {action.title}
                            </h3>
                            <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 sm:mt-1 truncate">
                              {action.description}
                            </p>
                          </div>
                          <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all flex-shrink-0" />
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                </div>
              ))}
            </div>
          </div>

          {/* Daily Heartbeat CTA */}
          <Link href="/dashboard/heartbeat">
            <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)] transition-colors cursor-pointer group hover:border-[var(--re-brand)]">
              <CardContent className="pt-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                  <div className="flex items-center gap-3 sm:gap-4">
                    <div className="p-2.5 sm:p-3 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                      <Activity className="h-5 w-5 sm:h-6 sm:w-6 text-re-text-secondary" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-sm sm:text-base group-hover:text-re-info transition-colors">
                        Daily Compliance Heartbeat
                      </h3>
                      <p className="text-xs sm:text-sm text-muted-foreground">
                        Score, alerts, chain status &amp; next actions — your
                        morning check
                      </p>
                    </div>
                  </div>
                  <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-re-info group-hover:translate-x-1 transition-all" />
                </div>
              </CardContent>
            </Card>
          </Link>

          {/* FSMA 204 Deadline Banner */}
          {experimentalFeaturesEnabled() && (
          <Card className="border-[var(--re-brand)] bg-[var(--re-surface-card)]">
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="p-2.5 sm:p-3 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                    <BarChart3 className="h-5 w-5 sm:h-6 sm:w-6 text-re-brand-dark" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-sm sm:text-base">
                      FSMA 204 Compliance
                    </h3>
                    <p className="text-xs sm:text-sm text-muted-foreground">
                      FDA deadline: July 2028 • Start tracking your readiness
                    </p>
                  </div>
                </div>
                <Link href="/fsma" className="w-full sm:w-auto">
                  <Button
                    variant="outline"
                    className="min-h-[48px] w-full sm:w-auto active:scale-[0.98] transition-transform"
                  >
                    View FSMA Dashboard
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
          )}
        </div>
      </PageContainer>
    </div>
  );
}
