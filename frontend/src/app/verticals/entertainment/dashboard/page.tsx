'use client';

import React, { useState } from 'react';
import { Film, Users, DollarSign, Clock, FileText, AlertCircle, Calculator, CheckCircle, XCircle } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    AlertsWidget,
    QuickActionsPanel,
    ExportButton,
    ComplianceReportButton,
    HeatMapWidget,
    type HeatMapRow,
    type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import {
    useEntertainmentMetrics,
    useEntertainmentTimeline,
    useSafetyAlerts,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View PCOS Docs', icon: FileText, href: '/docs/entertainment', variant: 'outline' },
];

export default function EntertainmentDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { data: metrics, isLoading: metricsLoading } = useEntertainmentMetrics();
    const { data: timeline, isLoading: timelineLoading } = useEntertainmentTimeline();
    const { data: alerts, isLoading: alertsLoading } = useSafetyAlerts();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    return (
        <VerticalDashboardLayout
            title="Production Compliance OS"
            subtitle="Union Rules, Safety & Crew Management"
            icon={Film}
            iconColor="text-purple-600 dark:text-purple-400"
            iconBgColor="bg-purple-100 dark:bg-purple-900"
            systemStatus={{ label: 'Production Live', variant: 'success', icon: Film }}
        >
            {/* Metrics Grid */}
            {metricsLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                    {[...Array(4)].map((_, i) => (
                        <Skeleton key={i} className="h-32 w-full" />
                    ))}
                </div>
            ) : (
                <ComplianceMetricsGrid metrics={metrics || []} columns={4} />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column (2/3 width) */}
                <div className="lg:col-span-2 space-y-6">

                    {/* Recent Activity */}
                    {timelineLoading ? (
                        <Skeleton className="h-48 w-full" />
                    ) : (
                        <ComplianceTimeline events={timeline || []} title="Production Feed" maxItems={5} />
                    )}

                    {/* PCOS Compliance HeatMap */}
                    <HeatMapWidget
                        title="Production Compliance HeatMap"
                        description="Weekly compliance scores by department"
                        columnLabels={['Wk 1', 'Wk 2', 'Wk 3', 'Wk 4', 'Wk 5', 'Wk 6']}
                        rows={[
                            { category: 'On-Set Safety', cells: [{ value: 95 }, { value: 92 }, { value: 88 }, { value: 95 }, { value: 97 }, { value: 93 }] },
                            { category: 'Union Rules', cells: [{ value: 100 }, { value: 100 }, { value: 85 }, { value: 90 }, { value: 100 }, { value: 100 }] },
                            { category: 'Insurance', cells: [{ value: 100 }, { value: 100 }, { value: 100 }, { value: 78 }, { value: 95 }, { value: 100 }] },
                            { category: 'Licensing', cells: [{ value: 88 }, { value: 92 }, { value: 90 }, { value: 94 }, { value: 88 }, { value: 96 }] },
                            { category: 'Minor Work Permits', cells: [{ value: 100 }, { value: 0 }, { value: 100 }, { value: 100 }, { value: 0 }, { value: 100 }] },
                        ]}
                    />

                    {/* Crew Compliance Tracker */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Crew Compliance Tracker</CardTitle>
                            <CardDescription>Department-level compliance status for current production</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                {[
                                    { dept: 'Camera Department', compliant: 12, total: 12, issue: null },
                                    { dept: 'Lighting & Grip', compliant: 18, total: 19, issue: 'Safety cert expiring — J. Martinez' },
                                    { dept: 'Art Department', compliant: 8, total: 8, issue: null },
                                    { dept: 'Stunts', compliant: 5, total: 6, issue: 'Insurance gap — Unit #3' },
                                    { dept: 'Transportation', compliant: 14, total: 14, issue: null },
                                ].map((d) => (
                                    <div key={d.dept} className="flex items-center justify-between p-3 rounded-lg border bg-card hover:shadow-sm transition-shadow">
                                        <div className="flex items-center gap-3">
                                            {d.compliant === d.total ? (
                                                <CheckCircle className="w-5 h-5 text-emerald-500" />
                                            ) : (
                                                <XCircle className="w-5 h-5 text-amber-500" />
                                            )}
                                            <div>
                                                <p className="text-sm font-medium">{d.dept}</p>
                                                {d.issue && (
                                                    <p className="text-xs text-amber-600 dark:text-amber-400">{d.issue}</p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <span className={`text-sm font-semibold ${d.compliant === d.total ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'
                                                }`}>
                                                {d.compliant}/{d.total}
                                            </span>
                                            <p className="text-xs text-muted-foreground">crew compliant</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Right Column (1/3 width) */}
                <div className="space-y-6">
                    {/* Rule Engine Monitor */}
                    <RealTimeMonitor
                        title="Union Rule Engine"
                        description="Contract Validation"
                        health={{ status: 'HEALTHY', message: 'Validating against 2024 Contracts', lastCheck: 'Now', uptime: '100%' }}
                        stats={[
                            { label: 'Violations', value: '0', status: 'ok' },
                            { label: 'Warnings', value: '2', status: 'warning' },
                        ]}
                        onRefresh={handleRefresh}
                        isRefreshing={isRefreshing}
                    />

                    {/* Alerts */}
                    {alertsLoading ? (
                        <Skeleton className="h-32 w-full" />
                    ) : (
                        <AlertsWidget alerts={alerts || []} />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'Production Compliance Report',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value })) || [],
                        }}
                        filename="production_compliance_daily"
                        variant="default"
                        className="w-full"
                    />

                    <ComplianceReportButton
                        dashboardTitle="Production Compliance OS Report"
                        vertical="Entertainment"
                        reportData={{
                            summary: 'PCOS compliance report covering union rules, on-set safety, insurance, licensing, and crew verification status across all active productions.',
                            metrics: metrics?.map(m => ({
                                label: m.label,
                                value: m.value,
                                status: 'pass' as const,
                            })) || [],
                            alerts: alerts?.map(a => ({
                                severity: a.severity || 'warning',
                                message: a.title || a.message || '',
                                timestamp: typeof a.timestamp === 'string' ? a.timestamp : a.timestamp instanceof Date ? a.timestamp.toISOString() : undefined,
                            })) || [],
                        }}
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
