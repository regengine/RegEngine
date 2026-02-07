'use client';

import React, { useState } from 'react';
import { Shield, Activity, RefreshCw, AlertTriangle, FileText, Database, Search } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    AlertsWidget,
    QuickActionsPanel,
    ComplianceScoreGauge,
    ExportButton,
    type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import {
    useDashboardMetrics,
    useHighRiskLots,
    useActivityTimeline,
    useSystemHealth,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View FSMA Guide', icon: FileText, href: '/docs/food-safety', variant: 'outline' },
];

export default function FoodSafetyDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { data: metrics, isLoading: metricsLoading } = useDashboardMetrics();
    const { data: risks, isLoading: risksLoading } = useHighRiskLots();
    const { data: timeline, isLoading: timelineLoading } = useActivityTimeline();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    return (
        <VerticalDashboardLayout
            title="FSMA 204 Compliance Dashboard"
            subtitle="End-to-End Food Traceability & Safety"
            icon={Shield}
            iconColor="text-green-600 dark:text-green-400"
            iconBgColor="bg-green-100 dark:bg-green-900"
            systemStatus={{ label: 'Traceability Active', variant: 'success', icon: Activity }}
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
                    {/* Compliance Score */}
                    <Card>
                        <CardHeader>
                            <CardTitle>FSMA 204 Readiness Score</CardTitle>
                            <CardDescription>
                                Based on KDE completeness and 24h recall capability
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={98} label="Readiness Score" size="lg" showTrend trend={1.2} />
                        </CardContent>
                    </Card>

                    {/* High Risk Lots */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>High Priority Lots</CardTitle>
                                    <CardDescription>Lots with missing critical tracking events or anomalies</CardDescription>
                                </div>
                                <button
                                    onClick={handleRefresh}
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`} />
                                </button>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {risksLoading ? (
                                <div className="space-y-3">
                                    {[...Array(3)].map((_, i) => (
                                        <Skeleton key={i} className="h-20 w-full" />
                                    ))}
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {risks?.map((lot) => (
                                        <div
                                            key={lot.tlc}
                                            className="p-4 rounded-lg border bg-card hover:shadow-md transition-shadow flex items-center justify-between"
                                        >
                                            <div>
                                                <div className="font-mono text-sm font-bold text-gray-800 dark:text-gray-200">
                                                    {lot.tlc}
                                                </div>
                                                <div className="text-sm text-gray-500">
                                                    {lot.product_description}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className={`text-sm font-semibold ${lot.gap_count > 0 ? 'text-amber-600' : 'text-green-600'}`}>
                                                    {lot.gap_count} Gaps Detected
                                                </div>
                                                <div className="text-xs text-gray-500">
                                                    Last Event: {lot.last_event}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Activity Timeline */}
                    {timelineLoading ? (
                        <Skeleton className="h-48 w-full" />
                    ) : (
                        <ComplianceTimeline events={timeline || []} title="Recent Traceability Events" maxItems={5} />
                    )}
                </div>

                {/* Right Column (1/3 width) */}
                <div className="space-y-6">
                    {/* System Health Monitor */}
                    {healthLoading ? (
                        <Skeleton className="h-32 w-full" />
                    ) : (
                        <RealTimeMonitor
                            title="Traceability Engine"
                            description="Neo4j Graph Status"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'Event Ingestion', value: '45/sec', status: 'ok' },
                                { label: 'Query Latency', value: '12ms', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'FSMA 204 Compliance Report',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value })) || [],
                            tables: [
                                {
                                    title: 'High Risk Lots',
                                    headers: ['TLC', 'Product', 'Risk Score', 'Gaps'],
                                    rows: risks?.map(r => [r.tlc, r.product_description, r.risk_score.toString(), r.gap_count.toString()]) || [],
                                }
                            ]
                        }}
                        filename="fsma_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
