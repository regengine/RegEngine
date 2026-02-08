'use client';

import React, { useState } from 'react';
import { Film, Users, DollarSign, Clock, FileText, AlertCircle, Calculator } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    AlertsWidget,
    QuickActionsPanel,
    ExportButton,
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

                    {/* Payroll / Residuals Monitor */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Union Payroll Status</CardTitle>
                            <CardDescription>Current pay period validation</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-48 flex flex-col items-center justify-center border-2 border-dashed rounded text-muted-foreground gap-2">
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-xs font-medium">
                                    Demo Preview
                                </span>
                                <span>SAG-AFTRA &amp; IATSE Payroll Visualization</span>
                                <span className="text-xs text-muted-foreground/60">Connect production payroll system to enable</span>
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
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
