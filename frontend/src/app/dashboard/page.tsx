'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useOrganizations } from '@/hooks/use-organizations';
import { useSystemStatus, useSystemMetrics } from '@/hooks/use-api';
import { SystemHealthWidget } from '@/components/dashboard/system-health-widget';
import { MetricsOverviewWidget } from '@/components/dashboard/metrics-overview-widget';
import { ScanHistoryWidget } from '@/components/dashboard/scan-history-widget';
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
    BarChart3,
    Building2,
    Truck,
    Settings,
    CheckCircle2,
    WifiOff,
} from 'lucide-react';
import { GettingStartedCard } from '@/components/dashboard/getting-started-card';

// Base quick actions (overridden by tenant type)
const getQuickActions = (tenantType: 'retailer' | 'supplier' | 'system') => {
    const commonActions = [
        {
            title: 'Compliance Score',
            description: 'View your compliance grade',
            icon: Shield,
            href: '/dashboard/compliance',
            color: 'text-re-brand',
            bg: 'bg-re-brand-muted dark:bg-re-brand/30',
        },
        {
            title: 'Alerts',
            description: 'Review compliance alerts',
            icon: AlertTriangle,
            href: '/dashboard/alerts',
            color: 'text-re-warning',
            bg: 'bg-re-warning-muted dark:bg-re-warning/30',
        },
        {
            title: 'Import Data',
            description: 'CSV, IoT, or API ingestion',
            icon: Upload,
            href: '/tools/data-import',
            color: 'text-re-info',
            bg: 'bg-re-info-muted dark:bg-re-info/30',
        },
    ];

    if (tenantType === 'retailer') {
        return [
            ...commonActions,
            {
                title: 'Supplier Network',
                description: 'Manage supplier compliance',
                icon: Building2,
                href: '/dashboard/suppliers',
                color: 'text-re-warning',
                bg: 'bg-re-warning-muted dark:bg-re-warning/30',
            },
            {
                title: 'Product Catalog',
                description: 'Product catalog management',
                icon: FileCheck,
                href: '/dashboard/products',
                color: 'text-purple-500',
                bg: 'bg-purple-100 dark:bg-purple-900/30',
            },
            {
                title: 'Recall Readiness',
                description: 'Preparedness assessment',
                icon: TrendingUp,
                href: '/dashboard/recall-report',
                color: 'text-indigo-500',
                bg: 'bg-indigo-100 dark:bg-indigo-900/30',
            },
        ];
    }

    if (tenantType === 'supplier') {
        return [
            ...commonActions,
            {
                title: 'Recall Readiness',
                description: 'Preparedness assessment',
                icon: TrendingUp,
                href: '/dashboard/recall-report',
                color: 'text-re-warning',
                bg: 'bg-re-warning-muted dark:bg-re-warning/30',
            },
            {
                title: 'Archive Jobs',
                description: 'Recurring export retention',
                icon: Upload,
                href: '/dashboard/export-jobs',
                color: 'text-re-brand',
                bg: 'bg-re-brand-muted dark:bg-re-brand/30',
            },
            {
                title: 'Audit Log',
                description: 'Immutable event history',
                icon: Search,
                href: '/dashboard/audit-log',
                color: 'text-rose-500',
                bg: 'bg-rose-100 dark:bg-rose-900/30',
            },
            {
                title: 'Mock Drill',
                description: 'FDA recall simulation',
                icon: Truck,
                href: '/dashboard/recall-drills',
                color: 'text-indigo-500',
                bg: 'bg-indigo-100 dark:bg-indigo-900/30',
            },
        ];
    }

    // System admin
    return [
        {
            title: 'System Settings',
            description: 'Manage account & integrations',
            icon: Settings,
            href: '/dashboard/settings',
            color: 'text-re-info',
            bg: 'bg-re-info-muted dark:bg-re-info/30',
        },
        {
            title: 'Team',
            description: 'Manage team members & roles',
            icon: Building2,
            href: '/dashboard/team',
            color: 'text-re-brand',
            bg: 'bg-re-brand-muted dark:bg-re-brand/30',
        },
        {
            title: 'Audit Log',
            description: 'System event history',
            icon: Activity,
            href: '/dashboard/audit-log',
            color: 'text-purple-500',
            bg: 'bg-purple-100 dark:bg-purple-900/30',
        },
        {
            title: 'Archive Jobs',
            description: 'Retention & export scheduling',
            icon: Upload,
            href: '/dashboard/export-jobs',
            color: 'text-re-warning',
            bg: 'bg-re-warning-muted dark:bg-re-warning/30',
        },
    ];
};

export default function DashboardPage() {
    const { user, isHydrated, apiKey } = useAuth()
    const { tenantId } = useTenant();
    const router = useRouter();

    const effectiveUser = user;
    const effectiveTenantId = tenantId;

    // Fetch real service health status
    const [healthStatus, setHealthStatus] = useState<'loading' | 'operational' | 'degraded' | 'disruption'>('loading');
    useEffect(() => {
        fetch('/api/health')
            .then((res) => {
                if (!res.ok) { setHealthStatus('disruption'); return; }
                return res.json();
            })
            .then((data: { status?: string; overall_status?: string } | undefined) => {
                if (!data) return;
                const s = data.overall_status ?? data.status ?? 'unknown';
                if (s === 'healthy' || s === 'ok' || s === 'up') setHealthStatus('operational');
                else if (s === 'degraded') setHealthStatus('degraded');
                else setHealthStatus('disruption');
            })
            .catch(() => setHealthStatus('disruption'));
    }, []);

    useEffect(() => {
        if (isHydrated && !effectiveUser) {
            router.push(`/login?next=${encodeURIComponent('/dashboard')}`);
        }
    }, [isHydrated, effectiveUser, router]);

    // Get the current org from Supabase
    const { organizations } = useOrganizations();
    const currentOrg = organizations.find(o => o.id === (effectiveTenantId || tenantId));

    // Fetch real system metrics from backend
    const { data: systemMetrics } = useSystemMetrics();

    // Derive tenant type from org plan or default to 'retailer'
    // Organization type is not in the schema yet, so use plan as a heuristic
    const tenantType = useMemo((): 'retailer' | 'supplier' | 'system' => {
        if (currentOrg?.plan === 'system' || currentOrg?.plan === 'admin') return 'system';
        if (currentOrg?.plan === 'supplier') return 'supplier';
        return 'retailer';
    }, [currentOrg?.plan]);
    const quickActions = useMemo(() => {
        return getQuickActions(tenantType);
    }, [tenantType]);

    // Fetch pending reviews count from backend via proxy
    const { data: pendingReviewsData } = useQuery({
        queryKey: ['pending-reviews', effectiveTenantId],
        queryFn: async () => {
            const res = await fetch(`/api/ingestion/api/v1/compliance/pending-reviews/${effectiveTenantId}`, {
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': apiKey!,
                },
            });
            if (!res.ok) return null;
            return res.json();
        },
        enabled: !!effectiveTenantId && !!apiKey,
    });
    const pendingReviews = pendingReviewsData?.pending_reviews ?? 0;

    // Use real metrics from backend when available, fall back to demo data from hook
    const metrics = useMemo(() => {
        if (systemMetrics) {
            return {
                documentsIngested: systemMetrics.events_ingested ?? systemMetrics.total_documents ?? 0,
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
    const isDemo = !!(systemMetrics as unknown as Record<string, unknown>)?._demo;

    if (!isHydrated || !effectiveUser) {
        return null;
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
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
                                    : 'Welcome to RegEngine. Here\'s your compliance overview.'
                                }
                            </p>
                        </div>
                        <div className="flex items-center gap-2">
                            {currentOrg?.plan && currentOrg.plan !== 'free' && (
                                <Badge variant="secondary" className="bg-gradient-to-r from-amber-100 to-orange-100 text-re-warning dark:from-amber-900/30 dark:to-orange-900/30 dark:text-re-warning">
                                    {currentOrg.plan.charAt(0).toUpperCase() + currentOrg.plan.slice(1)}
                                </Badge>
                            )}
                            {healthStatus === 'loading' ? (
                                <Badge variant="outline" className="bg-re-surface-elevated text-re-text-muted dark:bg-re-surface-base/30 dark:text-re-text-tertiary">
                                    <Activity className="w-3 h-3 mr-1 animate-pulse" />
                                    Checking...
                                </Badge>
                            ) : healthStatus === 'operational' ? (
                                <Badge variant="outline" className="bg-re-success-muted text-re-success dark:bg-re-success/30 dark:text-re-success">
                                    <CheckCircle2 className="w-3 h-3 mr-1" />
                                    All Systems Operational
                                </Badge>
                            ) : healthStatus === 'degraded' ? (
                                <Badge variant="outline" className="bg-re-warning-muted text-re-warning dark:bg-re-warning/30 dark:text-re-warning">
                                    <AlertTriangle className="w-3 h-3 mr-1" />
                                    Degraded Performance
                                </Badge>
                            ) : isDemo ? (
                                <Badge variant="outline" className="bg-re-warning-muted text-re-warning dark:bg-re-warning/30 dark:text-re-warning">
                                    <Activity className="w-3 h-3 mr-1" />
                                    Demo Mode
                                </Badge>
                            ) : (
                                <Badge variant="outline" className="bg-re-danger-muted text-re-danger dark:bg-re-danger/30 dark:text-re-danger">
                                    <WifiOff className="w-3 h-3 mr-1" />
                                    Service Disruption
                                </Badge>
                            )}
                        </div>
                    </div>

                    {/* Getting Started (new users) */}
                    <GettingStartedCard />

                    {/* Operational Widgets */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2">
                            <MetricsOverviewWidget />
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
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-re-info-muted dark:bg-re-info/30 flex-shrink-0">
                                        <FileCheck className="h-4 w-4 sm:h-5 sm:w-5 text-re-info" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xl sm:text-2xl font-bold truncate">
                                            {metrics.documentsIngested > 0
                                                ? metrics.documentsIngested.toLocaleString()
                                                : '—'}
                                        </p>
                                        <p className="text-[11px] sm:text-xs text-muted-foreground">Documents Ingested</p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-4 sm:pt-6 pb-4">
                                <div className="flex items-center gap-2 sm:gap-3">
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-re-brand-muted dark:bg-re-brand/30 flex-shrink-0">
                                        <Shield className="h-4 w-4 sm:h-5 sm:w-5 text-re-brand" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xl sm:text-2xl font-bold truncate">
                                            {metrics.complianceScore > 0
                                                ? `${metrics.complianceScore}%`
                                                : '—'}
                                        </p>
                                        <p className="text-[11px] sm:text-xs text-muted-foreground">Compliance Score</p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-4 sm:pt-6 pb-4">
                                <div className="flex items-center gap-2 sm:gap-3">
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-re-warning-muted dark:bg-re-warning/30 flex-shrink-0">
                                        <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-re-warning" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xl sm:text-2xl font-bold">{metrics.openAlerts}</p>
                                        <p className="text-[11px] sm:text-xs text-muted-foreground">Open Alerts</p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-4 sm:pt-6 pb-4">
                                <div className="flex items-center gap-2 sm:gap-3">
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex-shrink-0">
                                        <Clock className="h-4 w-4 sm:h-5 sm:w-5 text-purple-500" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xl sm:text-2xl font-bold truncate">
                                            {metrics.pendingReviews > 0
                                                ? metrics.pendingReviews
                                                : '—'}
                                        </p>
                                        <p className="text-[11px] sm:text-xs text-muted-foreground">Pending Reviews</p>
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
                                        <Card className="h-full hover:border-primary/50 hover:shadow-md active:scale-[0.98] transition-all cursor-pointer group">
                                            <CardContent className="pt-4 sm:pt-6 pb-4 min-h-[48px]">
                                                <div className="flex items-center gap-3 sm:gap-4">
                                                    <div className={`p-2.5 sm:p-3 rounded-lg ${action.bg} flex-shrink-0`}>
                                                        <action.icon className={`h-5 w-5 sm:h-6 sm:w-6 ${action.color}`} />
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



                    {/* Daily Heartbeat CTA */}
                    <Link href="/dashboard/heartbeat">
                        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-blue-200 dark:border-blue-800 hover:shadow-md transition-shadow cursor-pointer group">
                            <CardContent className="pt-6">
                                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                                    <div className="flex items-center gap-3 sm:gap-4">
                                        <div className="p-2.5 sm:p-3 rounded-lg bg-white dark:bg-re-surface-card shadow-sm flex-shrink-0">
                                            <Activity className="h-5 w-5 sm:h-6 sm:w-6 text-re-info" />
                                        </div>
                                        <div>
                                            <h3 className="font-semibold text-sm sm:text-base group-hover:text-re-info transition-colors">Daily Compliance Heartbeat</h3>
                                            <p className="text-xs sm:text-sm text-muted-foreground">
                                                Score, alerts, chain status &amp; next actions — your morning check
                                            </p>
                                        </div>
                                    </div>
                                    <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-re-info group-hover:translate-x-1 transition-all" />
                                </div>
                            </CardContent>
                        </Card>
                    </Link>

                    {/* FSMA 204 Deadline Banner */}
                    <Card className="bg-gradient-to-r from-emerald-50 to-blue-50 dark:from-emerald-900/20 dark:to-blue-900/20 border-emerald-200 dark:border-re-brand">
                        <CardContent className="pt-6">
                            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                                <div className="flex items-center gap-3 sm:gap-4">
                                    <div className="p-2.5 sm:p-3 rounded-lg bg-white dark:bg-re-surface-card shadow-sm flex-shrink-0">
                                        <BarChart3 className="h-5 w-5 sm:h-6 sm:w-6 text-re-brand-dark" />
                                    </div>
                                    <div>
                                        <h3 className="font-semibold text-sm sm:text-base">FSMA 204 Compliance</h3>
                                        <p className="text-xs sm:text-sm text-muted-foreground">
                                            FDA deadline: July 2028 • Start tracking your readiness
                                        </p>
                                    </div>
                                </div>
                                <Link href="/fsma" className="w-full sm:w-auto">
                                    <Button variant="outline" className="min-h-[48px] w-full sm:w-auto active:scale-[0.98] transition-transform">
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
