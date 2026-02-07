'use client';

import React, { useState } from 'react';
import { Dices, Activity, Shield, DollarSign, FileText, AlertTriangle, Users } from 'lucide-react';
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
    useGamingMetrics,
    useGamingTimeline,
    useComplianceAlerts,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View AML Compliance Guide', icon: FileText, href: '/docs/gaming', variant: 'outline' },
];

export default function GamingDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { data: metrics, isLoading: metricsLoading } = useGamingMetrics();
    const { data: timeline, isLoading: timelineLoading } = useGamingTimeline();
    const { data: alerts, isLoading: alertsLoading } = useComplianceAlerts();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    return (
        <VerticalDashboardLayout
            title="Gaming Compliance Monitor"
            subtitle="Real-Time Casino & Sportsbook Oversight"
            icon={Dices}
            iconColor="text-amber-600 dark:text-amber-400"
            iconBgColor="bg-amber-100 dark:bg-amber-900"
            systemStatus={{ label: 'GLI Verified', variant: 'success', icon: Shield }}
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
                        <ComplianceTimeline events={timeline || []} title="Live Transaction Feed" maxItems={5} />
                    )}

                    {/* Active Player Map Placeholder */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Jurisdiction Heatmap</CardTitle>
                            <CardDescription>Active player sessions by region</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-64 bg-muted/50 rounded flex items-center justify-center text-muted-foreground">
                                Interactive Map Visualization Placeholder
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Right Column (1/3 width) */}
                <div className="space-y-6">
                    {/* AML Risk Monitor */}
                    <RealTimeMonitor
                        title="AML Risk Engine"
                        description="Pattern Matching Active"
                        health={{ status: 'HEALTHY', message: 'Scanning all txn > $500', lastCheck: 'Now', uptime: '100%' }}
                        stats={[
                            { label: 'Scan Rate', value: '2.4k/s', status: 'ok' },
                            { label: 'Risk Level', value: 'Low', status: 'ok' },
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
                            title: 'Gaming Compliance Report',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value })) || [],
                        }}
                        filename="gaming_compliance_daily"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
