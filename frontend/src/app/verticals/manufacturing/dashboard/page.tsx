'use client';

import React, { useState } from 'react';
import { Factory, Activity, Award, AlertCircle, Download, Target, Shield, BarChart3, FileText } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    QuickActionsPanel,
    ComplianceScoreGauge,
    ExportButton,
    type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';

import {
    useDashboardMetrics,
    useISOCertifications,
    useNCRs,
    useAuditTimeline,
    useSystemHealth,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View ISO 9001 Guide', icon: FileText, href: '/docs/manufacturing', variant: 'outline' },
];

export default function ManufacturingDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDashboardMetrics();
    const { data: certifications, isLoading: certsLoading } = useISOCertifications();
    const { data: ncrs, isLoading: ncrsLoading } = useNCRs(8);
    const { data: auditTimeline, isLoading: timelineLoading } = useAuditTimeline(5);
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    if (metricsError) {
        return (
            <VerticalDashboardLayout
                title="Manufacturing Compliance Dashboard"
                subtitle="ISO 9001/14001/45001 Triple-Certification"
                icon={Factory}
                iconColor="text-amber-600 dark:text-amber-400"
                iconBgColor="bg-amber-100 dark:bg-amber-900"
                systemStatus={{ label: 'Error Loading Data', variant: 'error', icon: AlertCircle }}
            >
                <Card>
                    <CardContent className="py-12 text-center">
                        <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3>
                        <button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary text-primary-foreground rounded-md">Retry</button>
                    </CardContent>
                </Card>
            </VerticalDashboardLayout>
        );
    }

    return (
        <VerticalDashboardLayout
            title="Manufacturing Compliance Dashboard"
            subtitle="ISO 9001/14001/45001 Triple-Certification"
            icon={Factory}
            iconColor="text-amber-600 dark:text-amber-400"
            iconBgColor="bg-amber-100 dark:bg-amber-900"
            systemStatus={{ label: 'All Systems Operational', variant: 'success', icon: Activity }}
        >
            {metricsLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                    {[...Array(4)].map((_, i) => <Card key={i}><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>)}
                </div>
            ) : (
                <ComplianceMetricsGrid metrics={metrics || []} columns={4} />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Quality Compliance Score</CardTitle>
                            <CardDescription>Overall ISO certification health</CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={95} label="Quality" size="lg" showTrend trend={2} />
                        </CardContent>
                    </Card>

                    {certsLoading ? (
                        <Card><CardContent className="p-6"><Skeleton className="h-48 w-full" /></CardContent></Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>ISO Certification Matrix</CardTitle>
                                <CardDescription>Triple-certification status</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {certifications?.map((cert) => (
                                        <div key={cert.standard} className="p-3 rounded-lg border bg-card">
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="flex items-center gap-2">
                                                    <Award className="w-4 h-4 text-amber-600" />
                                                    <span className="font-semibold text-sm">{cert.standard}</span>
                                                    <Badge variant={cert.status === 'certified' ? 'default' : 'secondary'}>{cert.status}</Badge>
                                                </div>
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                Cert Body: {cert.certBody} • Expires: {new Date(cert.expiryDate).toLocaleDateString()}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                Last Audit: {new Date(cert.lastAudit).toLocaleDateString()} • Next: {new Date(cert.nextAudit).toLocaleDateString()}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {ncrsLoading ? (
                        <Card><CardContent className="p-6"><Skeleton className="h-64 w-full" /></CardContent></Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Non-Conformance Reports (NCRs)</CardTitle>
                                <CardDescription>Active quality issues</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {ncrs && ncrs.length > 0 ? ncrs.map((ncr) => (
                                        <div key={ncr.id} className="p-3 rounded-lg border bg-card text-sm">
                                            <div className="flex items-center justify-between mb-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-mono text-xs">{ncr.id}</span>
                                                    <Badge variant={ncr.severity === 'critical' ? 'destructive' : ncr.severity === 'major' ? 'outline' : 'secondary'} className="text-xs">
                                                        {ncr.severity}
                                                    </Badge>
                                                    <Badge variant="outline" className="text-xs">{ncr.standard}</Badge>
                                                </div>
                                                <Badge variant={ncr.status === 'closed' ? 'default' : 'secondary'} className="text-xs">{ncr.status}</Badge>
                                            </div>
                                            <div className="text-xs font-medium mb-1">{ncr.title}</div>
                                            <div className="text-xs text-muted-foreground">
                                                Raised: {new Date(ncr.raisedDate).toLocaleDateString()} • Due: {new Date(ncr.dueDate).toLocaleDateString()} • Assignee: {ncr.assignee}
                                            </div>
                                        </div>
                                    )) : <p className="text-sm text-muted-foreground text-center py-4">No open NCRs</p>}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>

                <div className="space-y-6">
                    {healthLoading ? (
                        <Card><CardContent className="p-6"><Skeleton className="h-32 w-full" /></CardContent></Card>
                    ) : (
                        <RealTimeMonitor
                            title="System Health"
                            description="Manufacturing compliance infrastructure"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'Quality System', value: 'Active', status: 'ok' },
                                { label: 'NCR Tracker', value: 'Running', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {timelineLoading ? (
                        <Card><CardContent className="p-6"><Skeleton className="h-48 w-full" /></CardContent></Card>
                    ) : (
                        <ComplianceTimeline events={auditTimeline || []} title="Audit Timeline" maxItems={5} />
                    )}

                    <QuickActionsPanel actions={quickActions} />

                    <ExportButton
                        data={{
                            title: 'Manufacturing Compliance Dashboard Export',
                            subtitle: 'ISO 9001/14001/45001 Triple-Certification',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value, helpText: m.helpText })) || [],
                            tables: [
                                {
                                    title: 'ISO Certifications',
                                    headers: ['Standard', 'Status', 'Cert Body', 'Expiry Date', 'Last Audit'],
                                    rows: certifications?.map(c => [c.standard, c.status, c.certBody, new Date(c.expiryDate).toLocaleDateString(), new Date(c.lastAudit).toLocaleDateString()]) || [],
                                },
                                {
                                    title: 'Active NCRs',
                                    headers: ['NCR ID', 'Severity', 'Title', 'Status', 'Due Date'],
                                    rows: ncrs?.slice(0, 10).map(n => [n.id, n.severity, n.title, n.status, new Date(n.dueDate).toLocaleDateString()]) || [],
                                },
                            ],
                            metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 95 },
                        }}
                        filename="manufacturing_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
