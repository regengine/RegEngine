'use client';

import React, { useState } from 'react';
import { Car, Activity, FileCheck, AlertCircle, Download, Award, FileText } from 'lucide-react';
import { VerticalDashboardLayout, ComplianceMetricsGrid, RealTimeMonitor, ComplianceTimeline, QuickActionsPanel, ComplianceScoreGauge, ExportButton, type QuickAction } from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useDashboardMetrics, useSystemHealth, useAuditTimeline } from './api';

const quickActions: QuickAction[] = [
    { label: 'View IATF 16949 Guide', icon: FileText, href: '/docs/automotive', variant: 'outline' },
];
export default function AutomotiveDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const { data: metrics, isLoading: metricsLoading, error } = useDashboardMetrics();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: auditTimeline, isLoading: timelineLoading } = useAuditTimeline(5);

    if (error) return (
        <VerticalDashboardLayout title="Automotive Compliance Dashboard" subtitle="IATF 16949 & PPAP Monitoring" icon={Car} iconColor="text-blue-600" iconBgColor="bg-blue-100" systemStatus={{ label: 'Error', variant: 'error', icon: AlertCircle }}>
            <Card><CardContent className="py-12 text-center"><AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" /><h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3><button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary text-primary-foreground rounded-md">Retry</button></CardContent></Card>
        </VerticalDashboardLayout>
    );

    return (
        <VerticalDashboardLayout title="Automotive Compliance Dashboard" subtitle="IATF 16949 & PPAP Monitoring" icon={Car} iconColor="text-blue-600" iconBgColor="bg-blue-100" systemStatus={{ label: 'Operational', variant: 'success', icon: Activity }}>
            {metricsLoading ? <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">{[...Array(4)].map((_, i) => <Card key={i}><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>)}</div> : <ComplianceMetricsGrid metrics={metrics || []} columns={4} />}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <Card><CardHeader><CardTitle>IATF 16949 Compliance Score</CardTitle><CardDescription>Automotive quality management system</CardDescription></CardHeader><CardContent className="flex items-center justify-center py-8"><ComplianceScoreGauge score={98} label="IATF" size="lg" showTrend trend={3} /></CardContent></Card>
                </div>

                <div className="space-y-6">
                    {healthLoading ? <Card><CardContent className="p-6"><Skeleton className="h-32 w-full" /></CardContent></Card> : <RealTimeMonitor title="System Health" description="Automotive compliance infrastructure" health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }} stats={[{ label: 'PPAP System', value: 'Active', status: 'ok' }, { label: '8D Tracker', value: 'Running', status: 'ok' }]} onRefresh={() => { setIsRefreshing(true); setTimeout(() => setIsRefreshing(false), 1000); }} isRefreshing={isRefreshing} />}
                    {timelineLoading ? <Card><CardContent className="p-6"><Skeleton className="h-48 w-full" /></CardContent></Card> : <ComplianceTimeline events={auditTimeline || []} title="Activity Timeline" maxItems={5} />}
                    <QuickActionsPanel actions={quickActions} />
                    <ExportButton data={{ title: 'Automotive Compliance Dashboard Export', subtitle: 'IATF 16949 & PPAP Monitoring', metrics: metrics?.map(m => ({ label: m.label, value: m.value, helpText: m.helpText })) || [], tables: [], metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 98 } }} filename="automotive_compliance_report" variant="default" className="w-full" />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
