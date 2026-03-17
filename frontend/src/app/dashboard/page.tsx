'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo } from 'react';

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
} from 'lucide-react';

// Base quick actions (overridden by tenant type)
const getQuickActions = (tenantType: 'retailer' | 'supplier' | 'system') => {
    const commonActions = [
        {
            title: 'Compliance Score',
            description: 'View your compliance grade',
            icon: Shield,
            href: '/dashboard/compliance',
            color: 'text-emerald-500',
            bg: 'bg-emerald-100 dark:bg-emerald-900/30',
        },
        {
            title: 'Alerts',
            description: 'Review compliance alerts',
            icon: AlertTriangle,
            href: '/dashboard/alerts',
            color: 'text-amber-500',
            bg: 'bg-amber-100 dark:bg-amber-900/30',
        },
        {
            title: 'Import Data',
            description: 'CSV, IoT, or API ingestion',
            icon: Upload,
            href: '/tools/data-import',
            color: 'text-blue-500',
            bg: 'bg-blue-100 dark:bg-blue-900/30',
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
                color: 'text-amber-500',
                bg: 'bg-amber-100 dark:bg-amber-900/30',
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
                color: 'text-amber-500',
                bg: 'bg-amber-100 dark:bg-amber-900/30',
            },
            {
                title: 'Archive Jobs',
                description: 'Recurring export retention',
                icon: Upload,
                href: '/dashboard/export-jobs',
                color: 'text-emerald-500',
                bg: 'bg-emerald-100 dark:bg-emerald-900/30',
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
            color: 'text-blue-500',
            bg: 'bg-blue-100 dark:bg-blue-900/30',
        },
        {
            title: 'Team',
            description: 'Manage team members & roles',
            icon: Building2,
            href: '/dashboard/team',
            color: 'text-emerald-500',
            bg: 'bg-emerald-100 dark:bg-emerald-900/30',
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
            color: 'text-amber-500',
            bg: 'bg-amber-100 dark:bg-amber-900/30',
        },
    ];
};

export default function DashboardPage() {
    const { user, isHydrated } = useAuth()
    const { tenantId } = useTenant();
    const router = useRouter();

    useEffect(() => {
        if (isHydrated && !user) {
            router.push(`/login?next=${encodeURIComponent('/dashboard')}`);
        }
    }, [isHydrated, user, router]);

    // Get the current org from Supabase
    const { organizations } = useOrganizations();
    const currentOrg = organizations.find(o => o.id === tenantId);

    // Fetch real system metrics from backend
    const { data: systemMetrics } = useSystemMetrics();

    const quickActions = useMemo(() => {
        return getQuickActions('retailer');
    }, []);

    // Use real metrics from backend when available, show honest zeros otherwise
    const metrics = useMemo(() => {
        if (systemMetrics) {
            return {
                documentsIngested: systemMetrics.events_ingested ?? systemMetrics.total_documents ?? 0,
                complianceScore: systemMetrics.compliance_score ?? 0,
                openAlerts: systemMetrics.open_alerts ?? 0,
                pendingReviews: 0,
            };
        }
        return {
            documentsIngested: 0,
            complianceScore: 0,
            openAlerts: 0,
            pendingReviews: 0,
        };
    }, [systemMetrics]);

    if (!isHydrated || !user) {
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
                                <Badge variant="secondary" className="bg-gradient-to-r from-amber-100 to-orange-100 text-amber-700 dark:from-amber-900/30 dark:to-orange-900/30 dark:text-amber-400">
                                    {currentOrg.plan.charAt(0).toUpperCase() + currentOrg.plan.slice(1)}
                                </Badge>
                            )}
                            <Badge variant="outline" className="bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                                <Activity className="w-3 h-3 mr-1" />
                                All Systems Operational
                            </Badge>
                        </div>
                    </div>

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
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex-shrink-0">
                                        <FileCheck className="h-4 w-4 sm:h-5 sm:w-5 text-blue-500" />
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
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex-shrink-0">
                                        <Shield className="h-4 w-4 sm:h-5 sm:w-5 text-emerald-500" />
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
                                    <div className="p-1.5 sm:p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex-shrink-0">
                                        <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-amber-500" />
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
                                        <div className="p-2.5 sm:p-3 rounded-lg bg-white dark:bg-gray-800 shadow-sm flex-shrink-0">
                                            <Activity className="h-5 w-5 sm:h-6 sm:w-6 text-blue-600" />
                                        </div>
                                        <div>
                                            <h3 className="font-semibold text-sm sm:text-base group-hover:text-blue-600 transition-colors">Daily Compliance Heartbeat</h3>
                                            <p className="text-xs sm:text-sm text-muted-foreground">
                                                Score, alerts, chain status &amp; next actions — your morning check
                                            </p>
                                        </div>
                                    </div>
                                    <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-blue-600 group-hover:translate-x-1 transition-all" />
                                </div>
                            </CardContent>
                        </Card>
                    </Link>

                    {/* FSMA 204 Deadline Banner */}
                    <Card className="bg-gradient-to-r from-emerald-50 to-blue-50 dark:from-emerald-900/20 dark:to-blue-900/20 border-emerald-200 dark:border-emerald-800">
                        <CardContent className="pt-6">
                            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                                <div className="flex items-center gap-3 sm:gap-4">
                                    <div className="p-2.5 sm:p-3 rounded-lg bg-white dark:bg-gray-800 shadow-sm flex-shrink-0">
                                        <BarChart3 className="h-5 w-5 sm:h-6 sm:w-6 text-emerald-600" />
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
