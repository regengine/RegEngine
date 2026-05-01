"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageContainer } from "@/components/layout/page-container";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth-context";
import { useTenant } from "@/lib/tenant-context";
import { useOrganizations } from "@/hooks/use-organizations";
import { useSystemStatus, useSystemMetrics } from "@/hooks/use-api";
import { SystemHealthWidget } from "@/components/dashboard/system-health-widget";
import { MetricsOverviewWidget } from "@/components/dashboard/metrics-overview-widget";
import { ScanHistoryWidget } from "@/components/dashboard/scan-history-widget";
import { fetchWorkbenchReadinessSummary } from "@/lib/api-hooks";
import {
  Shield,
  Upload,
  Search,
  FileCheck,
  AlertTriangle,
  TrendingUp,
  Activity,
  Clock,
  ArrowRight,
  Archive,
  BarChart3,
  Building2,
  FlaskConical,
  Link2,
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
      title: "Compliance Score",
      description: "View your compliance grade",
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
        title: "Archive Jobs",
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
        title: "Mock Drill",
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
      title: "Archive Jobs",
      description: "Retention & export scheduling",
      icon: Upload,
      href: "/dashboard/export-jobs",
      color: "text-re-warning",
      bg: "bg-re-warning-muted dark:bg-re-warning/30",
    },
  ];
};

const DATA_INFLOW_ENTRY_POINTS = [
  {
    title: "Import files",
    description:
      "Use for regulatory documents, CSV files, and normal customer uploads that need parsing and curation.",
    href: "/ingest",
    icon: Upload,
    color: "text-re-info",
    bg: "bg-re-info-muted dark:bg-re-info/30",
  },
  {
    title: "Inflow Lab",
    description:
      "Use for FSMA 204 event simulation, webhook contract checks, and tagged demo traffic.",
    href: "/dashboard/inflow-lab",
    icon: FlaskConical,
    color: "text-re-brand",
    bg: "bg-re-brand-muted dark:bg-re-brand/30",
  },
  {
    title: "Integrations",
    description:
      "Use to confirm connector readiness, mapping exceptions, and customer-visible support claims.",
    href: "/dashboard/integrations",
    icon: Link2,
    color: "text-re-warning",
    bg: "bg-re-warning-muted dark:bg-re-warning/30",
  },
  {
    title: "FDA Export",
    description:
      "Use after data is curated and ready for recall, archive, or regulator response packages.",
    href: "/dashboard/export-jobs",
    icon: Archive,
    color: "text-re-text-secondary",
    bg: "bg-re-surface-elevated",
  },
];

export default function DashboardPage() {
  const { user, isHydrated, apiKey } = useAuth();
  const { tenantId } = useTenant();
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

  // Get the current org from Supabase
  const { organizations } = useOrganizations();
  const currentOrg = organizations.find(
    (o) => o.id === (effectiveTenantId || tenantId),
  );

  // Fetch real system metrics from backend
  const { data: systemMetrics } = useSystemMetrics();

  // Check design partner status from tenant settings
  const { data: onboardingData } = useOnboardingStatus(effectiveTenantId);
  const partnerTier = onboardingData?.partner_tier as string | undefined;

  // Derive tenant type from org plan or default to 'retailer'
  // Organization type is not in the schema yet, so use plan as a heuristic
  const tenantType = useMemo((): "retailer" | "supplier" | "system" => {
    if (currentOrg?.plan === "system" || currentOrg?.plan === "admin")
      return "system";
    if (currentOrg?.plan === "supplier") return "supplier";
    return "retailer";
  }, [currentOrg?.plan]);
  const quickActions = useMemo(() => {
    return getQuickActions(tenantType);
  }, [tenantType]);

  // Fetch pending reviews count from backend via proxy
  const { data: pendingReviewsData } = useQuery({
    queryKey: ["pending-reviews", effectiveTenantId],
    queryFn: async () => {
      const res = await fetch(
        `/api/ingestion/api/v1/compliance/pending-reviews/${effectiveTenantId}`,
        {
          headers: {
            "Content-Type": "application/json",
            "X-RegEngine-API-Key": apiKey!,
          },
        },
      );
      if (!res.ok) return null;
      return res.json();
    },
    enabled: !!effectiveTenantId && !!apiKey,
  });
  const pendingReviews = pendingReviewsData?.pending_reviews ?? 0;

  const { data: workbenchReadiness } = useQuery({
    queryKey: ["dashboard-workbench-readiness", effectiveTenantId],
    queryFn: () =>
      fetchWorkbenchReadinessSummary(effectiveTenantId || "", apiKey || ""),
    enabled: !!effectiveTenantId && !!apiKey,
    staleTime: 60_000,
  });

  // Use real metrics from backend when available, fall back to zeros from hook
  const metrics = useMemo(() => {
    if (systemMetrics) {
      return {
        documentsIngested:
          systemMetrics.events_ingested ?? systemMetrics.total_documents ?? 0,
        complianceScore: systemMetrics.compliance_score ?? 0,
        openAlerts: systemMetrics.open_alerts ?? 0,
        pendingReviews,
      };
    }
    return {
      documentsIngested: 0,
      complianceScore: 0,
      openAlerts: 0,
      pendingReviews,
    };
  }, [systemMetrics, pendingReviews]);

  if (!isHydrated || !effectiveUser) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6 sm:space-y-8"
        >
          {/* Welcome Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl sm:text-3xl font-bold">Dashboard</h1>
              </div>
              <p className="text-muted-foreground mt-1">
                {currentOrg
                  ? `Welcome, ${currentOrg.name}. Here's your compliance overview.`
                  : "Welcome to RegEngine. Here's your compliance overview."}
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
              {currentOrg?.plan && currentOrg.plan !== "free" && (
                <Badge
                  variant="secondary"
                  className="bg-re-surface-elevated text-re-warning border border-[var(--re-surface-border)]"
                >
                  {currentOrg.plan.charAt(0).toUpperCase() +
                    currentOrg.plan.slice(1)}
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
                    <Link href="/dashboard/inflow-lab" className="w-full xl:w-auto">
                      <Button
                        variant="outline"
                        className="min-h-[44px] w-full xl:w-auto active:scale-[0.98] transition-transform"
                      >
                        Open Inflow Lab
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="space-y-6">
              <SystemHealthWidget />
              <ScanHistoryWidget />
            </div>
          </div>

          {/* Quick Stats - Now tenant-specific */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            <Card>
              <CardContent className="pt-4 sm:pt-6 pb-4">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="p-1.5 sm:p-2 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                    <FileCheck className="h-4 w-4 sm:h-5 sm:w-5 text-re-info" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xl sm:text-2xl font-bold truncate">
                      {metrics.documentsIngested > 0
                        ? metrics.documentsIngested.toLocaleString()
                        : "—"}
                    </p>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">
                      Documents Ingested
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 sm:pt-6 pb-4">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="p-1.5 sm:p-2 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                    <Shield className="h-4 w-4 sm:h-5 sm:w-5 text-re-brand" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xl sm:text-2xl font-bold truncate">
                      {metrics.complianceScore > 0
                        ? `${metrics.complianceScore}%`
                        : "—"}
                    </p>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">
                      Compliance Score
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 sm:pt-6 pb-4">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="p-1.5 sm:p-2 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                    <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-re-warning" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xl sm:text-2xl font-bold">
                      {metrics.openAlerts}
                    </p>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">
                      Open Alerts
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 sm:pt-6 pb-4">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="p-1.5 sm:p-2 rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                    <Clock className="h-4 w-4 sm:h-5 sm:w-5 text-re-text-secondary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xl sm:text-2xl font-bold truncate">
                      {metrics.pendingReviews > 0
                        ? metrics.pendingReviews
                        : "—"}
                    </p>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">
                      Pending Reviews
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Quick Actions - Now tenant-type specific */}
          <div>
            <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {quickActions.map((action, index) => (
                <motion.div
                  key={action.href}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
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
                </motion.div>
              ))}
            </div>
          </div>

          <div>
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-4">
              <div>
                <h2 className="text-xl font-semibold">Intake</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Choose the path by source: import for customer files, Inflow
                  Lab for simulated FSMA events, integrations for connector
                  status, export for FDA packages.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
              {DATA_INFLOW_ENTRY_POINTS.map((entry) => (
                <Link
                  key={entry.href}
                  href={entry.href}
                  aria-label={`Open ${entry.title}`}
                >
                  <Card className="h-full hover:border-primary/50 active:scale-[0.98] transition-all cursor-pointer group">
                    <CardContent className="pt-4 sm:pt-5 pb-4 min-h-[156px] flex flex-col">
                      <div className="flex items-start gap-3">
                        <div
                          className={`p-2.5 rounded-sm border border-[var(--re-surface-border)] ${entry.bg} flex-shrink-0`}
                        >
                          <entry.icon className={`h-5 w-5 ${entry.color}`} />
                        </div>
                        <div className="min-w-0">
                          <h3 className="font-semibold text-sm sm:text-base group-hover:text-primary transition-colors">
                            {entry.title}
                          </h3>
                          <p className="text-xs sm:text-sm text-muted-foreground mt-1 leading-relaxed">
                            {entry.description}
                          </p>
                        </div>
                      </div>
                      <div className="mt-auto pt-4 flex items-center text-xs font-medium text-primary">
                        Open
                        <ArrowRight className="ml-1.5 h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" />
                      </div>
                    </CardContent>
                  </Card>
                </Link>
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
        </motion.div>
      </PageContainer>
    </div>
  );
}
