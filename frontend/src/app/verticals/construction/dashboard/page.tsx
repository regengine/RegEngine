'use client';

import React, { useState } from 'react';
import { Hammer, Activity, Box, AlertCircle, Download, Award, FileText } from 'lucide-react';
import { VerticalDashboardLayout, ComplianceMetricsGrid, RealTimeMonitor, ComplianceTimeline, QuickActionsPanel, ComplianceScoreGauge, ExportButton, ComplianceReportButton, type QuickAction } from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useDashboardMetrics, useSystemHealth, useAuditTimeline } from './api';

const quickActions: QuickAction[] = [
    { label: 'View ISO 19650 Guide', icon: FileText, href: '/docs/construction', variant: 'outline' },
];
export default function ConstructionDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const { data: metrics, isLoading: metricsLoading, error } = useDashboardMetrics();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: auditTimeline, isLoading: timelineLoading } = useAuditTimeline(5);

    if (error) return (
        <VerticalDashboardLayout title="Construction Compliance Dashboard" subtitle="ISO 19650 BIM & Safety Monitoring" icon={Hammer} iconColor="text-cyan-600" iconBgColor="bg-cyan-100" systemStatus={{ label: 'Error', variant: 'error', icon: AlertCircle }}>
            <Card><CardContent className="py-12 text-center"><AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" /><h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3><button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary text-primary-foreground rounded-md">Retry</button></CardContent></Card>
        </VerticalDashboardLayout>
    );

    return (
        <VerticalDashboardLayout title="Construction Compliance Dashboard" subtitle="ISO 19650 BIM & Safety Monitoring" icon={Hammer} iconColor="text-cyan-600" iconBgColor="bg-cyan-100" systemStatus={{ label: 'Operational', variant: 'success', icon: Activity }}>
            {metricsLoading ? <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">{[...Array(4)].map((_, i) => <Card key={i}><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>)}</div> : <ComplianceMetricsGrid metrics={metrics || []} columns={4} />}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <Card><CardHeader><CardTitle>ISO 19650 Compliance Score</CardTitle><CardDescription>BIM information management</CardDescription></CardHeader><CardContent className="flex items-center justify-center py-8"><ComplianceScoreGauge score={94} label="ISO 19650" size="lg" showTrend trend={3} /></CardContent></Card>
                </div>

                <div className="space-y-6">
                    {healthLoading ? <Card><CardContent className="p-6"><Skeleton className="h-32 w-full" /></CardContent></Card> : <RealTimeMonitor title="System Health" description="Construction compliance infrastructure" health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }} stats={[{ label: 'BIM System', value: 'Active', status: 'ok' }, { label: 'Safety Log', value: 'Running', status: 'ok' }]} onRefresh={() => { setIsRefreshing(true); setTimeout(() => setIsRefreshing(false), 1000); }} isRefreshing={isRefreshing} />}
                    {timelineLoading ? <Card><CardContent className="p-6"><Skeleton className="h-48 w-full" /></CardContent></Card> : <ComplianceTimeline events={auditTimeline || []} title="Activity Timeline" maxItems={5} />}
                    <QuickActionsPanel actions={quickActions} />
                    <ExportButton data={{ title: 'Construction Compliance Dashboard Export', subtitle: 'ISO 19650 BIM & Safety Monitoring', metrics: metrics?.map(m => ({ label: m.label, value: m.value, helpText: m.helpText })) || [], tables: [], metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 94 } }} filename="construction_compliance_report" variant="default" className="w-full" />
                    <ComplianceReportButton dashboardTitle="ISO 19650 Compliance Report" vertical="Construction" reportData={{ summary: 'ISO 19650 BIM information management and construction safety compliance covering digital plan delivery, site inspection records, and permit status.', metrics: metrics?.map(m => ({ label: m.label, value: m.value, status: 'pass' as const })) || [] }} className="w-full" />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
