'use client';

import React, { useState } from 'react';
import { Plane, Activity, Shield, AlertCircle, Download, Award, FileText } from 'lucide-react';
import { VerticalDashboardLayout, ComplianceMetricsGrid, RealTimeMonitor, ComplianceTimeline, QuickActionsPanel, ComplianceScoreGauge, ExportButton, ComplianceReportButton, type QuickAction } from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useDashboardMetrics, useSystemHealth, useAuditTimeline } from './api';

const quickActions: QuickAction[] = [
    { label: 'View NADCAP Requirements', icon: FileText, href: '/docs/aerospace/nadcap', variant: 'outline' },
];
export default function AerospaceDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const { data: metrics, isLoading: metricsLoading, error } = useDashboardMetrics();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: auditTimeline, isLoading: timelineLoading } = useAuditTimeline(5);

    if (error) return (
        <VerticalDashboardLayout title="Aerospace Compliance Dashboard" subtitle="AS9100 & FAI Monitoring" icon={Plane} iconColor="text-indigo-600" iconBgColor="bg-indigo-100" systemStatus={{ label: 'Error', variant: 'error', icon: AlertCircle }}>
            <Card><CardContent className="py-12 text-center"><AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" /><h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3><button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary text-primary-foreground rounded-md">Retry</button></CardContent></Card>
        </VerticalDashboardLayout>
    );

    return (
        <VerticalDashboardLayout title="Aerospace Compliance Dashboard" subtitle="AS9100 & FAI Monitoring" icon={Plane} iconColor="text-indigo-600" iconBgColor="bg-indigo-100" systemStatus={{ label: 'Operational', variant: 'success', icon: Activity }}>
            {metricsLoading ? <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">{[...Array(4)].map((_, i) => <Card key={i}><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>)}</div> : <ComplianceMetricsGrid metrics={metrics || []} columns={4} />}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <Card><CardHeader><CardTitle>AS9100 Compliance Score</CardTitle><CardDescription>Aerospace quality management system</CardDescription></CardHeader><CardContent className="flex items-center justify-center py-8"><ComplianceScoreGauge score={97} label="AS9100" size="lg" showTrend trend={2} /></CardContent></Card>
                </div>

                <div className="space-y-6">
                    {healthLoading ? <Card><CardContent className="p-6"><Skeleton className="h-32 w-full" /></CardContent></Card> : <RealTimeMonitor title="System Health" description="Aerospace compliance infrastructure" health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }} stats={[{ label: 'FAI System', value: 'Active', status: 'ok' }, { label: 'Config Mgmt', value: 'Running', status: 'ok' }]} onRefresh={() => { setIsRefreshing(true); setTimeout(() => setIsRefreshing(false), 1000); }} isRefreshing={isRefreshing} />}
                    {timelineLoading ? <Card><CardContent className="p-6"><Skeleton className="h-48 w-full" /></CardContent></Card> : <ComplianceTimeline events={auditTimeline || []} title="Activity Timeline" maxItems={5} />}
                    <QuickActionsPanel actions={quickActions} />
                    <ExportButton data={{ title: 'Aerospace Compliance Dashboard Export', subtitle: 'AS9100 & FAI Monitoring', metrics: metrics?.map(m => ({ label: m.label, value: m.value, helpText: m.helpText })) || [], tables: [], metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 97 } }} filename="aerospace_compliance_report" variant="default" className="w-full" />
                    <ComplianceReportButton dashboardTitle="AS9100 Compliance Report" vertical="Aerospace" reportData={{ summary: 'AS9100 aerospace quality management compliance covering FAI documentation, NADCAP special process certification, and configuration management status across all programs.', metrics: metrics?.map(m => ({ label: m.label, value: m.value, status: 'pass' as const })) || [] }} className="w-full" />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
